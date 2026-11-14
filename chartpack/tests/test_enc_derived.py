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
        # a band's patches overlap the nosurvey drawn over every zoom (both nosurvey): one union for the layer
        masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", lo)])
        parts = [shape(f.geometry) for f in _layer(feats, "depare", lo)] + [masked] + lnd
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


def test_shared_length_along_a_many_vertex_mask_piece():
    """_shared measures each thin part's boundary along the mask by the mask's own segments (an STRtree of them),
    not by an overlay with the whole piece (PR 133 review: unprepared tests against a 100,003-vertex piece took
    seconds); parts off the piece by float noise still count, a part at a corner counts nothing."""
    from chartpack.enc.derived import _shared

    area = shapely.union_all([box(-10, -10, 10, 10), shapely.Point(-10, 0).buffer(5, 4096)])
    parts = np.array([box(10 + 1e-12, -1, 10.5, 1), box(10, 10, 10.5, 11), box(30, 0, 31, 1)], object)
    lengths = _shared(parts, shapely.get_parts(area))
    assert lengths[0] == pytest.approx(2.0, rel=1e-6) and lengths[1] == pytest.approx(0, abs=1e-8) and lengths[2] == 0

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


# ---- plan8-patchfix (Ruling 48): a thin part goes to nosurvey only along it; no per-band nosurvey part too thin

def _step_case(mask=True):
    """At FINE_RES_DEG, 1 m water west of column 80 and 5 m east of it: the 1.8-2 band is a strip about one unit
    wide at every band's minzoom, between the 0.9-1.8 and 2-3.6 bands, as the 1.8-2 band of dry run 3
    (43547724046, 15/4328/10573). mask: a no-survey box over the north 10 rows, which the strip meets at its tip
    only. Returns (features, core, the mask)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d = FINE_RES_DEG
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    depth = np.where(np.arange(N)[None, :] < 80, 1.0, 5.0) * np.ones((N, 1))
    nosurvey = box(core[0], Y0 - 10 * d, core[2], Y0) if mask else EMPTY
    return _derive(depth, transform=transform, core=core, nosurvey=nosurvey), core, nosurvey


def _band_area(feats, lo, drval1):
    return sum(shape(f.geometry).area for f in _layer(feats, "depare", lo) if f.props["DRVAL1"] == drval1)


def test_long_thin_band_touching_the_mask_at_its_tip_goes_with_the_mask():
    """Ruling 55 (C): a thin band that meets nosurvey only along its short tip (under a quarter of its perimeter)
    goes to nosurvey, emitted at its band's zooms inside the nosurvey piece it meets (the whole mask box here), so
    it is never a thin patch alone (dry run 3) and never thin depth beside nosurvey (dry run 4 north)."""
    with_mask, core, mask = _step_case()
    without, _, _ = _step_case(mask=False)
    for lo, hi, _ in BANDS:
        band = shapely.union_all([shape(f.geometry) for f in _layer(without, "depare", lo) if f.props["DRVAL1"] == "1.8"])
        assert band.area > 0 and _band_area(with_mask, lo, "1.8") < 0.01 * band.area, lo
        held = [shape(f.geometry) for f in _layer(with_mask, "nosurvey")
                if f.props["tippecanoe"] == {"minzoom": lo, "maxzoom": hi} and shape(f.geometry).intersects(band)]
        assert held and all(g.intersection(mask).area > 0.9 * mask.area for g in held), lo


@pytest.mark.parametrize("case", ["step", "sliver", "patch", "hole", "finger"])
def test_every_band_nosurvey_part_is_wide_enough_to_draw(case):
    """Every nosurvey part emitted for one band's zooms is at least THIN_UNITS wide at that band's minzoom, so
    tippecanoe never draws it as a square over depth."""
    feats = {"step": lambda: _step_case()[0], "sliver": lambda: _sliver_features(),
             "patch": lambda: _patch_case()[0], "hole": lambda: _hole_case()[0],
             "finger": lambda: _finger_case()[0]}[case]()
    for lo, hi, _ in BANDS:
        parts = [shape(f.geometry) for f in _layer(feats, "nosurvey")
                 if f.props["tippecanoe"] == {"minzoom": lo, "maxzoom": hi}]
        assert all(_units_width(p, lo) >= 2 for p in parts), (lo, sorted(round(_units_width(p, lo), 2) for p in parts))


def _sliver_features():
    depth, transform, core, nosurvey, _ = _sliver_case()
    return _derive(depth, transform=transform, core=core, nosurvey=nosurvey)


def _hole_case():
    """At FINE_RES_DEG, 20 m water under a no-survey box with a hole of 4 by 4 fine cells (14 m in Web Mercator):
    the depth in the hole is thin at zoom 10, where no 2-unit (19 m) disk fits in it (R.3, a surveyed pocket in
    the mask). Returns (features, core, the hole)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d = FINE_RES_DEG
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    hole = box(X0 + 78 * d, Y0 - 82 * d, X0 + 82 * d, Y0 - 78 * d)
    mask = box(X0 + 40 * d, Y0 - 120 * d, X0 + 120 * d, Y0 - 40 * d).difference(hole)
    return _derive(np.full((N, N), 20.0), transform=transform, core=core, nosurvey=mask), core, hole


def test_depth_in_a_mask_hole_still_goes_to_nosurvey():
    """R.3: a surveyed pocket in the mask, too thin at a band's minzoom, is nosurvey at that band (it shares its
    whole perimeter with the mask); depth at the bands it is wide enough for."""
    feats, core, hole = _hole_case()
    inner = hole.buffer(-1e-9)
    for lo, _, _ in BANDS:
        depth = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", lo)])
        thin = _units_width(hole, lo) < 1  # a square of side s: 2 A / P is s / 2, and a 2-unit disk fits when s >= 2
        assert (depth.intersection(hole).area < 1e-6 * hole.area) == thin, lo
        assert masked.covers(inner) == thin, lo


def test_depcnt_on_a_dropped_part_edge_does_not_survive_float_noise():
    """A depth contour along the edge of a dropped part, off it by float noise only (dry run 3, 16/8641/21143: 19 %
    of a 1.8 line lay on the edge and survived the difference), is removed with the part."""
    from chartpack.enc.derived import _lines_off

    gone = box(-124.0, 49.0, -123.9999, 49.001)
    lines = np.array([shapely.LineString([(-123.9999 + 1e-13, 49.0002), (-123.9999 + 1e-13, 49.0008)]),
                      shapely.LineString([(-123.9998, 49.0002), (-123.9998, 49.0008)])], object)
    kept = _lines_off(lines, gone)
    assert len(kept) == 1 and kept[0].equals(lines[1])


def test_thin_part_whose_patch_is_still_thin_goes_with_the_nosurvey_it_borders():
    """Ruling 55 (C), closing review M2: a 3 m strip of depth between a 3 m strip of mask and land is sent, and its
    zoom-10 patch (the strip and the mask beside it, 6 m) is still under 2 units (19 m). It is not given back to
    depth: it goes, emitted at zooms 10 to 11 inside the whole mask piece it borders, not alone."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d, m = FINE_RES_DEG, 1 / 111319.49  # degrees of longitude per Web Mercator meter
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    west = X0 + 80.3 * d
    mask = box(west - 3 * m, core[1], west, core[3])
    strip = box(west, core[1], west + 3 * m, core[3])
    land = box(west + 3 * m, core[1], core[2], core[3])
    feats = _derive(np.full((N, N), 20.0), transform=transform, core=core, nosurvey=mask, land=land)
    for lo, hi in ((10, 11), (12, 13)):
        depth = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        assert depth.intersection(strip).area < 1e-6 * strip.area, lo
    held = [shape(f.geometry) for f in _layer(feats, "nosurvey")
            if f.props["tippecanoe"] == {"minzoom": 10, "maxzoom": 11} and shape(f.geometry).intersects(strip)]
    assert held and all(g.intersection(mask).area > 0.99 * mask.area for g in held)


def _finger_case():
    """At FINE_RES_DEG, 20 m water; a no-survey box east of column 80 with a notch 1.5 m (Web Mercator) wide and
    60 m long: surveyed water poking into the mask as a finger of the wide depth area west of it. The finger is
    under 2 units wide at zooms 10 (19 m) and 12 (4.8 m), over it at 14 (1.2 m), as the 2-3.6 finger of
    haida-gwaii-south 13/1098/2676 (dry run 43547768743). Returns (features, the finger)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d, m = FINE_RES_DEG, 1 / 111319.49
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    edge, mid = X0 + 80 * d, Y0 - 80 * d
    finger = box(edge, mid - 0.75 * m, edge + 60 * m, mid + 0.75 * m)
    mask = box(edge, core[1], core[2], core[3]).difference(finger)
    return _derive(np.full((N, N), 20.0), transform=transform, core=core, nosurvey=mask), finger


def test_thin_finger_of_a_wide_depth_area_goes_to_nosurvey():
    """A finger of a depth area that is wide as a whole, thinner than 2 units at a band's minzoom and lying along
    the mask, is nosurvey at that band (2 A / P of the whole area does not see it, and tippecanoe draws the finger
    as a spike inside the nosurvey); depth where it is wide enough; the rest of the area stays depth."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    feats, finger = _finger_case()
    finger_core = (X0, Y0 - N * FINE_RES_DEG, X0 + N * FINE_RES_DEG, Y0)
    for lo, _, _ in BANDS:
        depth = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        masked = shapely.union_all([shape(f.geometry) for f in _shown(feats, "nosurvey", lo)])
        thin = _units_width(finger, lo) < 2
        assert (depth.intersection(finger).area < 0.05 * finger.area) == thin, lo
        if thin:
            assert masked.intersection(finger).area > 0.95 * finger.area, lo
        assert depth.area > 0.4 * box(*finger_core).area, lo  # the area west of the mask stays depth


def _comb_case():
    """At FINE_RES_DEG, 20 m water in a band 60 m (Web Mercator) wide between land (west) and a mask (east), with
    teeth 3 m wide and 30 m long every 6 m poking into the mask: as a whole the part is under 2 units wide at zoom
    10 (19 m) by 2 A / P, but its band holds a core a 2-unit disk fits in (the ragged NONNA-100 parts of the
    overview, dry run 43547809585). Returns (features, the band, the teeth)."""
    from chartpack.bathy.blocks import FINE_RES_DEG

    d, m = FINE_RES_DEG, 1 / 111319.49
    transform, core = (X0, d, 0.0, Y0, 0.0, -d), (X0, Y0 - N * d, X0 + N * d, Y0)
    west = X0 + 20 * d
    band = box(west, core[1], west + 60 * m, core[3])
    ys = np.arange(core[1] + 3 * m, core[3] - 3 * m, 6 * m)
    teeth = shapely.union_all([box(west + 60 * m, y, west + 90 * m, y + 3 * m) for y in ys])
    land = box(core[0], core[1], west, core[3])
    mask = box(west + 60 * m, core[1], core[2], core[3]).difference(teeth)
    feats = _derive(np.full((N, N), 20.0), transform=transform, core=core, nosurvey=mask, land=land)
    return feats, band, teeth


def test_wide_ragged_part_beside_nosurvey_keeps_its_core():
    """A part thin by 2 A / P only because of its ragged edge keeps its core as depth beside the nosurvey; only the
    pieces an opening by 2 units takes off (the teeth) go."""
    feats, band, teeth = _comb_case()
    whole = shapely.union_all([band, teeth])
    assert _units_width(whole, 10) < 2  # the case is what it says: thin as a whole at zoom 10
    for lo in (10, 12):
        depth = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", lo)])
        assert depth.intersection(band).area > 0.8 * band.area, lo
    depth10 = shapely.union_all([shape(f.geometry) for f in _layer(feats, "depare", 10)])
    assert depth10.intersection(teeth).area < 0.2 * teeth.area


# ---- plan8-patchfix review (fix round 8)

def _big_mask_case():
    """The patchfix review's timing case (I1): a wiggly mask of 100,000 vertices with a hole of 16,384, 3,000 small
    boxes just off its edge, and one part of 50,000 vertices filling the hole along its whole edge."""
    t = np.linspace(0, 2 * np.pi, 100000, endpoint=False)
    r = 1 + 0.01 * np.sin(400 * t)
    mask = shapely.Polygon(np.column_stack([r * np.cos(t), r * np.sin(t)])).difference(
        shapely.Point(0, 0).buffer(0.3, 4096))
    ang = np.linspace(0, 2 * np.pi, 3000, endpoint=False)
    parts = [box(1.02 * np.cos(a), 1.02 * np.sin(a), 1.02 * np.cos(a) + 0.001, 1.02 * np.sin(a) + 0.001) for a in ang]
    return mask, np.array(parts + [shapely.Point(0, 0).buffer(0.3, 12500)], object)


def _old_shared(parts, reach):
    """The shared length as 1c25266 measured it, a whole part ring against each buffered mask segment: the O(n x m)
    way the timing test compares with."""
    from chartpack.enc.derived import _EDGE_DEG, _segments

    out = np.zeros(len(parts))
    segs = shapely.buffer(_segments(reach)[0], _EDGE_DEG, quad_segs=1)
    rings = shapely.boundary(parts)
    which, seg = shapely.STRtree(segs).query(rings, predicate="intersects")
    np.add.at(out, which, shapely.length(shapely.intersection(rings[which], segs[seg])))
    return out


def test_meeting_and_share_tests_stay_fast_on_a_long_mask_edge():
    """On the case, each step takes under a third of the time of the way it replaced, timed in the same run (a
    ratio, so a slow runner does not fail it): the mask prepared and tested first (_meeting) against the
    unprepared test, and the shared length segment against segment (_shared) against whole rings (_old_shared).
    On the review's machine the old ways took 3.75 s and 5.56 s, the new ones 0.008 s and 0.40 s."""
    import time

    from chartpack.enc.derived import _meeting, _shared

    mask, parts = _big_mask_case()
    reach = shapely.get_parts(mask)

    def timed(f):
        t = time.perf_counter()
        out = f()
        return out, time.perf_counter() - t

    meets, new = timed(lambda: _meeting(parts, mask))
    old_meets, old = timed(lambda: shapely.intersects(parts, mask))
    assert meets.tolist() == old_meets.tolist() == [False] * 3000 + [True] and new < old / 3, (new, old)
    shared, new = timed(lambda: _shared(parts, reach))
    old_shared, old = timed(lambda: _old_shared(parts, reach))
    assert np.allclose(shared, old_shared, atol=1e-6) and new < old / 3, (new, old)


def test_share_rule_sends_at_a_quarter_of_the_perimeter():
    """_to_nosurvey alone (no patch guard): a 1 by 10 part whose long side lies along the mask for 4.4 (a share of
    0.2 of its perimeter of 22) stays depth; one along it for 6.6 (0.3) goes. Pins SHARE_MIN = 0.25 (review M1)."""
    from chartpack.enc.derived import SHARE_MIN, _to_nosurvey

    assert SHARE_MIN == 0.25
    area = shapely.union_all([box(0, 0, 10, 4.4), box(0, 20, 10, 26.6)])
    parts = np.array([box(10, 0, 11, 10), box(10, 20, 11, 30)], object)
    assert _to_nosurvey(parts, np.ones(2, bool), area).tolist() == [False, True]


def test_ragged_part_reached_through_a_sent_part_keeps_its_core():
    """Review M3: a part thin by 2 A / P only (a 3-unit band with teeth) that reaches the nosurvey only through a
    thin strip already sent is opened too: its core stays depth instead of going whole with the strip. Units of
    zoom 10 at the equator."""
    from chartpack.enc.derived import _select

    u = 360 / (2**10 * 4096)

    def ubox(x0, y0, x1, y1):
        return box(x0 * u, y0 * u, x1 * u, y1 * u)

    area = ubox(0, 0, 10, 40)
    strip = ubox(10, 0, 10.5, 40)
    band = ubox(10.5, 0, 13.5, 40)
    ragged = shapely.union_all([band] + [ubox(13.5, y, 16.5, y + 0.4) for y in range(2, 40, 4)])
    assert _units_width(ragged, 10) < 2
    every = np.array([strip, ragged], object)
    cand, drop, pieces, parent, _, _ = _select(every, area, 10, 8 * u)
    assert drop[0] and not drop[1]  # the strip goes, the ragged part is not sent whole
    gone = shapely.union_all(cand[drop])
    assert gone.intersection(band.buffer(-1.1 * u)).area == 0  # its core stays depth


def test_a_core_found_in_round_one_survives_a_later_round():
    """Review N1: in one band, a ragged part meeting the mask is opened in round 1 of _select (its core is found
    there), and a second ragged part reached only through a sent strip makes a round 2. The first part's core must
    still count in round 2: it is not sent whole, and its core stays depth."""
    from chartpack.enc.derived import _select

    u = 360 / (2**10 * 4096)

    def ubox(x0, y0, x1, y1):
        return box(x0 * u, y0 * u, x1 * u, y1 * u)

    def comb(x0, y0):  # a 3-unit band 40 long with 10 teeth 0.4 by 3 on its east side: 2 A / P 1.81
        return shapely.union_all([ubox(x0, y0, x0 + 3, y0 + 40)]
                                 + [ubox(x0 + 3, y, x0 + 6, y + 0.4) for y in range(y0 + 2, y0 + 40, 4)])

    area = shapely.union_all([ubox(0, 0, 10, 40), ubox(0, 50, 10, 90)])
    first = comb(10, 50)  # along the mask itself: opened in round 1
    strip, second = ubox(10, 0, 10.5, 40), comb(10.5, 0)  # reached through the strip: opened in round 2
    every = np.array([first, strip, second], object)
    cand, drop, _, _, gone, _ = _select(every, area, 10, 8 * u)
    assert not drop[0] and drop[1] and not drop[2]
    for part in (first, second):
        core = shapely.intersection(part, ubox(part.bounds[0] / u + 1.1, part.bounds[1] / u, part.bounds[0] / u + 1.9,
                                               part.bounds[3] / u))
        assert gone.intersection(core).area < 1e-9 * core.area  # float noise along a joined piece's edge only


def test_wide_part_reached_through_a_sent_sliver_loses_its_finger():
    """PR 134 review: a wide part meeting the nosurvey only through a thin sliver sent to it is opened too, so its
    finger between the sliver's two arms goes with them (else it stays depth between two nosurvey arms and draws
    as a spike past the patch). Units of zoom 12 at the equator; the mask is y < 0."""
    from chartpack.enc.derived import _select

    u = 360 / (2**12 * 4096)

    def ubox(x0, y0, x1, y1):
        return box(x0 * u, y0 * u, x1 * u, y1 * u)

    mask = ubox(-50, -10, 50, 0)
    sliver = shapely.union_all([ubox(-50, 0, 50, 1).difference(ubox(-0.2, 0.3, 0.2, 1)),
                                ubox(-1.2, 1, -0.2, 20), ubox(0.2, 1, 1.2, 20)])
    wide = ubox(-50, 0, 50, 60).difference(sliver)
    finger = ubox(-0.2, 0.3, 0.2, 20)
    cand, drop, pieces, parent, gone, _ = _select(np.array([sliver, wide], object), mask, 12, 8 * u)
    assert drop[0] and not drop[1]
    assert gone.intersection(finger).area > 0.9 * finger.area


def _round_resegmenting_to_nosurvey(parts, thin, area):
    """_to_nosurvey as 9cd03e9 ran it: every round re-segments every open thin part and measures it against the new
    reach (the PR 134 review's build-time finding), kept here to time the new one against."""
    from chartpack.enc.derived import _EDGE_DEG, SHARE_MIN, _segments

    def shared(ps, reach):
        out = np.zeros(len(ps))
        mine, owner = _segments(ps)
        theirs, _ = _segments(reach)
        a, b = shapely.STRtree(theirs).query(mine, predicate="dwithin", distance=_EDGE_DEG)
        if len(a):
            np.add.at(out, owner[a], shapely.length(shapely.intersection(
                mine[a], shapely.buffer(theirs[b], _EDGE_DEG, quad_segs=1))))
        return out

    out = np.zeros(len(parts), bool)
    index = np.flatnonzero(thin)
    need = SHARE_MIN * shapely.length(parts[index])
    got = np.zeros(len(index))
    reach = shapely.get_parts(area)
    while len(reach):
        open_ = ~out[index]
        got[open_] += shared(parts[index[open_]], reach)
        new = index[open_ & (got >= need)]
        out[new] = True
        reach = parts[new]
    return out


def test_share_rounds_cost_the_new_reach_not_every_open_part():
    """PR 134 review: a chain of 400 strips (0.5 by 4, each along the next) from the mask, beside 2,000 unrelated
    thin parts. Each round measures only the open parts near the parts newly sent, against them: under a third of
    the time of re-segmenting every open part each round (timed in the same run), same result."""
    import time

    from chartpack.enc.derived import _to_nosurvey

    area = box(-1, 0, 0, 4)
    chain = [box(0.5 * i, 0, 0.5 * (i + 1), 4) for i in range(400)]
    other = [box(1000 + 3 * i, 0, 1000.5 + 3 * i, 4) for i in range(2000)]
    parts = np.array(chain + other, object)
    thin = np.ones(len(parts), bool)
    t = time.perf_counter()
    new = _to_nosurvey(parts, thin, area)
    t_new = time.perf_counter() - t
    t = time.perf_counter()
    old = _round_resegmenting_to_nosurvey(parts, thin, area)
    t_old = time.perf_counter() - t
    assert new.tolist() == old.tolist() == [True] * 400 + [False] * 2000
    assert t_new < t_old / 3, (t_new, t_old)


def test_thin_strip_whose_square_falls_in_a_pocket_goes():
    """PR 134 review (Minor): a curved thin strip ringing a small mask pocket meets it at one point only (under the
    0.25 share), but tippecanoe would draw it as its same-area square at its centroid, deep inside the pocket. The
    strip goes to nosurvey when that square (in tile units at the band's minzoom) reaches more than the check's
    NOSURVEY_TOLERANCE_UNITS into the nosurvey. Units of zoom 10 at the equator."""
    from chartpack.enc.derived import _SQUARE_REACH_UNITS, _select
    from chartpack.pack.check import NOSURVEY_TOLERANCE_UNITS

    assert _SQUARE_REACH_UNITS == NOSURVEY_TOLERANCE_UNITS
    u = 360 / (2**10 * 4096)
    pocket = shapely.Point(0, 0).buffer(10 * u, 64)
    t = np.linspace(0.3, 6.0, 400)
    outer = np.column_stack([0.5 * u + 11.3 * u * np.cos(t), 11.3 * u * np.sin(t)])
    inner = np.column_stack([0.5 * u + 10.5 * u * np.cos(t), 10.5 * u * np.sin(t)])[::-1]
    strip = shapely.Polygon(np.vstack([outer, inner]))
    assert strip.is_valid and _units_width(strip, 10) < 2 and strip.distance(pocket) < 1e-12
    cand, drop, _, _, gone, _ = _select(np.array([strip], object), pocket, 10, 8 * u)
    assert drop[0]


def _whole_mask_square_in(parts, area, z):
    """_square_in as 6e05f28 ran it: each hit's box overlaid with the whole mask (PR 134 review 5902634552), kept
    here to time the new one against."""
    from chartpack.enc.derived import _SQUARE_REACH_UNITS, _meeting, _units

    out = np.zeros(len(parts), bool)
    to_units, to_lonlat = _units(z)
    units = shapely.transform(parts, to_units)
    x, y = shapely.get_x(shapely.centroid(units)), shapely.get_y(shapely.centroid(units))
    half = np.sqrt(shapely.area(units)) / 2
    squares = shapely.box(x - half, y - half, x + half, y + half)
    hit = np.flatnonzero(_meeting(shapely.transform(squares, to_lonlat), area))
    if len(hit):
        m = half[hit] + _SQUARE_REACH_UNITS + 1
        near = shapely.transform(shapely.box(x[hit] - m, y[hit] - m, x[hit] + m, y[hit] + m), to_lonlat)
        local = shapely.transform(shapely.intersection(area, near), to_units)
        out[hit] = shapely.intersects(shapely.buffer(local, -_SQUARE_REACH_UNITS), squares[hit])
    return out


def test_square_test_cost_follows_the_squares_not_the_mask():
    """PR 134 review: a ragged mask of 200,000 vertices, 3,000 units across, and 1,000 thin strips whose squares
    meet it, some deep in it and some at its edge. _square_in puts the mask near each square together from its pieces (split once):
    under a third of the time of overlaying the whole mask per square (timed in the same run), same result."""
    import time

    from chartpack.enc.derived import _square_in

    u = 360 / (2**10 * 4096)
    t = np.linspace(0, 2 * np.pi, 200000, endpoint=False)
    r = (1500 + 3 * np.sin(997 * t)) * u
    mask = shapely.Polygon(np.column_stack([r * np.cos(t), r * np.sin(t)]))
    ang = np.linspace(0, 2 * np.pi, 1000, endpoint=False)
    rad = np.where(np.arange(1000) % 2, 1490, 1499) * u  # deep inside, and at the edge
    parts = np.array([shapely.affinity.rotate(box(q - 0.25 * u, -5 * u, q + 0.25 * u, 5 * u), a, origin=(0, 0),
                                              use_radians=True) for q, a in zip(rad, ang)], object)
    t0 = time.perf_counter()
    new = _square_in(parts, mask, 10)
    t_new = time.perf_counter() - t0
    t0 = time.perf_counter()
    old = _whole_mask_square_in(parts, mask, 10)
    t_old = time.perf_counter() - t0
    assert new.tolist() == old.tolist() and new[1::2].all()
    assert t_new < t_old / 3, (t_new, t_old)


def test_share_rule_runs_on_from_a_part_the_square_rule_sent():
    """PR 134 review: the square rule sends the strip ringing the pocket; a second thin strip along its outer
    edge (half its own perimeter), touching no mask and with its own square away from the pocket, then goes by the
    share rule run on from the first."""
    from chartpack.enc.derived import _select

    u = 360 / (2**10 * 4096)
    pocket = shapely.Point(0, 0).buffer(10 * u, 64)

    t = np.linspace(0.3, 6.0, 571)  # every 0.01 rad, so the two strips share the vertices of their common arc

    def arc_strip(r0, r1, sel):
        outer = np.column_stack([0.5 * u + r1 * u * np.cos(t[sel]), r1 * u * np.sin(t[sel])])
        inner = np.column_stack([0.5 * u + r0 * u * np.cos(t[sel]), r0 * u * np.sin(t[sel])])[::-1]
        return shapely.Polygon(np.vstack([outer, inner]))

    ring = arc_strip(10.5, 11.3, slice(None))
    beside = arc_strip(11.3, 11.8, slice(230, 331))  # 2.6 to 3.6 rad
    assert beside.distance(pocket) > 0.5 * u
    cand, drop, _, _, _, _ = _select(np.array([ring, beside], object), pocket, 10, 8 * u)
    assert drop.tolist() == [True, True]


def _within(seconds, f):
    """f() or a test failure after seconds (SIGALRM, as pytest runs tests in the main thread): a loop that never
    ends fails instead of hanging the suite (the repo has no pytest-timeout)."""
    import signal

    def stop(*_):
        raise TimeoutError(f"still running after {seconds} s")

    old = signal.signal(signal.SIGALRM, stop)
    signal.alarm(seconds)
    try:
        return f()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


@pytest.mark.parametrize("wkt, depth, most", [(_SLIVER, None, 1), (_CELLS_WITH_HOLE, None, 450), (_CELLS_WITH_HOLE, 2, 5)])
def test_subdivide_survives_a_sliver_and_keeps_the_area(wkt, depth, most, monkeypatch):
    """_subdivide cuts with an overlay, not GEOS's fast rectangle clip: halving the haida-gwaii sliver of PR 130
    made clip_by_rect raise "Invalid number of points in LinearRing found 3" (dry run of haida-gwaii-south at
    18a474f). A piece size of 3 vertices forces the cuts; the pieces are valid and cover the input exactly. The
    loop guards are pinned (PR 135 review): the split ends within 10 s, a cut that leaves no smaller piece keeps
    its input (408 pieces for the cells today, capped at 450), and with _CUT_DEPTH at 2 the cells give at most
    5."""
    from chartpack.enc import derived

    monkeypatch.setattr(derived, "_PIECE_VERTICES", 3)
    if depth is not None:
        monkeypatch.setattr(derived, "_CUT_DEPTH", depth)
    geom = shapely.from_wkt(wkt)
    pieces = _within(10, lambda: derived._subdivide(geom).geometries)
    assert 0 < len(pieces) <= most
    assert shapely.is_valid(pieces).all()
    assert shapely.union_all(pieces).symmetric_difference(geom).area < 1e-12 * geom.area


# ---- plan8-edgefix (Ruling 55)

def _ubox(z):
    u = 360 / (2**z * 4096)
    return u, lambda x0, y0, x1, y1: box(x0 * u, y0 * u, x1 * u, y1 * u)


def test_a_hairline_finger_is_a_candidate_not_a_crumb():
    """Dry run 4 north, 10/134/328: a finger 0.1 units wide and 8 long (0.8 unit2) off a wide part, into the mask,
    is longer than 2 units, so it is a finger, not a corner crumb (crumbs are under 1 unit2 and about a unit
    across); it goes with the mask while the wide part stays depth. Units of zoom 10 at the equator."""
    from chartpack.enc.derived import _fingers, _select

    u, ubox = _ubox(10)
    finger = ubox(20, 9.95, 28, 10.05)
    part = shapely.union_all([ubox(0, 0, 20, 20), finger])
    pieces, parent, cored = _fingers(np.array([part], object), np.array([True]), 10)
    assert cored[0] and any(p.intersection(finger).area > 0.9 * finger.area for p in pieces)
    mask = ubox(20, 0, 40, 20).difference(finger)
    cand, drop, _, _, gone, _ = _select(np.array([part], object), mask, 10, 8 * u)
    assert not drop[0] and gone.intersection(finger).area > 0.9 * finger.area
