import json
import math

import shapely
from shapely.geometry import box, shape

from chartpack.enc.catalog import _intersects, parse_catalog
from chartpack.grid import GRID_ZOOM, load_grid, owned_tiles, seams, tile_bounds, tiles_meeting
from chartpack.region import load_region

WAVE1 = ["sound-south", "sound-central", "north-sound", "strait", "wa-coast", "overview"]
BANDS = {"sound-south": (3, 4, 5), "sound-central": (3, 4, 5), "north-sound": (3, 4, 5),
         "strait": (1, 2, 3, 4, 5), "wa-coast": (1, 2, 3, 4, 5), "overview": (1, 2, 3)}
VIEWS = {
    "sound-south": {"tacoma-narrows"},
    "sound-central": {"everett", "possession-bar", "point-no-point", "jeff-head", "admiralty-inlet", "corner",
                      "lake-washington"},
    "north-sound": {"friday-harbor"},
    "strait": set(),
    "wa-coast": {"neah-bay-grounds"},
    "overview": set(),
}


def _regions(regions_dir):
    return {name: load_region(regions_dir / f"{name}.toml") for name in WAVE1}


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
    regions = _regions(regions_dir)
    assert [r.name for r in regions.values()] == WAVE1
    for r in regions.values():
        assert (r.charts_version, r.bathy_version) == ("1.0.0", "1.0.0"), r.name
        assert r.clip == regions_dir / "clip/canada-wa.geojson", r.name
        assert r.datum_file == regions_dir / "datum/wa-stations.toml", r.name
        assert r.overview == (r.name == "overview"), r.name
    assert load_grid(regions_dir / "grid.toml") == WAVE1[:-1]


def test_puget_north_is_gone(regions_dir):
    assert not (regions_dir / "puget-north.toml").exists()
    assert "puget-north" not in load_grid(regions_dir / "grid.toml")


def test_global_caps(regions_dir):
    assert {r.name: r.dem_maxzoom for r in _regions(regions_dir).values()} == {name: 14 for name in WAVE1}


def test_region_packs_list_both_bathy_sources(regions_dir):
    """Every region pack reads CUDEM, then CRM where CUDEM is absent; the overview is CRM only (load_region)."""
    for r in _regions(regions_dir).values():
        if r.overview:
            assert r.bathy_sources == ["crm"]
        else:
            assert (r.bathy_sources, r.coarse_fallback) == (["cudem", "crm"], "crm"), r.name


def test_every_box_tile_is_owned_or_canadian(regions_dir):
    owned = _owned(regions_dir)
    clip_path = regions_dir / "clip/canada-wa.geojson"
    clip = shape(json.loads(clip_path.read_text())["geometry"])
    every = set().union(*owned.values())
    assert sum(len(t) for t in owned.values()) == len(every)  # no tile has two owners
    for r in _regions(regions_dir).values():
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
        assert sorted(r.cells) == list(BANDS[r.name]), r.name
        for band, names in r.cells.items():
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
