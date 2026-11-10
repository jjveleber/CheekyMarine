import json
from pathlib import Path

import pytest
from shapely.geometry import box

from chartpack.grid import GRID_ZOOM, assign, keep_tiles, load_grid, owned_tiles, tile_bounds, tiles_meeting
from chartpack.mbtiles import MBTiles
from chartpack.region import Region, RegionError

from tilemath import tile_of


def _region(name, bbox, overview=False):
    return Region(name=name, charts_version="0.1.0", bathy_version="0.1.0", bbox=bbox, cells={}, bathy_sources=[],
                  coarse_fallback="crm", clip=None, dem_maxzoom=14, datum_file=Path("x.toml"), views=[], overview=overview)


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
    owner = assign([a, b], ["a", "b"], None)
    assert set(owner) == tiles_meeting(a.bbox) | tiles_meeting(b.bbox)
    assert set(owner) == tiles_meeting((-123.0, 47.0, -122.0, 48.0))
    assert tiles_meeting(a.bbox).isdisjoint(tiles_meeting(b.bbox))
    assert {owner[t] for t in tiles_meeting(a.bbox)} == {"a"} and {owner[t] for t in tiles_meeting(b.bbox)} == {"b"}


def test_overlap_goes_to_first_in_order():
    a = _region("a", (-123.0, 47.0, -122.0, 47.6))
    b = _region("b", (-123.0, 47.4, -122.0, 48.0))
    overlap = tiles_meeting(a.bbox) & tiles_meeting(b.bbox)
    assert overlap
    assert {assign([a, b], ["a", "b"], None)[t] for t in overlap} == {"a"}
    assert {assign([a, b], ["b", "a"], None)[t] for t in overlap} == {"b"}


def test_overview_and_unlisted_regions():
    a, ov = _region("a", (-123.0, 47.0, -122.0, 47.6)), _region("ov", (-130.0, 40.0, -120.0, 50.0), overview=True)
    assert set(assign([a, ov], ["a"], None)) == tiles_meeting(a.bbox)
    with pytest.raises(RegionError, match="not in the grid order"):
        assign([a], [], None)
    with pytest.raises(RegionError, match="were not given"):
        assign([a], ["a", "b"], None)


def test_tile_inside_clip_is_unowned():
    tile = (163, 356)
    clip = box(*tile_bounds(GRID_ZOOM, *tile)).buffer(0.001)
    a = _region("a", (-123.0, 47.0, -122.0, 48.0))
    owner = assign([a], ["a"], clip)
    assert tile not in owner and tiles_meeting(a.bbox) - {tile} == set(owner)


def test_tile_partly_inside_clip_is_owned():
    tile = (163, 356)
    w, s, e, n = tile_bounds(GRID_ZOOM, *tile)
    clip = box(w, s, (w + e) / 2, n)
    assert assign([_region("a", (-123.0, 47.0, -122.0, 48.0))], ["a"], clip)[tile] == "a"


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
    owner = assign([_region(n, b) for n, b in WAVE1.items()], order, None)
    assert owner[tile_of(10, -122.55, 47.27)] == "sound-south"
    assert owner[tile_of(10, -122.34, 47.60)] == "sound-central"


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
