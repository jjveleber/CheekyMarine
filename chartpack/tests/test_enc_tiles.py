import json
from collections import Counter

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Polygon, box, shape
from shapely import STRtree
from shapely.ops import unary_union
from shapely.validation import make_valid

from chartpack.enc.reader import read_cell
from chartpack.enc.schema import LAYERS
from chartpack.enc.tiles import build_enc_mbtiles
from chartpack.region import load_region
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


def _hazard_geoms(z, tiles):
    """{(class, VALSOU, WATLEV): [lon/lat geometry]} decoded from the hazard layer at zoom z."""
    got = {}
    for x, y, data in tiles:
        for feat in decode_pbf(data).get("hazard", []):
            p = feat["properties"]
            geom = shapely.transform(
                shape(feat["geometry"]), lambda c: np.array([to_lonlat(z, x, y, px, py) for px, py in c])
            )
            got.setdefault((p["class"], p.get("VALSOU"), p.get("WATLEV")), []).append(geom)
    return got


def test_every_hazard_in_every_zoom_of_its_band(enc_pack, fixtures_dir):
    """Hazards (points, lines and polygons) keep class, VALSOU, WATLEV and position at every zoom.

    Tile coordinates are integers, so positions are compared within 1.5 tile units.
    """
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    hazards = [f for f in feats if f.layer == "hazard"]
    assert hazards
    keys = {(f.props["class"], f.props.get("VALSOU"), f.props.get("WATLEV")) for f in hazards}
    for z in ZOOMS:  # band 4 at 11-12 and fill-in at 13-16 (no band 5 in test-cell)
        got = _hazard_geoms(z, list(enc_pack.tiles_at(z)))
        tol = 1.5 * 360 / 2**z / EXTENT
        for f in hazards:
            key = (f.props["class"], f.props.get("VALSOU"), f.props.get("WATLEV"))
            pt = shape(f.geometry).representative_point()
            assert any(g.distance(pt) <= tol for g in got.get(key, [])), (z, key, pt.wkt)
        assert set(got) <= keys, z  # nothing invented


def _layer_polys(enc_pack, layer, z):
    """([lon/lat polygons], [props], STRtree) of a layer at zoom z, each clipped to its own tile."""
    polys, props = [], []
    for x, y, data in enc_pack.tiles_at(z):
        for pr, poly in _tile_polys(decode_pbf(data).get(layer, []), z, x, y):
            polys.append(poly)
            props.append(pr)
    return polys, props, STRtree(polys)


@pytest.mark.parametrize("layer, source_layer", [("depare", "depare"), ("lndare", "lndare")])
def test_every_source_polygon_present_at_every_zoom(enc_pack, fixtures_dir, layer, source_layer):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    sources = [f for f in feats if f.layer == source_layer]
    assert sources
    for z in ZOOMS:
        polys, props, tree = _layer_polys(enc_pack, layer, z)
        tol = 1.5 * 360 / 2**z / EXTENT
        for f in sources:
            for part in _polys(shape(f.geometry)):
                pt = part.representative_point()
                hits = tree.query(pt.buffer(tol))
                ok = any(
                    polys[i].distance(pt) <= tol
                    and (layer != "depare" or (props[i].get("DRVAL1"), props[i].get("DRVAL2")) == (f.props.get("DRVAL1"), f.props.get("DRVAL2")))
                    for i in hits
                )
                assert ok, (z, f.props, pt.wkt)


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
    valdco = json.loads(md["cheekymarine:valdco"])
    assert valdco and valdco == sorted(valdco, key=float) and len(set(valdco)) == len(valdco)
    assert {l["id"] for l in json.loads(md["json"])["vector_layers"]} == {l.name for l in LAYERS}


def _cell_without(fixtures_dir, layer):
    meta, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    return meta, [f for f in feats if f.layer != layer]


def test_missing_tippecanoe_names_install_script(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    monkeypatch.setattr("chartpack.enc.tiles.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="scripts/install-tippecanoe.sh"):
        build_enc_mbtiles([_cell_without(fixtures_dir, "line")], tmp_path / "o.mbtiles",
                          region=load_region(regions_dir / "test-cell.toml"), work=tmp_path / "w")


def test_layer_without_features_is_named(tmp_path, fixtures_dir, regions_dir):
    with pytest.raises(RuntimeError, match="line"):
        build_enc_mbtiles([_cell_without(fixtures_dir, "line")], tmp_path / "o.mbtiles",
                          region=load_region(regions_dir / "test-cell.toml"), work=tmp_path / "w")


def _seabed_at(enc_pack, z):
    """[(props, lon/lat geometry)] of the seabed layer at zoom z."""
    out = []
    for x, y, data in enc_pack.tiles_at(z):
        for feat in decode_pbf(data).get("seabed", []):
            geom = shapely.transform(
                shape(feat["geometry"]), lambda c: np.array([to_lonlat(z, x, y, px, py) for px, py in c])
            )
            out.append((feat["properties"], geom))
    return out


def _enc_seabed_first_zoom(f):
    """Band 4 (drawn from z11): the later of the SCAMIN zoom and, for areas and lines, the zoom at which the
    feature is about 48 px across (R37)."""
    from chartpack.enc.scamin import minzoom_for_extent, minzoom_for_scamin

    size = minzoom_for_extent(f.props["extent"]) if "extent" in f.props else 0
    return max(minzoom_for_scamin(f.props["SCAMIN"], 4), size)


@pytest.mark.parametrize("z", [13, 16])
def test_seabed_in_tiles_with_label(enc_pack, fixtures_dir, z):
    """Every source SBDARE and WEDKLP feature is in the tiles from its first zoom on (always at the pack's top
    zoom), with its codes and label."""
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    sources = [f for f in feats if f.layer == "seabed"]
    assert {f.props["class"] for f in sources} == {"SBDARE", "WEDKLP"}
    shown = [f for f in sources if _enc_seabed_first_zoom(f) <= z]
    assert shown and (z < 16 or len(shown) == len(sources))
    got = [(p, g) for p, g in _seabed_at(enc_pack, z) if p["src"] == "enc"]
    tol = 1.5 * 360 / 2**z / EXTENT
    keys = ("class", "NATSUR", "NATQUA", "CATWED", "label", "src", "cell")
    for f in shown:
        want = tuple(f.props.get(k) for k in keys)
        pt = shape(f.geometry).representative_point()
        assert any(tuple(p.get(k) for k in keys) == want and g.distance(pt) <= tol for p, g in got), (want, pt.wkt)
    assert {tuple(p.get(k) for k in keys) for p, _ in got} == {tuple(f.props.get(k) for k in keys) for f in shown}


def test_seabed_thinned_by_scamin_and_size(enc_pack, fixtures_dir):
    """SCAMIN 59999 (SBDARE) and 119999 (WEDKLP) in the test cell give minzoom 12 and 11 (R44), and a small area
    waits until it is about 48 px across (R37); below its first zoom a feature is absent, from there on it is
    always drawn (never randomly dropped)."""
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    sources = [f for f in feats if f.layer == "seabed"]
    assert len({_enc_seabed_first_zoom(f) for f in sources}) > 2  # the size rule moves some areas later
    keys = ("class", "NATSUR", "NATQUA", "CATWED", "label")
    for z in ZOOMS:
        want = {tuple(f.props.get(k) for k in keys) for f in sources if _enc_seabed_first_zoom(f) <= z}
        got = {tuple(p.get(k) for k in keys) for p, _ in _seabed_at(enc_pack, z) if p["src"] == "enc"}
        assert got == want, z


def test_build_without_seabed_features(tmp_path, fixtures_dir, regions_dir):
    """seabed is an optional layer (ruling R21): a region with none still builds."""
    out = build_enc_mbtiles([_cell_without(fixtures_dir, "seabed")], tmp_path / "o.mbtiles",
                            region=load_region(regions_dir / "test-cell.toml"), work=tmp_path / "w")
    with MBTiles.open(out) as m:
        md = m.metadata()
    assert "seabed" not in {l["id"] for l in json.loads(md["json"])["vector_layers"]}
    assert json.loads(md["cheekymarine:seabed"]) == []


def test_seabed_metadata_lists_distinct_codes(enc_pack, fixtures_dir, test_region):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    keys = ("src", "class", "NATSUR", "NATQUA", "CATWED", "folk", "substrate")
    want = {tuple(f.props.get(k) for k in keys) for f in feats + _usgs(fixtures_dir, test_region) if f.layer == "seabed"}
    got = json.loads(enc_pack.metadata()["cheekymarine:seabed"])
    assert len(got) == len(want) and {tuple(d.get(k) for k in keys) for d in got} == want


def _usgs(fixtures_dir, region):
    """The USGS fixture features the session pack is built with (tests/conftest.py)."""
    from chartpack.seabed.cmecs import read_cmecs
    from chartpack.seabed.usseabed import FILES, read_usseabed

    return (read_usseabed([fixtures_dir / "seabed" / n for n in FILES], region.bbox)
            + read_cmecs(fixtures_dir / "seabed" / "CMECS_OffshoreSeattle.zip", "seattle", region.bbox))


def test_usgs_seabed_in_tiles_not_quilted(enc_pack, fixtures_dir, test_region):
    """usSEABED samples and CMECS polygons join the seabed layer from their minzoom to the top zoom (samples
    from 13; CMECS polygons from 13 or, when smaller, from about 48 px across, R37), every one of them, with no
    cell or band (they are not quilted), and never before their minzoom."""
    sources = _usgs(fixtures_dir, test_region)
    assert {f.props["src"] for f in sources} == {"usseabed", "usgs-cmecs"}
    for z in ZOOMS:
        got = [(p, g) for p, g in _seabed_at(enc_pack, z) if p["src"] != "enc"]
        shown = [f for f in sources if f.props["tippecanoe"]["minzoom"] <= z]
        assert {(p["src"], p.get("substrate"), p.get("folk")) for p, _ in got} == {
            (f.props["src"], f.props.get("substrate"), f.props.get("folk")) for f in shown}, z
        for p, _ in got:
            assert set(p) <= {"src", "class", "folk", "substrate", "label", "extent"}, p
        if z not in (13, 16):
            continue
        tol = 1.5 * 360 / 2**z / EXTENT
        for f in shown:
            key = tuple(f.props.get(k) for k in ("src", "folk", "substrate", "label"))
            pt = shape(f.geometry).representative_point()
            assert any(tuple(p.get(k) for k in ("src", "folk", "substrate", "label")) == key and g.distance(pt) <= tol
                       for p, g in got), (key, pt.wkt)


def test_metadata_has_no_temp_paths(enc_pack):
    md = enc_pack.metadata()
    assert md["description"] == "CheekyMarine charts pack test-cell" and "generator_options" not in md
