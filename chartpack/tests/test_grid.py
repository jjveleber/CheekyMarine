import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon, box, mapping, shape

from chartpack.bathy.blocks import BLOCK_MARGIN_DEG
from chartpack.grid import (
    GRID_ZOOM,
    assign,
    canada_side,
    content_tiles,
    fetch_extent,
    keep_tiles,
    load_grid,
    offshore_shore_tiles,
    owned_tiles,
    tile_bounds,
    tiles_area,
    tiles_meeting,
    tiles_meeting_area,
)
from chartpack.mbtiles import MBTiles
from chartpack.region import Region, RegionError, load_region

from tilemath import tile_of


def _region(name, bbox, overview=False, clip=None, charts_kind="enc", area=None):
    return Region(name=name, charts_version="0.1.0", bathy_version="0.1.0", bbox=bbox, cells={}, bathy_sources=[],
                  coarse_fallback="crm", clip=clip, dem_maxzoom=14, datum_file=Path("x.toml"), views=[], overview=overview,
                  charts_kind=charts_kind, area=area)


def _clip_file(tmp_path, geom):
    """A clip GeoJSON Feature, as in regions/clip/canada-wa.geojson."""
    path = tmp_path / "clip.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(geom)}))
    return path


def test_tile_bounds_round_trip():
    w, s, e, n = tile_bounds(10, 163, 356)
    assert w < -122.4 < e and s < 47.9 < n
    assert tiles_meeting((-122.4001, 47.8999, -122.3999, 47.9001)) == {(163, 356)}


def test_edge_touch_does_not_count():
    w, s, e, n = tile_bounds(10, 163, 356)
    assert tiles_meeting((w, s, e, n)) == {(163, 356)}


def test_shared_edge_has_one_owner():
    seam = tile_bounds(10, 163, 356)[1]  # a zoom-10 tile line
    a = _region("a", (-123.0, 47.0, -122.0, seam))
    b = _region("b", (-123.0, seam, -122.0, 48.0))
    owner = assign([a, b], ["a", "b"])
    assert set(owner) == tiles_meeting(a.bbox) | tiles_meeting(b.bbox)
    assert set(owner) == tiles_meeting((-123.0, 47.0, -122.0, 48.0))
    assert tiles_meeting(a.bbox).isdisjoint(tiles_meeting(b.bbox))
    assert {owner[t] for t in tiles_meeting(a.bbox)} == {"a"} and {owner[t] for t in tiles_meeting(b.bbox)} == {"b"}


def test_overlap_goes_to_first_in_order():
    a = _region("a", (-123.0, 47.0, -122.0, 47.6))
    b = _region("b", (-123.0, 47.4, -122.0, 48.0))
    overlap = tiles_meeting(a.bbox) & tiles_meeting(b.bbox)
    assert overlap
    assert {assign([a, b], ["a", "b"])[t] for t in overlap} == {"a"}
    assert {assign([a, b], ["b", "a"])[t] for t in overlap} == {"b"}


def test_overview_and_unlisted_regions():
    a, ov = _region("a", (-123.0, 47.0, -122.0, 47.6)), _region("ov", (-130.0, 40.0, -120.0, 50.0), overview=True)
    assert set(assign([a, ov], ["a"])) == tiles_meeting(a.bbox)
    with pytest.raises(RegionError, match="not in the grid order"):
        assign([a], [])
    with pytest.raises(RegionError, match="were not given"):
        assign([a], ["a", "b"])


def test_tile_inside_own_clip_is_not_taken(tmp_path):
    """A region with a clip does not take a tile wholly inside it; with no later region the tile has no owner."""
    tile = (163, 356)
    clip = _clip_file(tmp_path, box(*tile_bounds(GRID_ZOOM, *tile)).buffer(0.001))
    a = _region("a", (-123.0, 47.0, -122.0, 48.0), clip=clip)
    owner = assign([a], ["a"])
    assert tile not in owner and tiles_meeting(a.bbox) - {tile} == set(owner)


def test_tile_partly_inside_clip_is_owned(tmp_path):
    tile = (163, 356)
    w, s, e, n = tile_bounds(GRID_ZOOM, *tile)
    clip = _clip_file(tmp_path, box(w, s, (w + e) / 2, n))
    assert assign([_region("a", (-123.0, 47.0, -122.0, 48.0), clip=clip)], ["a"])[tile] == "a"


def test_tile_inside_clip_is_owned(tmp_path):
    """A BC box wholly inside a clip polygon keeps its tiles: the clip only stops the region that carries it,
    and no tile is dropped."""
    tile = (163, 356)
    inside = box(*tile_bounds(GRID_ZOOM, *tile)).buffer(0.001)
    us = _region("us", (-123.0, 47.0, -122.0, 48.0), clip=_clip_file(tmp_path, inside))
    w, s, e, n = tile_bounds(GRID_ZOOM, *tile)
    bc = _region("bc", (w, s, e, n), charts_kind="derived-inshore")
    assert assign([bc], ["bc"]) == {tile: "bc"}
    owner = assign([us, bc], ["us", "bc"])
    assert owner[tile] == "bc"
    assert set(owner) == tiles_meeting(us.bbox)
    assert {owner[t] for t in tiles_meeting(us.bbox) - {tile}} == {"us"}


def test_offshore_before_inshore_raises_in_assign():
    a = _region("in", (-123.0, 47.0, -122.0, 47.6), charts_kind="derived-inshore")
    b = _region("off", (-124.0, 47.0, -123.0, 47.6), charts_kind="derived-offshore")
    assert set(assign([a, b], ["in", "off"]).values()) == {"in", "off"}
    with pytest.raises(RegionError, match="off.*before.*in"):
        assign([a, b], ["off", "in"])


OFFSHORE_SOUTH = [[[-132.864, 51.0], [-129.2, 51.0], [-129.184, 50.85], [-128.6, 50.85], [-128.595, 49.407],
                   [-126.6, 49.4], [-126.6, 48.45], [-128.302, 48.45], [-129.469, 49.135], [-130.024, 49.683],
                   [-132.44, 50.756], [-132.864, 51.0]]]  # spec appendix


def test_polygon_area_tiles():
    area = Polygon(OFFSHORE_SOUTH[0])
    tiles = tiles_meeting_area(area)
    assert tile_of(GRID_ZOOM, -128.0, 48.0) not in tiles  # in the bounds, south of the ring
    assert tile_of(GRID_ZOOM, -130.0, 50.0) in tiles
    assert tile_of(GRID_ZOOM, -132.5, 49.0) not in tiles  # in the bounds, west of the ring's southwest edge
    assert tiles < tiles_meeting(area.bounds)
    for t in tiles:
        assert area.intersection(box(*tile_bounds(GRID_ZOOM, *t))).area > 0, t


def test_polygon_area_edge_touch_does_not_count():
    w, s, e, n = tile_bounds(GRID_ZOOM, 163, 356)
    assert tiles_meeting_area(box(w, s, e, n)) == {(163, 356)}


def test_assign_uses_the_area_not_the_box():
    area = Polygon(OFFSHORE_SOUTH[0])
    off = _region("off", area.bounds, charts_kind="derived-offshore", area=area)
    assert set(assign([off], ["off"])) == tiles_meeting_area(area)


def test_offshore_owning_shore_tile_is_reported():
    regions = {"in": _region("in", (0, 0, 1, 1), charts_kind="derived-inshore"),
               "off": _region("off", (0, 0, 1, 1), charts_kind="derived-offshore"),
               "us": _region("us", (0, 0, 1, 1))}
    owner = {(1, 1): "in", (2, 1): "off", (3, 1): "off", (4, 1): "us"}
    assert offshore_shore_tiles(owner, regions, {(1, 1), (3, 1), (4, 1)}) == {(3, 1)}
    assert offshore_shore_tiles(owner, regions, {(1, 1), (4, 1)}) == set()


def test_canada_side_whole_for_bc_owner_cut_for_us_owner():
    tile = (163, 356)
    w, s, e, n = tile_bounds(GRID_ZOOM, *tile)
    clip = box(w, (s + n) / 2, e + 1.0, n + 1.0)  # the north half of the tile is Canadian
    for kind in ("derived-inshore", "derived-offshore"):
        assert canada_side(clip, tile, _region("bc", (w, s, e, n), charts_kind=kind)).equals(box(w, s, e, n))
    assert canada_side(clip, tile, _region("us", (w, s, e, n))).equals(box(w, (s + n) / 2, e, n))


def _mbtiles(path, rows):
    with MBTiles.create(path, fmt="pbf") as m:
        for z, x, y in rows:
            m.put_tile(z, x, y, b"t")
    return path


def _left(path):
    """({(z, x, y)} of the XYZ tiles left, metadata)"""
    with MBTiles.open(path) as m:
        return {(z, x, y) for z in range(0, 17) for x, y, _ in m.tiles_at(z)}, m.metadata()


def test_keep_tiles_prunes_unowned_and_out_of_range(tmp_path):
    rows = [(9, 81, 178), (10, 163, 356), (10, 164, 356), (12, 652, 1424), (12, 656, 1424)]
    path = _mbtiles(tmp_path / "a.mbtiles", rows)
    keep_tiles(path, {(163, 356)}, minzoom=10, maxzoom=16)
    left, md = _left(path)
    assert left == {(10, 163, 356), (12, 652, 1424)}
    assert md["minzoom"] == "10" and md["maxzoom"] == "16"
    assert json.loads(md["cheekymarine:owned"]) == [[163, 356]]
    w, s, e, n = tile_bounds(10, 163, 356)
    assert md["bounds"] == f"{w},{s},{e},{n}"


def test_keep_tiles_uses_xyz_rows(tmp_path):
    # z10 y=356 is stored as TMS row 667; its z11 children are y=712,713 (TMS 1335, 1334).
    path = _mbtiles(tmp_path / "a.mbtiles", [(11, 326, 712), (11, 326, 713), (11, 326, 711), (11, 326, 714)])
    keep_tiles(path, {(163, 356)}, minzoom=10, maxzoom=16)
    left, _ = _left(path)
    assert left == {(11, 326, 712), (11, 326, 713)}


def test_overview_keeps_only_low_zooms(tmp_path):
    rows = [(5, 1, 1), (6, 10, 20), (9, 81, 178), (10, 163, 356), (12, 652, 1424)]
    path = _mbtiles(tmp_path / "a.mbtiles", rows)
    keep_tiles(path, None, minzoom=6, maxzoom=9)
    left, md = _left(path)
    assert left == {(6, 10, 20), (9, 81, 178)}
    assert md["cheekymarine:owned"] == "null" and md["minzoom"] == "6" and md["maxzoom"] == "9"



def test_overview_records_content_tiles(tmp_path):
    path = _mbtiles(tmp_path / "a.mbtiles", [(9, 81, 178)])
    keep_tiles(path, None, minzoom=6, maxzoom=9, content={(164, 356), (163, 356)})
    _, md = _left(path)
    assert md["cheekymarine:owned"] == "null"
    assert json.loads(md["cheekymarine:content"]) == [[163, 356], [164, 356]]


def test_overview_with_no_content_tiles_fails(tmp_path):
    """An empty content area would let the pack check compare nothing and pass."""
    path = _mbtiles(tmp_path / "a.mbtiles", [(9, 81, 178)])
    with pytest.raises(RegionError, match="content"):
        keep_tiles(path, None, minzoom=6, maxzoom=9, content=set())


def test_region_pack_has_no_content_key(tmp_path):
    path = _mbtiles(tmp_path / "a.mbtiles", [(10, 163, 356)])
    keep_tiles(path, {(163, 356)}, minzoom=10, maxzoom=16)
    _, md = _left(path)
    assert "cheekymarine:content" not in md

WAVE1 = {
    "sound-south": (-123.25, 46.95, -122.1, 47.45),
    "sound-central": (-123.25, 47.45, -122.1, 48.2),
    "north-sound": (-123.35, 48.2, -122.25, 49.05),
    "strait": (-124.8, 47.95, -123.25, 48.6),
    "wa-coast": (-127.0, 46.15, -123.3984375, 48.6),
}


def test_wave1_order_puts_narrows_south():
    order = list(WAVE1)
    owner = assign([_region(n, b) for n, b in WAVE1.items()], order)
    assert owner[tile_of(10, -122.55, 47.27)] == "sound-south"
    assert owner[tile_of(10, -122.34, 47.60)] == "sound-central"


def _wave1_files(regions_dir):
    return [load_region(regions_dir / f"{name}.toml") for name in WAVE1]


def _fixture_owners(fixtures_dir):
    return {(x, y): name for x, y, name in json.loads((fixtures_dir / "wave1-owners.json").read_text())}


def test_wave1_owners_exact(regions_dir, fixtures_dir):
    """The wave 1 owner map is the one written from the plan 7 code (tests/fixtures/README.md): no tile gained,
    none lost, none moved."""
    assert assign(_wave1_files(regions_dir), load_grid(regions_dir / "grid.toml")) == _fixture_owners(fixtures_dir)


def test_wholly_canadian_tile_in_us_box_goes_to_bc(regions_dir, fixtures_dir):
    """A tile inside a US box whose water is only Canadian (wholly inside the clip) goes to the BC region listed
    later; a tile holding US and Canadian water stays with its US pack; no wave 1 tile changes owner.
    The Victoria tile (-123.37, 48.42) is about half US water (the Strait south of the border), so it is the
    shared case; Saanich Inlet's tile, inside the strait box, is wholly Canadian."""
    bc = _region("bc-south-georgia", (-123.95, 48.3, -122.2, 49.6), charts_kind="derived-inshore")
    owner = assign(_wave1_files(regions_dir) + [bc], load_grid(regions_dir / "grid.toml") + [bc.name])
    clip = shape(json.loads((regions_dir / "clip/canada-wa.geojson").read_text())["geometry"])
    saanich = tile_of(GRID_ZOOM, -123.50, 48.55)
    assert saanich in tiles_meeting(WAVE1["strait"]) and clip.contains(box(*tile_bounds(GRID_ZOOM, *saanich)))
    assert owner[saanich] == "bc-south-georgia"
    victoria = tile_of(GRID_ZOOM, -123.37, 48.42)
    v = box(*tile_bounds(GRID_ZOOM, *victoria))
    assert 0 < v.intersection(clip).area < v.area  # US and Canadian water
    assert owner[victoria] == "north-sound"
    assert owner[tile_of(GRID_ZOOM, -123.01, 48.54)] == "north-sound"  # Friday Harbor
    wave1 = _fixture_owners(fixtures_dir)
    assert saanich not in wave1
    assert {t: owner[t] for t in wave1} == wave1


def test_fetch_extent_covers_owned_tiles_plus_margin(regions_dir):
    """A region in the grid: its content tiles' bounds grown by the block margin, so it holds every owned tile
    grown by that margin. A region not in the grid: its bbox grown by the same margin."""
    r = load_region(regions_dir / "north-sound.toml")
    w, s, e, n = tiles_area(content_tiles(r, regions_dir)).bounds
    m = BLOCK_MARGIN_DEG
    extent = fetch_extent(r, regions_dir)
    assert extent == pytest.approx((w - m, s - m, e + m, n + m), abs=1e-12)
    assert extent[0] < r.bbox[0] - m  # the owned tiles reach past the box
    for tile in owned_tiles(r, regions_dir):
        tw, ts, te, tn = tile_bounds(GRID_ZOOM, *tile)
        assert extent[0] <= tw - m and extent[1] <= ts - m and te + m <= extent[2] and tn + m <= extent[3]
    toba = load_region(regions_dir / "test-toba.toml")
    tw, ts, te, tn = toba.bbox
    assert fetch_extent(toba, regions_dir) == pytest.approx((tw - m, ts - m, te + m, tn + m), abs=1e-12)


def test_grid_zoom_must_be_10(tmp_path):
    (tmp_path / "grid.toml").write_text('zoom = 11\norder = ["a"]\n')
    with pytest.raises(RegionError, match="zoom"):
        load_grid(tmp_path / "grid.toml")


def test_shipped_grid_is_wave1():
    assert load_grid(Path(__file__).resolve().parent.parent / "regions" / "grid.toml") == list(WAVE1)


def test_owned_tiles(tmp_path, regions_dir):
    (tmp_path / "grid.toml").write_text('zoom = 10\norder = ["a", "b"]\n')
    a = _region("a", (-123.0, 47.0, -122.0, 47.6))
    assert owned_tiles(_region("ov", a.bbox, overview=True), tmp_path) is None
    with pytest.raises(RegionError, match="b.toml"):
        owned_tiles(a, tmp_path)
    with pytest.raises(RegionError, match="not in"):
        owned_tiles(_region("c", a.bbox), tmp_path)
    (tmp_path / "b.toml").write_text((regions_dir / "test-cell.toml").read_text().replace("test-cell", "b"))
    owned = owned_tiles(a, tmp_path)
    assert owned and owned <= tiles_meeting(a.bbox)


def test_keep_tiles_on_tile_join_schema(tmp_path):
    """tile-join writes `map` and `images` tables with `tiles` a view over them: prune through map, drop orphan images."""
    import sqlite3

    path = tmp_path / "j.mbtiles"
    conn = sqlite3.connect(path)
    conn.executescript(
        "create table metadata (name text, value text);"
        "create table map (zoom_level integer, tile_column integer, tile_row integer, tile_id text);"
        "create table images (tile_id text, tile_data blob);"
        "create view tiles as select map.zoom_level as zoom_level, map.tile_column as tile_column,"
        " map.tile_row as tile_row, images.tile_data as tile_data from map join images on map.tile_id = images.tile_id;")
    for i, (z, x, y) in enumerate([(10, 163, 356), (10, 164, 356)]):
        conn.execute("insert into map values (?, ?, ?, ?)", (z, x, 2**z - 1 - y, f"t{i}"))
        conn.execute("insert into images values (?, ?)", (f"t{i}", b"t"))
    conn.commit()
    conn.close()
    keep_tiles(path, {(163, 356)}, minzoom=10, maxzoom=16)
    conn = sqlite3.connect(path)
    assert conn.execute("select count(*) from tiles").fetchone() == (1,)
    assert conn.execute("select tile_id from images").fetchall() == [("t0",)]
    conn.close()
