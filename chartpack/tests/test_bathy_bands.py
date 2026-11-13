import numpy as np
import pytest
from make_ridge import BBOX, NODATA, PIXEL_DEG
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from chartpack.bathy.bands import bands_by_zoom, build_bands
from chartpack.bathy.contours import BANDS, DEPTHS_FT, M_TO_FT, MAJOR_FT, min_zoom
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
        assert p["minzoom"] == min_zoom(p["depth_max_ft"] or 1000)


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
    bands.bands_by_zoom(ridge_depth, TRANSFORM)  # the ridge's center, 47.9 N, rounds to 48
    assert seen == [zoom_tolerance_deg(11, 48.0), zoom_tolerance_deg(13, 48.0), zoom_tolerance_deg(15, 48.0)]


def test_deepest_band_is_past_1000():
    deep = np.tile(np.arange(200) * 2.5, (200, 1))  # 0 to 497 m
    feats = build_bands(deep, TRANSFORM, levels_ft=DEPTHS_FT)
    spans = {(f["properties"]["depth_min_ft"], f["properties"]["depth_max_ft"]) for f in feats}
    assert (1000, None) in spans and (900, 1000) in spans
    assert max(f["properties"]["depth_min_ft"] for f in feats) == 1000
    assert {f["properties"]["minzoom"] for f in feats if f["properties"]["depth_min_ft"] == 1000} == {10}


# Two readings exactly at MLLW (0 m) above a land cell: contourpy pinches the band's ring to a point or a
# zero-width slit at each node that sits exactly on a level, so the polygon is invalid and cutting it at a core
# edge through those nodes raised "TopologyException: Ring edge missing" (haida-gwaii block (133, 331)).
ON_LEVEL = np.ones((6, 6))
ON_LEVEL[2, 2] = ON_LEVEL[3, 2] = 0.0
ON_LEVEL[4, 2] = -0.3
ON_LEVEL_TRANSFORM = (0.0, 1.0, 0.0, 6.0, 0.0, -1.0)  # cell centers 0.5 to 5.5; the core edge y 2.5 meets row 3


def test_bands_cut_at_a_core_edge_through_readings_exactly_on_a_level():
    feats = build_bands(ON_LEVEL, ON_LEVEL_TRANSFORM, levels_ft=[30], simplify_deg=0, core=(0.5, 0.5, 5.5, 2.5))
    assert feats and all(shape(f["geometry"]).is_valid for f in feats)


@pytest.mark.parametrize("cells", [[(2, 2)], [(2, 1), (2, 2), (2, 3)], [(2, 2), (3, 3)]])
def test_bands_are_valid_polygons_where_readings_sit_exactly_on_a_level(cells):
    depth = np.ones((6, 6))
    for cell in cells:
        depth[cell] = 0.0
    feats = build_bands(depth, ON_LEVEL_TRANSFORM, levels_ft=[30], simplify_deg=0)
    assert feats and all(shape(f["geometry"]).is_valid for f in feats)


def test_a_reading_exactly_on_a_level_stays_on_its_shallower_side():
    """contourpy draws a band for lower < depth <= upper: a reading at 0 m is in no band and one at exactly 30 ft
    is in the 0 to 30 ft band, never deeper."""
    depth = np.full((5, 5), 5.0)
    depth[1, 1] = 0.0
    depth[3, 3] = 30 / M_TO_FT
    feats = build_bands(depth, ON_LEVEL_TRANSFORM, levels_ft=[30], simplify_deg=0)
    at = {(lo, hi): unary_union([shape(f["geometry"]) for f in feats if f["properties"]["depth_min_ft"] == lo])
          for lo, hi in ((0, 30), (30, None))}
    mllw, thirty = Point(1.5, 4.5), Point(3.5, 2.5)  # the centers of cells (1, 1) and (3, 3)
    assert not any(g.intersects(mllw) for g in at.values())
    assert at[(0, 30)].intersects(thirty) and not at[(30, None)].intersects(thirty)
