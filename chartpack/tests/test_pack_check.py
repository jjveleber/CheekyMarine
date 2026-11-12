import gzip
import json
import sqlite3
from datetime import datetime, timezone

import mapbox_vector_tile
import pytest
import shapely

from chartpack.pack.check import check_pack
from chartpack.pack.manifest import describe_pack, write_manifest


def _rewrite_tiles(mbtiles, z, edit):
    """Replace every tile at zoom z by edit(layers), layers being a list for mapbox_vector_tile.encode."""
    conn = sqlite3.connect(mbtiles)
    # tile-join writes tiles as a view over map and images; flatten it to a table so rows can be updated
    conn.executescript("create table flat as select * from tiles; drop view tiles; alter table flat rename to tiles;")
    rows = conn.execute("select tile_column, tile_row, tile_data from tiles where zoom_level=?", (z,)).fetchall()
    for col, row, data in rows:
        raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        decoded = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True})
        layers = edit([{"name": n, **layer} for n, layer in decoded.items()])
        out = mapbox_vector_tile.encode(layers, default_options={"y_coord_down": True})
        conn.execute("update tiles set tile_data=? where zoom_level=? and tile_column=? and tile_row=?",
                     (gzip.compress(out), z, col, row))
    conn.commit()
    conn.close()


def _refresh(pack, region):
    """Rewrite the manifest after a deliberate edit so only the edit's own check can fail."""
    kind, sources, notice = describe_pack(pack)
    write_manifest(pack, pack=kind, region=region, sources=sources, notice=notice, built=datetime.now(timezone.utc))


def test_check_passes_on_built_pack(charts_pack_root, fixtures_dir):
    assert check_pack(charts_pack_root, enc_zips=[fixtures_dir / "US4WA1HK.zip"]) == []
    assert check_pack(charts_pack_root) == []


def test_check_catches_a_removed_hazard(charts_pack_root_copy, fixtures_dir, test_region):
    removed = []

    def drop_one(layers):
        for layer in layers:
            if layer["name"] == "hazard" and layer["features"]:
                removed.append(layer["features"].pop(0))
        return layers

    _rewrite_tiles(charts_pack_root_copy / "enc.mbtiles", 16, drop_one)
    assert removed
    _refresh(charts_pack_root_copy, test_region)
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert any("hazard" in e for e in errs)
    assert check_pack(charts_pack_root_copy) == []  # the hazard comparison needs the source zips


def test_check_catches_corrupt_file(charts_pack_root_copy):
    path = charts_pack_root_copy / "sprites" / "nav.png"
    data = bytearray(path.read_bytes())
    data[-5] ^= 0xFF
    path.write_bytes(bytes(data))
    errs = check_pack(charts_pack_root_copy)
    assert len(errs) == 1 and "sprites/nav.png" in errs[0] and "sha256" in errs[0]


def test_check_catches_missing_and_unlisted_files(charts_pack_root_copy):
    (charts_pack_root_copy / "NOTICE").unlink()
    (charts_pack_root_copy / "extra.txt").write_text("x")
    errs = check_pack(charts_pack_root_copy)
    assert any("NOTICE" in e and "missing" in e for e in errs) and any("extra.txt" in e for e in errs)


def test_check_without_manifest(tmp_path):
    assert any("manifest" in e for e in check_pack(tmp_path))
    (tmp_path / "manifest.json").write_text("{not json")
    assert any("manifest" in e for e in check_pack(tmp_path))


def test_check_catches_missing_metadata_key(charts_pack_root_copy, test_region):
    conn = sqlite3.connect(charts_pack_root_copy / "enc.mbtiles")
    conn.execute("delete from metadata where name='cheekymarine:valdco'")
    conn.commit()
    conn.close()
    _refresh(charts_pack_root_copy, test_region)
    assert any("cheekymarine:valdco" in e for e in check_pack(charts_pack_root_copy))


def test_check_catches_layer_mismatch(charts_pack_root_copy, test_region):
    conn = sqlite3.connect(charts_pack_root_copy / "enc.mbtiles")
    meta = json.loads(conn.execute("select value from metadata where name='json'").fetchone()[0])
    meta["vector_layers"] = [l for l in meta["vector_layers"] if l["id"] != "meta"] + [{"id": "bogus", "fields": {}}]
    conn.execute("update metadata set value=? where name='json'", (json.dumps(meta),))
    conn.commit()
    conn.close()
    _refresh(charts_pack_root_copy, test_region)
    errs = check_pack(charts_pack_root_copy)
    assert any("meta" in e and "missing" in e for e in errs) and any("bogus" in e for e in errs)


def test_check_allows_pack_without_seabed(charts_pack_root_copy, test_region):
    """seabed is optional (ruling R21): a pack whose region has no seabed features passes."""
    conn = sqlite3.connect(charts_pack_root_copy / "enc.mbtiles")
    meta = json.loads(conn.execute("select value from metadata where name='json'").fetchone()[0])
    meta["vector_layers"] = [l for l in meta["vector_layers"] if l["id"] != "seabed"]
    conn.execute("update metadata set value=? where name='json'", (json.dumps(meta),))
    conn.commit()
    conn.close()
    _refresh(charts_pack_root_copy, test_region)
    assert not [e for e in check_pack(charts_pack_root_copy) if "seabed" in e]


def test_check_catches_safety_layer_empty_in_band_range(charts_pack_root_copy, test_region):
    _rewrite_tiles(charts_pack_root_copy / "enc.mbtiles", 12, lambda layers: [l for l in layers if l["name"] != "navaid"])
    _refresh(charts_pack_root_copy, test_region)
    assert check_pack(charts_pack_root_copy) == ["enc.mbtiles: safety layer navaid has no features at zoom 12"]


def test_check_catches_style_using_unknown_icon(charts_pack_root_copy, test_region):
    path = charts_pack_root_copy / "styles" / "nav-day.json"
    style = json.loads(path.read_text())
    next(l for l in style["layers"] if "icon-image" in l.get("layout", {}))["layout"]["icon-image"] = "no-such-icon"
    path.write_text(json.dumps(style))
    _refresh(charts_pack_root_copy, test_region)
    assert any("nav-day.json" in e and "no-such-icon" in e for e in check_pack(charts_pack_root_copy))


def test_check_catches_depare_missing_from_coverage(charts_pack_root_copy, fixtures_dir, test_region):
    _rewrite_tiles(charts_pack_root_copy / "enc.mbtiles", 16, lambda layers: [l for l in layers if l["name"] != "depare"])
    _refresh(charts_pack_root_copy, test_region)
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert any("depare and lndare cover" in e for e in errs)


def test_check_catches_hazard_not_in_source(charts_pack_root_copy, fixtures_dir, test_region):
    def add_one(layers):
        for layer in layers:
            if layer["name"] == "hazard" and layer["features"]:
                feat = layer["features"][0]
                layer["features"].append({**feat, "properties": {**feat["properties"], "VALSOU": "99.9"}})
                break
        return layers

    _rewrite_tiles(charts_pack_root_copy / "enc.mbtiles", 16, add_one)
    _refresh(charts_pack_root_copy, test_region)
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert any("hazard" in e and "not in the source cells" in e for e in errs)


def test_hazard_on_a_seam_of_finer_cells_is_quilted_away(charts_pack_root, fixtures_dir, monkeypatch):
    """A coarse-band hazard on the shared edge of two finer cells lies inside their union, so the quilt
    clips it out; the check must not expect it (puget-north: an OBSTRN of US3WA1DF on the -122.7 seam)."""
    from shapely.geometry import box, mapping

    from chartpack.enc.reader import CellMeta, Feature, read_cell
    from chartpack.pack import check

    meta, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    seam = Feature("hazard", {"type": "Point", "coordinates": [-122.25, 47.85]},
                   {"cell": meta.name, "band": 4, "class": "OBSTRN", "WATLEV": 3})
    cells = {
        "hk": (meta, feats + [seam]),
        "west": (CellMeta("US5TESTW", 5, 1, 0, "20260101", mapping(box(-122.30, 47.80, -122.25, 47.90))), []),
        "east": (CellMeta("US5TESTE", 5, 1, 0, "20260101", mapping(box(-122.25, 47.80, -122.20, 47.90))), []),
    }
    monkeypatch.setattr(check, "read_cell", lambda path: cells[str(path)])
    assert check_pack(charts_pack_root, enc_zips=["hk", "west", "east"]) == []


# ---- plan 7: size cap, four bathy files, ownership-aware checks

def _bathy_pack(tmp_path, test_region, tiles):
    """A minimal bathy pack: the four files, with a tile in each file named in `tiles`."""
    from chartpack.enc.schema import BATHY_LAYER_SPECS, OPTIONAL_LAYERS
    from chartpack.mbtiles import MBTiles
    from chartpack.pack.assemble import BATHY_FILES

    root = tmp_path / "bathy-pack"
    root.mkdir()
    layers = json.dumps({"vector_layers": [{"id": s.name} for s in BATHY_LAYER_SPECS if s.name not in OPTIONAL_LAYERS]})
    common = {"name": "t", "format": "pbf", "bounds": "0,0,1,1", "minzoom": "10", "maxzoom": "12", "cheekymarine:schema": "2",
              "cheekymarine:pack": "bathy", "cheekymarine:region": "t", "cheekymarine:version": "0.1.0",
              "cheekymarine:sources": "{}", "cheekymarine:built": "x", "json": layers,
              "cheekymarine:encoding": "terrarium"}
    for name in BATHY_FILES:
        with MBTiles.create(root / name, fmt="pbf") as m:
            m.set_metadata(common)
            if name in tiles:
                m.put_tile(10, 1, 1, b"x")
    write_manifest(root, pack="bathy", region=test_region, sources=[], notice="n", built=datetime.now(timezone.utc))
    return root


def test_over_cap_is_reported(charts_pack_root, monkeypatch):
    from chartpack.pack import check

    monkeypatch.setattr(check, "PACK_CAP_BYTES", 100)
    errs = check_pack(charts_pack_root)
    assert any(e.startswith("pack is ") and e.endswith(" bytes, over the 1.5 GB cap") for e in errs)


def test_bathy_needs_coarse_files(tmp_path, test_region):
    root = _bathy_pack(tmp_path, test_region, {"bathy.mbtiles"})
    assert check_pack(root) == []
    (root / "bathy-coarse.mbtiles").unlink()
    (root / "dem-coarse.mbtiles").unlink()
    write_manifest(root, pack="bathy", region=test_region, sources=[], notice="n", built=datetime.now(timezone.utc))
    errs = check_pack(root)
    assert "bathy-coarse.mbtiles: missing from the bathy pack" in errs
    assert "dem-coarse.mbtiles: missing from the bathy pack" in errs


def test_empty_bathy_file_allowed(tmp_path, test_region):
    root = _bathy_pack(tmp_path, test_region, {"bathy-coarse.mbtiles"})
    assert check_pack(root) == []


def test_all_bathy_files_empty_is_error(tmp_path, test_region):
    root = _bathy_pack(tmp_path, test_region, set())
    assert any("no tiles" in e for e in check_pack(root))


def _prune(pack, test_region, owned, minzoom, maxzoom):
    from chartpack.grid import keep_tiles

    keep_tiles(pack / "enc.mbtiles", owned, minzoom=minzoom, maxzoom=maxzoom)
    _refresh(pack, test_region)


def _z10_tiles(pack):
    from chartpack.mbtiles import MBTiles

    with MBTiles.open(pack / "enc.mbtiles") as m:
        return {(x >> 6, y >> 6) for x, y, _ in m.tiles_at(16)}


def test_region_pack_not_checked_below_z10(charts_pack_root_copy, test_region):
    from chartpack.pack.check import _band_zooms

    sources = json.dumps([{"cell": "US3WA1DF"}, {"cell": "US4WA1HK"}])  # a band 3 cell asks for zooms 6 to 10
    assert min(_band_zooms({"cheekymarine:sources": sources, "minzoom": "6", "maxzoom": "16"})) == 6
    assert min(_band_zooms({"cheekymarine:sources": sources, "minzoom": "10", "maxzoom": "16"})) == 10
    _prune(charts_pack_root_copy, test_region, _z10_tiles(charts_pack_root_copy), 10, 16)
    assert check_pack(charts_pack_root_copy) == []


def test_emptied_enc_pack_still_errors(charts_pack_root_copy, test_region):
    conn = sqlite3.connect(charts_pack_root_copy / "enc.mbtiles")
    conn.executescript("create table flat as select * from tiles; drop view tiles; alter table flat rename to tiles;"
                       "delete from tiles;")
    conn.commit()
    conn.close()
    _refresh(charts_pack_root_copy, test_region)
    assert any("safety layer" in e for e in check_pack(charts_pack_root_copy))


def test_overview_not_checked_at_z10(charts_pack_root_copy, test_region):
    _prune(charts_pack_root_copy, test_region, None, 6, 9)
    assert check_pack(charts_pack_root_copy) == []


def test_sources_clipped_to_owned_tiles(charts_pack_root_copy, fixtures_dir, test_region):
    """Owning one zoom-10 tile, the pack lacks hazards that lie in the cell's other tiles; they are not
    reported. The safety layer check stays pack-wide, so its errors are the only ones left."""
    tiles = sorted(_z10_tiles(charts_pack_root_copy))
    assert len(tiles) > 1
    _prune(charts_pack_root_copy, test_region, {tiles[0]}, 10, 16)
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert errs == [f"enc.mbtiles: safety layer {layer} has no features at zoom {z}"
                    for z in (11, 12) for layer in ("hazard", "navaid", "light")], errs


def _hazard_z10_tile(pack):
    """A zoom-10 tile with a hazard in its zoom-16 tiles."""
    from chartpack.mbtiles import MBTiles, decode_pbf

    with MBTiles.open(pack / "enc.mbtiles") as m:
        return next((x >> 6, y >> 6) for x, y, data in m.tiles_at(16) if decode_pbf(data).get("hazard"))


def _as_overview(pack, test_region, content):
    """Prune to the content tiles, then mark the pack as the overview (owned null) over them."""
    from chartpack.grid import keep_tiles

    keep_tiles(pack / "enc.mbtiles", content, minzoom=10, maxzoom=16)
    keep_tiles(pack / "enc.mbtiles", None, minzoom=10, maxzoom=16, content=content)
    _refresh(pack, test_region)


def test_overview_sources_clipped_to_content_tiles(charts_pack_root_copy, fixtures_dir, test_region):
    """The overview (owned null) is checked over its content tiles, not the whole cells: hazards and
    coverage of the cell outside them are not reported (#85)."""
    tile = _hazard_z10_tile(charts_pack_root_copy)
    assert len(_z10_tiles(charts_pack_root_copy)) > 1
    _as_overview(charts_pack_root_copy, test_region, {tile})
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert not [e for e in errs if "missing at zoom" in e or "cover" in e], errs


def test_overview_catches_a_missing_hazard_in_content_tiles(charts_pack_root_copy, fixtures_dir, test_region):
    tile = _hazard_z10_tile(charts_pack_root_copy)
    _as_overview(charts_pack_root_copy, test_region, {tile})
    _rewrite_tiles(charts_pack_root_copy / "enc.mbtiles", 16,
                   lambda layers: [layer for layer in layers if layer["name"] != "hazard"])
    _refresh(charts_pack_root_copy, test_region)
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert any("missing at zoom 16" in e for e in errs), errs


def test_tile_hazard_outside_owned_area_is_ignored(charts_pack_root_copy, fixtures_dir, test_region):
    """A hazard 20 tile pixels across the owned edge, in the buffer of the boundary tile, is not 'not in the
    source cells'."""
    from chartpack.mbtiles import MBTiles

    tiles = sorted(_z10_tiles(charts_pack_root_copy))
    _prune(charts_pack_root_copy, test_region, {tiles[0]}, 10, 16)
    _rewrite_tiles(charts_pack_root_copy / "enc.mbtiles", 16, lambda layers: layers)  # flatten the tiles view
    x10, y10 = tiles[0]
    layers = [{"name": "hazard", "features": [{
        "geometry": {"type": "Point", "coordinates": [-20, 2000]},
        "properties": {"class": "UWTROC", "VALSOU": "99.9", "WATLEV": 4}}]}]
    tile = gzip.compress(mapbox_vector_tile.encode(layers, default_options={"y_coord_down": True}))
    with MBTiles.open(charts_pack_root_copy / "enc.mbtiles") as m:
        m.put_tile(16, x10 * 64, y10 * 64 + 32, tile)  # west edge of the owned tile
    _refresh(charts_pack_root_copy, test_region)
    errs = check_pack(charts_pack_root_copy, enc_zips=[fixtures_dir / "US4WA1HK.zip"])
    assert errs == [f"enc.mbtiles: safety layer {layer} has no features at zoom {z}"
                    for z in (11, 12) for layer in ("hazard", "navaid", "light")], errs


def test_coarse_file_may_lack_contour_and_band(tmp_path, test_region):
    """bathy-coarse.mbtiles with only its coverage layer passes (a region whose CRM-only cells are land);
    bathy.mbtiles keeps the three-layer rule."""
    from chartpack.mbtiles import MBTiles

    root = _bathy_pack(tmp_path, test_region, {"bathy.mbtiles", "bathy-coarse.mbtiles"})
    for name in ("bathy.mbtiles", "bathy-coarse.mbtiles"):
        with MBTiles.open(root / name) as m:
            m.set_metadata({"json": json.dumps({"vector_layers": [{"id": "coverage"}]})})
    write_manifest(root, pack="bathy", region=test_region, sources=[], notice="n", built=datetime.now(timezone.utc))
    errs = check_pack(root)
    assert errs == ["bathy.mbtiles: schema layer band missing", "bathy.mbtiles: schema layer contour missing"]


def test_schema2_pack_without_new_layers_still_passes(charts_pack_root, fixtures_dir):
    """Schema 2 gains the optional nosurvey layer and the src attribute (plan 8 Task 9): a pack built without
    either passes the check as before."""
    from chartpack.enc.schema import LAYERS, OPTIONAL_LAYERS, SCHEMA_VERSION
    from chartpack.mbtiles import MBTiles

    specs = {spec.name: spec for spec in LAYERS}
    assert SCHEMA_VERSION == 2 and "nosurvey" in specs and "nosurvey" in OPTIONAL_LAYERS
    assert all("src" in specs[name].attributes for name in ("depare", "depcnt", "soundg", "lndare", "coalne"))
    with MBTiles.open(charts_pack_root / "enc.mbtiles") as m:
        layers = {l["id"]: l for l in json.loads(m.metadata()["json"])["vector_layers"]}
    assert "nosurvey" not in layers
    assert not any("src" in layers[name].get("fields", {}) for name in ("depare", "depcnt", "soundg", "lndare", "coalne"))
    assert check_pack(charts_pack_root, enc_zips=[fixtures_dir / "US4WA1HK.zip"]) == []


# ---- plan 8 Task 11: derived packs, the no-survey and Canada polygon rules (spec 7.1, 7.2)

Z, X, Y = 16, 10600, 23000  # a zoom-16 tile for the hand-made packs (about 121.77 W, 47.6 N)


def _tile_box(x0, y0, x1, y1, z=Z, x=X, y=Y):
    """A lon/lat polygon over the tile unit box (x0, y0, x1, y1) of tile z/x/y (4,096 units, y down)."""
    from shapely.geometry import Polygon
    from tilemath import to_lonlat

    return Polygon([to_lonlat(z, x, y, px, py) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])


CANADA = _tile_box(1000, 1000, 3000, 3000)  # a stand-in Canada polygon, inside the tile


def _square(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]}


def _point(x, y):
    return {"type": "Point", "coordinates": [x, y]}


def _put(path, z, x, y, layers):
    """Put one tile: layers maps a layer name to (geometry, properties) pairs in tile units."""
    from chartpack.mbtiles import MBTiles

    encoded = [{"name": name, "features": [{"geometry": g, "properties": p} for g, p in feats]}
               for name, feats in layers.items()]
    with MBTiles.open(path) as m:
        m.put_tile(z, x, y, gzip.compress(mapbox_vector_tile.encode(encoded, default_options={"y_coord_down": True})))


def _hand_pack(tmp_path, test_region, kind, tiles, *, minzoom=Z, maxzoom=Z, owned=None):
    """A charts pack holding enc.mbtiles alone (no styles): tiles maps (z, x, y) to _put layers; charts.kind kind."""
    import dataclasses

    from chartpack.enc.schema import LAYERS, OPTIONAL_LAYERS
    from chartpack.mbtiles import MBTiles

    root = tmp_path / "hand-pack"
    root.mkdir()
    built = {name for layers in tiles.values() for name in layers}
    layers = [{"id": s.name} for s in LAYERS if s.name not in OPTIONAL_LAYERS or s.name in built]
    with MBTiles.create(root / "enc.mbtiles", fmt="pbf") as m:
        m.set_metadata({
            "name": "t", "format": "pbf", "bounds": "-180,-85,180,85", "minzoom": str(minzoom),
            "maxzoom": str(maxzoom), "cheekymarine:schema": "2", "cheekymarine:pack": "charts",
            "cheekymarine:region": "t", "cheekymarine:version": "0.1.0", "cheekymarine:built": "x",
            "cheekymarine:sources": json.dumps([{"cell": "US5AAAAA", "edtn": 1, "updn": 0, "isdt": "2026-01-01"}]),
            "cheekymarine:valdco": "[]", "cheekymarine:seabed": "[]", "json": json.dumps({"vector_layers": layers}),
            **({"cheekymarine:owned": json.dumps(owned)} if owned is not None else {})})
    for (z, x, y), content in tiles.items():
        _put(root / "enc.mbtiles", z, x, y, content)
    write_manifest(root, pack="charts", region=dataclasses.replace(test_region, charts_kind=kind), sources=[],
                   notice="n", built=datetime.now(timezone.utc))
    return root


WATER = {"depare": [(_square(0, 0, 4096, 4096), {"src": "nonna10", "DRVAL1": "0", "DRVAL2": "5"})],
         "lndare": [(_square(0, 0, 10, 10), {"src": "fwa"})]}


def test_derived_layers_checked_at_every_zoom(tmp_path, test_region):
    from chartpack.pack.check import _check_derived_layers

    tiles = {(z, X >> (16 - z), Y >> (16 - z)): WATER for z in range(10, 17)}
    tiles[(14, X >> 2, Y >> 2)] = {"lndare": WATER["lndare"]}
    root = _hand_pack(tmp_path, test_region, "derived-inshore", tiles, minzoom=10, maxzoom=16)
    assert check_pack(root) == ["enc.mbtiles: derived layer depare has no features at zoom 14"]
    from chartpack.mbtiles import MBTiles

    with MBTiles.open(root / "enc.mbtiles") as m:  # an offshore pack needs no land
        assert _check_derived_layers(m, m.metadata(), "derived-offshore") == [
            "enc.mbtiles: derived layer depare has no features at zoom 14"]


def test_derived_inshore_pack_passes_check_without_navaids(tmp_path, test_region):
    root = _hand_pack(tmp_path, test_region, "derived-inshore", {(Z, X, Y): WATER})
    assert check_pack(root) == []


def test_enc_pack_still_needs_all_safety_layers(tmp_path, test_region):
    root = _hand_pack(tmp_path, test_region, "enc", {(Z, X, Y): WATER})
    errs = check_pack(root)
    assert "enc.mbtiles: safety layer navaid has no features at zoom 16" in errs
    assert "enc.mbtiles: safety layer hazard has no features at zoom 16" in errs
    manifest = json.loads((root / "manifest.json").read_text())
    del manifest["charts"]  # a pack from before plan 8: charts.kind enc
    (root / "manifest.json").write_text(json.dumps(manifest))
    assert check_pack(root) == errs


def test_depth_inside_nosurvey_fails_check(tmp_path, test_region):
    """A soundg inside a nosurvey polygon: one error naming the tile. A derived depare sharing the nosurvey edge, and
    a NOAA sounding (no src) inside it, are not errors."""
    tiles = {(Z, X, Y): {**WATER, "depare": [(_square(0, 0, 2048, 4096), {"src": "nonna10"})],
                         "nosurvey": [(_square(2048, 0, 4096, 4096), {})],
                         "soundg": [(_point(3000, 2000), {"src": "nonna10", "depth": "4.1"}),
                                    (_point(1000, 2000), {"src": "nonna10", "depth": "4.2"}),
                                    (_point(3000, 3000), {"depth": "4.3"})]}}
    root = _hand_pack(tmp_path, test_region, "derived-inshore", tiles)
    assert check_pack(root) == [f"enc.mbtiles: soundg depth inside a nosurvey area in tile {Z}/{X}/{Y}"]


def test_noaa_feature_inside_polygon_fails_check(tmp_path, test_region):
    tiles = {(Z, X, Y): {**WATER, "light": [(_point(2000, 2000), {"OBJNAM": "a"})],
                         "seabed": [(_point(2100, 2100), {"src": "enc"}), (_point(2200, 2200), {"src": "usseabed"}),
                                    (_point(500, 500), {"src": "usseabed"})]}}
    root = _hand_pack(tmp_path, test_region, "derived-inshore", tiles)
    assert check_pack(root) == []  # without the polygon nothing is checked
    tile = f"{Z}/{X}/{Y}"
    assert check_pack(root, canada=CANADA) == [f"enc.mbtiles: {layer} feature inside the Canada polygon in tile {tile}"
                                               for layer in ("light", "seabed", "seabed")]


def test_line_crossing_polygon_without_vertex_inside_fails_check(tmp_path, test_region):
    line = {"type": "LineString", "coordinates": [[500, 2000], [3500, 2000]]}
    root = _hand_pack(tmp_path, test_region, "derived-inshore", {(Z, X, Y): {**WATER, "line": [(line, {})]}})
    assert check_pack(root, canada=CANADA) == [
        f"enc.mbtiles: line feature inside the Canada polygon in tile {Z}/{X}/{Y}"]


def test_cut_edge_moved_by_simplification_passes_check(tmp_path, test_region):
    """A NOAA depare cut at the polygon's west edge (x = 1000), its edge moved 1.5 units inside by tippecanoe."""
    root = _hand_pack(tmp_path, test_region, "derived-inshore",
                      {(Z, X, Y): {**WATER, "depare": WATER["depare"] + [(_square(0, 0, 1001.5, 4096), {})]}})
    assert check_pack(root, canada=CANADA) == []


def test_derived_features_inside_polygon_pass_check(tmp_path, test_region):
    from chartpack.enc.bc import DERIVED_SRC

    tiles = {(Z, X, Y): {**WATER, "depare": [(_square(0, 0, 1500, 4096), {"src": "nonna100"})],
                         "nosurvey": [(_square(1500, 1500, 2500, 2500), {})],
                         "coalne": [({"type": "LineString", "coordinates": [[1200, 1200], [2800, 1200]]},
                                     {"src": "fwa"})],
                         "soundg": [(_point(1100 + 100 * i, 2800), {"src": s, "depth": "3"})
                                    for i, s in enumerate(DERIVED_SRC)]}}
    assert check_pack(_hand_pack(tmp_path, test_region, "derived-inshore", tiles), canada=CANADA) == []


def test_enc_contour_inside_canada_fails_bathy_check(tmp_path, test_region):
    from chartpack.mbtiles import MBTiles

    root = _bathy_pack(tmp_path, test_region, set())
    line = {"type": "LineString", "coordinates": [[1500, 500], [1500, 3500]]}
    for name, source in (("bathy.mbtiles", "enc"), ("bathy-coarse.mbtiles", "crm")):
        _put(root / name, Z, X, Y, {"contour": [(line, {"source": source, "depth_ft": 10})],
                                    "band": [(_square(0, 0, 4096, 4096), {})],
                                    "coverage": [(_square(0, 0, 4096, 4096), {"source": source})]})
        with MBTiles.open(root / name) as m:
            m.set_metadata({"minzoom": str(Z), "maxzoom": str(Z)})
    write_manifest(root, pack="bathy", region=test_region, sources=[], notice="n", built=datetime.now(timezone.utc))
    assert check_pack(root) == []
    assert check_pack(root, canada=CANADA) == [
        f"bathy.mbtiles: contour feature with source enc inside the Canada polygon in tile {Z}/{X}/{Y}"]


def _cover_pack(tmp_path, layers):
    """enc.mbtiles with the one tile Z/X/Y holding layers, owned the zoom-10 tile around it."""
    from chartpack.mbtiles import MBTiles

    path = tmp_path / "cover.mbtiles"
    with MBTiles.create(path, fmt="pbf") as m:
        m.set_metadata({"maxzoom": str(Z), "cheekymarine:owned": json.dumps([[X >> 6, Y >> 6]])})
    _put(path, Z, X, Y, layers)
    return path


def _cell(monkeypatch, hazards=()):
    """check.read_cell gives one band 4 cell covering exactly tile Z/X/Y, with the hazards (lon, lat, VALSOU)."""
    from shapely.geometry import mapping

    from chartpack.enc.reader import CellMeta, Feature
    from chartpack.pack import check

    meta = CellMeta("US4AAAAA", 4, 1, 0, "2026-01-01", mapping(_tile_box(0, 0, 4096, 4096)))
    feats = [Feature("hazard", {"type": "Point", "coordinates": [lon, lat]},
                     {"class": "UWTROC", "VALSOU": valsou, "WATLEV": 3}) for lon, lat, valsou in hazards]
    monkeypatch.setattr(check, "read_cell", lambda path: (meta, feats))


def test_cover_rule_counts_nosurvey(tmp_path, monkeypatch):
    from chartpack.mbtiles import MBTiles
    from chartpack.pack.check import _check_against_sources

    _cell(monkeypatch)
    path = _cover_pack(tmp_path, {"depare": [(_square(0, 0, 2048, 4096), {"src": "nonna10"})],
                                  "nosurvey": [(_square(2048, 0, 4096, 4096), {})]})
    with MBTiles.open(path) as m:
        assert _check_against_sources(m, m.metadata(), ["cell"], None) == []
    path.unlink()
    path = _cover_pack(tmp_path, {"depare": [(_square(0, 0, 2048, 4096), {"src": "nonna10"})]})
    with MBTiles.open(path) as m:
        assert [e[:24] for e in _check_against_sources(m, m.metadata(), ["cell"], None)] == ["depare and lndare cover "]


def test_hazard_rule_ignores_cut_canadian_side(tmp_path, monkeypatch):
    from tilemath import to_lonlat

    from chartpack.mbtiles import MBTiles
    from chartpack.pack.check import _check_against_sources

    _cell(monkeypatch, [(*to_lonlat(Z, X, Y, 2000, 2000), "1.2")])
    path = _cover_pack(tmp_path, {"depare": [(_square(0, 0, 4096, 4096), {})]})
    with MBTiles.open(path) as m:
        assert _check_against_sources(m, m.metadata(), ["cell"], CANADA) == []
        assert len(_check_against_sources(m, m.metadata(), ["cell"], None)) == 1  # the polygon is what excuses it


def test_us_side_hazard_still_required_in_rebuilt_pack(tmp_path, monkeypatch):
    from tilemath import to_lonlat

    from chartpack.mbtiles import MBTiles
    from chartpack.pack.check import _check_against_sources

    _cell(monkeypatch, [(*to_lonlat(Z, X, Y, 500, 500), "1.2")])
    path = _cover_pack(tmp_path, {"depare": [(_square(0, 0, 4096, 4096), {})]})
    with MBTiles.open(path) as m:
        errs = _check_against_sources(m, m.metadata(), ["cell"], CANADA)
    assert len(errs) == 1 and errs[0].startswith("hazard ('UWTROC', '1.2', 3) at ") and "missing at zoom 16" in errs[0]


@pytest.mark.parametrize("z", [15, 16])
def test_cut_along_long_diagonal_polygon_edge_passes_check(tmp_path, test_region, regions_dir, z):
    """A NOAA depare cut by apply_rules along a long diagonal edge of the real polygon, drawn as tippecanoe draws
    it (vertices projected and rounded to the tile unit, straight in Mercator between them), passes the check: the
    build and the check share the polygon from load_canada, whose edges are dense enough that the Mercator chord of
    a cut edge stays within the tolerance (Dixon Entrance, an edge with a 4.55 m sagitta undensified)."""
    import math

    from shapely.geometry import box, mapping, shape

    from chartpack.enc.bc import apply_rules, load_canada
    from chartpack.enc.reader import Feature
    from chartpack.pack.check import _tile_units

    canada = load_canada(regions_dir)
    (x0, y0), (x1, y1) = (-130.021, 55.338), (-130.041, 55.452)
    noaa = Feature("depare", mapping(box(x1 - 0.01, y0 - 0.01, x0 + 0.01, y1 + 0.01)), {"DRVAL1": "0"})
    cut = shapely.union_all([shape(f.geometry) for f in apply_rules([noaa], [], canada)])
    lon, lat = (x0 + x1) / 2, (y0 + y1) / 2
    n = 2**z
    x, y = int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    drawn = shapely.set_precision(_tile_units(z, x, y, cut), 1.0).intersection(box(-80, -80, 4176, 4176))
    assert not drawn.is_empty
    tiles = {(z, x, y): {**WATER, "depare": WATER["depare"] + [(mapping(p), {}) for p in shapely.get_parts(drawn)]}}
    root = _hand_pack(tmp_path, test_region, "derived-inshore", tiles, minzoom=z, maxzoom=z)
    assert check_pack(root, canada=canada) == []


@pytest.mark.parametrize("inside, errors", [(2.5, 0), (5.0, 1)])
def test_depth_edge_moved_into_nosurvey_by_tiling(tmp_path, test_region, inside, errors):
    """A derived depare cut at the nosurvey edge (x = 2048) and moved into it by tippecanoe, up to 2.5 units on a
    diagonal edge, passes; one reaching 5 units in is an error. The rule allows CANADA_TOLERANCE_UNITS, as the
    Canada rule does."""
    tiles = {(Z, X, Y): {**WATER, "depare": [(_square(0, 0, 2048 + inside, 4096), {"src": "nonna10"})],
                         "nosurvey": [(_square(2048, 0, 4096, 4096), {})]}}
    root = _hand_pack(tmp_path, test_region, "derived-inshore", tiles)
    assert len(check_pack(root)) == errors


@pytest.mark.parametrize("drawn, errors", [(False, 1), (True, 0)])
def test_straddling_area_hazard_us_part_still_required(tmp_path, monkeypatch, drawn, errors):
    """An obstruction area across the polygon's west edge (x = 1000 units), mostly inside, so its representative
    point is Canadian: its US part is kept by the build, so the check still expects it in the tiles."""
    from shapely.geometry import mapping

    from chartpack.enc.reader import CellMeta, Feature
    from chartpack.mbtiles import MBTiles
    from chartpack.pack import check
    from chartpack.pack.check import _check_against_sources

    area = _tile_box(900, 1500, 2900, 1700)
    assert CANADA.contains(area.representative_point()) and not CANADA.covers(area)
    meta = CellMeta("US4AAAAA", 4, 1, 0, "2026-01-01", mapping(_tile_box(0, 0, 4096, 4096)))
    feats = [Feature("hazard", mapping(area), {"class": "OBSTRN", "VALSOU": "3.1", "WATLEV": 3})]
    monkeypatch.setattr(check, "read_cell", lambda path: (meta, feats))
    layers = {"depare": [(_square(0, 0, 4096, 4096), {})]}
    if drawn:  # the US part, as apply_rules leaves it
        layers["hazard"] = [(_square(900, 1500, 1000, 1700), {"class": "OBSTRN", "VALSOU": "3.1", "WATLEV": 3})]
    path = _cover_pack(tmp_path, layers)
    with MBTiles.open(path) as m:
        errs = _check_against_sources(m, m.metadata(), ["cell"], CANADA)
    assert len(errs) == errors, errs
