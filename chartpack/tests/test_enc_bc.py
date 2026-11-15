import json
import math
import shutil

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.affinity import translate

from chartpack.enc.bc import (
    DERIVED_SRC,
    JDF_STRIP_BOX,
    NOTICE_CELLS,
    SEGMENT_DEG,
    BcError,
    apply_rules,
    area_km2,
    check_canadian_areas,
    check_notices,
    chs_notice_areas,
    load_canada,
)
from chartpack.enc.reader import Feature

# The bc-offshore-south outline of the plan 8 spec appendix.
OFFSHORE_SOUTH = [(-132.864, 51.0), (-129.2, 51.0), (-129.184, 50.85), (-128.6, 50.85), (-128.595, 49.407),
                  (-126.6, 49.4), (-126.6, 48.45), (-128.302, 48.45), (-129.469, 49.135), (-130.024, 49.683),
                  (-132.44, 50.756), (-132.864, 51.0)]


def _committed(regions_dir):
    return json.loads((regions_dir / "clip" / "canada-chs.geojson").read_text())


def _shape(path):
    data = json.loads(path.read_text())
    return shape(data.get("geometry", data))


def test_chs_notice_found_by_dfo_text_only():
    notice = box(-123.4, 48.5, -123.2, 48.7)
    general = box(-124.0, 48.0, -123.0, 48.4)
    source = box(-125.0, 48.0, -124.5, 48.4)
    notes = [
        (notice, "(c) Fisheries and Oceans Canada 2024. Published by the Canadian Hydrographic Service. A licence"
                 " is required from the Canadian Hydrographic Service (www.charts.gc.ca) to reproduce or distribute"
                 " this work."),
        (general, "COPYRIGHT\r\nHowever, this product contains Canadian Hydrographic Service copyrighted works, and"
                  " is published with the authorization of the Canadian Hydrographic Service."),
        (source, "AUTHORITIES\r\nHydrography and topography by the National Ocean Service, with additional data"
                 " from the Canadian Hydrographic Service."),
        (box(-122.0, 48.0, -121.5, 48.4), None),
    ]
    assert chs_notice_areas(notes).equals(notice)
    assert chs_notice_areas(notes[1:]).is_empty


def test_canada_chs_file_is_valid_and_lists_cells(regions_dir):
    data = _committed(regions_dir)
    assert data["type"] == "Feature" and data["properties"]["name"] == "canada-chs"
    geometry = shape(data["geometry"])
    assert geometry.is_valid and not geometry.is_empty
    cells = {c["cell"]: c for c in data["properties"]["cells"]}
    assert {"US1GLBDD", "US1GLBDC", *NOTICE_CELLS} <= set(cells)
    assert {name for name, c in cells.items() if c["notice"]} == set(NOTICE_CELLS)
    for c in cells.values():
        assert c["band"] == int(c["cell"][2])
        assert isinstance(c["edition"], int) and isinstance(c["update"], int)
        assert len(c["issued"]) == 10 and c["issued"][4] == "-"


def test_canada_chs_covers_west_of_134_4(regions_dir):
    polygon = shape(_committed(regions_dir)["geometry"])
    assert polygon.contains(Point(-135.0, 53.5))
    assert polygon.contains(Polygon(OFFSHORE_SOUTH))


def test_jdf_strip_is_inside_polygon(regions_dir):
    polygon = shape(_committed(regions_dir)["geometry"])
    wa = _shape(regions_dir / "clip" / "canada-wa.geojson")
    assert 35.0 <= area_km2(polygon.difference(wa).intersection(box(*JDF_STRIP_BOX))) <= 45.0


def test_canada_chs_agrees_with_canada_wa(regions_dir):
    """load_canada passes the border comparison and gives the committed polygon with edges no longer than
    SEGMENT_DEG (the committed file is not densified)."""
    committed = shape(_committed(regions_dir)["geometry"])
    canada = load_canada(regions_dir)
    assert canada.equals(shapely.segmentize(committed, SEGMENT_DEG))
    assert canada.symmetric_difference(committed).area < 1e-12
    xy = shapely.get_coordinates(canada.exterior)
    assert np.hypot(*np.diff(xy, axis=0).T).max() <= SEGMENT_DEG + 1e-12
    assert np.hypot(*np.diff(shapely.get_coordinates(committed.exterior), axis=0).T).max() > SEGMENT_DEG


def test_border_disagreement_fails(regions_dir, tmp_path):
    shutil.copytree(regions_dir / "clip", tmp_path / "clip")
    path = tmp_path / "clip" / "canada-wa.geojson"
    data = json.loads(path.read_text())
    shifted = translate(shape(data["geometry"]), xoff=50 / (111320 * math.cos(math.radians(48.5))), yoff=50 / 111320)
    data["geometry"] = shifted.__geo_interface__
    path.write_text(json.dumps(data))
    with pytest.raises(BcError, match="wider than 20 m"):
        load_canada(tmp_path)


# ---- Task 11: the guards (spec 7.2)

CHS_TEXT = "(c) Fisheries and Oceans Canada 2024. Published by the Canadian Hydrographic Service."
CANADA = box(-123.0, 49.0, -122.0, 50.0)  # a stand-in Canada polygon for the guard and rule tests
_M_LON = 1 / (111320 * math.cos(math.radians(49.5)))  # degrees of longitude per meter at 49.5 N


def test_listed_cell_without_notice_fails_build():
    with pytest.raises(BcError, match=NOTICE_CELLS[0]):
        check_notices([(NOTICE_CELLS[0], [(box(-122.8, 49.2, -122.6, 49.4), "general notes")])], CANADA)
    check_notices([("US4WA1HK", [(box(-122.8, 49.2, -122.6, 49.4), "general notes")])], CANADA)


def test_missing_notice_text_file_fails_build():
    with pytest.raises(BcError, match="US4WA1HK"):
        check_notices([("US4WA1HK", [(box(-122.8, 49.2, -122.6, 49.4), None)])], CANADA)


@pytest.mark.parametrize("outside_m, fails", [(100.0, True), (10.0, False)])
def test_chs_notice_outside_polygon_fails_build(outside_m, fails):
    """A notice area whose farthest point lies outside_m east of the polygon: over BORDER_TOLERANCE_M fails naming
    the cell."""
    area = box(-122.5, 49.4, -122.0 + outside_m * _M_LON, 49.6)
    cells = [("US4WA1HK", []), (NOTICE_CELLS[2], [(area, CHS_TEXT)])]
    if fails:
        with pytest.raises(BcError, match=NOTICE_CELLS[2]):
            check_notices(cells, CANADA)
    else:
        check_notices(cells, CANADA)


def test_canadian_area_outside_polygon_fails_build():
    """A band 1 cell labels water 5 km past the polygon Canadian (like the water west of 134.4 W that US1GLBDC
    labels Canadian): BcError naming the cell and the area; the same area inside a loaded notice cell's coverage
    passes, and so does an area outside the owned tiles."""
    owned = box(-123.5, 49.0, -122.5, 50.0)
    canadian = box(-123.0 - 5000 * _M_LON, 49.2, -122.8, 49.4)
    band1 = ("US1GLBDC", 1, canadian, box(-140, 40, -110, 60))
    with pytest.raises(BcError, match=r"US1GLBDC.* km2"):
        check_canadian_areas([band1], CANADA, owned)
    notice = (NOTICE_CELLS[2], 3, Polygon(), box(-124, 49.0, -122.9, 49.5))
    check_canadian_areas([band1, notice], CANADA, owned)
    with pytest.raises(BcError, match="US4AAAAA"):  # band 4 and 5 cells: no notice-cell exemption
        check_canadian_areas([("US4AAAAA", 4, canadian, owned), notice], CANADA, owned)
    check_canadian_areas([band1], CANADA, box(-122.8, 49.0, -122.5, 50.0))
    check_canadian_areas([("US3AAAAA", 3, canadian, owned)], CANADA, owned)  # band 3 is not checked


# ---- Task 11: the rules (spec 7.2)

def _f(layer, geom, band=None, **props):
    """A feature as the quilt gives it (cell and band from a NOAA cell) or, with src, a derived one."""
    base = {"tippecanoe": {"minzoom": 10, "maxzoom": 16}}
    if band is not None:
        base.update(cell=f"US{band}AAAAA", band=band)
    return Feature(layer, mapping(geom), {**base, **props})


def _geoms(features, layer, **match):
    return [shape(f.geometry) for f in features
            if f.layer == layer and all(f.props.get(k) == v for k, v in match.items())]


STRADDLE = box(-122.5, 49.4, -121.5, 49.6)  # across the polygon's east edge at -122.0
INSIDE_PT, OUTSIDE_PT = Point(-122.4, 49.5), Point(-121.6, 49.5)


@pytest.mark.parametrize("band", [1, 2, 3, 4, 5])
def test_noaa_cut_at_polygon_every_band(band):
    cut = [_f("depare", STRADDLE, band, DRVAL1="0", DRVAL2="5"),
           _f("coalne", LineString([(-122.5, 49.5), (-121.5, 49.5)]), band)]
    for layer in ("light", "navaid", "soundg"):
        cut += [_f(layer, INSIDE_PT, band, OBJNAM="in"), _f(layer, OUTSIDE_PT, band, OBJNAM="out")]
    out = apply_rules(cut, [], CANADA)
    assert shapely.union_all(_geoms(out, "depare")).equals(box(-122.0, 49.4, -121.5, 49.6))
    assert shapely.union_all(_geoms(out, "coalne")).equals(LineString([(-122.0, 49.5), (-121.5, 49.5)]))
    for layer in ("light", "navaid", "soundg"):
        assert [f.props["OBJNAM"] for f in out if f.layer == layer] == ["out"], layer
    assert all(f.props["band"] == band for f in out)


def test_usgs_seabed_cut_at_polygon():
    seabed = [_f("seabed", INSIDE_PT, src="usseabed", folk="S"), _f("seabed", OUTSIDE_PT, src="usseabed", folk="M"),
              _f("seabed", STRADDLE, src="usgs-cmecs", substrate="Sand"), _f("seabed", INSIDE_PT, src="enc")]
    out = apply_rules(seabed, [], CANADA)
    assert [f.props.get("folk") for f in out if f.geometry["type"] == "Point"] == ["M"]
    assert shapely.union_all(_geoms(out, "seabed", src="usgs-cmecs")).equals(box(-122.0, 49.4, -121.5, 49.6))


def test_us_side_untouched():
    """Features wholly outside the polygon come out as they went in, props and geometry."""
    cut = [_f("depare", box(-121.8, 49.1, -121.2, 49.9), 4, DRVAL1="0", DRVAL2="5"),
           _f("hazard", OUTSIDE_PT, 5, VALSOU="1.2"), _f("line", LineString([(-121.9, 49.0), (-121.1, 49.9)]), 3)]
    assert apply_rules(cut, [], CANADA) == cut


def test_alaskan_water_keeps_noaa_depth_and_land():
    """Outside the polygon in a BC-owned tile: NOAA depare and lndare kept; no derived depare and no nosurvey
    under either; a derived depare where no NOAA area lies kept; derived features inside the polygon kept."""
    noaa_water, noaa_land = box(-121.9, 49.0, -121.6, 49.5), box(-121.6, 49.0, -121.4, 49.5)
    cut = [_f("depare", noaa_water, 4, DRVAL1="0", DRVAL2="5"), _f("lndare", noaa_land, 4)]
    tile = box(-122.5, 49.0, -121.0, 50.0)  # the BC-owned tile: the polygon's east part and Alaskan water
    derived = [_f("depare", tile, src="nonna100", DRVAL1="5", DRVAL2="10"), _f("nosurvey", tile),
               _f("depcnt", LineString([(-122.5, 49.2), (-121.0, 49.2)]), src="nonna100", VALDCO="5"),
               _f("soundg", Point(-121.7, 49.2), src="nonna100", depth="4.1"),
               _f("soundg", Point(-121.2, 49.2), src="nonna100", depth="4.2")]
    out = apply_rules(cut, derived, CANADA)
    assert _geoms(out, "depare", cell="US4AAAAA") == [noaa_water] and _geoms(out, "lndare") == [noaa_land]
    noaa = noaa_water.union(noaa_land)
    for layer in ("depare", "nosurvey"):
        geom = shapely.union_all(_geoms(out, layer, src="nonna100" if layer == "depare" else None))
        assert geom.intersection(noaa).area < 1e-12, layer
        assert geom.equals(tile.difference(noaa)) or geom.symmetric_difference(tile.difference(noaa)).area < 1e-12
    line = shapely.union_all(_geoms(out, "depcnt"))
    assert line.length == pytest.approx(1.5 - 0.5) and not line.intersection(noaa).length
    assert [f.props["depth"] for f in out if f.layer == "soundg"] == ["4.2"]


def test_derived_land_only_inside_polygon():
    land = box(-122.2, 49.2, -121.8, 49.4)  # across the east edge
    derived = [_f("lndare", land, src="fwa"), _f("coalne", land.exterior, src="fwa")]
    out = apply_rules([], derived, CANADA)
    assert shapely.union_all(_geoms(out, "lndare")).equals(box(-122.2, 49.2, -122.0, 49.4))
    assert CANADA.covers(shapely.union_all(_geoms(out, "coalne")))
    assert {f.props["src"] for f in out} == {"fwa"}


def test_derived_src_names():
    assert DERIVED_SRC == ("nonna10", "nonna100", "crm", "etopo", "fwa")


# ---- plan8-checkfix F2: NOAA slivers left along the polygon by the cut (Ruling 41)

def _sliver_fixture(fixtures_dir):
    """The real NOAA features behind the overview's Canada-rule errors (canada-slivers.json, see the README)."""
    rows = json.loads((fixtures_dir / "canada-slivers.json").read_text())
    return [Feature(r["layer"], mapping(shapely.from_wkt(r["wkt"])), r["props"]) for r in rows]


def test_real_slivers_along_the_polygon_are_dropped(fixtures_dir, regions_dir):
    """M_QUAL CATZOC 6 and MIPARE WA of US3WA1EF and CTNARE of US1GLBDD: the cut leaves a part 1 to 6 m wide
    along the polygon (the cells' own edges lie a meter or so outside it), which tippecanoe draws as a square
    straddling the edge. Dropped: every part of them lies within BORDER_TOLERANCE_M of the polygon. Of the other
    features of the fixture, M_QUAL CATZOC 3 (outside the polygon) comes out unchanged and the unnamed MIPARE
    (inside it) is cut away as before."""
    from chartpack.enc.bc import BORDER_TOLERANCE_M, to_m

    canada = load_canada(regions_dir)
    feats = _sliver_fixture(fixtures_dir)
    out = apply_rules(feats, [], canada)
    kept = {(f.props["class"], f.props.get("CATZOC"), f.props.get("OBJNAM")) for f in out}
    assert kept == {("M_QUAL", 3, None)}
    assert out == [f for f in feats if f.props.get("CATZOC") == 3]
    slivers = [f for f in feats if f.props.get("CATZOC") == 6 or f.props.get("OBJNAM") == "WA"
               or f.props["class"] == "CTNARE"]
    assert len(slivers) == 3
    for f in slivers:  # each is cut to one thin part, under BORDER_TOLERANCE_M wide, before it is dropped
        part = to_m(shape(f.geometry).difference(canada))
        assert 0 < 2 * part.area / part.length < BORDER_TOLERANCE_M / 2


@pytest.mark.parametrize("layer", ["depare", "lndare", "coalne", "hazard"])
def test_safety_slivers_wider_than_a_meter_are_kept(fixtures_dir, regions_dir, layer):
    """The same CATZOC 6 sliver as a safety layer's area (or its outline as a line), cut: its parts lie up to
    6 m from the polygon, more than SAFETY_BORDER_M, so it is kept (plan8-bordersliver drops only the parts
    wholly within SAFETY_BORDER_M)."""
    canada = load_canada(regions_dir)
    sliver = next(f for f in _sliver_fixture(fixtures_dir) if f.props.get("CATZOC") == 6)
    geom = shape(sliver.geometry)
    feat = Feature(layer, mapping(geom.exterior if layer == "coalne" else geom), {"cell": "US3WA1EF", "band": 3})
    assert apply_rules([feat], [], canada)


# ---- plan8-bordersliver: needles of NOAA safety layers along the polygon

def test_real_depare_needles_along_the_polygon_are_dropped(fixtures_dir, regions_dir):
    """US4WA1IE edition 1.0 DEPARE 164.5 to 182.8 near -123.93, 48.28 (border-sliver.json, see the README): row 0
    is the cell's depare along the polygon, whose border vertices lie up to 0.13 m from the polygon's, so the cut
    leaves needle parts all within a meter of its edge; row 1 is the US-side depth area next to them. The needles
    are dropped, the depth area comes back whole (its part outside the polygon), and nothing else."""
    from chartpack.enc.bc import SAFETY_BORDER_M, to_m

    canada = load_canada(regions_dir)
    feats = _border_slivers(fixtures_dir)
    uncut = shape(feats[0].geometry).difference(canada)
    assert not uncut.is_empty and to_m(uncut).area < 100  # the zigzag: what the cut leaves is only needles
    out = apply_rules(feats, [], canada)
    assert len(out) == 1
    kept = shape(out[0].geometry)  # the whole 1.0 km2 part, up to the cut's own rounding (1e-7 m2)
    assert to_m(kept.symmetric_difference(shape(feats[1].geometry).difference(canada))).area < 1e-3
    assert to_m(kept).area == pytest.approx(1_001_337, abs=1)
    assert SAFETY_BORDER_M == 1.0


def test_thin_triangle_that_projects_to_a_self_intersection_is_dropped(fixtures_dir, regions_dir):
    """US3WA1EF 1.5 DEPARE 36.5 to 54.8 as the north-sound quilt leaves it near -123.14, 48.39 (thin-triangle.json,
    see the README): a valid lon/lat polygon of 5 vertices, a thin triangle 2.7 km long along the Canada
    polygon. The cut leaves a needle of it outside the polygon that is self-intersecting once densified and
    projected to meters. The needle is dropped, and apply_rules no longer fails with a GEOS TopologyException."""
    canada = load_canada(regions_dir)
    row = json.loads((fixtures_dir / "thin-triangle.json").read_text())[0]
    geom = shapely.from_wkt(row["wkt"])
    assert geom.is_valid
    assert apply_rules([Feature(row["layer"], mapping(geom), row["props"])], [], canada) == []


def test_invalid_projected_part_reaching_past_the_margin_is_not_a_sliver(fixtures_dir, regions_dir):
    """The needle of thin-triangle.json plus a real 0.0003 degree square 44 m off the polygon: invalid once
    projected, so make_valid runs, and it must keep the square (the part is not wholly within 1 m). A make_valid
    step that dropped every invalid part would read it as a sliver and drop real NOAA content (PR 142 review)."""
    from chartpack.enc.bc import _sliver, to_m

    canada = load_canada(regions_dir)
    geom = shapely.from_wkt(json.loads((fixtures_dir / "thin-triangle.json").read_text())[0]["wkt"])
    w, s, e, n = geom.bounds
    needle = geom.difference(canada.intersection(box(w - 1e-6, s - 1e-6, e + 1e-6, n + 1e-6)))
    x, y = needle.representative_point().coords[0]
    square = box(x + 0.001, y, x + 0.0013, y + 0.0003)
    assert not canada.intersects(square) and to_m(square).distance(to_m(canada)) > 40
    both = shapely.MultiPolygon([needle, square])
    assert not to_m(shapely.segmentize(both, 0.01)).is_valid
    assert _sliver(needle, canada, 1.0)
    assert not _sliver(both, canada, 1.0)


def test_valid_keeps_a_valid_part_and_both_lobes_of_a_bowtie():
    """_valid (shared by _outside_m and load_canada's comparison) returns a valid part as it is and keeps both lobes
    of an invalid one. The existing test_border_disagreement_fails covers load_canada's guard still raising."""
    from chartpack.enc.bc import _valid

    square = box(0, 0, 10, 10)
    assert _valid(square) is square
    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert not bowtie.is_valid
    fixed = _valid(bowtie)
    assert fixed.is_valid and fixed.area == pytest.approx(50)


def _border_slivers(fixtures_dir):
    rows = json.loads((fixtures_dir / "border-sliver.json").read_text())
    return [Feature(r["layer"], mapping(shapely.from_wkt(r["wkt"])), r["props"]) for r in rows]


@pytest.mark.parametrize("layer", ["depare", "lndare", "hazard", "coalne"])
def test_safety_part_two_meters_from_the_edge_is_kept_whole(layer):
    """A NOAA safety part reaching 2 m from the polygon's east edge (-122.0) is kept whole, narrow end and all."""
    wide = 2.0 * _M_LON
    geom = Polygon([(-122.5, 49.4), (-122.0, 49.4), (-122.0 + wide, 49.5), (-122.0, 49.6), (-122.5, 49.6)])
    line = LineString([(-122.5, 49.5), (-122.0 + wide, 49.5)])
    feat = _f(layer, line if layer == "coalne" else geom, 4, DRVAL1="0")
    out = apply_rules([feat], [], CANADA)
    assert len(out) == 1
    assert shapely.union_all(_geoms(out, layer)).equals(
        (line if layer == "coalne" else geom).difference(CANADA))
    assert shapely.union_all(_geoms(out, layer)).bounds[2] == pytest.approx(-122.0 + wide)


@pytest.mark.parametrize("layer", ["depare", "coalne"])
def test_safety_part_within_a_meter_is_dropped(layer):
    """The same shape reaching only 0.5 m past the edge is dropped (a zero-width contour part too)."""
    wide = 0.5 * _M_LON
    geom = Polygon([(-122.5, 49.4), (-122.0, 49.4), (-122.0 + wide, 49.5), (-122.0, 49.6), (-122.5, 49.6)])
    line = LineString([(-122.5, 49.5), (-122.0 + wide, 49.5)])
    feat = _f(layer, line if layer == "coalne" else geom, 4)
    assert apply_rules([feat], [], CANADA) == []


def test_derived_feature_near_the_edge_is_untouched():
    """Derived features (the second argument) are not thinned: a derived depare reaching 0.5 m past the polygon
    edge, a needle by the rule, is cut as before (the part outside the polygon is kept) and not dropped."""
    wide = 0.5 * _M_LON
    geom = Polygon([(-122.5, 49.4), (-122.0, 49.4), (-122.0 + wide, 49.5), (-122.0, 49.6), (-122.5, 49.6)])
    inside = _f("depare", geom, src="nonna100", DRVAL1="0")
    out = apply_rules([], [inside], CANADA)
    assert out == [inside]


def test_wide_part_along_the_polygon_is_kept():
    """A NOAA area cut at the polygon's east edge (-122.0) whose kept part is 50 m wide: more than
    BORDER_TOLERANCE_M from the polygon in places, so kept; a 10 m wide one is dropped."""
    for width_m, kept in ((50.0, True), (10.0, False)):
        area = box(-122.5, 49.4, -122.0 + width_m * _M_LON, 49.6)
        out = apply_rules([_f("area", area, 3, OBJNAM="a")], [], CANADA)
        assert bool(out) == kept, width_m
