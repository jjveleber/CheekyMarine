import json

import numpy as np
import pytest
from make_ridge import BBOX, NODATA, PIXEL_DEG

from chartpack.bathy.contours import (
    DEPTHS_FT,
    FINE_FT,
    build_contours,
    chaikin_line,
    contours_by_zoom,
    min_zoom,
)
from chartpack.bathy.merge import fill_land, to_mllw_depth

TRANSFORM = (BBOX[0], PIXEL_DEG, 0.0, BBOX[3], 0.0, -PIXEL_DEG)


def _depth(fixtures_dir):
    return to_mllw_depth(np.load(fixtures_dir / "ridge.npy"), NODATA, 0.715)


@pytest.fixture
def ridge_depth(fixtures_dir):
    """Ridge (21 m crest) made shallower by 12 m with a north-south wiggle, land removed.

    Straight contours would simplify to two points, so the wiggle gives them real shape.
    """
    d = _depth(fixtures_dir) - 12.0 + 3.0 * np.sin(np.arange(200) * 2 * np.pi / 40)[:, None]
    d[d < -5.0] = np.nan  # the land columns
    return d


@pytest.fixture
def ridge_depth_with_land(fixtures_dir):
    d = _depth(fixtures_dir)
    d[50:60, 50:60] = 40.0  # no hole: only the shore matters here
    return fill_land(d)


@pytest.mark.parametrize("d,z", [(60, 10), (30, 12), (40, 13), (500, 13), (70, 14), (25, 15)])
def test_min_zoom(d, z):
    assert min_zoom(d) == z


def test_chaikin_keeps_endpoints():
    pts = [(0, 0), (1, 1), (2, 0)]
    out = chaikin_line(pts)
    assert out[0] == (0, 0) and out[-1] == (2, 0) and len(out) == 4


def test_ridge_contours_at_expected_depths(ridge_depth):
    feats = build_contours(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)
    depths = {f["properties"]["depth_ft"] for f in feats}
    assert {70, 100, 200, 300} <= depths and 10 not in depths and 600 not in depths
    assert all(len(f["geometry"]["coordinates"]) >= 6 for f in feats)
    assert all(f["properties"]["minzoom"] == min_zoom(f["properties"]["depth_ft"]) for f in feats)


def test_lines_close_at_shore(ridge_depth_with_land):
    feats = build_contours(ridge_depth_with_land, TRANSFORM, levels_ft=[10], min_points=2)
    assert feats
    west, east = BBOX[0] + PIXEL_DEG / 2, BBOX[2] - PIXEL_DEG / 2
    south, north = BBOX[1] + PIXEL_DEG / 2, BBOX[3] - PIXEL_DEG / 2
    for f in feats:
        c = f["geometry"]["coordinates"]
        if c[0] == c[-1]:
            continue
        for lon, lat in (c[0], c[-1]):
            on_edge = (
                lon == pytest.approx(west, abs=1e-9)
                or lon == pytest.approx(east, abs=1e-9)
                or lat == pytest.approx(south, abs=1e-9)
                or lat == pytest.approx(north, abs=1e-9)
            )
            assert on_edge


def test_deterministic(ridge_depth):
    a = build_contours(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)
    b = build_contours(ridge_depth.copy(), TRANSFORM, levels_ft=DEPTHS_FT)
    assert json.dumps(a) == json.dumps(b)


def test_contours_by_zoom_assigns_bands(ridge_depth):
    feats = contours_by_zoom(ridge_depth, TRANSFORM, fine=True)
    assert {(f["tippecanoe"]["minzoom"], f["tippecanoe"]["maxzoom"]) for f in feats} == {(10, 11), (12, 13), (14, 16)}
    native = [f for f in feats if f["tippecanoe"]["minzoom"] == 14]
    assert any(f["properties"]["depth_ft"] == 25 for f in native)
    assert not any(f["properties"]["depth_ft"] == 25 for f in feats if f["tippecanoe"]["minzoom"] < 14)
    assert {f["properties"]["depth_ft"] for f in feats if f["tippecanoe"]["minzoom"] == 10} <= {60, 120, 180, 300, 600}
    assert all(f["properties"]["minzoom"] >= f["tippecanoe"]["minzoom"] for f in feats)
    assert all(f["properties"]["minzoom"] <= f["tippecanoe"]["maxzoom"] for f in feats)


def test_contours_by_zoom_without_fine_has_no_fine_levels(ridge_depth):
    feats = contours_by_zoom(ridge_depth, TRANSFORM, fine=False)
    assert not {f["properties"]["depth_ft"] for f in feats} & set(FINE_FT)
