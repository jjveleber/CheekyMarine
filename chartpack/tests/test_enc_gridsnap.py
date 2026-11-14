"""The derived features snapped to each band's minzoom tile grid (enc/gridsnap.py, plan8-gridsnap design)."""

import math

import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon, box, mapping, shape
from shapely.affinity import rotate

from chartpack.bathy.contours import BANDS
from chartpack.enc.gridsnap import _units, snap_derived
from chartpack.enc.reader import Feature
from chartpack.grid import tile_bounds

TILE = (163, 356)
CORE = tile_bounds(10, *TILE)
ALL = (10, 16)


def _origin(z):
    """The global units of zoom z at the core's north-west corner (integers: a zoom-10 tile edge is on every grid
    from zoom 6 up)."""
    return TILE[0] * 4096 * 2 ** (z - 10), TILE[1] * 4096 * 2 ** (z - 10)


def _ll(geom, z=10, core=CORE):
    """geom given in units of zoom z from the core's north-west corner, in lon/lat."""
    x0, y0 = _origin(z) if core is CORE else core
    return shapely.transform(shapely.affinity.translate(geom, x0, y0), _units(z)[1])


def _u(geom, z=10):
    """A lon/lat geometry in units of zoom z from the core's north-west corner."""
    x0, y0 = _origin(z)
    return shapely.affinity.translate(shapely.transform(geom, _units(z)[0]), -x0, -y0)


def _f(layer, geom, zooms=ALL, core=CORE, **props):
    return Feature(layer, mapping(geom), {**props, "tippecanoe": {"minzoom": zooms[0], "maxzoom": zooms[1],
                                                                 "core": list(core)}})


def _depare(geom, lo, hi, zooms, src="nonna10"):
    return _f("depare", geom, zooms, DRVAL1=lo, DRVAL2=hi, src=src)


def _band_of(features, z):
    return [f for f in features if f.props["tippecanoe"]["minzoom"] <= z <= f.props["tippecanoe"]["maxzoom"]]


def _union(features, layer, z, units=10):
    return shapely.union_all([_u(shape(f.geometry), units) for f in _band_of(features, z) if f.layer == layer])


def _case():
    """Per band, in zoom-10 units over the 4096-unit core: land (a circle), a nosurvey circle with a 0.3-unit
    sliver, and depth bands as rings of a slanted field, all cut to the core less land less nosurvey."""
    core = box(0, 0, 4096, 4096)
    land = shapely.Point(1000.3, 1000.7).buffer(600, quad_segs=64)
    mask = shapely.union_all([shapely.Point(3000.2, 3000.1).buffer(500, quad_segs=64), box(2000.1, 0, 2000.4, 4096)])
    mask = mask.difference(land)
    cut = core.difference(shapely.union_all([mask, land]))
    feats = [_f("lndare", _ll(land), src="fwa"), _f("nosurvey", _ll(mask))]
    for lo, hi, _ in BANDS:
        prev = shapely.Polygon()
        edges = ["0", "0.9", "1.8", "2", "3.6", "5", "5.4"]
        for i, r in enumerate((300.0, 300.4, 900.0, 1400.0, 2600.0, 9000.0)):
            ring = rotate(box(2048 - r, 2048 - r, 2048 + r, 2048 + r), 17, origin=(2048, 2048))
            part = ring.difference(prev).intersection(cut)
            prev = shapely.union_all([prev, ring])
            for p in shapely.get_parts(part):
                feats.append(_depare(_ll(p), edges[i], edges[i + 1], (lo, hi), "nonna10" if i < 3 else "nonna100"))
    return feats


def test_band_output_is_an_exact_integer_coverage_of_the_core():
    feats = snap_derived(_case(), BANDS)
    for lo, hi, _ in BANDS:
        x0, y0 = _origin(lo)
        polys = [shapely.transform(shape(f.geometry), _units(lo)[0]) for f in _band_of(feats, lo)
                 if f.layer in ("depare", "nosurvey", "lndare")]
        coords = shapely.get_coordinates(polys)
        assert np.abs(coords - np.round(coords)).max() < 1e-6, lo
        polys = shapely.set_precision(np.array(polys, object), 1.0)  # the 1e-9 float noise of the lon/lat round trip
        frame = box(x0, y0, x0 + 4096 * 2 ** (lo - 10), y0 + 4096 * 2 ** (lo - 10))
        union = shapely.union_all(polys)
        assert union.symmetric_difference(frame).area == 0, lo
        assert shapely.area(polys).sum() == frame.area, lo
        assert shapely.coverage_is_valid(polys), lo
        assert all(f.props["tippecanoe"] == {"minzoom": lo, "maxzoom": hi} for f in _band_of(feats, lo)
                   if f.layer != "coalne"), lo


@pytest.mark.parametrize("rounding", ["round", "floor"])
def test_tippecanoe_quantization_leaves_every_vertex_in_place_at_every_zoom_of_the_band(rounding):
    """A model of tippecanoe's write: lon/lat to a 2^32 world (rounded, or floored), then to the 4,096 tile units of
    zoom z with rounding. Every snapped vertex lands on its own grid point at every zoom of its band, so nothing
    can collapse into a square."""
    op = np.round if rounding == "round" else np.floor
    for f in snap_derived(_case(), BANDS):
        if f.layer not in ("depare", "nosurvey", "lndare"):
            continue
        lo, hi = f.props["tippecanoe"]["minzoom"], f.props["tippecanoe"]["maxzoom"]
        c = shapely.get_coordinates(shape(f.geometry))
        wx = op((c[:, 0] + 180) / 360 * 2.0**32)
        wy = op((1 - np.log(np.tan(np.radians(c[:, 1])) + 1 / np.cos(np.radians(c[:, 1]))) / math.pi) / 2 * 2.0**32)
        mine = np.round(shapely.get_coordinates(shapely.transform(shape(f.geometry), _units(lo)[0])))
        for z in range(lo, hi + 1):
            s = 20 - z
            tx, ty = (wx + 2 ** (s - 1)) // 2**s, (wy + 2 ** (s - 1)) // 2**s
            assert (tx == mine[:, 0] * 2 ** (z - lo)).all() and (ty == mine[:, 1] * 2 ** (z - lo)).all(), (f.layer, z)


def test_each_class_stays_within_a_unit_and_a_half_of_its_place():
    given = _case()
    feats = snap_derived(given, BANDS)
    for lo, _, _ in BANDS:
        for layer in ("depare", "lndare"):
            before = _union(given, layer, lo, lo).buffer(1.5)
            assert before.covers(_union(feats, layer, lo, lo)), (lo, layer)
        before = _union(given, "nosurvey", lo, lo)
        after = _union(feats, "nosurvey", lo, lo)
        assert after.buffer(1.5).covers(before.buffer(-1.0)), lo  # the 0.3-unit sliver may vanish


def test_a_sliver_of_nosurvey_under_one_unit_vanishes():
    feats = snap_derived(_case(), BANDS)
    ns = _union(feats, "nosurvey", 10)
    assert ns.intersection(box(1990, 0, 2010, 4096)).area < 1.0
    assert _union(feats, "nosurvey", 14, 14).area > 0


def _thin_case(lo=10, angle=0.0):
    """nosurvey west of x 10; a 1-unit depth strip along it (2-3.6), a 1-unit strip beside that one only (3.6-5),
    wide depth (5-5.4) east to 100; a 1-unit strip between two wide depth bands at x 60 (5.4-7.3) touching no
    nosurvey. Units of zoom lo, 1000 units into the core, rotated by angle about that place."""
    def part(x0, x1):
        return _ll(rotate(box(1000 + x0, 1000, 1000 + x1, 1200), angle, origin=(1000, 1000)), lo)

    zooms = next((a, b) for a, b, _ in BANDS if a == lo)
    return [_f("nosurvey", part(-50, 10), zooms), _depare(part(10, 11), "2", "3.6", zooms),
            _depare(part(11, 12), "3.6", "5", zooms), _depare(part(12, 60), "5", "5.4", zooms),
            _depare(part(60, 61), "5.4", "7.3", zooms), _depare(part(61, 100), "7.3", "9.1", zooms),
            _f("nosurvey", part(100, 150), zooms)]


def _snap_one(feats, lo):
    return snap_derived(feats, [b for b in BANDS if b[0] == lo])


def test_thin_depth_along_nosurvey_goes_but_not_by_chain_nor_between_depth():
    feats = _snap_one(_thin_case(), 10)
    by = {f.props["DRVAL1"]: f for f in feats if f.layer == "depare"}
    assert "2" not in by  # the strip along nosurvey goes
    assert {"3.6", "5", "5.4", "7.3"} <= set(by)  # beside it only (no chain), wide, and between depth bands
    assert _union(feats, "nosurvey", 10).covers(box(1010, 1000, 1011, 1200).buffer(-1e-6))


@pytest.mark.parametrize("angle", [17.0, 33.0])
def test_rotated_parts_keep_their_wide_depth(angle):
    """PR 136 review: slanted edges must not leave hairline faces that join crumbs; the wide parts stay depth and
    only depth along the nosurvey and thinner than a unit goes."""
    given = _thin_case(angle=angle)
    feats = _snap_one(given, 10)
    wide = _union([f for f in given if f.props.get("DRVAL1") == "5"], "depare", 10)
    kept = _union([f for f in feats if f.props.get("DRVAL1") == "5"], "depare", 10)
    assert kept.area > 0.97 * wide.area
    assert _union(feats, "depare", 10).area > 0.97 * _union(given, "depare", 10).area


def test_contours_are_the_edges_between_depth_bands_only():
    feats = _snap_one(_thin_case(), 10)
    lines = {f.props["VALDCO"]: f for f in feats if f.layer == "depcnt"}
    assert set(lines) == {"5", "5.4", "7.3"}  # 3.6 borders nosurvey now (the strip at 2-3.6 went)
    ns = _union(feats, "nosurvey", 10)
    for value, f in lines.items():
        g = _u(shape(f.geometry))
        assert g.length > 190 and ns.intersection(g).length < 1e-6, value
    assert {f.props["src"] for f in lines.values()} == {"nonna10"}


def test_contour_src_is_the_coarser_of_its_two_faces():
    zooms = (10, 11)
    feats = _snap_one([_depare(_ll(box(0, 0, 50, 100)), "0", "0.9", zooms, "nonna10"),
                       _depare(_ll(box(50, 0, 100, 100)), "0.9", "1.8", zooms, "nonna100")], 10)
    (line,) = [f for f in feats if f.layer == "depcnt"]
    assert line.props["src"] == "nonna100" and line.props["VALDCO"] == "0.9"


def test_soundings_only_on_the_depth_drawn_at_their_zoom():
    given = _thin_case()
    points = {"deep": (1030, 1100), "nosurvey": (980, 1100), "strip": (1010.5, 1100)}
    for name, (x, y) in points.items():
        given.append(_f("soundg", _ll(shapely.Point(x, y)), (10, 10), depth="3", src="nonna10", name=name))
    kept = {f.props["name"] for f in _snap_one(given, 10) if f.layer == "soundg"}
    assert kept == {"deep"}


def test_adjacent_cores_meet_on_their_shared_edge():
    """Two cores side by side, a slanted band edge across both: their snapped depth meets on the shared core edge
    with no gap and no overlap."""
    east = tile_bounds(10, TILE[0] + 1, TILE[1])
    shallow = Polygon([(0, 0), (8192, 0), (8192, 2000.37 + 0.11 * 8192), (0, 2000.37)])
    deep = box(0, 0, 8192, 4096).difference(shallow)
    feats = []
    for core, x0 in ((CORE, 0), (east, 4096)):
        frame = box(x0, 0, x0 + 4096, 4096)
        for poly, (a, b) in ((shallow, ("0", "0.9")), (deep, ("0.9", "1.8"))):
            feats.append(_f("depare", _ll(poly.intersection(frame)), (10, 11), core, DRVAL1=a, DRVAL2=b,
                            src="nonna10"))
    out = _snap_one(feats, 10)
    polys = np.array([shapely.set_precision(_u(shape(f.geometry)), 1.0) for f in out if f.layer == "depare"], object)
    assert shapely.area(polys).sum() == 2 * 4096**2
    assert shapely.union_all(polys).equals(box(0, 0, 8192, 4096))


def test_faces_under_no_derived_class_are_dropped():
    """apply_rules cuts derived features away where NOAA cover lies: that side is no class and gives no output."""
    half = Polygon([(0, 0), (2000.4, 0), (2300.7, 4096), (0, 4096)])
    out = _snap_one([_depare(_ll(half), "0", "0.9", (10, 11))], 10)
    got = _union(out, "depare", 10)
    assert half.buffer(1.5).covers(got) and got.area > half.area - 4096 * 1.5


def test_non_derived_features_and_coalne_pass():
    noaa = Feature("depare", mapping(box(0, 0, 1, 1)), {"DRVAL1": "0", "tippecanoe": {"minzoom": 10, "maxzoom": 16}})
    coast = _f("coalne", _ll(shapely.LineString([(5, 5), (50, 7)])), src="fwa")
    out = snap_derived([noaa, coast], BANDS)
    assert out[0] is noaa
    assert out[1].geometry == coast.geometry and out[1].props["tippecanoe"] == {"minzoom": 10, "maxzoom": 16}


# The GEOS 3-point ring class (PR 130 _tiles, PR 135 _subdivide): a sliver that collapses on the grid, and cells
# with a hole, as land and nosurvey in a core of their own.
_SLIVER = ("POLYGON ((-133.04445376 53.751789670000015, -133.04428348 53.75183096999998, "
           "-133.04444260251748 53.75179237615475, -133.04445376 53.751789670000015))")


def test_a_collapsing_sliver_and_cells_with_a_hole_snap_without_error():
    sliver = shapely.from_wkt(_SLIVER)
    lon, lat = sliver.centroid.x, sliver.centroid.y
    n = 2**10
    tile = (int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))
    core = tile_bounds(10, *tile)
    cells = shapely.from_wkt("POLYGON ((0 5, 1 5, 1 4, 2 4, 2 3, 2 2, 3 2, 3 1, 3 0, 2 0, 1 0, 0 0, 0 1, 0 2, 0 3,"
                             " 0 4, 0 5), (1 2, 1 1, 2 1, 2 2, 1 2))")
    ox, oy = tile[0] * 4096, tile[1] * 4096
    cells = _ll(shapely.affinity.scale(cells, 1.37, 1.37, origin=(0, 0)), 10, (ox + 100.3, oy + 100.6))
    rest = box(*core).difference(shapely.union_all([sliver, cells]))
    feats = [_f("lndare", sliver, (10, 16), core, src="fwa"), _f("nosurvey", cells, (10, 16), core)]
    feats += [_f("depare", p, (lo, hi), core, DRVAL1="0", DRVAL2="0.9", src="nonna10")
              for lo, hi, _ in BANDS for p in shapely.get_parts(rest)]
    out = snap_derived(feats, BANDS)
    for lo, _, _ in BANDS:
        polys = [shape(f.geometry) for f in _band_of(out, lo) if f.layer != "coalne"]
        assert polys and shapely.is_valid(shapely.transform(np.array(polys, object), _units(lo)[0])).all(), lo


def test_thin_depth_meeting_nosurvey_at_a_corner_only_stays():
    zooms = (10, 11)
    feats = _snap_one([_f("nosurvey", _ll(box(1000, 1000, 1010, 1010)), zooms),
                       _depare(_ll(box(1010, 1010, 1011, 1060)), "0", "0.9", zooms)], 10)
    assert [f.props["DRVAL1"] for f in feats if f.layer == "depare"] == ["0"]
