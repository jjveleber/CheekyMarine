"""Nav depth areas, contours and soundings derived from a NONNA depth grid (plan 8 Task 10)."""

import math
import tomllib
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon, box, shape

from chartpack.bathy.blocks import SOURCE_NAMES
from chartpack.bathy.contours import BANDS, block_factor
from chartpack.enc.derived import block_min, derived_features

ROOT = Path(__file__).resolve().parent.parent
LEVELS = tomllib.loads((ROOT / "regions" / "bc-valdco.toml").read_text())["levels_m"]
D = 0.0002  # cell size: the coarsest band downsamples 8 times (checked below)
X0, Y0 = -124.0, 49.0  # on multiples of 8 cells from (-180, 90)
N = 160
TRANSFORM = (X0, D, 0.0, Y0, 0.0, -D)
CORE = (X0, Y0 - N * D, X0 + N * D, Y0)
EMPTY = Polygon()
DEPTH_LAYERS = ("depare", "depcnt", "soundg")


def _src(name, shape=(N, N)):
    return np.full(shape, SOURCE_NAMES.index(name), np.int8)


def _derive(depth, src=None, *, nosurvey=EMPTY, land=EMPTY, transform=TRANSFORM, core=CORE):
    return derived_features(depth.astype(np.float32), _src("nonna10", depth.shape) if src is None else src,
                            transform, core=core, levels_m=LEVELS, nosurvey=nosurvey, land=land, lat=49.0)


def _layer(features, layer, minzoom=None):
    return [f for f in features if f.layer == layer
            and (minzoom is None or f.props["tippecanoe"]["minzoom"] == minzoom)]


def _center(row, col):
    return X0 + (col + 0.5) * D, Y0 - (row + 0.5) * D


def _slope():
    """Depth from -2 m (drying) in the north row to 120 m in the south row, with a wiggle across."""
    rows, cols = np.mgrid[0:N, 0:N]
    return -2.0 + 122.0 * rows / (N - 1) + 3.0 * np.sin(cols / 9.0)


def test_block_min_takes_shallowest():
    depth = np.array([[10.0, 4.0, np.nan, np.nan], [7.0, np.nan, np.nan, np.nan]], np.float32)
    out, transform = block_min(depth, TRANSFORM, 2)
    assert out.shape == (1, 2)
    assert out[0, 0] == 4.0 and np.isnan(out[0, 1])
    assert transform == (X0, 2 * D, 0.0, Y0, 0.0, -2 * D)


def test_contour_values_are_all_in_levels():
    feats = _derive(_slope())
    levels = {format(float(v), ".15g") for v in LEVELS}
    contours = _layer(feats, "depcnt")
    assert contours and {f.props["VALDCO"] for f in contours} <= levels
    pairs = set(zip(sorted(LEVELS, key=float), sorted(LEVELS, key=float)[1:]))
    for f in _layer(feats, "depare"):
        lo, hi = f.props["DRVAL1"], f.props["DRVAL2"]
        assert (float(lo) < 0 and hi == "0") or (float(lo), float(hi)) in {(float(a), float(b)) for a, b in pairs}


def _plain_with_shoal():
    depth = np.full((N, N), 50.0)
    depth[83, 77] = 3.0
    return depth


def test_shoal_survives_downsampling():
    assert block_factor(TRANSFORM, BANDS[0][2]) == 8
    feats = _derive(_plain_with_shoal())
    point = shapely.Point(_center(83, 77))
    shoal = [f for f in _layer(feats, "depare", BANDS[0][0]) if float(f.props["DRVAL1"]) <= 3.0]
    assert shoal and any(shape(f.geometry).distance(point) < 8 * D for f in shoal)
    assert float(min(_layer(feats, "soundg", BANDS[0][0]), key=lambda f: float(f.props["depth"])).props["depth"]) == 3.0


def test_shoal_survives_end_to_end(tmp_path, test_region):
    from test_bathy_blocks import _real_block

    data = np.full((41, 41), -50.0)
    data[20, 20] = -3.0
    result, _ = _real_block(tmp_path, data, test_region)
    nav = result.nav_depth
    core = (nav.transform[0], nav.transform[3] + nav.data.shape[0] * nav.transform[5],
            nav.transform[0] + nav.data.shape[1] * nav.transform[1], nav.transform[3])
    feats = derived_features(nav.data, result.nav_src, nav.transform, core=core, levels_m=LEVELS, nosurvey=EMPTY,
                             land=EMPTY, lat=49.0)
    assert any(float(f.props["DRVAL1"]) <= 3.0 for f in _layer(feats, "depare", BANDS[0][0]))


def _assert_clear_of(feats, area):
    """No depth geometry meets the interior of area, at every band (area shrunk by 1e-9 degree, about 0.1 mm, so a
    shared edge in float noise does not count)."""
    inner = area.buffer(-1e-9)
    for f in feats:
        if f.layer in DEPTH_LAYERS:
            geom = shape(f.geometry)
            assert not shapely.relate_pattern(geom, inner, "T********"), (f.layer, f.props)


def test_no_depth_inside_nosurvey():
    mask = shapely.Point(_center(100, 40)).buffer(30 * D)
    feats = _derive(_slope(), nosurvey=mask)
    assert {f.props["tippecanoe"]["minzoom"] for f in _layer(feats, "depare")} == {lo for lo, _, _ in BANDS}
    _assert_clear_of(feats, mask)
    masked = _layer(feats, "nosurvey")
    assert masked and math.isclose(shapely.union_all([shape(f.geometry) for f in masked]).area, mask.area, rel_tol=1e-9)
    assert all(box(*CORE).covers(shape(f.geometry)) for f in masked)


def test_no_depth_on_land():
    land = Polygon([_center(10, 10), _center(10, 90), _center(70, 60), _center(60, 5)])
    feats = _derive(_slope(), land=land)
    assert _layer(feats, "depare") and _layer(feats, "soundg")
    _assert_clear_of(feats, land)


def test_soundings_only_from_nonna():
    assert not _layer(_derive(_slope(), _src("etopo")), "soundg")
    assert _layer(_derive(_slope(), _src("crm")), "depare")  # the depth areas still come from any source
    soundings = _layer(_derive(_slope(), _src("nonna100")), "soundg")
    assert soundings and {f.props["src"] for f in soundings} == {"nonna100"}
    for lo, hi, _ in BANDS:  # one per 96 px cell at each zoom
        for z in range(lo, hi + 1):
            assert _layer(soundings, "soundg", z)


def test_drying_area_has_negative_drval1():
    depth = _slope() + 6.0  # no drying cell but the north row
    depth[0, :] = -1.23
    drying = [f for f in _layer(_derive(depth), "depare") if f.props["DRVAL2"] == "0"]
    assert drying and {f.props["DRVAL1"] for f in drying} == {"-1.3"}


def test_src_is_coarser_when_mixed():
    depth = 5.0 + 100.0 * np.mgrid[0:N, 0:N][0] / (N - 1)  # deeper to the south: every area spans west to east
    depth[30:40, 20:30] = 1.0  # a shoal on the NONNA-10 side only
    src = _src("nonna10")
    src[:, N // 2:] = SOURCE_NAMES.index("nonna100")
    split = X0 + N // 2 * D
    feats = _derive(depth, src)
    for f in _layer(feats, "depare") + _layer(feats, "depcnt"):
        minx, _, maxx, _ = shape(f.geometry).bounds
        if minx < split < maxx:
            assert f.props["src"] == "nonna100", f.props
    west = [f for f in _layer(feats, "depare") if f.props["src"] == "nonna10"]
    assert west and all(shape(f.geometry).bounds[2] < split for f in west)
    assert {f.props["src"] for f in _layer(feats, "soundg")} == {"nonna10", "nonna100"}


def test_land_features_carry_fwa_src():
    land = box(X0 - 0.01, Y0 - 20 * D, X0 + 40 * D, Y0 + 0.01)  # reaches past the core
    feats = _derive(_slope(), land=land)
    lnd, coast = _layer(feats, "lndare"), _layer(feats, "coalne")
    assert lnd and coast
    assert all(f.props["src"] == "fwa" for f in lnd + coast)
    assert all(box(*CORE).covers(shape(f.geometry)) for f in lnd + coast)
    assert math.isclose(sum(shape(f.geometry).area for f in lnd), 40 * D * 20 * D, rel_tol=1e-9)
