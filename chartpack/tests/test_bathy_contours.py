import json
import math

import numpy as np
import pytest
from make_ridge import BBOX, NODATA, PIXEL_DEG

from chartpack.bathy.contours import (
    DEPTHS_FT,
    FINE_FT,
    MAJOR_FT,
    build_contours,
    chaikin_line,
    contours_by_zoom,
    min_zoom,
    zoom_tolerance_deg,
)
from chartpack.bathy.merge import fill_land, to_mllw_depth

TRANSFORM = (BBOX[0], PIXEL_DEG, 0.0, BBOX[3], 0.0, -PIXEL_DEG)


def _depth(fixtures_dir):
    return to_mllw_depth(np.load(fixtures_dir / "ridge.npy"), NODATA, 0.715)


@pytest.fixture
def ridge_depth(fixtures_dir):
    d = _depth(fixtures_dir)
    d[d < 0] = np.nan  # the land columns
    return d


@pytest.fixture
def shallow_ridge_depth(ridge_depth):
    """The ridge 12 m shallower, so the 5 ft steps (25 ft = 7.6 m) exist."""
    return ridge_depth - 12.0


@pytest.fixture
def ridge_depth_with_land(fixtures_dir):
    d = _depth(fixtures_dir)
    d[50:60, 50:60] = 40.0  # no hole: only the shore matters here
    return fill_land(d)


@pytest.mark.parametrize("d,z", [(60, 10), (30, 12), (40, 13), (500, 10), (450, 12), (70, 14), (25, 15)])
def test_min_zoom(d, z):
    assert min_zoom(d) == z


def test_chaikin_keeps_endpoints():
    pts = [(0, 0), (1, 1), (2, 0)]
    out = chaikin_line(pts)
    assert out[0] == (0, 0) and out[-1] == (2, 0) and len(out) == 4


def test_ridge_contours_at_expected_depths(ridge_depth):
    feats = build_contours(ridge_depth, TRANSFORM, levels_ft=DEPTHS_FT)
    depths = {f["properties"]["depth_ft"] for f in feats}
    assert {70, 100, 200, 300} <= depths and 10 not in depths and 1200 not in depths
    assert all(len(f["geometry"]["coordinates"]) >= 2 for f in feats)
    assert all(f["properties"]["minzoom"] == min_zoom(f["properties"]["depth_ft"]) for f in feats)


def test_lines_close_at_shore(ridge_depth_with_land):
    feats = build_contours(ridge_depth_with_land, TRANSFORM, levels_ft=[10])
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


def test_contours_by_zoom_assigns_bands(shallow_ridge_depth):
    feats = contours_by_zoom(shallow_ridge_depth, TRANSFORM, fine=True)
    assert {(f["tippecanoe"]["minzoom"], f["tippecanoe"]["maxzoom"]) for f in feats} == {(10, 11), (12, 13), (14, 16)}
    native = [f for f in feats if f["tippecanoe"]["minzoom"] == 14]
    assert any(f["properties"]["depth_ft"] == 25 for f in native)
    assert not any(f["properties"]["depth_ft"] == 25 for f in feats if f["tippecanoe"]["minzoom"] < 14)
    assert {f["properties"]["depth_ft"] for f in feats if f["tippecanoe"]["minzoom"] == 10} <= MAJOR_FT
    assert all(f["properties"]["minzoom"] >= f["tippecanoe"]["minzoom"] for f in feats)
    assert all(f["properties"]["minzoom"] <= f["tippecanoe"]["maxzoom"] for f in feats)


def test_contours_by_zoom_without_fine_has_no_fine_levels(ridge_depth):
    feats = contours_by_zoom(ridge_depth, TRANSFORM, fine=False)
    assert not {f["properties"]["depth_ft"] for f in feats} & set(FINE_FT)


def test_straight_contour_survives_default_min_points():
    plane = np.tile(np.arange(200) * 0.3, (200, 1))  # depth rises west to east; 100 ft = 30.48 m at col ~101.6
    feats = build_contours(plane, TRANSFORM, levels_ft=[100])
    assert len(feats) == 1
    assert len(feats[0]["geometry"]["coordinates"]) >= 2


@pytest.mark.parametrize("zoom", range(10, 17))
def test_zoom_tolerance_is_one_pixel_at_latitude_48(zoom):
    """R33: Douglas-Peucker tolerance = the 256 px Web Mercator ground resolution at 48 N, z16 uses z15."""
    metres = 156543.03392804097 * math.cos(math.radians(48)) / 2 ** min(zoom, 15)
    assert zoom_tolerance_deg(zoom, 48.0) == pytest.approx(metres / 111320.0)
    assert 95 < 156543.03392804097 * math.cos(math.radians(48)) / 2**10 < 105  # about 100 m at z10


def test_finer_zoom_contours_keep_more_vertices(ridge_depth):
    """The ridge with a gentle north-south wiggle (contour offset about 40 m, wavelength 4 km): about one pixel
    at z15 (3 m) keeps the bends that one pixel at z10 (100 m) straightens."""
    wiggly = ridge_depth + 0.5 * np.sin(2 * np.pi * np.arange(200) / 40)[:, None]
    z10 = build_contours(wiggly, TRANSFORM, levels_ft=[100], simplify_deg=zoom_tolerance_deg(10, 48.0))
    z15 = build_contours(wiggly, TRANSFORM, levels_ft=[100], simplify_deg=zoom_tolerance_deg(15, 48.0))
    count = lambda feats: sum(len(f["geometry"]["coordinates"]) for f in feats)
    assert len(z10) == len(z15) and count(z15) > count(z10)


def test_contours_by_zoom_simplify_at_the_top_zoom_of_each_range(ridge_depth, monkeypatch):
    from chartpack.bathy import contours

    seen = []
    real = contours.build_contours
    monkeypatch.setattr(contours, "build_contours", lambda *a, **k: seen.append(k["simplify_deg"]) or real(*a, **k))
    contours.contours_by_zoom(ridge_depth, TRANSFORM, fine=False)  # the ridge's center, 47.9 N, rounds to 48
    assert seen == [zoom_tolerance_deg(11, 48.0), zoom_tolerance_deg(13, 48.0), zoom_tolerance_deg(15, 48.0)]


def test_levels_match_spec():
    assert DEPTHS_FT == list(range(10, 301, 10)) + list(range(350, 601, 50)) + list(range(700, 1001, 100))
    assert MAJOR_FT == frozenset({60, 120, 180, 300, 400, 500, 600, 800, 1000})


def test_no_contour_past_1000():
    slope = np.tile(np.arange(200) * 2.5, (200, 1))  # 0 to 497 m, so 1,630 ft at the deep edge
    feats = build_contours(slope, TRANSFORM, levels_ft=DEPTHS_FT)
    depths = {f["properties"]["depth_ft"] for f in feats}
    assert 1000 in depths and max(depths) == 1000


def test_majors_offshore():
    assert min_zoom(500) == 10 and min_zoom(450) == 12
    assert all(min_zoom(d) == 10 for d in (400, 600, 800, 1000))
    assert all(min_zoom(d) == 12 for d in (350, 550, 700, 900))


def test_coarse_and_overview_bands():
    from chartpack.bathy.contours import COARSE_BANDS, OVERVIEW_BANDS

    assert COARSE_BANDS == ((10, 11, 150.0), (12, 12, 30.0)) and OVERVIEW_BANDS == ((6, 9, 300.0),)


def test_coarse_top_band_holds_every_level():
    """bathy-coarse stops at z12 and is overzoomed past it, so its z12 band carries every 10 ft level to 300
    (and the deep ones), each with its own minzoom for the style tiers; z10-11 and the overview keep theirs."""
    from chartpack.bathy.contours import COARSE_BANDS, OVERVIEW_BANDS

    slope = np.tile(np.arange(200) * 0.5, (200, 1)).astype(np.float32)  # 0 to 99.5 m: past 300 ft
    feats = contours_by_zoom(slope, TRANSFORM, fine=False, bands=COARSE_BANDS, overzoomed=True)
    top = {f["properties"]["depth_ft"]: f["properties"]["minzoom"] for f in feats if f["tippecanoe"]["minzoom"] == 12}
    assert set(range(10, 301, 10)) <= set(top)
    assert all(top[ft] == max(min_zoom(ft), 12) for ft in top if ft not in MAJOR_FT)
    assert top[250] == min_zoom(250) == 14 and top[200] == 13
    low = {f["properties"]["depth_ft"] for f in feats if f["tippecanoe"]["minzoom"] == 10}
    assert low == {ft for ft in range(10, 301, 10) if min_zoom(ft) <= 11 or ft in MAJOR_FT}
    overview = contours_by_zoom(slope, TRANSFORM, fine=False, bands=OVERVIEW_BANDS)
    assert {f["properties"]["depth_ft"] for f in overview} <= MAJOR_FT


def test_tolerance_scales_with_cos_lat():
    """#18: the ground resolution of one pixel shrinks with cos(latitude)."""
    ratio = zoom_tolerance_deg(12, 54.0) / zoom_tolerance_deg(12, 48.0)
    assert ratio == pytest.approx(math.cos(math.radians(54)) / math.cos(math.radians(48)), abs=1e-9)


def test_tolerance_latitude_rounded_to_quarter_degree():
    assert zoom_tolerance_deg(12, 53.9) == zoom_tolerance_deg(12, 54.0)


def test_contours_by_zoom_use_the_core_latitude(ridge_depth, monkeypatch):
    """#18: the tolerance comes from the latitude of the block core's center, not a fixed 48 N."""
    from chartpack.bathy import contours

    seen = []
    real = contours.build_contours
    monkeypatch.setattr(contours, "build_contours", lambda *a, **k: seen.append(k["simplify_deg"]) or real(*a, **k))
    contours.contours_by_zoom(ridge_depth, TRANSFORM, fine=False, core=(-122.5, 53.9, -122.3, 54.1))
    assert seen == [zoom_tolerance_deg(11, 54.0), zoom_tolerance_deg(13, 54.0), zoom_tolerance_deg(15, 54.0)]
