"""Fine and coarse bathy built block by block over the owned zoom-10 tiles (plan 7, Task 12).

Synthetic sources only: the ridge of make_ridge.py as CUDEM and a west-to-east slope as CRM, written
as small GeoTIFFs. The grid resolutions are patched coarser than the real 1/9 and 1 arc-second so a
whole zoom-10 tile stays small; the coarse cell stays a whole number of fine cells, as in production.
"""

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import shapely
from make_ridge import NODATA, ridge_grid
from osgeo import gdal, osr
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

from chartpack.bathy import blocks
from chartpack.bathy.blocks import BlockSources, area_datum, build_block, iter_blocks
from chartpack.bathy.crm import crm_path, crm_wcs_url
from chartpack.bathy.cudem import CudemTile, parse_urllist, tiles_for_bbox
from chartpack.bathy.merge import COVERAGE_CELL_DEG
from chartpack.datum import geoid
from chartpack.grid import tile_bounds
from chartpack.mbtiles import MBTiles, decode_pbf

FINE = 0.0004
COARSE = 0.0012
AREA = (-123.0, 47.25, -122.0, 48.25)  # W, S, E, N: holds the read bounds of every block below
NORTH, SOUTH = (163, 356), (163, 357)  # two zoom-10 tiles stacked north-south near Kingston
SPLIT_LON = -122.52  # CUDEM west of here in the split tests; a multiple of COARSE from -180
FEATURES = ("fine_contours", "fine_bands", "fine_coverage", "coarse_contours", "coarse_bands", "coarse_coverage")


def _wkt() -> str:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    return srs.ExportToWkt()


def _write_tif(path, data, bbox) -> None:
    rows, cols = data.shape
    ds = gdal.GetDriverByName("GTiff").Create(str(path), cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((bbox[0], (bbox[2] - bbox[0]) / cols, 0.0, bbox[3], 0.0, -(bbox[3] - bbox[1]) / rows))
    ds.SetProjection(_wkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    band.WriteArray(data.astype(np.float32))
    ds = None


def _cudem_elev(west_of: float | None = None, patch: tuple | None = None) -> np.ndarray:
    """The ridge over AREA at 0.0005 degree, with a north-south wiggle so contours bend across tile edges.

    west_of keeps CUDEM only west of that longitude; patch keeps it only inside that (W, S, E, N) box.
    """
    elev = ridge_grid(2000, 2000) + 5.0 * np.sin(2 * np.pi * np.arange(2000) / 100)[:, None]
    lon = AREA[0] + (np.arange(2000) + 0.5) * 0.0005
    lat = AREA[3] - (np.arange(2000) + 0.5) * 0.0005
    if west_of is not None:
        elev[:, lon > west_of] = NODATA
    if patch is not None:
        w, s, e, n = patch
        inside = ((lon > w) & (lon < e))[None, :] & ((lat > s) & (lat < n))[:, None]
        elev[~inside] = NODATA
    return elev


def _crm_elev() -> np.ndarray:
    return np.tile(np.linspace(-30.0, -300.0, 400, dtype=np.float32), (400, 1))  # 0.0025 degree over AREA


def _urllist() -> str:
    """CUDEM tile urls over AREA in the NCEI naming (north-west corner), all read from the local file."""
    names = (f"ncei19_n{north:.2f}_w{-west:.2f}".replace(".", "x") + "_2023v1"
             for west in (-123.0, -122.75, -122.5, -122.25) for north in (47.5, 47.75, 48.0, 48.25))
    return "\n".join(f"https://example.test/{name}.tif" for name in names)


def _cudem_tiles() -> list[CudemTile]:
    return parse_urllist(_urllist())


@pytest.fixture
def small_grids(monkeypatch):
    monkeypatch.setattr(blocks, "FINE_RES_DEG", FINE)
    monkeypatch.setattr(blocks, "COARSE_RES_DEG", COARSE)


@pytest.fixture
def sources(tmp_path, monkeypatch, small_grids, zero_geoid):
    """write(cudem elevation) -> (cudem tiles, crm path); CUDEM urls read from the local file."""
    cudem_tif, crm_tif = tmp_path / "cudem.tif", tmp_path / "crm.tif"
    _write_tif(crm_tif, _crm_elev(), AREA)
    real = blocks.read_window
    monkeypatch.setattr(blocks, "read_window",
                        lambda src, bbox: real(str(cudem_tif) if src.startswith("/vsicurl/") else src, bbox))

    def write(elev):
        _write_tif(cudem_tif, elev, AREA)
        return _cudem_tiles(), crm_tif

    return write


def _block(tile):
    return next(b for b in iter_blocks({tile}))


def _sources(tiles=(), crm=None, nonna10=None, nonna100=None, etopo=None) -> BlockSources:
    return BlockSources(list(tiles), crm, nonna10, nonna100, etopo)


def _build(tile, sources_write, test_region, elev, lake_mask=None):
    tiles, crm = sources_write(elev)
    _, core, read = _block(tile)
    datum = area_datum(test_region, Path("unused"))  # zero_geoid: no grid is read
    return core, build_block(core, read, _sources(tiles_for_bbox(tiles, read), crm), datum, None, lake_mask=lake_mask)


def _coords(features) -> np.ndarray:
    pts = [shapely.get_coordinates(shape(f["geometry"])) for f in features]
    return np.concatenate(pts) if pts else np.empty((0, 2))


def test_iter_blocks_cover_owned_exactly(small_grids):
    owned = {(163, 356), (164, 356), (163, 357), (164, 357)}
    found = list(iter_blocks(owned))
    assert sorted(t for t, _, _ in found) == sorted(owned)
    cores = [box(*core) for _, core, _ in found]
    union = unary_union(cores)
    assert union.area == pytest.approx(sum(c.area for c in cores), rel=1e-9)  # no overlap
    tiles = unary_union([box(*tile_bounds(10, *t)) for t in owned])
    assert union.symmetric_difference(tiles).area < 1e-12
    for (x, y), core, read in found:
        assert core == tile_bounds(10, x, y)
        w, s, e, n = read
        assert core[0] - 0.02 - COARSE < w <= core[0] - 0.02 and core[1] - 0.02 - COARSE < s <= core[1] - 0.02
        assert core[2] + 0.02 <= e < core[2] + 0.02 + COARSE and core[3] + 0.02 <= n < core[3] + 0.02 + COARSE
        for v in ((w + 180) / COARSE, (s - 90) / COARSE, (e + 180) / COARSE, (n - 90) / COARSE):
            assert v == pytest.approx(round(v), abs=1e-6)  # snapped to the global coarse cell


def test_block_features_clipped_to_core(sources, test_region):
    core, result = _build(NORTH, sources, test_region, _cudem_elev(west_of=SPLIT_LON))
    w, s, e, n = core
    for name in FEATURES:
        pts = _coords(getattr(result, name))
        assert len(pts), name
        assert pts[:, 0].min() >= w - 1e-5 and pts[:, 0].max() <= e + 1e-5, name  # 1e-5: coordinates are rounded
        assert pts[:, 1].min() >= s - 1e-5 and pts[:, 1].max() <= n + 1e-5, name


def test_fine_and_coarse_split_by_source(sources, test_region):
    _, result = _build(NORTH, sources, test_region, _cudem_elev(west_of=SPLIT_LON))
    tol = 4 * FINE  # the 150 m band averages 4 by 4 fine cells
    for name in ("fine_contours", "fine_bands"):
        assert _coords(getattr(result, name))[:, 0].max() <= SPLIT_LON + tol, name
    assert _coords(result.coarse_contours)[:, 0].min() >= SPLIT_LON - tol
    under = blocks._under_cells() * COARSE  # the coarse bands run this far under the fine ones
    assert SPLIT_LON - tol - under <= _coords(result.coarse_bands)[:, 0].min() < SPLIT_LON - tol
    assert _coords(result.fine_coverage)[:, 0].max() <= SPLIT_LON + COVERAGE_CELL_DEG
    assert _coords(result.coarse_coverage)[:, 0].min() >= SPLIT_LON - COVERAGE_CELL_DEG
    assert {f["properties"]["source"] for f in result.fine_contours} == {"cudem"}
    assert {f["properties"]["source"] for f in result.coarse_contours} == {"crm"}


def test_coarse_fills_per_cell(sources, test_region):
    patch = (-122.5507, 47.8503, -122.5297, 47.8697)  # one small CUDEM patch, edges off the coarse cells
    core, result = _build(NORTH, sources, test_region, _cudem_elev(patch=patch))
    grid = result.coarse_grid
    lon = grid.transform[0] + (np.arange(grid.data.shape[1]) + 0.5) * grid.transform[1]
    lat = grid.transform[3] + (np.arange(grid.data.shape[0]) + 0.5) * grid.transform[5]
    w, s, e, n = patch
    margin = COARSE  # a coarse cell partly over the patch keeps its CRM value (coarse is drawn under fine)
    under = blocks._under_cells() * COARSE  # and so do the cells this far in, under the fine bands
    inside = ((lon > w + margin + under) & (lon < e - margin - under))[None, :] & (
        (lat > s + margin + under) & (lat < n - margin - under))[:, None]
    assert inside.any() and np.isnan(grid.data[inside]).all()
    ring = ((lon > w) & (lon < e))[None, :] & ((lat > s) & (lat < n))[:, None]
    ring &= ~(((lon > w + under) & (lon < e - under))[None, :] & ((lat > s + under) & (lat < n - under))[:, None])
    outside = ~(((lon > w - margin) & (lon < e + margin))[None, :] & ((lat > s - margin) & (lat < n + margin))[:, None])
    outside &= ((lon > core[0]) & (lon < core[2]))[None, :] & ((lat > core[1]) & (lat < core[3]))[:, None]
    assert ring.any() and np.isfinite(grid.data[ring]).all()
    assert np.isfinite(grid.data[outside]).all()
    cudem = result.fine_cudem
    assert cudem.sum() > 0 and cudem.mean() < 0.01
    k = round(COARSE / FINE)
    cells = cudem.reshape(grid.data.shape[0], k, grid.data.shape[1], k)
    partly = cells.any(axis=(1, 3)) & ~cells.all(axis=(1, 3))
    assert partly.any() and np.isfinite(grid.data[partly]).all()
    assert np.isnan(grid.data[cells.all(axis=(1, 3))]).any()
    assert result.coarse_contours and result.fine_contours
    pts = _coords(result.coarse_contours)  # the coarse contours stop at the cells fine owns: no doubled lines
    assert not ((pts[:, 0] > w + margin) & (pts[:, 0] < e - margin) & (pts[:, 1] > s + margin)
                & (pts[:, 1] < n - margin)).any()


PATCH = (-122.5507, 47.8503, -122.5297, 47.8697)  # edges off the coarse cells


@pytest.mark.parametrize("elev, lines", [
    (dict(west_of=SPLIT_LON), [((SPLIT_LON - 0.01, lat), (SPLIT_LON + 0.01, lat)) for lat in (47.8, 47.87, 47.95)]),
    (dict(patch=PATCH), [((PATCH[0] - 0.01, 47.86), (PATCH[2] + 0.01, 47.86)),
                         ((-122.54, PATCH[1] - 0.01), (-122.54, PATCH[3] + 0.01))]),
])
def test_bands_leave_no_gap_at_the_cudem_edge(sources, test_region, elev, lines):
    """At every zoom the coarse bands (overzoomed past 12) and the fine bands together fill every point of a
    line across the CUDEM edge: the coarse bands run under the fine ones instead of stopping short of them."""
    _, result = _build(NORTH, sources, test_region, _cudem_elev(**elev))

    def drawn(features, z):
        return unary_union([shape(f["geometry"]) for f in features
                            if f["tippecanoe"]["minzoom"] <= z <= f["tippecanoe"]["maxzoom"]])

    for z in range(10, 17):
        filled = drawn(result.fine_bands, z).union(drawn(result.coarse_bands, min(z, 12)))
        for a, b in lines:
            line = shapely.LineString([a, b])
            assert line.difference(filled).length < 1e-9, (z, a)


def test_coarse_bands_stay_off_dry_cudem(sources, test_region):
    """A CUDEM patch whose rim is above MLLW (fine draws no band there) over CRM water: the coarse bands do not
    run under the dry rim past the one partial coarse cell at each edge of it."""
    elev = _cudem_elev(patch=PATCH)
    lon = AREA[0] + (np.arange(2000) + 0.5) * 0.0005
    lat = AREA[3] - (np.arange(2000) + 0.5) * 0.0005
    w, s, e, n = PATCH
    inner = (w + 0.005, s + 0.005, e - 0.005, n - 0.005)
    rim = ((lon > w) & (lon < e))[None, :] & ((lat > s) & (lat < n))[:, None]
    rim &= ~(((lon > inner[0]) & (lon < inner[2]))[None, :] & ((lat > inner[1]) & (lat < inner[3]))[:, None])
    elev[rim] = 2.0
    _, result = _build(NORTH, sources, test_region, elev)
    dry = box(*PATCH).buffer(-COARSE, join_style="mitre").difference(box(*inner).buffer(COARSE, join_style="mitre"))
    coarse = unary_union([shape(f["geometry"]) for f in result.coarse_bands])
    assert coarse.intersection(dry).area < 1e-12
    assert result.fine_bands and coarse.intersects(box(*PATCH))  # the partial cells still hold coarse bands


def test_under_cells_at_the_real_resolutions():
    """Per side at z10-11 (the worst zoom): half a block-meaned cell, the band simplify tolerance at z11 (4.6e-4
    deg) and 1.5 tippecanoe tile units at z10 (1.29e-4 deg). Coarse: 6 cells of 1/3600 -> 8.33e-4 + 4.6e-4 +
    1.29e-4 = 1.42e-3; fine: 52 cells of 1/32400 -> 8.02e-4 + 4.6e-4 + 1.29e-4 = 1.39e-3; together 10.1 coarse
    cells, so 11."""
    assert blocks._under_cells() == 11


def test_crm_only_block_coarse_z12_has_every_level(sources, test_region):
    """A block with no CUDEM value: its coarse z12 band holds the 10 ft levels with min_zoom 13 and 14 (the
    style shows them on the overzoomed z12 tiles), e.g. 250 ft with minzoom 14."""
    tiles, crm = sources(np.full((2000, 2000), NODATA, np.float32))
    _write_tif(crm, -np.tile(np.linspace(-68.0, 188.0, 400, dtype=np.float32), (400, 1)), AREA)  # 10 to 100 m deep
    _, core, read = _block(NORTH)
    datum = area_datum(test_region, Path("unused"))
    result = build_block(core, read, _sources(tiles_for_bbox(tiles, read), crm), datum, None)
    assert not result.fine_contours
    top = {(f["properties"]["depth_ft"], f["properties"]["minzoom"])
           for f in result.coarse_contours if f["tippecanoe"]["minzoom"] == 12}
    assert (250, 14) in top and (200, 13) in top and (110, 14) in top


def test_block_without_cudem_tile_skips_fine(sources, test_region, monkeypatch):
    """No CUDEM tile meets the read bounds: no fine merge, no fine features or grid; coarse builds as usual."""
    _, crm = sources(_cudem_elev())
    _, core, read = _block(NORTH)
    merges = []
    real = blocks.merge_ordered
    monkeypatch.setattr(blocks, "merge_ordered", lambda layers, bbox, res_deg: merges.append(res_deg) or real(
        layers, bbox, res_deg))
    result = build_block(core, read, _sources(crm=crm), area_datum(test_region, Path("unused")), None)
    assert merges == [COARSE]
    assert not (result.fine_contours or result.fine_bands or result.fine_coverage)
    assert result.fine_grid is None and result.fine_cudem is None
    assert result.coarse_contours and result.coarse_bands and result.coarse_coverage


@pytest.mark.parametrize("kind", ["fine", "coarse"])
def test_lake_rule_stays_out_of_the_dem(kind, sources, test_region, tmp_path):
    """A flat bottom at NAVD88 -20 m under a lake whose low level is 6.0 m: the contours and bands see the lake
    depth (26 m inside, 19.3 m by the one 0.7 m station outside), but the DEM grids are the terrain with the
    station offset alone, so the hillshade draws no step along the shore."""
    from test_datum_offsets import _lake_region

    _, core, read = _block(NORTH)
    w, s, e, n = core
    lake = box(w + 0.1003, s + 0.0507, w + 0.2011, s + 0.1509)  # edges off the cells
    region = _lake_region(test_region, tmp_path, mapping(lake))
    flat = np.full((2000, 2000), -20.0, np.float32)
    tiles, crm = sources(flat if kind == "fine" else np.full((2000, 2000), NODATA, np.float32))
    _write_tif(crm, np.full((400, 400), -20.0, np.float32), AREA)
    result = build_block(core, read, _sources(tiles_for_bbox(tiles, read), crm), area_datum(region, Path("unused")),
                         None)
    grid = getattr(result, f"{kind}_grid")
    x0, dx, _, y0, _, dy = grid.transform
    lon = x0 + (np.arange(grid.data.shape[1]) + 0.5) * dx
    lat = y0 + (np.arange(grid.data.shape[0]) + 0.5) * dy
    inner = ((lon > w) & (lon < e))[None, :] & ((lat > s) & (lat < n))[:, None]
    assert np.isfinite(grid.data[inner]).all()
    np.testing.assert_allclose(grid.data[inner], 19.3, atol=1e-3)
    rim = [f for f in getattr(result, f"{kind}_contours") if f["properties"]["depth_ft"] == 80]
    assert rim and all(lake.boundary.distance(shape(f["geometry"])) < 0.005 for f in rim)


def test_lake_mask_removes_water_in_block(sources, test_region):
    """Lakes with no datum rule (the datum file's lake mask): no depth inside, in either grid or any feature."""
    _, _, read = _block(NORTH)
    mid = (read[1] + read[3]) / 2
    clip = box(read[0] - 1, read[1] - 1, read[2] + 1, mid)  # the south half of the block
    core, result = _build(NORTH, sources, test_region, _cudem_elev(west_of=SPLIT_LON), lake_mask=clip)
    inner = clip.buffer(-COVERAGE_CELL_DEG)
    for name in FEATURES:
        feats = getattr(result, name)
        assert feats, name
        assert not any(shape(f["geometry"]).intersects(inner) for f in feats), name
    for grid in (result.fine_grid, result.coarse_grid):
        lat = grid.transform[3] + (np.arange(grid.data.shape[0]) + 0.5) * grid.transform[5]
        assert np.isnan(grid.data[lat < mid]).all()
        assert np.isfinite(grid.data[lat > mid]).any()


def test_fine_dem_has_no_false_cliff(sources, test_region, tmp_path):
    """The fine DEM is the CUDEM-over-CRM merge: a z12 tile across the CUDEM edge has no 0 m cells where CRM has
    depth, and a z12 tile with no CUDEM cell is not written."""
    import io

    from PIL import Image

    from chartpack.bathy.dem import build_dem_mbtiles, terrarium_decode

    core, result = _build(NORTH, sources, test_region, _cudem_elev(west_of=SPLIT_LON))
    grid = result.fine_grid
    fine_tiles, _ = blocks.dem_tiles(blocks.fine_owned_z12(result.fine_cudem, grid.transform, NORTH), NORTH, 12)
    out = build_dem_mbtiles(grid.data, grid.transform, tmp_path / "dem.mbtiles", minzoom=12, maxzoom=12,
                            tiles=fine_tiles, within=core)

    def tile_at(lon, lat):
        n = 2**12
        return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)

    with MBTiles.open(out) as m:
        across = m.get_tile(12, *tile_at(SPLIT_LON, 47.87))
        assert across is not None
        elev = terrarium_decode(np.asarray(Image.open(io.BytesIO(across)).convert("RGB")))
        assert elev.max() < -1.0  # deep water on both sides of the CUDEM edge: no flat 0 m strip
        assert m.get_tile(12, *tile_at(-122.40, 47.87)) is None  # CRM only: the coarse DEM draws it


def _edge_ends(features, edge_lat, band_lo):
    """(depth_ft, lon, lat) of every contour end point on the latitude edge_lat in one tippecanoe band."""
    ends = []
    for f in features:
        if f["tippecanoe"]["minzoom"] != band_lo:
            continue
        coords = f["geometry"]["coordinates"]
        for lon, lat in (coords[0], coords[-1]):
            if abs(lat - edge_lat) < 2e-5:
                ends.append((f["properties"]["depth_ft"], lon, lat))
    return ends


@pytest.mark.parametrize("kind, band_lo", [("fine", 14), ("fine", 10), ("coarse", 10), ("coarse", 12)])
def test_adjacent_blocks_contours_meet(sources, test_region, kind, band_lo):
    """The two blocks either side of an edge end each contour at the same raw crossing point (native band
    and the 150 m band, which is block-mean downsampled from the fine grid)."""
    elev = _cudem_elev(west_of=SPLIT_LON)
    north_core, north = _build(NORTH, sources, test_region, elev)
    south_core, south = _build(SOUTH, sources, test_region, elev)
    edge = north_core[1]
    assert edge == south_core[3]
    a = _edge_ends(getattr(north, f"{kind}_contours"), edge, band_lo)
    b = _edge_ends(getattr(south, f"{kind}_contours"), edge, band_lo)
    assert a and len(a) == len(b)
    # Within one fine cell is the requirement; the same raw crossing gives the same point up to the 5 decimal
    # rounding of the coordinates, so the test holds the tighter bound that misaligned grids would miss.
    tol = 2e-5
    for depth, lon, lat in a:
        assert any(d == depth and abs(lon - x) <= tol and abs(lat - y) <= tol for d, x, y in b), (depth, lon)


def _region_dir(tmp_path, *, overview=False, dem_maxzoom=12):
    regions = tmp_path / "regions"
    regions.mkdir()
    shutil.copytree(Path(__file__).parent.parent / "regions" / "datum", regions / "datum")
    shutil.copytree(Path(__file__).parent.parent / "regions" / "clip", regions / "clip")  # the Canada polygon
    # the overview is in no grid: the grid holds a region pack over the same box
    (regions / "grid.toml").write_text(f'zoom = 10\norder = ["{"pk" if overview else "blk"}"]\n')
    for name in ("blk", "pk") if overview else ("blk",):
        head = "overview = true\n" if name == "blk" and overview else ""
        (regions / f"{name}.toml").write_text(head + f"""name = "{name}"
charts_version = "0.1.0"
bathy_version = "0.1.0"
bbox = [-122.6, 47.8, -122.4, 47.95]

[enc]

[bathy]
sources = {'["crm"]' if name == "blk" and overview else '["cudem", "crm"]'}
dem_maxzoom = {dem_maxzoom}

[datum]
file = "datum/wa-stations.toml"
""")
    return regions / "blk.toml"


def _zooms(path) -> set[int]:
    with MBTiles.open(path) as m:
        return {z for z in range(20) if any(True for _ in m.tiles_at(z))}


def _layer_features(path, layer) -> list[dict]:
    with MBTiles.open(path) as m:
        return [f for z in range(20) for _, _, data in m.tiles_at(z) for f in decode_pbf(data).get(layer, [])]


@pytest.fixture(scope="module")
def region_pack(tmp_path_factory):
    """build-bathy of one owned tile: CUDEM west of SPLIT_LON, CRM everywhere."""
    from chartpack.cli import main

    tmp = tmp_path_factory.mktemp("blk")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(blocks, "FINE_RES_DEG", FINE)
        mp.setattr(blocks, "COARSE_RES_DEG", COARSE)
        mp.setattr(geoid, "egm2008_to_navd88_nodes", lambda lons, lats, cache: np.zeros((len(lats), len(lons))))
        mp.setattr(geoid, "missing_grids", lambda cache: [])
        region = _region_dir(tmp)
        cache = tmp / "cache"
        (cache / "cudem").mkdir(parents=True)
        (cache / "crm").mkdir()
        (cache / "cudem" / "urllist8483.txt").write_text(_urllist())
        cudem_tif = tmp / "cudem.tif"
        _write_tif(cudem_tif, _cudem_elev(west_of=SPLIT_LON), AREA)
        for _, _, read in iter_blocks({NORTH}):
            _write_tif(crm_path(read, cache), _crm_elev(), AREA)
        real = blocks.read_window
        mp.setattr(blocks, "read_window",
                   lambda src, bbox: real(str(cudem_tif) if src.startswith("/vsicurl/") else src, bbox))
        assert main(["build-bathy", str(region), str(tmp / "out"), "--cache", str(cache), "--work", str(tmp / "work")]) == 0
        root = tmp / "out" / "bathy-blk-0.1.0"
        assert main(["check", str(root)]) == 0
    return root


def test_each_output_has_coverage(region_pack):
    fine = _layer_features(region_pack / "bathy.mbtiles", "coverage")
    coarse = _layer_features(region_pack / "bathy-coarse.mbtiles", "coverage")
    assert fine and {f["properties"]["source"] for f in fine} == {"cudem"}
    assert coarse and {f["properties"]["source"] for f in coarse} == {"crm"}


def test_sources_record_the_real_requests(region_pack):
    """CUDEM tiles meeting the owned tile (not only its read margin) and the per-tile CRM request."""
    with MBTiles.open(region_pack / "bathy.mbtiles") as m:
        src = json.loads(m.metadata()["cheekymarine:sources"])
    _, core, _ = _block(NORTH)
    assert [t["name"] for t in src["cudem"]] == [t.name for t in tiles_for_bbox(_cudem_tiles(), core)]
    assert src["crm"].startswith("https://www.ngdc.noaa.gov/thredds/wcs/crm/cudem/crm_vol8_2025.nc")
    assert "per owned zoom-10 tile" in src["crm"]
    assert src["crm"] in (region_pack / "NOTICE").read_text()


def test_coarse_maxzoom_is_12(region_pack):
    for name in ("bathy-coarse.mbtiles", "dem-coarse.mbtiles"):
        with MBTiles.open(region_pack / name) as m:
            md = m.metadata()
        assert (md["minzoom"], md["maxzoom"]) == ("10", "12"), name
        # the owned zoom-10 tile holds CUDEM, so its z10 DEM tile is the fine DEM's (one source per tile)
        assert _zooms(region_pack / name) == ({11, 12} if name.startswith("dem") else {10, 11, 12}), name
        assert json.loads(md["cheekymarine:owned"]) == [list(NORTH)]
    assert max(_zooms(region_pack / "bathy.mbtiles")) == 16
    with MBTiles.open(region_pack / "dem.mbtiles") as m:
        assert m.metadata()["maxzoom"] == "12"


def _build_overview(tmp, mp):
    from chartpack.cli import main

    region = _region_dir(tmp, overview=True)
    cache = tmp / "cache"
    (cache / "crm").mkdir(parents=True)
    bounds = blocks.overview_bounds((-122.6, 47.8, -122.4, 47.95))
    cols, rows = round((bounds[2] - bounds[0]) * 3600), round((bounds[3] - bounds[1]) * 3600)
    _write_tif(crm_path(bounds, cache), np.tile(np.linspace(-30.0, -300.0, cols, dtype=np.float32), (rows, 1)),
               bounds)  # native 1 arc-second, as the WCS serves it
    reads = []
    real = blocks.read_window
    mp.setattr(blocks, "read_window", lambda src, bbox: reads.append(src) or real(src, bbox))
    assert main(["build-bathy", str(region), str(tmp / "out"), "--cache", str(cache), "--work", str(tmp / "work")]) == 0
    root = tmp / "out" / "bathy-blk-0.1.0"
    assert main(["check", str(root)]) == 0
    return root, reads


def test_overview_build_path(tmp_path, monkeypatch, zero_geoid):
    root, reads = _build_overview(tmp_path, monkeypatch)
    assert len(reads) == 1 and not reads[0].startswith("/vsicurl/")  # one CRM read, no CUDEM
    for name in ("bathy-coarse.mbtiles", "dem-coarse.mbtiles"):
        assert _zooms(root / name) == {6, 7, 8, 9}, name
        with MBTiles.open(root / name) as m:
            md = m.metadata()
        assert (md["minzoom"], md["maxzoom"]) == ("6", "9") and md["cheekymarine:owned"] == "null"
    contours = _layer_features(root / "bathy-coarse.mbtiles", "contour")
    assert contours and all(f["properties"]["major"] for f in contours)
    assert _layer_features(root / "bathy-coarse.mbtiles", "coverage")
    with MBTiles.open(root / "bathy-coarse.mbtiles") as m:
        request = json.loads(m.metadata()["cheekymarine:sources"])["crm"]
    assert request == crm_wcs_url(blocks.overview_bounds((-122.6, 47.8, -122.4, 47.95)))  # the native request
    assert "width" not in request and request in (root / "NOTICE").read_text()


def test_overview_block_means_native_crm(tmp_path, test_region, zero_geoid):
    """The overview reads CRM at its native 1 arc-second and block-means it to 0.0025 degree (9 by 9 cells) on
    the global grid. West of a step on an overview cell edge a checkerboard of 100 m and 200 m depths averages
    to about 150 m in every cell (point sampling gives 100 or 200); east of it the depth is 300 m in every
    cell, including the one next to the step (a wider resampling kernel would mix the two sides)."""
    bbox = (-122.6, 47.8, -122.4, 47.95)
    read = blocks.overview_bounds(bbox)
    rows, cols = round((read[3] - read[1]) * 3600), round((read[2] - read[0]) * 3600)
    step = cols // 2 // 9 * 9  # a whole number of overview cells from the read's west edge
    elev = np.where((np.arange(rows)[:, None] + np.arange(cols)[None, :]) % 2 == 0, -100.0, -200.0)
    elev[:, step:] = -300.0
    crm = tmp_path / "crm.tif"
    _write_tif(crm, elev.astype(np.float32), read)
    datum = area_datum(test_region, Path("unused"))
    grid = blocks.build_overview(bbox, _sources(crm=crm), datum, None, Polygon()).coarse_grid
    x0, dx, _, y0, _, dy = grid.transform
    assert dx == pytest.approx(0.0025) and dy == pytest.approx(-0.0025)
    assert (x0 + 180) / 0.0025 == pytest.approx(round((x0 + 180) / 0.0025), abs=1e-6)
    assert (90 - y0) / 0.0025 == pytest.approx(round((90 - y0) / 0.0025), abs=1e-6)
    depth = grid.data + datum("crm", grid.transform, grid.data.shape)
    np.testing.assert_allclose(depth[:, : step // 9], 150.0, atol=100.0 / 81 + 1e-3)
    np.testing.assert_allclose(depth[:, step // 9 :], 300.0, atol=1e-3)


OVERVIEW_BBOX = (-122.6, 47.8, -122.4, 47.95)
OVERVIEW_WEST = box(-123.0, 47.0, -122.5, 48.5)  # the Canadian column: west of -122.5, an overview cell edge


def _overview_sources(tmp_path):
    """NONNA-100 over the overview read at 20 to 50 m with a hole, CRM (50 m) over the south half only, ETOPO
    (300 m) everywhere; returns (sources, the hole)."""
    read = blocks.overview_bounds(OVERVIEW_BBOX)
    hole = (-122.58, 47.85, -122.54, 47.90)
    nonna100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", read, lambda lon, lat: np.where(
        _inside(lon, lat, hole), _const(0.0)(lon, lat), -(20.0 + 30.0 * (np.sin(lon * 4000.0) > 0))))
    crm = _write_grid(tmp_path / "crm.tif", -50.0, (read[0], read[1], read[2], 47.875))
    etopo = _write_grid(tmp_path / "etopo.tif", -300.0, AREA)
    return _sources(crm=crm, nonna100=nonna100, etopo=[etopo]), hole


def test_overview_merges_the_coarse_sources(tmp_path, test_region, zero_geoid):
    """build_overview over the coarse sources (plan 8 spec 6): NONNA-100 first on the Canadian column, then CRM,
    then ETOPO; each on its datum before the block mean. The Nav grids are the shallowest value of each cell on
    the Canadian column (nav_depth of every source, nav_survey of NONNA-100), nan in the no-survey area and on the
    US side."""
    sources, hole = _overview_sources(tmp_path)
    datum = area_datum(test_region, Path("unused"))
    r = blocks.build_overview(OVERVIEW_BBOX, sources, datum, OVERVIEW_WEST, box(*hole))
    g, src, nav = r.coarse_grid, r.coarse_source, r.nav_depth
    assert g.transform == nav.transform and src.shape == g.data.shape == nav.data.shape == r.nav_src.shape

    def at(arr, lon, lat):
        return _cell(g.transform, arr, lon, lat)

    def crm_depth(lon, lat):  # the CRM depth on MLLW: 50 m less the datum offset there
        return 50.0 - at(datum("crm", g.transform, g.data.shape, lakes=False), lon, lat)

    name = blocks.SOURCE_NAMES
    west_north, west_hole = (-122.55, 47.93), (-122.56, 47.885)
    east_north, east_south = (-122.45, 47.93), (-122.45, 47.83)
    assert name[at(src, *west_north)] == "nonna100" and 20.0 <= at(g.data, *west_north) <= 50.0
    assert name[at(src, *west_hole)] == "etopo" and at(g.data, *west_hole) == pytest.approx(296.0)
    assert name[at(src, *east_north)] == "etopo" and at(g.data, *east_north) == pytest.approx(296.0)
    assert name[at(src, *east_south)] == "crm" and at(g.data, *east_south) == pytest.approx(crm_depth(*east_south))
    assert at(nav.data, *west_north) in (20.0, 50.0) and name[at(r.nav_src, *west_north)] == "nonna100"
    assert np.isnan(at(nav.data, *west_hole)) and np.isnan(at(nav.data, *east_north))
    assert at(r.nav_survey.data, *west_north) == at(nav.data, *west_north)
    assert np.isnan(at(r.nav_survey.data, *west_hole)) and np.isnan(at(r.nav_survey.data, *east_north))
    both = np.isfinite(nav.data)
    assert both.any() and (nav.data[both] <= g.data[both] + 1e-4).all()  # shoal: never deeper than the mean
    assert (nav.data[both] < g.data[both] - 1.0).any()
    assert not np.isfinite(nav.data[:, round((-122.5 - g.transform[0]) / g.transform[1]):]).any()  # US side: none
    grades = {(f["properties"]["source"], f["properties"]["grade"]) for f in r.coarse_coverage}
    assert grades == {("nonna100", "coarse-survey"), ("crm", "survey"), ("crm", "rough"), ("etopo", "rough")}
    assert r.coarse_contours and r.coarse_bands and r.fine_grid is None


def test_overview_nav_offshore_never_deeper_than_any_source(tmp_path, test_region, zero_geoid):
    """An overview cell that mixes NONNA-100 (50 m) and a shallower coarse value (ETOPO, 10 m after its shift):
    nav_depth, the offshore Nav grid, takes the shallowest value of every source present (10 m), while nav_survey,
    the inshore Nav grid, takes the NONNA-100 cells only (50 m)."""
    read = blocks.overview_bounds(OVERVIEW_BBOX)
    nonna100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", read,
                                 _const(-50.0, (read[0], read[1], -122.5313, read[3])))
    etopo = _write_grid(tmp_path / "etopo.tif", -14.0, AREA)
    r = blocks.build_overview(OVERVIEW_BBOX, _sources(nonna100=nonna100, etopo=[etopo]),
                              area_datum(test_region, Path("unused")), OVERVIEW_WEST, Polygon())
    nav, survey = r.nav_depth.data, r.nav_survey.data
    mixed = np.isfinite(survey) & np.isclose(nav, 10.0)
    assert mixed.any() and np.allclose(survey[mixed], 50.0)
    assert set(np.unique(nav[np.isfinite(nav)]).round(3)) == {10.0, 50.0}  # 50 m only where NONNA-100 alone
    assert (nav[np.isfinite(survey)] <= survey[np.isfinite(survey)]).all()
    assert (r.nav_src[mixed] == blocks.SOURCE_NAMES.index("etopo")).all()  # the coarsest source of the cell


def test_overview_strips_give_one_read(tmp_path, test_region, zero_geoid, monkeypatch):
    """build_overview reads in strips to bound its memory; the strips give the grids of one read."""
    sources, hole = _overview_sources(tmp_path)
    datum = area_datum(test_region, Path("unused"))
    whole = blocks.build_overview(OVERVIEW_BBOX, sources, datum, OVERVIEW_WEST, box(*hole))
    monkeypatch.setattr(blocks, "OVERVIEW_STRIP_DEG", 0.05)  # three strips, each a whole number of overview cells
    strips = blocks.build_overview(OVERVIEW_BBOX, sources, datum, OVERVIEW_WEST, box(*hole))
    for a, b in ((whole.coarse_grid, strips.coarse_grid), (whole.nav_depth, strips.nav_depth),
                 (whole.nav_survey, strips.nav_survey)):
        assert a.transform == b.transform
        np.testing.assert_allclose(a.data, b.data, atol=1e-4)
    np.testing.assert_array_equal(whole.coarse_source, strips.coarse_source)
    np.testing.assert_array_equal(whole.nav_src, strips.nav_src)


def test_overview_has_empty_fine_files(tmp_path, monkeypatch, zero_geoid):
    root, _ = _build_overview(tmp_path, monkeypatch)
    for name in ("bathy.mbtiles", "dem.mbtiles"):
        assert _zooms(root / name) == set(), name
        with MBTiles.open(root / name) as m:
            md = m.metadata()
        assert "maxzoom" in md and md["cheekymarine:pack"] == "bathy", name


def test_all_cudem_water_region_builds(tmp_path, monkeypatch, zero_geoid):
    """Water all CUDEM, CRM only on land: bathy-coarse holds coverage alone (no contour, no band) and the pack
    passes check."""
    from chartpack.cli import main

    monkeypatch.setattr(blocks, "FINE_RES_DEG", FINE)
    monkeypatch.setattr(blocks, "COARSE_RES_DEG", COARSE)
    region = _region_dir(tmp_path)
    cache = tmp_path / "cache"
    (cache / "cudem").mkdir(parents=True)
    (cache / "cudem" / "urllist8483.txt").write_text(_urllist())
    cudem_tif = tmp_path / "cudem.tif"
    _write_tif(cudem_tif, _cudem_elev(west_of=SPLIT_LON), AREA)
    for _, _, read in iter_blocks({NORTH}):
        dest = crm_path(read, cache)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write_tif(dest, np.full((400, 400), 5.0, np.float32), AREA)  # CRM: land everywhere
    real = blocks.read_window
    monkeypatch.setattr(blocks, "read_window",
                        lambda src, bbox: real(str(cudem_tif) if src.startswith("/vsicurl/") else src, bbox))
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")]) == 0
    root = tmp_path / "out" / "bathy-blk-0.1.0"
    assert main(["check", str(root)]) == 0
    assert _layer_features(root / "bathy-coarse.mbtiles", "coverage")
    assert not _layer_features(root / "bathy-coarse.mbtiles", "contour")


def test_block_without_cudem_tile_writes_no_fine_dem(tmp_path, monkeypatch, zero_geoid):
    """build-bathy of a tile no CUDEM tile meets: the fine merge never runs, dem.mbtiles and bathy.mbtiles hold
    no tiles, the coarse files do, and the pack passes check."""
    from chartpack.cli import main

    monkeypatch.setattr(blocks, "FINE_RES_DEG", FINE)
    monkeypatch.setattr(blocks, "COARSE_RES_DEG", COARSE)
    region = _region_dir(tmp_path)
    cache = tmp_path / "cache"
    (cache / "cudem").mkdir(parents=True)
    (cache / "cudem" / "urllist8483.txt").write_text("https://example.test/ncei19_n46x00_w125x00_2023v1.tif")
    for _, _, read in iter_blocks({NORTH}):
        dest = crm_path(read, cache)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write_tif(dest, _crm_elev(), AREA)
    merges = []
    real = blocks.merge_ordered
    monkeypatch.setattr(blocks, "merge_ordered", lambda layers, bbox, res_deg: merges.append(res_deg) or real(
        layers, bbox, res_deg))
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")]) == 0
    root = tmp_path / "out" / "bathy-blk-0.1.0"
    assert main(["check", str(root)]) == 0
    assert FINE not in merges
    assert _zooms(root / "dem.mbtiles") == set() and _zooms(root / "bathy.mbtiles") == set()
    assert _zooms(root / "dem-coarse.mbtiles") == {10, 11, 12}
    assert _layer_features(root / "bathy-coarse.mbtiles", "contour")


def _tile_at(z, lon, lat):
    n = 2**z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


@pytest.fixture(scope="module")
def dem_pack(tmp_path_factory):
    """build-bathy of NORTH to dem_maxzoom 14: CUDEM west of SPLIT_LON, so of the zoom-12 columns 652 to 655
    of the tile, 652 is all CUDEM, 653 straddles the CUDEM edge and 654 and 655 are CRM only."""
    from chartpack.cli import main

    tmp = tmp_path_factory.mktemp("dem")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(blocks, "FINE_RES_DEG", FINE)
        mp.setattr(blocks, "COARSE_RES_DEG", COARSE)
        mp.setattr(geoid, "egm2008_to_navd88_nodes", lambda lons, lats, cache: np.zeros((len(lats), len(lons))))
        mp.setattr(geoid, "missing_grids", lambda cache: [])
        region = _region_dir(tmp, dem_maxzoom=14)
        cache = tmp / "cache"
        (cache / "cudem").mkdir(parents=True)
        (cache / "crm").mkdir()
        (cache / "cudem" / "urllist8483.txt").write_text(_urllist())
        cudem_tif = tmp / "cudem.tif"
        _write_tif(cudem_tif, _cudem_elev(west_of=SPLIT_LON), AREA)
        for _, _, read in iter_blocks({NORTH}):
            _write_tif(crm_path(read, cache), _crm_elev(), AREA)
        real = blocks.read_window
        mp.setattr(blocks, "read_window",
                   lambda src, bbox: real(str(cudem_tif) if src.startswith("/vsicurl/") else src, bbox))
        assert main(["build-bathy", str(region), str(tmp / "out"), "--cache", str(cache), "--work", str(tmp / "work")]) == 0
        root = tmp / "out" / "bathy-blk-0.1.0"
        assert main(["check", str(root)]) == 0
    with MBTiles.open(root / "dem.mbtiles") as m:
        fine = {(z, x, y) for z in range(10, 15) for x, y, _ in m.tiles_at(z)}
    with MBTiles.open(root / "dem-coarse.mbtiles") as m:
        coarse = {(z, x, y) for z in range(10, 13) for x, y, _ in m.tiles_at(z)}
    return fine, coarse


def test_dem_one_source_per_tile(dem_pack):
    """No (z, x, y) at z10 to 12 is in both DEM files, and together they cover the whole owned tile there."""
    fine, coarse = dem_pack
    assert fine and coarse and not fine & coarse
    for z in (10, 11, 12):
        k = 2 ** (z - 10)
        whole = {(z, x, y) for x in range(NORTH[0] * k, (NORTH[0] + 1) * k) for y in range(NORTH[1] * k, (NORTH[1] + 1) * k)}
        assert {t for t in fine | coarse if t[0] == z} == whole, z


def test_fine_dem_below_z12_only_under_fine_owned_tiles(dem_pack):
    """Every z13 and z14 fine tile has a fine-owned z12 ancestor, and every fine-owned z12 tile has all its
    descendants to dem_maxzoom (CRM parts included: the fine DEM is the whole merge)."""
    fine, _ = dem_pack
    owned12 = {(x, y) for z, x, y in fine if z == 12}
    deep = {t for t in fine if t[0] > 12}
    assert deep and all((x >> (z - 12), y >> (z - 12)) in owned12 for z, x, y in deep)
    for z in (13, 14):
        k = 2 ** (z - 12)
        assert {(x, y) for zz, x, y in deep if zz == z} == {
            (x * k + i, y * k + j) for x, y in owned12 for i in range(k) for j in range(k)}, z


def test_dem_ownership_by_cudem_cells(dem_pack):
    """A z12 tile straddling the CUDEM edge is fine only (with its z10 and z11 ancestors); a CRM-only z12 tile
    (and the z11 tile holding only CRM-only z12 tiles) is coarse only."""
    fine, coarse = dem_pack
    lat = 47.9
    x_edge, y = _tile_at(12, SPLIT_LON, lat)
    assert x_edge == 653
    assert (12, 653, y) in fine and (12, 653, y) not in coarse
    assert (12, 652, y) in fine
    for x in (654, 655):
        assert (12, x, y) in coarse and (12, x, y) not in fine
    assert (11, 326, y >> 1) in fine and (11, 327, y >> 1) in coarse
    assert (10, *NORTH) in fine and (10, *NORTH) not in coarse


def test_fine_ownership_decided_by_the_owning_block(sources, test_region):
    """A CUDEM patch inside SOUTH's core, but within NORTH's read margin: SOUTH owns its z12 tile and NORTH owns
    no z12 tile at all, so the two blocks give one answer for the tile they both read."""
    _, south_core, _ = _block(SOUTH)
    w, s, e, n = south_core
    patch = (w + 0.05, n - 0.015, w + 0.08, n - 0.005)
    elev = _cudem_elev(patch=patch)
    _, north = _build(NORTH, sources, test_region, elev)
    _, south = _build(SOUTH, sources, test_region, elev)
    assert north.fine_cudem.any()  # NORTH reads the patch in its margin
    assert blocks.fine_owned_z12(north.fine_cudem, north.fine_grid.transform, NORTH) == set()
    tile = _tile_at(12, (patch[0] + patch[2]) / 2, (patch[1] + patch[3]) / 2)
    assert blocks.fine_owned_z12(south.fine_cudem, south.fine_grid.transform, SOUTH) == {tile}


# NONNA in the block build, source order by side of the border (plan 8 Task 6). NONNA fixtures are mosaics on the
# product's native EPSG:3857 grid (make_nonna), raw elevations as CHS stores them: depths negative.

_R = 6378137.0


def _write_nonna_over(path, product, bbox, raw) -> Path:
    """A NONNA mosaic over bbox (W, S, E, N, grown to native cell edges): raw(lon, lat) gives the stored value
    (elevation, NODATA for no data) at each native cell center, from 2D lon and lat arrays."""
    from make_nonna import edge_transform, write_nonna

    ex, px, _, ey, _, py = edge_transform(product, 0, 0)
    w, s, e, n = bbox
    x = [_R * math.radians(v) for v in (w, e)]
    y = [_R * math.log(math.tan(math.pi / 4 + math.radians(v) / 2)) for v in (n, s)]
    col0, col1 = math.floor((x[0] - ex) / px), math.ceil((x[1] - ex) / px)
    row0, row1 = math.floor((y[0] - ey) / py), math.ceil((y[1] - ey) / py)
    cx = ex + (np.arange(col0, col1) + 0.5) * px
    cy = ey + (np.arange(row0, row1) + 0.5) * py
    lon = np.degrees(cx / _R)[None, :]
    lat = np.degrees(2 * np.arctan(np.exp(cy / _R)) - np.pi / 2)[:, None]
    lon, lat = np.broadcast_arrays(lon, lat)
    return write_nonna(path, np.asarray(raw(lon, lat), np.float32), product, col0, row0)


def _inside(lon, lat, b):
    return (lon > b[0]) & (lon < b[2]) & (lat > b[1]) & (lat < b[3])


def _const(value, *boxes):
    """raw(lon, lat): value inside any of the boxes, NODATA elsewhere."""
    from make_nonna import NODATA as NONNA_NODATA

    def raw(lon, lat):
        inside = np.zeros(lon.shape, bool)
        for b in boxes:
            inside |= _inside(lon, lat, b)
        return np.where(inside, value, NONNA_NODATA)

    return raw


def _cell(transform, arr, lon, lat):
    x0, dx, _, y0, _, dy = transform
    return arr[int((lat - y0) / dy), int((lon - x0) / dx)]


def _sub(core, fw, fs, fe, fn):
    """The box at fractions (fw, fs, fe, fn) of the core."""
    w, s, e, n = core
    return (w + fw * (e - w), s + fs * (n - s), w + fe * (e - w), s + fn * (n - s))


def _center(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _split(read):
    """A canada polygon over the north half of the read box (the Canadian column), and its south edge."""
    mid = round((read[1] + read[3]) / 2, 4) + 0.00013  # off the fine and coarse cell edges
    return box(read[0] - 1, mid, read[2] + 1, read[3] + 1), mid


def _source_name(arr, transform, lon, lat):
    return blocks.SOURCE_NAMES[_cell(transform, arr, lon, lat)]


def _fine_split(sources, test_region, tmp_path):
    """CUDEM everywhere and NONNA-10 over a box across the side line: (result, box, side line latitude)."""
    tiles, crm = sources(_cudem_elev())
    _, core, read = _block(NORTH)
    canada, mid = _split(read)
    b = (core[0] + 0.05, mid - 0.03, core[0] + 0.15, mid + 0.03)
    nonna10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", b, _const(-25.0, b))
    result = build_block(core, read, _sources(tiles_for_bbox(tiles, read), crm, nonna10=nonna10),
                         area_datum(test_region, Path("unused")), canada)
    return result, b, mid


def test_canadian_side_prefers_nonna10_over_cudem(sources, test_region, tmp_path):
    result, b, mid = _fine_split(sources, test_region, tmp_path)
    lon = (b[0] + b[2]) / 2
    t = result.fine_grid.transform
    assert _source_name(result.fine_source, t, lon, mid + 0.02) == "nonna10"
    assert _cell(t, result.fine_grid.data, lon, mid + 0.02) == pytest.approx(25.0)
    assert _source_name(result.fine_source, t, lon, b[3] + 0.02) == "cudem"  # past the NONNA box: CUDEM
    assert _cell(t, result.fine_cudem, lon, mid + 0.02)  # NONNA-10 is fine-tier water
    assert {f["properties"]["source"] for f in result.fine_coverage} == {"cudem", "nonna10"}


def test_us_side_ignores_nonna(sources, test_region, tmp_path):
    result, b, mid = _fine_split(sources, test_region, tmp_path)
    lon = (b[0] + b[2]) / 2
    t = result.fine_grid.transform
    assert _source_name(result.fine_source, t, lon, mid - 0.02) == "cudem"
    rows = np.arange(result.fine_source.shape[0])
    lat = t[3] + (rows + 0.5) * t[5]
    assert not (result.fine_source[lat < mid] == blocks.SOURCE_NAMES.index("nonna10")).any()
    assert not (result.nav_src[lat < mid] != 0).any() and np.isnan(result.nav_depth.data[lat < mid]).all()


def test_cudem_fills_nonna10_holes_on_canadian_side(sources, test_region, tmp_path):
    from make_nonna import NODATA as NONNA_NODATA

    tiles, crm = sources(_cudem_elev())
    _, core, read = _block(NORTH)
    b = _sub(core, 0.2, 0.2, 0.6, 0.6)
    hole = _sub(core, 0.35, 0.35, 0.45, 0.45)
    nonna10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", b,
                                lambda lon, lat: np.where(_inside(lon, lat, hole), NONNA_NODATA, -25.0))
    result = build_block(core, read, _sources(tiles_for_bbox(tiles, read), crm, nonna10=nonna10),
                         area_datum(test_region, Path("unused")), box(*read))
    t = result.fine_grid.transform
    assert _source_name(result.fine_source, t, *_center(hole)) == "cudem"
    assert _cell(t, result.fine_cudem, *_center(hole))
    assert _source_name(result.fine_source, t, b[0] + 0.01, b[1] + 0.01) == "nonna10"


def _write_grid(path, value, *boxes) -> Path:
    """A lon/lat GeoTIFF over AREA at 0.0025 degree (as the CRM and ETOPO stand-ins): value inside the boxes,
    nodata elsewhere."""
    lon = AREA[0] + (np.arange(400) + 0.5) * 0.0025
    lat = AREA[3] - (np.arange(400) + 0.5) * 0.0025
    inside = np.zeros((400, 400), bool)
    for b in boxes:
        inside |= _inside(lon[None, :], lat[:, None], b)
    _write_tif(path, np.where(inside, value, NODATA).astype(np.float32), AREA)
    return Path(path)


def test_coarse_order_canadian_side(small_grids, zero_geoid, test_region, tmp_path):
    _, core, read = _block(NORTH)
    q = [_sub(core, 0.1, 0.1, 0.4, 0.4), _sub(core, 0.6, 0.1, 0.9, 0.4), _sub(core, 0.1, 0.6, 0.4, 0.9),
         _sub(core, 0.6, 0.6, 0.9, 0.9)]  # only nonna100, only crm, only etopo, all three
    nonna100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", read, _const(-60.0, q[0], q[3]))
    crm = _write_grid(tmp_path / "crm.tif", -70.0, q[1], q[3])
    etopo = _write_grid(tmp_path / "etopo.tif", -80.0, q[2], q[3])
    result = build_block(core, read, _sources(crm=crm, nonna100=nonna100, etopo=etopo),
                         area_datum(test_region, Path("unused")), box(*read))
    t = result.coarse_grid.transform
    assert [_source_name(result.coarse_source, t, *_center(b)) for b in q] == ["nonna100", "crm", "etopo", "nonna100"]
    assert result.fine_grid is None  # no fine-tier source in the block


def test_etopo_last_on_us_side(small_grids, zero_geoid, test_region, tmp_path):
    _, core, read = _block(NORTH)
    west = (read[0], read[1], (core[0] + core[2]) / 2, read[3])
    nonna100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", read, _const(-60.0, read))
    crm = _write_grid(tmp_path / "crm.tif", -70.0, west)
    etopo = _write_grid(tmp_path / "etopo.tif", -80.0, AREA)
    result = build_block(core, read, _sources(crm=crm, nonna100=nonna100, etopo=etopo),
                         area_datum(test_region, Path("unused")), None)
    t = result.coarse_grid.transform
    lat = (core[1] + core[3]) / 2
    assert _source_name(result.coarse_source, t, core[0] + 0.05, lat) == "crm"
    assert _source_name(result.coarse_source, t, core[2] - 0.05, lat) == "etopo"
    assert not (result.coarse_source == blocks.SOURCE_NAMES.index("nonna100")).any()
    assert result.nav_depth is None and result.nonna_valid is None  # no Canadian column


def test_no_datum_shift_for_nonna(small_grids, test_region, tmp_path, monkeypatch, zero_geoid):
    """A NONNA cell (Canadian chart datum) keeps its depth; a CUDEM cell is shifted by the station offset."""
    cudem_tif = tmp_path / "cudem.tif"
    _write_tif(cudem_tif, np.full((2000, 2000), -40.0, np.float32), AREA)
    real = blocks.read_window
    monkeypatch.setattr(blocks, "read_window",
                        lambda src, bbox: real(str(cudem_tif) if src.startswith("/vsicurl/") else src, bbox))
    _, core, read = _block(NORTH)
    canada, mid = _split(read)
    b = (core[0] + 0.05, mid - 0.03, core[0] + 0.15, mid + 0.03)
    nonna10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", b, _const(-30.0, b))
    datum = area_datum(test_region, Path("unused"))
    result = build_block(core, read, _sources(tiles_for_bbox(_cudem_tiles(), read), nonna10=nonna10), datum, canada)
    grid = result.fine_grid
    lon = (b[0] + b[2]) / 2
    assert _cell(grid.transform, grid.data, lon, mid + 0.02) == 30.0
    offset = _cell(grid.transform, datum("cudem", grid.transform, grid.data.shape, lakes=False), lon, mid - 0.02)
    assert abs(offset) > 0.1
    assert _cell(grid.transform, grid.data, lon, mid - 0.02) == pytest.approx(40.0 - offset, abs=1e-4)


def test_coverage_grade_per_source(sources, test_region, tmp_path):
    """Coverage carries the grade: survey for CUDEM, NONNA-10 and US-side CRM; coarse-survey for NONNA-100; rough
    for ETOPO and Canadian-side CRM."""
    tiles, _ = sources(_cudem_elev(west_of=SPLIT_LON))
    _, core, read = _block(NORTH)
    canada, mid = _split(read)
    n10 = (SPLIT_LON + 0.02, mid + 0.02, SPLIT_LON + 0.06, mid + 0.06)
    n100 = (SPLIT_LON + 0.08, mid + 0.02, SPLIT_LON + 0.12, mid + 0.06)
    hole = (SPLIT_LON + 0.08, mid - 0.08, SPLIT_LON + 0.12, mid - 0.04)  # no CRM: ETOPO fills (US side)
    crm = tmp_path / "crm2.tif"
    lon = AREA[0] + (np.arange(400) + 0.5) * 0.0025
    lat = AREA[3] - (np.arange(400) + 0.5) * 0.0025
    elev = _crm_elev()
    elev[_inside(lon[None, :], lat[:, None], hole)] = NODATA
    _write_tif(crm, elev, AREA)
    nonna10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", n10, _const(-25.0, n10))
    nonna100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", n100, _const(-60.0, n100))
    etopo = _write_grid(tmp_path / "etopo.tif", -80.0, AREA)
    result = build_block(core, read, _sources(tiles_for_bbox(tiles, read), crm, nonna10, nonna100, etopo),
                         area_datum(test_region, Path("unused")), canada)
    fine = {(f["properties"]["source"], f["properties"]["grade"]) for f in result.fine_coverage}
    coarse = {(f["properties"]["source"], f["properties"]["grade"]) for f in result.coarse_coverage}
    assert fine == {("cudem", "survey"), ("nonna10", "survey")}
    assert coarse == {("crm", "survey"), ("crm", "rough"), ("nonna100", "coarse-survey"), ("etopo", "rough")}
    for f in result.coarse_coverage:
        if f["properties"]["source"] == "crm":
            bounds = shape(f["geometry"]).bounds
            if f["properties"]["grade"] == "rough":
                assert bounds[1] >= mid - COVERAGE_CELL_DEG
            else:
                assert bounds[3] <= mid + COVERAGE_CELL_DEG
    assert all(f["properties"] == {**blocks.LABELS[f["properties"]["source"]], "grade": f["properties"]["grade"]}
               for f in result.coarse_coverage)


def test_nav_depth_keeps_isolated_shoal(test_region, tmp_path):
    """One native NONNA-10 cell of 3.0 m in a 50.0 m plain, at the real resolutions: nav_depth (min on depth) holds
    3.0 in every fine cell of that native cell, from nonna10."""
    data = np.full((9, 9), -50.0)
    data[4, 4] = -3.0
    result, native = _real_block(tmp_path, data, test_region)
    nav = result.nav_depth
    c, r = _native_index(nav, native)
    shoal = (c == 4) & (r == 4)
    assert shoal.sum() > 4 and (nav.data[shoal] == 3.0).all() and np.nanmin(nav.data) == 3.0
    assert (result.nav_src[shoal] == blocks.SOURCE_NAMES.index("nonna10")).all()
    assert result.nonna_valid.shape == result.fine_grid.data.shape


def test_no_blank_water_in_block(small_grids, zero_geoid, test_region, tmp_path):
    """ETOPO everywhere and nothing else: every water cell of the coarse grid in the core (what the block draws) has
    a value."""
    _, core, read = _block(NORTH)
    etopo = _write_grid(tmp_path / "etopo.tif", -200.0, AREA)
    result = build_block(core, read, _sources(etopo=etopo), area_datum(test_region, Path("unused")), None)
    grid = result.coarse_grid
    x0, dx, _, y0, _, dy = grid.transform
    lon = x0 + (np.arange(grid.data.shape[1]) + 0.5) * dx
    lat = y0 + (np.arange(grid.data.shape[0]) + 0.5) * dy
    inner = _inside(lon[None, :], lat[:, None], core)
    assert np.isfinite(grid.data[inner]).all()
    assert (result.coarse_source[inner] == blocks.SOURCE_NAMES.index("etopo")).all()
    assert result.coarse_contours or result.coarse_bands


# PR #122 review fixes, at the real fine and coarse resolutions (a real build enlarges NONNA: fine cells of about
# 3.4 m, NONNA-10 cells of about 12.7 m), over a small read box so the grids stay small.

def _native_cells(product, col, row, data, tmp_path):
    """A NONNA mosaic of data (raw elevations) whose north-west cell is native cell (col, row), and its lon/lat
    box."""
    from make_nonna import edge_transform, write_nonna

    path = write_nonna(tmp_path / f"{product}.tif", np.asarray(data, np.float32), product, col, row)
    x0, px, _, y0, _, py = edge_transform(product, col, row)
    rows, cols = np.asarray(data).shape

    def lat(y):
        return math.degrees(2 * math.atan(math.exp(y / _R)) - math.pi / 2)

    bbox = (math.degrees(x0 / _R), lat(y0 + rows * py), math.degrees((x0 + cols * px) / _R), lat(y0))
    return path, bbox, (x0, px, y0, py)


def _native_index(grid, native):
    """The native (col, row) offset, from the mosaic's north-west cell, of each fine cell center of grid."""
    x0, px, y0, py = native
    gx, dx, _, gy, _, dy = grid.transform
    rows, cols = grid.data.shape
    lon = gx + (np.arange(cols) + 0.5) * dx
    lat = gy + (np.arange(rows) + 0.5) * dy
    c = np.floor((_R * np.radians(lon) - x0) / px).astype(int)
    r = np.floor((_R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) - y0) / py).astype(int)
    return np.broadcast_arrays(c[None, :], r[:, None])


def _real_block(tmp_path, data, test_region, product="nonna10"):
    """build_block at the real resolutions over a 9 by 9 native cell mosaic of data (Canadian column)."""
    from make_nonna import A_COL, A_ROW

    k = 1 if product == "nonna10" else 8  # near the same place on either grid
    path, bbox, native = _native_cells(product, A_COL // k, A_ROW // k, data, tmp_path)
    read = blocks.snap_out(bbox, blocks.COARSE_RES_DEG)
    sources = _sources(nonna10=path) if product == "nonna10" else _sources(nonna100=path)
    return build_block(read, read, sources, area_datum(test_region, Path("unused")), box(*read)), native


def test_nav_depth_and_valid_keep_nonna_holes(tmp_path, test_region):
    """F3: no fill-in. A one-native-cell hole stays a hole of exactly that footprint in nav_depth and nonna_valid,
    for NONNA-10 and NONNA-100 alike; and a one-cell 3.0 m shoal holds 3.0 in every fine cell of that native
    cell."""
    from make_nonna import NODATA as NONNA_NODATA

    for product in ("nonna10", "nonna100"):
        data = np.full((9, 9), -50.0)
        data[4, 4] = NONNA_NODATA
        data[2, 6] = -3.0
        result, native = _real_block(tmp_path, data, test_region, product)
        nav = result.nav_depth
        c, r = _native_index(nav, native)
        hole = (c == 4) & (r == 4)
        shoal = (c == 6) & (r == 2)
        inside = (c >= 0) & (c < 9) & (r >= 0) & (r < 9)
        assert hole.sum() > 4 and shoal.sum() > 4, product
        assert np.isnan(nav.data[hole]).all() and np.isfinite(nav.data[inside & ~hole]).all(), product
        assert (result.nonna_valid == (inside & ~hole)).all(), product
        assert (nav.data[shoal] == 3.0).all(), product


def test_crm_grade_cut_at_the_border(small_grids, zero_geoid, test_region, tmp_path):
    """F4: CRM on both sides of the border in one coverage block: "rough" lies only on the Canadian side and
    "survey" only on the US side."""
    _, core, read = _block(NORTH)
    canada, mid = _split(read)
    crm = _write_grid(tmp_path / "crm.tif", -70.0, AREA)
    result = build_block(core, read, _sources(crm=crm), area_datum(test_region, Path("unused")), canada)
    graded = {"rough": [], "survey": []}
    for f in result.coarse_coverage:
        graded[f["properties"]["grade"]].append(shape(f["geometry"]))
    rough, survey = unary_union(graded["rough"]), unary_union(graded["survey"])
    assert not rough.is_empty and not survey.is_empty
    assert rough.bounds[1] >= mid - 1e-9 and survey.bounds[3] <= mid + 1e-9
    assert rough.intersection(survey).area < 1e-12
    assert abs(rough.union(survey).area - box(*core).area) < 1e-9  # together they still cover the core


@pytest.mark.parametrize("product", ["nonna10", "nonna100"])
def test_fish_nonna_cells_read_true(tmp_path, test_region, product):
    """Owner ruling (2026-11-12): the Fish grids draw NONNA as exact squares (nearest). At the real resolutions
    (NONNA-10 in the fine grid, NONNA-100 in the coarse grid) a one-cell 3.0 m shoal reads 3.0 and a one-cell
    drying height of 1.5 m reads -1.5 in every grid cell of that native cell, and the plain reads 50.0."""
    data = np.full((9, 9), -50.0)
    data[2, 2] = -3.0
    data[6, 6] = 1.5
    result, native = _real_block(tmp_path, data, test_region, product)
    grid = result.fine_grid if product == "nonna10" else result.coarse_grid
    source = result.fine_source if product == "nonna10" else result.coarse_source
    c, r = _native_index(grid, native)
    shoal, drying = (c == 2) & (r == 2), (c == 6) & (r == 6)
    inside = (c >= 0) & (c < 9) & (r >= 0) & (r < 9)
    assert shoal.sum() > 1 and drying.sum() > 1, product
    assert (grid.data[shoal] == 3.0).all() and (grid.data[drying] == -1.5).all(), product
    assert (grid.data[inside & ~shoal & ~drying] == 50.0).all(), product
    assert (source[inside] == blocks.SOURCE_NAMES.index(product)).all(), product


@pytest.mark.parametrize("product", ["nonna10", "nonna100"])
def test_nonna_coverage_cut_at_the_border(small_grids, zero_geoid, test_region, tmp_path, product):
    """PR #122 re-check: NONNA on both sides of the side line (it is used on the Canadian side only): its coverage
    (fine for NONNA-10, coarse for NONNA-100) ends exactly at the line, not one coverage block onto US water."""
    _, core, read = _block(NORTH)
    canada, mid = _split(read)
    b = (core[0] + 0.05, mid - 0.03, core[0] + 0.15, mid + 0.03)
    path = _write_nonna_over(tmp_path / f"{product}.tif", product, b, _const(-25.0, b))
    result = build_block(core, read, _sources(**{product: path}), area_datum(test_region, Path("unused")), canada)
    feats = [f for f in result.fine_coverage + result.coarse_coverage if f["properties"]["source"] == product]
    assert feats, product
    covered = unary_union([shape(f["geometry"]) for f in feats])
    assert covered.bounds[1] >= mid - 1e-9, (product, covered.bounds[1], mid)
    assert covered.bounds[3] > mid + 0.02  # it still covers the Canadian side
