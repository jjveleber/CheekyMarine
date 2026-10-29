import json
from pathlib import Path

import numpy as np
import pytest
from make_ridge import NODATA
from osgeo import osr
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union
from tilemath import to_lonlat

from chartpack.bathy.bands import bands_by_zoom
from chartpack.bathy.contours import MAJOR_FT, contours_by_zoom
from chartpack.bathy.cudem import CudemTile, Grid
from chartpack.bathy.merge import COVERAGE_CELL_DEG, coverage_polygons, merge_to_mllw, tag_source, uncovered_area
from chartpack.bathy.tiles import BATHY_LAYERS, build_bathy_mbtiles, enc_fallback_contours
from chartpack.enc.reader import CellMeta, Feature, read_cell
from chartpack.mbtiles import MBTiles, decode_pbf

BBOX = (-122.4, 47.7, -122.25, 47.85)  # the south-west quarter of test-cell, where the ridge is
FALLBACK_BBOX = (-122.4, 47.7, -122.1, 47.85)  # the south half: the fallback alone in the south-east
RES = 0.002
REGION_BBOX = (-122.4, 47.7, -122.1, 48.0)
NAMES = {1: "cudem", 2: "crm"}
LABELS = {
    1: {"source": "cudem", "resolution_m": 3, "date": "2023"},
    2: {"source": "crm", "resolution_m": 30, "date": "2025"},
}


def _wkt() -> str:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    return srs.ExportToWkt()


@pytest.fixture(scope="module")
def built(test_region, tmp_path_factory):
    """Ridge as cudem over the south-west quarter, a sloped fallback over the south half, the test-cell ENC."""
    base = tmp_path_factory.mktemp("bathy_tiles")
    fixtures_dir = Path(__file__).parent / "fixtures"
    ridge = np.load(fixtures_dir / "ridge.npy")
    px = (BBOX[2] - BBOX[0]) / ridge.shape[1]
    cudem = Grid(ridge, NODATA, (BBOX[0], px, 0.0, BBOX[3], 0.0, -px), _wkt())
    slope = np.tile(np.linspace(-10.0, -100.0, 30, dtype=np.float32), (15, 1))  # deepens west to east
    fallback = Grid(slope, -9999.0, (FALLBACK_BBOX[0], 0.01, 0.0, FALLBACK_BBOX[3], 0.0, -0.01), _wkt())
    grid, source = merge_to_mllw([(cudem, "cudem")], fallback, 2.02, 0.715, REGION_BBOX, res_deg=RES)
    transform = grid.transform
    contours = tag_source(contours_by_zoom(grid.data, transform, fine=True), source, transform, NAMES)
    bands = bands_by_zoom(grid.data, transform)
    coverage = coverage_polygons(source, transform, LABELS)
    uncovered = uncovered_area(source, transform, treat_fallback_as_uncovered=False)
    enc = enc_fallback_contours([read_cell(fixtures_dir / "US4WA1HK.zip")], uncovered)
    tiles = [CudemTile("ncei19_n47x85_w122x50_2023v1", "https://example.test/a.tif", 47.85, -122.5, 2023, 1)]
    out = build_bathy_mbtiles(
        contours + enc, bands, coverage, base / "bathy.mbtiles", region=test_region, work=base / "work",
        cudem_tiles=tiles,
    )
    return {"out": out, "enc": enc, "uncovered": uncovered, "coverage": coverage, "contours": contours}


@pytest.fixture(scope="module")
def bathy_pack(built):
    with MBTiles.open(built["out"]) as m:
        yield m


def _features(pack, layer, zooms):
    for z in zooms:
        for x, y, data in pack.tiles_at(z):
            for f in decode_pbf(data).get(layer, []):
                yield z, x, y, f


def test_bathy_layers_and_metadata(bathy_pack):
    md = bathy_pack.metadata()
    assert md["cheekymarine:pack"] == "bathy"
    assert {l["id"] for l in json.loads(md["json"])["vector_layers"]} == set(BATHY_LAYERS)
    assert md["cheekymarine:schema"] == "1" and md["cheekymarine:region"] == "test-cell"
    assert md["cheekymarine:version"] == "0.1.0" and md["name"] == "bathy-test-cell"
    assert md["minzoom"] == "10" and md["maxzoom"] == "16" and md["format"] == "pbf"
    assert md["bounds"] == "-122.4,47.7,-122.1,48.0" and md["description"] == "CheekyMarine bathy pack test-cell"
    assert "generator_options" not in md and "cheekymarine:built" in md


def test_sources_metadata(bathy_pack):
    src = json.loads(bathy_pack.metadata()["cheekymarine:sources"])
    assert src["cudem"] == [
        {"name": "ncei19_n47x85_w122x50_2023v1", "url": "https://example.test/a.tif", "year": 2023, "version": 1}
    ]
    assert src["crm"].startswith("https://www.ngdc.noaa.gov/thredds/wcs/crm/cudem/crm_vol8_2025.nc")
    assert src["datum"] == {"station": "9447130", "navd88_to_mllw_m": 0.715, "msl_to_mllw_m": 2.02}


def test_contour_sources(bathy_pack):
    srcs = {f["properties"]["source"] for *_, f in _features(bathy_pack, "contour", range(10, 17))}
    assert srcs == {"cudem", "crm", "enc"}  # crm in the south-east, ENC in the north half with no grid at all


def test_contour_source_matches_coverage(built):
    """Each grid contour is tagged with the source under it: cudem lines over cudem coverage, crm over crm."""
    for name in ("cudem", "crm"):
        # coverage blocks of mixed source are labelled crm, so allow one coverage cell of slack
        area = unary_union([shape(f["geometry"]) for f in built["coverage"] if f["properties"]["source"] == name])
        area = area.buffer(COVERAGE_CELL_DEG)
        lines = [f for f in built["contours"] if f["properties"]["source"] == name]
        assert lines, name
        assert all(area.contains(shape(f["geometry"]).representative_point()) for f in lines), name
    crm_only = box(-122.24, 47.7, -122.1, 47.85)
    assert not any(shape(f["geometry"]).within(crm_only) for f in built["contours"] if f["properties"]["source"] == "cudem")


def test_enc_fallback_only_outside_coverage(built):
    assert built["enc"]
    cudem_area = unary_union(
        [shape(f["geometry"]) for f in built["coverage"] if f["properties"]["source"] == "cudem"]
    )
    for f in built["enc"]:
        assert f["properties"]["source"] == "enc"
        assert shape(f["geometry"]).intersection(cudem_area).length < 1e-9


def test_enc_fallback_properties(built):
    f = built["enc"][0]
    # test-cell is one band 4 cell: the quilt draws it over band 4's and band 5's zoom ranges
    assert {(g["tippecanoe"]["minzoom"], g["tippecanoe"]["maxzoom"]) for g in built["enc"]} == {(11, 12), (13, 16)}
    assert set(f["properties"]) == {"depth_ft", "major", "minzoom", "source"}
    assert f["properties"]["major"] is False and f["properties"]["minzoom"] == f["tippecanoe"]["minzoom"]
    assert isinstance(f["properties"]["depth_ft"], int)
    assert 6 in {g["properties"]["depth_ft"] for g in built["enc"]}  # VALDCO 1.8 m


def test_enc_fallback_quilts_overlapping_bands():
    """Band 4 and band 5 cells over the same water: each zoom draws one band's depcnt, never both."""
    square = box(-122.4, 47.7, -122.3, 47.8)
    line = {"type": "LineString", "coordinates": [[-122.39, 47.75], [-122.31, 47.75]]}

    def cell(name, band, y):
        meta = CellMeta(name, band, 1, 0, "20260101", mapping(square))
        geometry = {"type": "LineString", "coordinates": [[x, y] for x, _ in line["coordinates"]]}
        return meta, [Feature("depcnt", geometry, {"VALDCO": "9.1"}), Feature("depare", geometry, {})]

    feats = enc_fallback_contours([cell("US4X", 4, 47.75), cell("US5X", 5, 47.751)], square)
    assert feats and all(f["properties"]["source"] == "enc" for f in feats)
    for z in range(10, 17):
        drawn = [f for f in feats if f["tippecanoe"]["minzoom"] <= z <= f["tippecanoe"]["maxzoom"]]
        assert len(drawn) == (0 if z == 10 else 1), z  # band 4 at 11..12, band 5 at 13..16, none at z10
        assert all(f["properties"]["minzoom"] == f["tippecanoe"]["minzoom"] for f in drawn)
    assert {f["geometry"]["coordinates"][0][1] for f in feats if f["tippecanoe"]["minzoom"] >= 13} == {47.751}


def test_tiled_enc_contours_outside_coverage(built, bathy_pack):
    area = built["uncovered"].buffer(0.003)
    seen = 0
    for z, x, y, f in _features(bathy_pack, "contour", [12]):
        if f["properties"]["source"] != "enc" or f["geometry"]["type"] != "LineString":
            continue
        for px, py in f["geometry"]["coordinates"]:
            assert area.contains(Point(*to_lonlat(z, x, y, px, py)))
            seen += 1
    assert seen


def test_major_minor_minzoom(bathy_pack):
    z10 = {
        f["properties"]["depth_ft"]
        for *_, f in _features(bathy_pack, "contour", [10])
        if f["properties"]["source"] == "cudem"
    }
    assert z10 and z10 <= {60, 120, 180, 300, 600}
    z14 = {f["properties"]["depth_ft"] for *_, f in _features(bathy_pack, "contour", [14])}
    assert 70 in z14


def test_coverage_layer(bathy_pack):
    feats = [f for *_, f in _features(bathy_pack, "coverage", [10])]
    assert feats and all("source" in f["properties"] and "resolution_m" in f["properties"] for f in feats)
    assert "cudem" in {f["properties"]["source"] for f in feats}


def test_bands_present(bathy_pack):
    bands = [f for *_, f in _features(bathy_pack, "band", [12])]
    assert bands and {"depth_min_ft", "minzoom"} <= set(bands[0]["properties"])


def test_z10_bands_are_the_coarse_complete_set(bathy_pack):
    """At z10 the bands run between the major levels only, so they tile the water with no gaps."""
    z10 = [f["properties"] for *_, f in _features(bathy_pack, "band", [10])]
    lows = {p["depth_min_ft"] for p in z10}
    assert len(lows) >= 3 and lows - {0} <= MAJOR_FT
    assert all(p["minzoom"] == 10 for p in z10)


def test_missing_layer_is_named(test_region, tmp_path):
    line = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[-122.3, 47.8], [-122.29, 47.81]]},
        "properties": {"depth_ft": 60, "major": True, "minzoom": 10, "source": "enc"},
        "tippecanoe": {"minzoom": 10, "maxzoom": 16},
    }
    with pytest.raises(RuntimeError, match="coverage"):
        build_bathy_mbtiles([line], [], [], tmp_path / "o.mbtiles", region=test_region, work=tmp_path / "w")
