import gzip
import json
import sqlite3
from datetime import datetime, timezone

import mapbox_vector_tile

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
