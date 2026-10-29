import gzip

import mapbox_vector_tile

from chartpack.mbtiles import MBTiles, decode_pbf


def test_roundtrip_and_tms_flip(tmp_path):
    with MBTiles.create(tmp_path / "t.mbtiles", fmt="pbf") as m:
        m.put_tile(3, 1, 2, b"abc")
    with MBTiles.open(tmp_path / "t.mbtiles") as m:
        assert m.get_tile(3, 1, 2) == b"abc"
        assert m.get_tile(3, 1, 5) is None
        row = m._conn.execute("select tile_row from tiles").fetchone()[0]
        assert row == (2**3 - 1) - 2
        assert list(m.tiles_at(3)) == [(1, 2, b"abc")]
        assert list(m.tiles_at(4)) == []


def test_metadata_roundtrip(tmp_path):
    with MBTiles.create(tmp_path / "t.mbtiles", fmt="png") as m:
        m.set_metadata({"name": "x", "a": "1"})
        m.set_metadata({"a": "2"})
        assert m.metadata() == {"format": "png", "name": "x", "a": "2"}


def test_decode_pbf_gunzips_and_y_grows_downward():
    layers = [{"name": "l", "features": [{"geometry": "POINT(10 20)", "properties": {"k": "v"}}]}]
    raw = mapbox_vector_tile.encode(layers, default_options={"y_coord_down": True})
    for data in (raw, gzip.compress(raw)):
        feat = decode_pbf(data)["l"][0]
        assert feat["properties"] == {"k": "v"}
        assert feat["geometry"]["coordinates"] == [10, 20]
