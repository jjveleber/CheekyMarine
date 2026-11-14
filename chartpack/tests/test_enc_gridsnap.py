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
    feats = snap_derived(list(given), BANDS)
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
    """feats (a copy: snap_derived empties its input) snapped at the band of minzoom lo only."""
    return snap_derived(list(feats), [b for b in BANDS if b[0] == lo])


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


def test_an_invalid_original_is_labeled_without_error():
    """A derived polygon that is invalid in tile units (from test_build_enc_derived_region_end_to_end: the nosurvey
    triangle cut by apply_rules, self-crossing at 2684671.54, 5839752.37 in zoom-14 units) made the overlap
    fallback raise TopologyException: labels use the originals made valid."""
    from chartpack.enc.gridsnap import _labels

    bad = shapely.from_wkt("POLYGON ((2684721.25499883 5839655.226940997, 2684667.6817537528 5839759.913786557, "
                           "2685752.6613333332 5837639.174093384, 2686172.091733333 5840002.708141658, "
                           "2684401.1633777777 5840280.66895269, 2684587.576888889 5839916.440077268, "
                           "2684721.25499883 5839655.226940997))")
    assert not bad.is_valid
    x, y = 2684680.0, 5839739.0  # beside the crossing, inside the valid part
    assert shapely.make_valid(bad).contains(shapely.Point(x, y))
    face = box(x - 2, y - 0.2, x + 2, y + 0.2)  # thin: labeled by its overlap
    assert _labels(np.array([face], object), np.array([bad], object)).tolist() == [0]


@pytest.mark.parametrize("collapsed, levels", [
    ([("2", "5")], ["2", "5"]),  # the reviewer's probe: a 0.3-unit 2-5 band between 0-2 and 5-10
    ([("2", "5"), ("5", "10")], ["2", "5", "10"]),  # two collapsed bands in a row, between 0-2 and 10-18.2
])
def test_a_band_collapsed_in_the_snap_keeps_its_contour_levels(collapsed, levels):
    """Ruling 59: where the snap closes one or more depth bands under a unit wide, their neighbors meet directly;
    that edge gets one depcnt per level of the original bands between them (shallow DRVAL2 <= L <= deep
    DRVAL1), src the coarser of the two faces."""
    zooms = (10, 11)
    x = 2000.6
    feats = [_depare(_ll(box(0, 0, x, 4096)), "0", "2", zooms)]
    for a, b in collapsed:
        feats.append(_depare(_ll(box(x, 0, x + 0.3, 4096)), a, b, zooms, "nonna100"))
        x += 0.3
    feats.append(_depare(_ll(box(x, 0, 4096, 4096)), collapsed[-1][1], "18.2" if len(collapsed) > 1 else "10",
                         zooms))
    out = _snap_one(feats, 10)
    assert {f.props["DRVAL1"] for f in out if f.layer == "depare"} == {"0", collapsed[-1][1]}
    lines = [f for f in out if f.layer == "depcnt"]
    assert sorted(f.props["VALDCO"] for f in lines) == sorted(levels)
    for f in lines:
        assert _u(shape(f.geometry)).length > 4000 and f.props["src"] == "nonna10"


@pytest.mark.parametrize("feature", [
    _f("nosurvey", _ll(box(0, 0, 10, 10)), (6, 9)),  # an area whose zooms hold no band
    _f("soundg", _ll(shapely.Point(5, 5)), (8, 8), depth="3", src="nonna10"),  # a sounding at a zoom of no band
    _f("depcnt", _ll(shapely.LineString([(0, 0), (9, 9)])), VALDCO="2", src="nonna10"),  # a layer the snap makes
])
def test_a_cored_feature_no_band_takes_is_an_error(feature):
    """Review Minor 3: a derived feature the bands do not consume would be dropped with no signal (for example a
    band list that does not match the one derived_features used): it raises, naming the layer and zooms."""
    with pytest.raises(ValueError, match=feature.layer):
        snap_derived([feature], BANDS)


def test_snap_derived_consumes_its_input():
    """Review Minor 5: the unsnapped features are released as the snap goes (the list given is emptied and each
    core's inputs are let go once snapped), so they and the per-band copies are not all held at the peak."""
    given = _case()
    out = snap_derived(given, BANDS)
    assert given == [] and out


def _big_core(n_mask=30_000, grid=120, seed=1):
    """A realistic synthetic core at zoom 14 (PR 137 review): one nosurvey mask of n_mask vertices with sub-unit
    edge noise (20 units), and contourpy depare of a smooth random field cut by it (many thin faces along the mask). Returns
    (features, the mask's vertex count)."""
    import contourpy
    from shapely import GeometryType

    z, side = 14, 4096 * 16
    rng = np.random.default_rng(seed)
    xs = np.linspace(0, side, grid)
    gx, gy = np.meshgrid(xs, xs)
    field = 20 + sum(rng.normal() * 15 * np.sin(gx / side * k1 * 6.3 + rng.uniform(0, 6.3))
                     * np.cos(gy / side * k2 * 6.3 + rng.uniform(0, 6.3))
                     for k1, k2 in rng.integers(1, 40, (24, 2)))
    t = np.linspace(0, 2 * np.pi, n_mask, endpoint=False)
    r = side * 0.3 + side * 0.002 * np.sin(t * 3000) + rng.normal(size=n_mask) * side * 0.0003  # 20-unit noise
    mask = shapely.make_valid(Polygon(np.column_stack([side / 2 + r * np.cos(t), side / 2 + r * np.sin(t)])))
    shapely.prepare(mask)
    gen = contourpy.contour_generator(xs, xs, field, fill_type="ChunkCombinedOffsetOffset")
    edges = ["-50", "0", "0.9", "1.8", "2", "3.6", "5", "5.4", "7.3", "9.1", "10", "18.2", "20", "27.4", "30",
             "36.5", "50", "12000"]
    feats = [_f("nosurvey", _ll(mask, z))]
    for a, b in zip(edges, edges[1:]):
        points, offsets, outer = gen.filled(float(a), float(b))
        if points[0] is None:
            continue
        polys = shapely.from_ragged_array(GeometryType.POLYGON, points[0], (offsets[0], outer[0]))
        meets = shapely.intersects(mask, polys)  # mask prepared: only the parts it meets need the overlay
        polys = np.concatenate([polys[~meets], shapely.get_parts(shapely.difference(polys[meets], mask))])
        for p in polys:
            if shapely.get_dimensions(p) == 2 and not p.is_empty:
                feats.append(_depare(_ll(p, z), a, b, (14, 16)))
    return feats, shapely.get_num_coordinates(mask)


def test_snapping_a_large_noisy_core_is_bounded_in_work_and_memory(monkeypatch):
    """PR 137 review (no wall clock: flaky on CI). On a 60,000-vertex noisy mask with many thin faces along it:
    - the thin rule builds each face boundary once: the boundaries it builds hold fewer vertices than the core's
      input (per-pair copies of the mask boundary held it once per pair);
    - the label fallback overlays a face with its originals clipped near it, never with the whole mask;
    - the label step's pair queries test against no tree geometry as large as a tenth of the mask (each large
      original is a query geometry, prepared once, or split in pieces), and no clip_by_rect gets the mask
      (fix round 3: one query per face against the unprepared mask, and a clip per face, cost O(mask) each);
    - the traced Python peak stays under 300 MB (GEOS memory is not traced: the counts above guard it)."""
    import sys
    import tracemalloc

    feats, mask_vertices = _big_core()
    given = sum(shapely.get_num_coordinates(shape(f.geometry)) for f in feats)
    built, fallback, tree_max, clip_max = [0], [0], [0], [0]
    boundary, intersection, clip_by_rect, tree_class = shapely.boundary, shapely.intersection, shapely.clip_by_rect, \
        shapely.STRtree

    class WatchedTree(tree_class):
        def __init__(self, geoms, *args, **kwargs):
            super().__init__(geoms, *args, **kwargs)
            if sys._getframe(1).f_code.co_name == "_labels":
                tree_max[0] = max(tree_max[0], int(np.max(shapely.get_num_coordinates(self.geometries), initial=0)))

    def watched_clip(g, *args, **kwargs):
        clip_max[0] = max(clip_max[0], int(np.max(shapely.get_num_coordinates(g), initial=0)))
        return clip_by_rect(g, *args, **kwargs)

    def counted_boundary(g, *args, **kwargs):
        out = boundary(g, *args, **kwargs)
        if sys._getframe(1).f_code.co_name == "_thin_to_nosurvey":
            built[0] += int(np.sum(shapely.get_num_coordinates(out)))
        return out

    def watched_intersection(a, b, *args, **kwargs):
        if sys._getframe(1).f_code.co_name == "_labels":  # the overlap fallback's overlay
            fallback[0] = max(fallback[0], int(np.max(shapely.get_num_coordinates(a), initial=0)))
        return intersection(a, b, *args, **kwargs)

    monkeypatch.setattr(shapely, "boundary", counted_boundary)
    monkeypatch.setattr(shapely, "intersection", watched_intersection)
    monkeypatch.setattr(shapely, "clip_by_rect", watched_clip)
    monkeypatch.setattr(shapely, "STRtree", WatchedTree)
    tracemalloc.start()
    out = snap_derived(feats, [b for b in BANDS if b[0] == 14])
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert any(f.layer == "depare" for f in out)
    print(f"work: boundaries {built[0]} of {given} input vertices, fallback max {fallback[0]} of {mask_vertices},"
          f" label tree max {tree_max[0]}, clip max {clip_max[0]}, traced peak {peak / 1e6:.1f} MB")
    assert built[0] < given, (built[0], given)
    assert 0 < fallback[0] < mask_vertices / 10, (fallback[0], mask_vertices)
    assert tree_max[0] < mask_vertices / 10, (tree_max[0], mask_vertices)
    assert clip_max[0] < mask_vertices / 10, (clip_max[0], mask_vertices)
    assert peak < 300e6, peak


def _whole_overlay_labels(faces, polys, deep_units):
    """The fallback labels as 500ea9e made them, for comparison: each face overlaid with its whole originals."""
    polys = np.where(shapely.is_valid(polys), polys, shapely.make_valid(polys))
    tree = shapely.STRtree(polys)
    points = shapely.point_on_surface(faces)
    deep = shapely.distance(points, shapely.boundary(faces)) >= deep_units
    label = np.full(len(faces), -1)
    for i in range(len(faces)):
        if deep[i]:
            inside = [j for j in tree.query(points[i], predicate="within")]
            if inside:
                label[i] = min(inside)
                continue
        near = tree.query(faces[i], predicate="intersects")
        if not len(near):
            continue
        areas = shapely.area(shapely.intersection(polys[near], faces[i]))
        best = int(np.argmax(areas))
        if areas[best] > 0 and areas[best] >= shapely.area(faces[i]) - areas.sum():
            label[i] = near[best]
    return label, int(np.sum(~deep))


def test_the_pieced_fallback_gives_the_labels_of_the_whole_overlay():
    """PR 137 review: the overlap fallback sums each face's overlaps over pieces of the faces and of the originals
    (one query, large polygons split once); on a noisy mask with many faces that take the fallback, every label
    equals the one the whole overlay gives."""
    from chartpack.enc import gridsnap

    feats, _ = _big_core(n_mask=6000, grid=60, seed=2)
    polys = shapely.transform(np.array([shape(f.geometry) for f in feats], object), _units(14)[0])
    x0, y0 = _origin(14)
    faces = gridsnap._faces(polys, box(x0, y0, x0 + 65536, y0 + 65536))
    whole, took = _whole_overlay_labels(faces, polys, gridsnap._DEEP_UNITS)
    pieced = gridsnap._labels(faces, polys)
    assert took > 100 and (pieced == whole).all(), (took, int(np.sum(pieced != whole)))


def test_pieces_cover_each_polygon_exactly_and_stay_small():
    """_pieces: a 30,000-vertex noisy mask splits into pieces of at most _PIECE_VERTICES vertices whose areas add
    up to the mask's, each owned by it; the PR 130 sliver (collapses in a cut box) splits without error."""
    from chartpack.enc.gridsnap import _PIECE_VERTICES, _pieces

    feats, _ = _big_core(n_mask=30_000, grid=20, seed=3)
    mask = shapely.transform(shape(feats[0].geometry), _units(14)[0])
    sliver = shapely.transform(shapely.from_wkt(_SLIVER), _units(14)[0])
    pieces, owner = _pieces(np.array([mask, sliver], object))
    assert (shapely.get_num_coordinates(pieces[owner == 0]) <= _PIECE_VERTICES).all()
    assert math.isclose(shapely.area(pieces[owner == 0]).sum(), mask.area, rel_tol=1e-9)
    assert math.isclose(shapely.area(pieces[owner == 1]).sum(), sliver.area, rel_tol=1e-6)