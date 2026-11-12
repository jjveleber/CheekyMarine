import json
import math

import pytest
import shapely
from shapely.geometry import box, shape

from chartpack.enc.catalog import _intersects, parse_catalog
from chartpack.enc.tiles import OVERVIEW_ZOOMS
from chartpack.grid import (
    GRID_ZOOM,
    load_grid,
    offshore_shore_tiles,
    owned_tiles,
    seams,
    tile_bounds,
    tiles_meeting,
    tiles_meeting_area,
)
from chartpack.region import RegionError, load_region

WAVE1 = ["sound-south", "sound-central", "north-sound", "strait", "wa-coast", "overview"]
BC_INSHORE = ["bc-south-georgia", "bc-vi-west-south", "bc-north-georgia", "bc-johnstone", "bc-vi-west-north",
              "bc-central", "bc-north", "haida-gwaii"]
BC_OFFSHORE = ["bc-offshore-south", "bc-offshore-north"]
GRID = WAVE1[:-1] + BC_INSHORE + BC_OFFSHORE  # plan 8 Task 15: the wave 1 order unchanged, then inshore, offshore
REBUILT = ["north-sound", "strait", "wa-coast", "overview"]  # 1.1.0: with Canadian-side data (plan 8 spec 4)
ALL = GRID + ["overview"]
BANDS = {"sound-south": (3, 4, 5), "sound-central": (3, 4, 5), "north-sound": (3, 4, 5),
         "strait": (1, 2, 3, 4, 5), "wa-coast": (1, 2, 3, 4, 5), "overview": (1, 2, 3),
         **{name: (1, 2, 3) for name in BC_INSHORE + BC_OFFSHORE},  # BC: the bands the catalog gives, of 1 to 3
         # and every band where the owned tiles hold US (Alaskan) water, so it keeps NOAA's finest detail
         "bc-north": (1, 2, 3, 4, 5), "bc-offshore-north": (1, 2, 3, 4, 5)}
INSHORE_ZOOMS, OFFSHORE_ZOOMS = (9, 11, 13, 15), (7, 9, 11)
VIEWS = {
    "sound-south": {"tacoma-narrows"},
    "sound-central": {"everett", "possession-bar", "point-no-point", "jeff-head", "admiralty-inlet", "corner",
                      "lake-washington"},
    "north-sound": {"friday-harbor", "victoria-haro-strait", "active-pass"},
    "strait": {"port-angeles"},
    "wa-coast": {"neah-bay-grounds"},
    "overview": {"strait-and-coast"},
    # plan 8 spec 15, each in the region owning its tile
    "bc-south-georgia": {"vancouver-indian-arm"},
    "bc-north-georgia": {"desolation-sound"},
    "bc-johnstone": {"knight-inlet-head"},
    "bc-vi-west-south": {"barkley-sound", "tofino-shelf", "crm-edge-49n"},
    "bc-vi-west-north": {"nootka-sound"},
    "bc-central": {"bella-bella"},
    "bc-north": {"prince-rupert", "dixon-entrance"},
    "haida-gwaii": {"masset"},
    "bc-offshore-south": {"offshore-south"},
    "bc-offshore-north": {"offshore-north"},
}
COAST_TILES = "bc-coast-tiles.json"  # written by the controller from the fetched coastline assets (Task 15 Step 4)


def _regions(regions_dir, names=ALL):
    return {name: load_region(regions_dir / f"{name}.toml") for name in names}


def _owned(regions_dir):
    regions = _regions(regions_dir)
    return {name: owned_tiles(regions[name], regions_dir) for name in load_grid(regions_dir / "grid.toml")}


def _area(tiles):
    return shapely.union_all([box(*tile_bounds(GRID_ZOOM, *t)) for t in tiles])


def _tile_of(lon, lat):
    n = 2**GRID_ZOOM
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return math.floor((lon + 180.0) / 360.0 * n), math.floor(y)


def test_wave1_regions_load(regions_dir):
    regions = _regions(regions_dir, WAVE1)
    assert [r.name for r in regions.values()] == WAVE1
    for r in regions.values():
        version = "1.1.0" if r.name in REBUILT else "1.0.0"
        assert (r.charts_version, r.bathy_version) == (version, version), r.name
        # the overview is rebuilt over US and BC water, so it has no clip (plan 8 spec 4)
        assert r.clip == (None if r.overview else regions_dir / "clip/canada-wa.geojson"), r.name
        assert r.datum_file == regions_dir / "datum/wa-stations.toml", r.name
        assert r.overview == (r.name == "overview"), r.name


def test_every_region_file_loads(regions_dir):
    """Every region file loads; the grid holds the wave 1 order unchanged, then the eight inshore BC packs, then the
    two offshore ones; the BC packs are 1.0.0 with the brief's sources; test-toba is gone."""
    files = {p.stem for p in regions_dir.glob("*.toml")} - {"grid", "bc-valdco"}
    assert files == set(ALL) | {"test-cell"}
    for name in files:
        assert load_region(regions_dir / f"{name}.toml").name == name
    assert load_grid(regions_dir / "grid.toml") == GRID
    for name, r in _regions(regions_dir, BC_INSHORE + BC_OFFSHORE).items():
        offshore = name in BC_OFFSHORE
        assert (r.charts_version, r.bathy_version) == ("1.0.0", "1.0.0"), name
        assert r.charts_kind == ("derived-offshore" if offshore else "derived-inshore"), name
        assert (r.area is not None) == offshore, name
        crm = ["crm"] if name in ("bc-south-georgia", "bc-vi-west-south", "bc-offshore-south") else []
        assert r.bathy_sources == (["nonna100"] if offshore else ["nonna10", "nonna100"]) + crm + ["etopo"], name
        assert r.dem_maxzoom == 14 and r.datum_file == regions_dir / "datum/wa-stations.toml", name
        assert r.clip is None, name
        assert all(v.zooms == (OFFSHORE_ZOOMS if offshore else INSHORE_ZOOMS) for v in r.views), name
    for name in ("north-sound", "strait", "wa-coast"):
        assert load_region(regions_dir / f"{name}.toml").bathy_sources == ["cudem", "crm", "nonna10", "nonna100"]
    assert load_region(regions_dir / "overview.toml").bathy_sources == ["nonna100", "crm", "etopo"]


def _owned_all(regions_dir):
    regions = _regions(regions_dir, GRID)
    return regions, {name: owned_tiles(r, regions_dir) for name, r in regions.items()}


# Owned zoom-10 tiles per region with the shipped boxes, polygons and grid order (plan 8 Task 15): a moved box or a
# changed order changes a count.
TILE_COUNTS = {"sound-south": 12, "sound-central": 12, "north-sound": 16, "strait": 13, "wa-coast": 92,
               "bc-south-georgia": 18, "bc-vi-west-south": 41, "bc-north-georgia": 28, "bc-johnstone": 39,
               "bc-vi-west-north": 33, "bc-central": 79, "bc-north": 116, "haida-gwaii": 83, "bc-offshore-south": 98,
               "bc-offshore-north": 159}
UNOWNED_TILES = "bc-unowned-tiles.json"  # the reviewed gaps next to the owned tiles (tests/fixtures/README.md)
UNOWNED_COAST_ALLOWED: set[tuple[int, int]] = set()  # unowned tiles known to hold coastline, owner-approved


def _neighbors(tile):
    x, y = tile
    return {(x + a, y + b) for a in (-1, 0, 1) for b in (-1, 0, 1)} - {tile}


def _unowned_next_to_owned(regions_dir, owned):
    """The unowned zoom-10 tiles that touch an owned tile (edge or corner) and meet the Canada polygon."""
    from chartpack.enc.bc import load_canada

    canada = load_canada(regions_dir)
    every = set().union(*owned.values())
    near = set().union(*(_neighbors(t) for t in every)) - every
    return {t for t in near if canada.intersection(box(*tile_bounds(GRID_ZOOM, *t))).area > 0}


def test_every_bc_tile_has_one_owner(regions_dir, fixtures_dir):
    """Each region owns the pinned number of tiles (a moved box or a changed grid order fails here until the table
    is updated on purpose), and the unowned tiles next to the owned ones that meet the Canada polygon are exactly
    the reviewed list: a new gap fails the test. The list holds the known gaps (Portland Canal and Observatory
    Inlet, the Vancouver Island interior column (154, 347) and (154, 348), inland and deep-ocean edges)."""
    _, owned = _owned_all(regions_dir)
    assert {name: len(tiles) for name, tiles in owned.items()} == TILE_COUNTS
    gaps = {tuple(t) for t in json.loads((fixtures_dir / UNOWNED_TILES).read_text())}
    assert _unowned_next_to_owned(regions_dir, owned) == gaps
    assert {(154, 347), (154, 348)} <= gaps


def test_no_unowned_tile_holds_coastline(regions_dir, fixtures_dir):
    """No unowned tile next to an owned one holds Freshwater Atlas coastline, but for the owner-approved
    UNOWNED_COAST_ALLOWED (empty): BC shore water always has a pack."""
    path = fixtures_dir / COAST_TILES
    if not path.is_file():
        pytest.skip(f"tests/fixtures/{COAST_TILES} is written by the controller from the fetched coastline assets"
                    " (plan 8 Task 15 Step 4)")
    coast = {tuple(t) for t in json.loads(path.read_text())}
    _, owned = _owned_all(regions_dir)
    assert (_unowned_next_to_owned(regions_dir, owned) & coast) <= UNOWNED_COAST_ALLOWED


def test_no_offshore_tile_holds_coastline(regions_dir, fixtures_dir):
    """Shore water is never offshore (plan 8 spec 4): no tile an offshore pack owns holds Freshwater Atlas
    coastline. The coast tiles come from the fetched coastline assets of every BC region."""
    path = fixtures_dir / COAST_TILES
    if not path.is_file():
        pytest.skip(f"tests/fixtures/{COAST_TILES} is written by the controller from the fetched coastline assets"
                    " (plan 8 Task 15 Step 4)")
    coast = {tuple(t) for t in json.loads(path.read_text())}
    regions, owned = _owned_all(regions_dir)
    owner = {tile: name for name, tiles in owned.items() for tile in tiles}
    assert offshore_shore_tiles(owner, regions, coast) == set()


def test_overview_rejects_fine_sources(tmp_path, regions_dir):
    """An overview lists coarse sources only: any subset of crm, nonna100 and etopo loads; cudem and nonna10 fail."""
    text = (regions_dir / "overview.toml").read_text()
    path = tmp_path / "ov.toml"
    for sources in (["crm"], ["nonna100"], ["etopo"], ["nonna100", "crm", "etopo"], ["crm", "etopo"]):
        path.write_text(text.replace('sources = ["nonna100", "crm", "etopo"]', f"sources = {json.dumps(sources)}"))
        assert load_region(path).bathy_sources == sources
    for sources in (["cudem", "crm"], ["nonna10", "nonna100"], ["nonna10", "etopo"], ["cudem", "nonna100"]):
        path.write_text(text.replace('sources = ["nonna100", "crm", "etopo"]', f"sources = {json.dumps(sources)}"))
        with pytest.raises(RegionError, match="overview"):
            load_region(path)


def test_puget_north_is_gone(regions_dir):
    assert not (regions_dir / "puget-north.toml").exists()
    assert "puget-north" not in load_grid(regions_dir / "grid.toml")


def test_global_caps(regions_dir):
    assert {r.name: r.dem_maxzoom for r in _regions(regions_dir).values()} == {name: 14 for name in ALL}


def test_region_packs_list_both_bathy_sources(regions_dir):
    """Every US region pack reads CUDEM, then CRM where CUDEM is absent, and the packs with Canadian water also
    NONNA (plan 8 spec 4); the overview reads the coarse sources only (load_region)."""
    for r in _regions(regions_dir, WAVE1).values():
        if r.overview:
            assert r.bathy_sources == ["nonna100", "crm", "etopo"]
        else:
            nonna = ["nonna10", "nonna100"] if r.name in REBUILT else []
            assert (r.bathy_sources, r.coarse_fallback) == (["cudem", "crm"] + nonna, "crm"), r.name


def test_every_box_tile_is_owned_or_canadian(regions_dir):
    owned = {name: tiles for name, tiles in _owned(regions_dir).items() if name in WAVE1}
    clip_path = regions_dir / "clip/canada-wa.geojson"
    clip = shape(json.loads(clip_path.read_text())["geometry"])
    every = set().union(*_owned(regions_dir).values())  # a wholly Canadian tile in a US box may go to a BC pack
    assert sum(len(t) for t in owned.values()) == len(set().union(*owned.values()))  # no tile has two owners
    for r in _regions(regions_dir, WAVE1).values():
        if r.overview:
            continue
        for tile in tiles_meeting(r.bbox):
            assert tile in every or clip.contains(box(*tile_bounds(GRID_ZOOM, *tile))), (r.name, tile)


def test_no_region_owns_nothing(regions_dir):
    for name, tiles in _owned(regions_dir).items():
        assert tiles, name


def test_views_inside_owned_tiles(regions_dir):
    owned = _owned(regions_dir)
    for r in _regions(regions_dir).values():
        assert {v.name for v in r.views} == VIEWS[r.name], r.name
        for v in r.views:
            if r.overview:  # owns no grid tile: inside its bbox, at its own zooms
                w, s, e, n = r.bbox
                assert w < v.lon < e and s < v.lat < n, v.name
                assert all(OVERVIEW_ZOOMS[0] <= z <= OVERVIEW_ZOOMS[1] for z in v.zooms), v.name
            else:
                assert _tile_of(v.lon, v.lat) in owned[r.name], (r.name, v.name)


def test_overview_lists_low_bands_only(regions_dir):
    r = load_region(regions_dir / "overview.toml")
    assert r.overview and owned_tiles(r, regions_dir) is None
    assert sorted(r.cells) == [1, 2, 3] and all(r.cells.values())


def test_wave1_cells_match_catalog(regions_dir, fixtures_dir):
    """Each named cell is Active, of its band and meets the owned tiles (the overview: all of them); and every
    Active fixture cell of the region's bands meeting them is named. The fixture holds every cell the regions name."""
    cat = parse_catalog((fixtures_dir / "ENCProdCat_excerpt.xml").read_bytes())
    owned = _owned(regions_dir)
    areas = {name: _area(tiles) for name, tiles in owned.items()}
    areas["overview"] = _area(set().union(*owned.values()))
    for r in _regions(regions_dir).values():
        if r.name in WAVE1:
            assert sorted(r.cells) == list(BANDS[r.name]), r.name
        else:  # a BC pack lists the bands of BANDS the catalog gives a cell for
            assert set(r.cells) <= set(BANDS[r.name]) and all(r.cells.values()), r.name
            assert {4, 5} <= set(r.cells) or 4 not in BANDS[r.name], r.name
        for band in BANDS[r.name]:
            names = r.cells.get(band, [])
            assert names == sorted(set(names)), (r.name, band)
            for n in names:
                assert cat[n].status == "Active" and cat[n].band == band and _intersects(cat[n], areas[r.name]), n
            meeting = {c.name for c in cat.values()
                       if c.band == band and c.status == "Active" and _intersects(c, areas[r.name])}
            assert meeting <= set(names), (r.name, band, sorted(meeting - set(names)))
    central = load_region(regions_dir / "sound-central.toml")
    assert central.cells[3] == ["US3WA1DF", "US3WA1DG", "US3WA1EF", "US3WA1EG"]
    assert set(central.cells[4]) >= {"US4WA1GJ", "US4WA1GK", "US4WA1HJ", "US4WA1HK", "US4WA1II", "US4WA1IJ", "US4WA1IK"}


def test_seams_printed(regions_dir):
    """seams() gives each pair's shared tile lines; the Sound splits at the zoom-10 rows next to 47.45 N and 48.2 N."""
    got = seams(_owned(regions_dir))
    assert all(a != b for a, b in got)
    (south,) = got[("sound-south", "sound-central")]
    (north,) = got[("sound-central", "north-sound")]
    for line, lat in ((south, 47.5172), (north, 48.2247)):
        (w, s), (e, n) = line
        assert abs(s - lat) < 1e-4 and abs(n - lat) < 1e-4 and w < e
    for line in [ln for lines in got.values() for ln in lines]:
        (w, s), (e, n) = line
        assert (w == e) != (s == n)  # each line runs along a tile row or column


def test_seams_merges_runs_and_keys_pairs_in_order():
    a = {(0, 0), (1, 0)}
    b = {(0, 1), (1, 1), (2, 0)}
    got = seams({"a": a, "b": b})
    assert set(got) == {("a", "b")}
    w0, s0, _, n0 = tile_bounds(GRID_ZOOM, 0, 0)
    e1 = tile_bounds(GRID_ZOOM, 1, 0)[2]
    assert sorted(got[("a", "b")]) == sorted([
        ((w0, s0), (e1, s0)),  # under row 0: one run over two tiles
        ((e1, s0), (e1, n0)),  # a's tile (1, 0) against b's tile (2, 0)
    ])



def test_overview_bbox_holds_every_owned_tile(regions_dir):
    """The overview's coarse read (overview_bounds of its bbox) covers every zoom-10 tile a region pack owns, so
    no owned water has depth at zoom 10 but none at zoom 6 to 9."""
    w, s, e, n = load_region(regions_dir / "overview.toml").bbox
    tw, ts, te, tn = _area(set().union(*_owned(regions_dir).values())).bounds
    assert w <= tw and s <= ts and e >= te and n >= tn, ((w, s, e, n), (tw, ts, te, tn))


CRM_VOL8 = (-127.0, 44.0, -121.75, 49.0)  # W, S, E, N: what CRM volume 8 fills (spec 7)


def test_every_crm_request_meets_crm(regions_dir):
    """Every CRM request of wave 1 (one per owned tile, over its read bounds, and the overview's one read) overlaps
    CRM volume 8, so none is wholly outside it: read_window raises on a window wholly outside its file. Some reach
    past -127 W or 49 N; that part reads as nodata (test_read_window_past_the_file_edge_is_nodata)."""
    from chartpack.bathy.blocks import iter_blocks, overview_bounds

    owned = {name: tiles for name, tiles in _owned(regions_dir).items() if name in WAVE1}
    reads = [read for tiles in owned.values() for _, _, read in iter_blocks(tiles)]
    reads.append(overview_bounds(load_region(regions_dir / "overview.toml").bbox))
    cw, cs, ce, cn = CRM_VOL8
    for w, s, e, n in reads:
        assert w < ce and e > cw and s < cn and n > cs, (w, s, e, n)


def test_wa_coast_reaches_the_sound_column(regions_dir):
    """wa-coast's east edge is the -123.3984 W column line, the west edge of sound-south and sound-central, so
    the column from -123.75 W to it south of the strait is wa-coast: Raymond on the Willapa River, the Chehalis
    above Cosmopolis and the Columbia at Skamokawa."""
    owned = _owned(regions_dir)
    for lon, lat in ((-123.73, 46.686), (-123.70, 46.97), (-123.455, 46.27)):
        assert _tile_of(lon, lat) in owned["wa-coast"], (lon, lat)
    south = _area(owned["sound-south"]).bounds  # W, S, E, N
    assert load_region(regions_dir / "wa-coast.toml").bbox[2] == south[0]
    got = seams(owned)
    assert got[("sound-south", "wa-coast")] == [((south[0], south[1]), (south[0], south[3]))]
    assert ("sound-central", "wa-coast") in got
