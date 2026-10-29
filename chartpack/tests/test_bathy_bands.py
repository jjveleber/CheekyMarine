import numpy as np
import pytest
from make_ridge import BBOX, NODATA, PIXEL_DEG
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from chartpack.bathy.bands import bands_by_zoom, build_bands
from chartpack.bathy.contours import BANDS, DEPTHS_FT, MAJOR_FT, min_zoom
from chartpack.bathy.merge import fill_land, to_mllw_depth

TRANSFORM = (BBOX[0], PIXEL_DEG, 0.0, BBOX[3], 0.0, -PIXEL_DEG)


@pytest.fixture
def ridge_depth(fixtures_dir):
    d = to_mllw_depth(np.load(fixtures_dir / "ridge.npy"), NODATA, 0.715)
    return fill_land(d)  # land columns sit at -0.3 m


def test_bands_tile_the_grid(ridge_depth):
    feats = build_bands(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)
    union = unary_union([shape(f["geometry"]) for f in feats])
    ok = ridge_depth > 0  # water only; nan compares False
    quads = ok[:-1, :-1] & ok[1:, :-1] & ok[:-1, 1:] & ok[1:, 1:]  # cells whose four corners are water
    grid_water_area = quads.sum() * PIXEL_DEG**2
    assert abs(union.area - grid_water_area) / grid_water_area < 0.01
    assert all(f["properties"]["depth_min_ft"] < (f["properties"]["depth_max_ft"] or 10**6) for f in feats)
    assert all(f["geometry"]["type"] == "Polygon" for f in feats)


def test_band_attributes(ridge_depth):
    feats = build_bands(ridge_depth, TRANSFORM, levels_ft=[100, 200, 300])
    spans = {(f["properties"]["depth_min_ft"], f["properties"]["depth_max_ft"]) for f in feats}
    assert spans == {(0, 100), (100, 200), (200, 300), (300, None)}
    for f in feats:
        p = f["properties"]
        assert p["minzoom"] == min_zoom(p["depth_max_ft"] or 600)


def test_land_fill_is_outside_every_band(ridge_depth):
    feats = build_bands(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)
    land = Point(BBOX[2] - PIXEL_DEG / 2, (BBOX[1] + BBOX[3]) / 2)
    assert not any(shape(f["geometry"]).contains(land) for f in feats)


def test_bands_by_zoom_gives_each_zoom_range_a_complete_band_set(ridge_depth):
    """Bands are disjoint, so thinning by omission leaves holes; each zoom range gets its own coarser set."""
    feats = bands_by_zoom(ridge_depth, TRANSFORM)
    native = unary_union([shape(f["geometry"]) for f in build_bands(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)])
    assert {(f["tippecanoe"]["minzoom"], f["tippecanoe"]["maxzoom"]) for f in feats} == {(lo, hi) for lo, hi, _ in BANDS}
    for lo, hi, _ in BANDS:
        part = [f for f in feats if f["tippecanoe"]["minzoom"] == lo]
        assert all(f["tippecanoe"]["maxzoom"] == hi and f["properties"]["minzoom"] == lo for f in part)
        union = unary_union([shape(f["geometry"]) for f in part])
        assert abs(union.area - native.area) / native.area < 0.05, (lo, hi)  # no water left unbanded
        levels = {f["properties"]["depth_min_ft"] for f in part} - {0}
        assert levels and all(min_zoom(ft) <= hi for ft in levels)
    z10 = {f["properties"]["depth_min_ft"] for f in feats if f["tippecanoe"]["minzoom"] == 10}
    assert z10 - {0} <= MAJOR_FT and len(z10) >= 3


def test_bands_by_zoom_simplify_at_the_top_zoom_of_each_range(ridge_depth, monkeypatch):
    """R33: band polygons follow the same per-zoom tolerance as the contours."""
    from chartpack.bathy import bands
    from chartpack.bathy.contours import zoom_tolerance_deg

    seen = []
    real = bands.build_bands
    monkeypatch.setattr(bands, "build_bands", lambda *a, **k: seen.append(k["simplify_deg"]) or real(*a, **k))
    bands.bands_by_zoom(ridge_depth, TRANSFORM)
    assert seen == [zoom_tolerance_deg(11), zoom_tolerance_deg(13), zoom_tolerance_deg(15)]
