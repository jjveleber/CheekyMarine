"""Nav depth areas, contours and soundings derived from a NONNA depth grid (plan 8 Task 10)."""

import math
import tomllib
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon, box, shape

from chartpack.bathy.blocks import SOURCE_NAMES
from chartpack.bathy.contours import BANDS, block_factor
from chartpack.enc.derived import DEEPEST_M, block_min, derived_features

ROOT = Path(__file__).resolve().parent.parent
LEVELS = tomllib.loads((ROOT / "regions" / "bc-valdco.toml").read_text())["levels_m"]
D = 0.0002  # cell size: the coarsest band downsamples 8 times (checked below)
X0, Y0 = -124.0, 49.0  # on multiples of 8 cells from (-180, 90)
N = 160
TRANSFORM = (X0, D, 0.0, Y0, 0.0, -D)
CORE = (X0, Y0 - N * D, X0 + N * D, Y0)
WIDE = (X0 - 1, Y0 - 1, X0 + 1, Y0 + 1)  # a core holding the center of every sounding cell the grid meets (_owns)
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


def _shown(features, layer, z):
    """The features of layer drawn at zoom z (their tippecanoe zoom range holds z)."""
    return [f for f in features if f.layer == layer
            and f.props["tippecanoe"]["minzoom"] <= z <= f.props["tippecanoe"]["maxzoom"]]


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
    ordered = sorted(float(v) for v in LEVELS)
    pairs = set(zip(ordered, ordered[1:])) | {(ordered[-1], DEEPEST_M)}
    for f in _layer(feats, "depare"):
        lo, hi = f.props["DRVAL1"], f.props["DRVAL2"]
        assert (float(lo) < 0 and hi == "0") or (float(lo), float(hi)) in pairs
    deepest = _derive(np.full((N, N), 3000.0))
    assert {(f.props["DRVAL1"], f.props["DRVAL2"]) for f in _layer(deepest, "depare")} == {
        (format(ordered[-1], ".15g"), format(DEEPEST_M, ".15g"))}


def _assert_shoal_kept(feats, square, depth=3.0):
    """At every band: every depare meeting the shoal square's interior has DRVAL1 <= depth and one covers the
    square; the square lies wholly on the shallow side of every depcnt deeper than depth (no such line meets it)."""
    for lo, _, _ in BANDS:
        meeting = [f for f in _layer(feats, "depare", lo)
                   if shape(f.geometry).intersection(square).area > 1e-9 * square.area]
        assert meeting and all(float(f.props["DRVAL1"]) <= depth for f in meeting), (lo, [f.props for f in meeting])
        assert any(shape(f.geometry).intersection(square).area > (1 - 1e-9) * square.area for f in meeting), lo
        deeper = [f for f in _layer(feats, "depcnt", lo) if float(f.props["VALDCO"]) > depth]
        assert not any(shape(f.geometry).intersects(square) for f in deeper), lo


@pytest.mark.parametrize("row, col", [(83, 83), (80, 80), (87, 87), (0, 0)])  # block center, corners, grid edge
def test_shoal_survives_downsampling(row, col):
    assert block_factor(TRANSFORM, BANDS[0][2]) == 8
    depth = np.full((N, N), 50.0)
    depth[row, col] = 3.0
    feats = _derive(depth, core=WIDE)
    _assert_shoal_kept(feats, box(X0 + col * D, Y0 - (row + 1) * D, X0 + (col + 1) * D, Y0 - row * D))
    assert float(min(_layer(feats, "soundg", BANDS[0][0]), key=lambda f: float(f.props["depth"])).props["depth"]) == 3.0


def test_shoal_survives_end_to_end(tmp_path, test_region):
    from test_bathy_blocks import _R, _real_block

    data = np.full((41, 41), -50.0)
    data[20, 20] = -3.0
    result, (x0, px, y0, py) = _real_block(tmp_path, data, test_region)
    nav = result.nav_depth
    core = (nav.transform[0], nav.transform[3] + nav.data.shape[0] * nav.transform[5],
            nav.transform[0] + nav.data.shape[1] * nav.transform[1], nav.transform[3])
    feats = derived_features(nav.data, result.nav_src, nav.transform, core=core, levels_m=LEVELS, nosurvey=EMPTY,
                             land=EMPTY, lat=49.0)

    def lat(y):
        return math.degrees(2 * math.atan(math.exp(y / _R)) - math.pi / 2)

    square = box(math.degrees((x0 + 20 * px) / _R), lat(y0 + 21 * py), math.degrees((x0 + 21 * px) / _R),
                 lat(y0 + 20 * py))
    _assert_shoal_kept(feats, square)


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
    for lo, _, _ in BANDS:  # every band's nosurvey holds the mask (and the water not drawn as depth)
        masked = _shown(feats, "nosurvey", lo)
        assert masked and shapely.union_all([shape(f.geometry) for f in masked]).covers(mask.buffer(-1e-9)), lo
    assert all(box(*CORE).covers(shape(f.geometry)) for f in _layer(feats, "nosurvey"))


def test_no_depth_on_land():
    land = Polygon([_center(10, 10), _center(10, 90), _center(70, 60), _center(60, 5)])
    feats = _derive(_slope(), land=land)
    assert _layer(feats, "depare") and _layer(feats, "soundg")
    _assert_clear_of(feats, land)


def test_soundings_only_from_nonna():
    assert not _layer(_derive(_slope(), _src("etopo")), "soundg")
    assert _layer(_derive(_slope(), _src("crm")), "depare")  # the depth areas still come from any source
    soundings = _layer(_derive(_slope(), _src("nonna100"), core=WIDE), "soundg")
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


def test_depth_stays_on_valid_cells():
    """Water with no value that is neither mask nor land gets no depth area: cut to the valid cells."""
    depth = np.full((N, N), np.nan)
    depth[:, :81] = 20.0
    feats = _derive(depth)
    edge = X0 + 81 * D
    for lo, _, _ in BANDS:
        areas = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        assert areas.bounds[2] <= edge + 1e-9, lo
    assert all(shape(f.geometry).bounds[2] <= edge + 1e-9 for f in feats if f.layer in DEPTH_LAYERS)


def test_band_areas_tile_the_water():
    """At every band the depth areas do not overlap and leave no gap in the valid cells less mask and land, but
    for the parts too thin to draw at the band's minzoom, which that band's nosurvey holds."""
    depth = _slope()
    depth[83, 77] = 3.0
    depth[120:, 100:] = np.nan
    nosurvey = shapely.Point(_center(100, 40)).buffer(20 * D)
    land = Polygon([_center(10, 10), _center(10, 90), _center(70, 60), _center(60, 5)])
    feats = _derive(depth, nosurvey=nosurvey, land=land)
    water = box(*CORE).difference(box(X0 + 100 * D, Y0 - N * D, X0 + N * D, Y0 - 120 * D)).difference(
        shapely.union_all([nosurvey, land]))
    tiny = 1e-6 * D * D
    for lo, _, _ in BANDS:
        areas = [shape(f.geometry) for f in _layer(feats, "depare", lo)]
        union = shapely.union_all(areas)
        masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", lo)])
        assert sum(a.area for a in areas) - union.area < tiny, lo
        assert water.difference(union.union(masked)).area < tiny, lo
        assert union.difference(water).area < tiny, lo
        assert union.intersection(masked).area < tiny, lo


@pytest.mark.parametrize("value, label", [(0.0, ("0", "0.9")), (-0.1, ("-0.1", "0")), (2.0, ("1.8", "2"))])
def test_flat_water_is_covered(value, label):
    """A plateau exactly on a level (float32 drying -0.1 included) is covered by the band holding it."""
    feats = _derive(np.full((N, N), value))
    for lo, _, _ in BANDS:
        areas = _layer(feats, "depare", lo)
        assert {(f.props["DRVAL1"], f.props["DRVAL2"]) for f in areas} == {label}, lo
        assert math.isclose(shapely.union_all([shape(f.geometry) for f in areas]).area, (N * D) ** 2, rel_tol=1e-9)


@pytest.mark.parametrize("case", ["hole", "half"])
def test_footprint_is_the_input_cells(case):
    """At FINE_RES_DEG (reduced 4 times before contouring) a nan region not lined up with the reduction blocks gets
    no depth geometry, and every valid input cell is covered at every band, by depth or (a part too thin to draw
    at the band's minzoom) by that band's nosurvey."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d = FINE_RES_DEG
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    depth = np.full((N, N), 20.0)
    if case == "hole":
        depth[41:44, 41:46] = np.nan  # one native NONNA-10 cell, 3 by 5 fine cells, across 4 by 4 blocks
        depth[40, 41] = 2.0  # a shoal beside it pulls the neighborhood minimum over the hole
        nan = box(X0 + 41 * d, Y0 - 44 * d, X0 + 46 * d, Y0 - 41 * d)
    else:
        depth[:, 81:] = np.nan  # column 81 is not on a 4-cell block edge
        nan = box(X0 + 81 * d, Y0 - N * d, X0 + N * d, Y0)
    feats = _derive(depth, transform=transform, core=core)
    water = box(*core).difference(nan)
    tiny = 1e-6 * d * d
    _assert_clear_of(feats, nan)
    for lo, _, _ in BANDS:
        union = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", lo)])
        assert union.intersection(nan).area < tiny, lo
        assert water.difference(union.union(masked)).area < tiny, lo


def test_src_none_on_every_valid_cell_is_an_error():
    with pytest.raises(ValueError, match="src is 0"):
        _derive(_slope(), _src("none"))


# _tiles inputs that GEOS's fast rectangle clip (clip_by_rect) mishandles, both valid polygons. A sliver of the
# haida-gwaii land cut (overview tile (-133.2421875, 53.748710796898976, -132.890625, 53.9560855309879)) whose
# clipped part collapses to a 3-point ring: "IllegalArgumentException: Invalid number of points in LinearRing
# found 3". And cells with a hole, whose clip at the tile (1.5, 0, 3.5, 3) comes out as a self-touching ring.
_SLIVER = ("POLYGON ((-133.04445376 53.751789670000015, -133.04428348 53.75183096999998, "
           "-133.04444260251748 53.75179237615475, -133.04445376 53.751789670000015))")
_CELLS_WITH_HOLE = ("POLYGON ((0 5, 1 5, 1 4, 2 4, 2 3, 2 2, 3 2, 3 1, 3 0, 2 0, 1 0, 0 0, 0 1, 0 2, 0 3, 0 4, 0 5),"
                    " (1 2, 1 1, 2 1, 2 2, 1 2))")


@pytest.mark.parametrize("wkt, core", [
    (_SLIVER, (-133.2421875, 53.748710796898976, -132.890625, 53.9560855309879)),
    (_CELLS_WITH_HOLE, (1.5, 0.0, 33.5, 48.0)),
])
def test_the_cut_tiles_are_valid_and_hold_the_cut_inside_the_core(wkt, core):
    from chartpack.enc.derived import _tiles

    cut = shapely.from_wkt(wkt)
    pieces = _tiles(cut, core).geometries
    assert len(pieces) and shapely.is_valid(pieces).all()
    inside = cut.intersection(box(*core))
    assert shapely.union_all(pieces).symmetric_difference(inside).area < 1e-12 * max(inside.area, 1e-12)


# ---- plan8-checkfix F1: per band, no depth part too thin to draw; nosurvey is the water not drawn as depth

def _units_width(geom, z):
    """The mean width (2 A / P) of a lon/lat polygon in tile units at zoom z (Web Mercator, 4,096 per tile)."""
    def to_units(c):
        n = 2**z * 4096
        return np.column_stack([(c[:, 0] + 180) / 360 * n,
                                (1 - np.arcsinh(np.tan(np.radians(c[:, 1]))) / math.pi) / 2 * n])
    g = shapely.transform(geom, to_units)
    return 2 * g.area / g.length


def _sliver_case():
    """At FINE_RES_DEG, 20 m water with a 3 m shoal in columns 80 and 81, and two no-survey boxes that leave a strip
    of surveyed water 3 m (Web Mercator) wide between them over the shoal, as a NONNA-100 edge leaves one beside the
    mask (run 43512658024). 3 m is under 2 tile units at zooms 10 (19 m) and 12 (4.8 m), over it at 14 (1.2 m)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d = FINE_RES_DEG
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    depth = np.full((N, N), 20.0)
    depth[:, 80:82] = 3.0
    west = X0 + 80.3 * d
    east = west + 3.0 / 111319.49  # 3 m in Web Mercator x
    nosurvey = shapely.union_all([box(X0 + 40 * d, core[1], west, core[3]), box(east, core[1], X0 + 120 * d, core[3])])
    strip = box(west, core[1], east, core[3])
    return depth, transform, core, nosurvey, strip


def test_thin_depth_part_goes_to_nosurvey_at_the_zooms_it_is_too_thin_for():
    depth, transform, core, nosurvey, strip = _sliver_case()
    feats = _derive(depth, transform=transform, core=core, nosurvey=nosurvey)
    inner = strip.buffer(-1e-9)
    for lo, _, _ in BANDS:
        areas = _layer(feats, "depare", lo)
        in_strip = shapely.union_all([shape(f.geometry) for f in areas]).intersection(strip).area
        masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", lo)])
        # every depth part beside nosurvey is wide enough to draw (a thin one elsewhere stays, see below)
        assert all(_units_width(shape(f.geometry), lo) >= 2 for f in areas if masked.intersects(shape(f.geometry))), lo
        if lo < 14:
            assert in_strip < 1e-6 * strip.area and masked.covers(inner), lo
        else:
            assert in_strip > (1 - 1e-6) * strip.area and not masked.intersects(inner), lo


def test_depcnt_and_soundg_only_on_the_depth_kept():
    """The contours and soundings of the strip go with its depth areas: none at zooms 10 to 13, kept at 14 to 16."""
    depth, transform, core, nosurvey, strip = _sliver_case()
    feats = _derive(depth, transform=transform, core=WIDE, nosurvey=nosurvey)
    inner = strip.buffer(-1e-9)
    for lo, hi, _ in BANDS:
        kept = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        lines = [shape(f.geometry) for f in _layer(feats, "depcnt", lo)]
        assert all(kept.buffer(1e-9).covers(g) for g in lines), lo
        points = [shape(f.geometry) for f in feats if f.layer == "soundg" and lo <= f.props["tippecanoe"]["minzoom"] <= hi]
        assert all(kept.covers(p) for p in points), lo
        assert any(inner.intersects(g) for g in lines + points) == (lo >= 14), lo


def test_depth_nosurvey_and_land_tile_the_core_per_band():
    """At every band, depare, nosurvey and lndare cover the core with no gap and no overlap: water with no value
    that the stored mask does not hold (here the nan corner) is nosurvey too."""
    depth = _slope()
    depth[83, 77] = 3.0
    depth[120:, 100:] = np.nan
    nosurvey = shapely.Point(_center(100, 40)).buffer(20 * D)
    land = Polygon([_center(10, 10), _center(10, 90), _center(70, 60), _center(60, 5)])
    feats = _derive(depth, nosurvey=nosurvey, land=land)
    core = box(*CORE)
    tiny = 1e-6 * D * D
    lnd = [shape(f.geometry) for f in _layer(feats, "lndare")]
    for lo, hi, _ in BANDS:
        assert all(f.props["tippecanoe"] in ({"minzoom": lo, "maxzoom": hi}, {"minzoom": 10, "maxzoom": 16})
                   for f in _shown(feats, "nosurvey", lo))
        parts = [shape(f.geometry) for f in _layer(feats, "depare", lo) + _shown(feats, "nosurvey", lo)] + lnd
        union = shapely.union_all(parts)
        assert sum(p.area for p in parts) - union.area < tiny, lo
        assert core.symmetric_difference(union).area < tiny, lo


def test_thin_depth_part_away_from_nosurvey_stays_depth():
    """The same strip between two land boxes: a thin part that meets no nosurvey area stays depth at every band (as
    at a block's core edge, where a band crossing at a slant leaves a sliver whose rest is in the next block).
    Dropped, it would become a thin nosurvey part alone between depth or land, which tippecanoe draws as a square
    over its neighbors."""
    depth, transform, core, nosurvey, strip = _sliver_case()
    feats = _derive(depth, transform=transform, core=core, land=nosurvey)
    for lo, _, _ in BANDS:
        areas = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        assert areas.intersection(strip).area > (1 - 1e-6) * strip.area, lo
        assert not any(shape(f.geometry).intersects(strip.buffer(-1e-9)) for f in _shown(feats, "nosurvey", lo)), lo


def test_thin_parts_beside_a_dropped_one_go_too():
    """_to_nosurvey: a thin part meeting the nosurvey area goes, then a thin part meeting that one, and so on; a thin
    part meeting neither stays, and a wide part beside them stays."""
    from chartpack.enc.derived import _to_nosurvey

    area = box(0, 0, 10, 10)
    parts = np.array([box(10, 0, 10.5, 10), box(10.5, 0, 11, 10), box(11, 0, 11.5, 10), box(20, 0, 20.5, 10),
                      box(11.5, 0, 30, 10)], object)
    thin = np.array([True, True, True, True, False])
    assert _to_nosurvey(parts, thin, area).tolist() == [True, True, True, False, False]
    assert _to_nosurvey(parts, thin, shapely.Polygon()).tolist() == [False] * 5


def test_nosurvey_not_repeated_per_band_where_no_depth_is_dropped():
    """The nosurvey no band changes is emitted once over every zoom, not once per band (3 times the coordinates in
    tippecanoe's input); only the parts a band's thin depth joins are emitted per band. Here, in flat water, the
    thin strip joins the two mask boxes at zooms 10 to 13; a round mask (many vertices) 34 m of depth from anything
    is never touched, so its coordinates are emitted once: under 1.5 times one band's count (3 times before)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    _, transform, core, nosurvey, strip = _sliver_case()
    depth = np.full((N, N), 20.0)
    far = shapely.Point(core[0] + 20 * FINE_RES_DEG, (core[1] + core[3]) / 2).buffer(10 * FINE_RES_DEG, 64)
    feats = _derive(depth, transform=transform, core=core, nosurvey=shapely.union_all([nosurvey, far]))
    masked = _layer(feats, "nosurvey")
    once = [f for f in masked if f.props["tippecanoe"] == {"minzoom": 10, "maxzoom": 16}]
    assert once and any(shape(f.geometry).intersects(far) for f in once)
    coords = sum(len(shapely.get_coordinates(shape(f.geometry))) for f in masked)
    per_band = max(sum(len(shapely.get_coordinates(shape(f.geometry))) for f in _shown(feats, "nosurvey", lo))
                   for lo, _, _ in BANDS)
    assert coords < 1.5 * per_band


def test_thin_part_meeting_nosurvey_at_a_corner_only_stays_depth():
    """_to_nosurvey: a thin part that meets the nosurvey area (or a part sent to it) only at a point stays depth;
    sent, it could not join the nosurvey and would be a thin nosurvey part alone (review N1). One sharing an edge
    goes, and so does a thin part sharing an edge with that one."""
    from chartpack.enc.derived import _to_nosurvey

    area = box(0, 0, 10, 10)
    parts = np.array([box(10, 10, 10.5, 20), box(10, 2, 10.5, 8), box(10.5, 8, 11, 9), box(10.5, 3, 11, 5)],
                     object)  # corner of area; edge of area; corner of part 1 only; edge of part 1
    assert _to_nosurvey(parts, np.ones(4, bool), area).tolist() == [False, True, False, True]


def test_nosurvey_at_every_zoom_is_the_core_less_land_less_that_zoom_depth():
    """At every zoom of every band, the nosurvey drawn there (every feature whose zoom range holds it) is exactly the
    core less land less the depth drawn there: none missing at a band whose thin depth joins no mask piece, and
    the thin parts of a band added at that band only (PR 133 review)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    depth, transform, core, nosurvey, strip = _sliver_case()
    land = box(core[0], core[1], core[0] + 20 * FINE_RES_DEG, core[3])
    feats = _derive(depth, transform=transform, core=core, nosurvey=nosurvey, land=land)
    tiny = 1e-6 * strip.area
    for lo, hi, _ in BANDS:
        for z in range(lo, hi + 1):
            depare = shapely.union_all([shape(f.geometry) for f in _shown(feats, "depare", z)])
            masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", z)])
            want = box(*core).difference(land).difference(depare)
            assert masked.symmetric_difference(want).area < tiny, z
            assert masked.covers(nosurvey.buffer(-1e-9)), z


def test_nosurvey_joined_by_thin_depth_is_not_repeated_per_band():
    """Every mask piece joined by thin depth (PR 133 review: a round, many-vertex mask grown from the west box the
    strip touches went out once per band, 684 coordinates for a 244-coordinate mask): the whole nosurvey goes out
    once over every zoom and each band adds only a local patch round its thin parts, so the total stays near one
    band's count."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    _, transform, core, nosurvey, strip = _sliver_case()
    depth = np.full((N, N), 20.0)
    west = nosurvey.geoms[0] if hasattr(nosurvey, "geoms") else nosurvey
    round_ = shapely.Point(west.bounds[0] + 5 * FINE_RES_DEG, (core[1] + core[3]) / 2).buffer(15 * FINE_RES_DEG, 64)
    feats = _derive(depth, transform=transform, core=core, nosurvey=shapely.union_all([nosurvey, round_]))
    coords = sum(len(shapely.get_coordinates(shape(f.geometry))) for f in _layer(feats, "nosurvey"))
    per_band = max(sum(len(shapely.get_coordinates(shape(f.geometry))) for f in _shown(feats, "nosurvey", lo))
                   for lo, _, _ in BANDS)
    assert any(f.props["tippecanoe"]["maxzoom"] < 14 for f in _layer(feats, "nosurvey"))  # the strip is joined
    assert coords < 1.3 * per_band, (coords, per_band)


def test_to_nosurvey_tests_against_prepared_mask_pieces(monkeypatch):
    """The large mask piece is prepared before the edge tests (PR 133 review: unprepared, each test rebuilt its
    topology, 3.9 s against 0.18 s for a 100,003-vertex piece and 500 thin parts)."""
    from chartpack.enc import derived

    seen = []
    relate = shapely.relate_pattern

    def spy(a, b, pattern):
        seen.append(bool(np.all(shapely.is_prepared(a))))
        return relate(a, b, pattern)

    monkeypatch.setattr(derived.shapely, "relate_pattern", spy)
    area = shapely.union_all([box(-10, -10, 10, 10), box(20, -10, 30, 10)])  # two pieces
    parts = np.array([box(10, -1, 10.5, 1), box(19.5, -1, 20, 1)], object)
    assert derived._to_nosurvey(parts, np.ones(2, bool), area).all()
    assert seen and all(seen)


def _patch_case():
    """Flat 20 m water, _sliver_case's strip of thin depth between two mask boxes, the east box cut short (13 m), and
    a third mask piece across 24 m of depth (wider than 2 units at zoom 10, 19 m), within PATCH_UNITS of the strip
    at zoom 10 but touching no thin part. Returns (features, core, strip, the third piece)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d = FINE_RES_DEG
    _, transform, core, nosurvey, strip = _sliver_case()
    west = nosurvey.intersection(box(core[0], core[1], strip.bounds[0], core[3]))
    east = box(strip.bounds[2], core[1], X0 + 85 * d, core[3])
    third = box(X0 + 92 * d, core[1], X0 + 100 * d, core[3])
    feats = _derive(np.full((N, N), 20.0), transform=transform, core=core,
                    nosurvey=shapely.union_all([west, east, third]))
    return feats, core, strip, third


def test_band_patch_holds_no_slice_of_an_untouched_mask_piece():
    """A band's nosurvey patch keeps only the parts joined to its thin depth: no slice of a mask piece across depth
    within reach (PR 133 review: such a slice can be under one unit wide and tile into a square over depth)."""
    feats, core, strip, third = _patch_case()
    patches = [f for f in _layer(feats, "nosurvey") if f.props["tippecanoe"]["maxzoom"] < 16]
    assert patches
    for f in patches:
        geom = shape(f.geometry)
        assert geom.intersection(strip).area > 0.5 * strip.area, f.props
        assert geom.intersection(third).area == 0, f.props


def test_band_patch_holds_the_nosurvey_its_thin_depth_joins():
    """Every patch part holds nosurvey beside the thin depth, never the thin part alone."""
    feats, core, strip, third = _patch_case()
    patches = [f for f in _layer(feats, "nosurvey") if f.props["tippecanoe"]["maxzoom"] < 16]
    assert patches and all(shape(f.geometry).difference(strip).area > 0.1 * strip.area for f in patches)
