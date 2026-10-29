import numpy as np
import pytest
from make_ridge import BBOX, NODATA, PIXEL_DEG
from shapely.geometry import shape
from shapely.ops import unary_union

from chartpack.bathy.bands import build_bands
from chartpack.bathy.contours import DEPTHS_FT, min_zoom
from chartpack.bathy.merge import to_mllw_depth

TRANSFORM = (BBOX[0], PIXEL_DEG, 0.0, BBOX[3], 0.0, -PIXEL_DEG)


@pytest.fixture
def ridge_depth(fixtures_dir):
    d = to_mllw_depth(np.load(fixtures_dir / "ridge.npy"), NODATA, 0.715)
    d[d < 0] = np.nan  # land
    return d


def test_bands_tile_the_grid(ridge_depth):
    feats = build_bands(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)
    union = unary_union([shape(f["geometry"]) for f in feats])
    ok = np.isfinite(ridge_depth)
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
