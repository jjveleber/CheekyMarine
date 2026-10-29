import json
from collections import Counter

import pytest
from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from chartpack.enc.reader import read_cell
from chartpack.enc.schema import LAYERS
from chartpack.mbtiles import MBTiles, decode_pbf

from tilemath import EXTENT, to_lonlat, tile_of

ZOOMS = range(11, 17)
TILE = box(0, 0, EXTENT, EXTENT)  # clip decoded polygons to the tile square, dropping the buffer


@pytest.fixture(scope="module")
def enc_pack(enc_pack_path):
    with MBTiles.open(enc_pack_path) as m:
        yield m


def _polys(geom):
    if geom.is_empty:
        return []
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in _polys(g)]
    return [geom] if isinstance(geom, Polygon) else []


def _tile_polys(feats, z, x, y):
    """(props, lon/lat polygon) of decoded tile features, clipped to the tile's own extent."""
    out = []
    for f in feats:
        g = make_valid(shape(f["geometry"])).intersection(TILE)
        for p in _polys(g):
            out.append((f["properties"], Polygon(
                [to_lonlat(z, x, y, px, py) for px, py in p.exterior.coords],
                [[to_lonlat(z, x, y, px, py) for px, py in r.coords] for r in p.interiors],
            )))
    return out


def test_counts_match_golden(enc_pack, golden):
    counts = {}
    for z in ZOOMS:
        per_layer = Counter()
        for _, _, data in enc_pack.tiles_at(z):
            for name, feats in decode_pbf(data).items():
                per_layer[name] += len(feats)
        counts[str(z)] = {l.name: per_layer.get(l.name, 0) for l in LAYERS}
    assert counts == golden("US4WA1HK_tiles.json")


def test_every_hazard_in_every_zoom_of_its_band(enc_pack, fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    expected = Counter((f.props["class"], f.props.get("VALSOU"), f.props.get("WATLEV")) for f in feats if f.layer == "hazard")
    assert expected
    for z in ZOOMS:  # band 4 at 11-12 and fill-in at 13-16 (no band 5 in test-cell)
        got = Counter()
        for _, _, data in enc_pack.tiles_at(z):
            for feat in decode_pbf(data).get("hazard", []):
                p = feat["properties"]
                got[(p["class"], p.get("VALSOU"), p.get("WATLEV"))] += 1
        # a feature can appear in several tiles (buffers), so compare keys
        assert set(got) == set(expected), z


def test_depare_values_byte_equal(enc_pack, fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    expected = {(f.props.get("DRVAL1"), f.props.get("DRVAL2")) for f in feats if f.layer == "depare"}
    got = set()
    for _, _, data in enc_pack.tiles_at(16):
        for feat in decode_pbf(data).get("depare", []):
            p = feat["properties"]
            assert all(isinstance(p.get(k), (str, type(None))) for k in ("DRVAL1", "DRVAL2"))
            got.add((p.get("DRVAL1"), p.get("DRVAL2")))
    assert got == expected


def test_depare_plus_lndare_cover_cell(enc_pack, fixtures_dir):
    meta, _ = read_cell(fixtures_dir / "US4WA1HK.zip")
    dep, land = [], []
    for x, y, data in enc_pack.tiles_at(16):
        layers = decode_pbf(data)
        dep += [p for _, p in _tile_polys(layers.get("depare", []), 16, x, y)]
        land += [p for _, p in _tile_polys(layers.get("lndare", []), 16, x, y)]
    covr = shape(meta.covr)
    union = unary_union(dep + land)
    assert covr.difference(union).area / covr.area < 1e-4
    overlap = sum(p.area for p in dep) - unary_union(dep).area
    assert overlap / covr.area < 1e-4


def test_polygon_crossing_tile_edge_is_in_both_tiles(enc_pack, fixtures_dir):
    z = 16
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    for f in feats:
        if f.layer != "depare":
            continue
        g = shape(f.geometry)
        x0, _ = tile_of(z, g.bounds[0], g.bounds[3])
        x1, _ = tile_of(z, g.bounds[2], g.bounds[3])
        if x1 != x0 + 1:
            continue
        edge_lon = to_lonlat(z, x1, 0, 0, 0)[0]
        cut = g.intersection(LineString([(edge_lon, g.bounds[1]), (edge_lon, g.bounds[3])]))
        if cut.is_empty or cut.length == 0:
            continue
        mid = cut.representative_point()
        _, y = tile_of(z, mid.x, mid.y)
        want = (f.props.get("DRVAL1"), f.props.get("DRVAL2"))
        for x in (x0, x1):
            data = enc_pack.get_tile(z, x, y)
            assert data is not None
            found = [
                p for props, p in _tile_polys(decode_pbf(data).get("depare", []), z, x, y)
                if (props.get("DRVAL1"), props.get("DRVAL2")) == want and p.intersection(g).area > 0
            ]
            assert found, (x, y, want)
        return
    pytest.fail("no depare in the fixture spans two adjacent z16 tiles in x")


def test_metadata(enc_pack, fixtures_dir):
    meta, _ = read_cell(fixtures_dir / "US4WA1HK.zip")
    md = enc_pack.metadata()
    assert md["format"] == "pbf" and md["cheekymarine:schema"] == "1" and md["cheekymarine:pack"] == "charts"
    assert md["cheekymarine:region"] == "test-cell" and md["cheekymarine:version"] == "0.1.0"
    assert md["name"] == "charts-test-cell" and md["bounds"] == "-122.4,47.7,-122.1,48.0"
    assert (md["minzoom"], md["maxzoom"]) == ("6", "16")
    assert md["cheekymarine:built"].endswith("Z")
    assert json.loads(md["cheekymarine:sources"]) == [
        {"cell": "US4WA1HK", "edtn": meta.edtn, "updn": meta.updn, "isdt": meta.isdt}
    ]
    assert {l["id"] for l in json.loads(md["json"])["vector_layers"]} == {l.name for l in LAYERS}
