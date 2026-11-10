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
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from chartpack.bathy import blocks
from chartpack.bathy.blocks import area_datum, build_block, iter_blocks
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


def _build(tile, sources_write, test_region, elev, clip=None):
    tiles, crm = sources_write(elev)
    _, core, read = _block(tile)
    datum = area_datum(test_region, Path("unused"))  # zero_geoid: no grid is read
    return core, build_block(core, read, tiles_for_bbox(tiles, read), crm, datum, clip)


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


def test_crm_only_block_coarse_z12_has_every_level(sources, test_region):
    """A block with no CUDEM value: its coarse z12 band holds the 10 ft levels with min_zoom 13 and 14 (the
    style shows them on the overzoomed z12 tiles), e.g. 250 ft with minzoom 14."""
    tiles, crm = sources(np.full((2000, 2000), NODATA, np.float32))
    _write_tif(crm, -np.tile(np.linspace(-68.0, 188.0, 400, dtype=np.float32), (400, 1)), AREA)  # 10 to 100 m deep
    _, core, read = _block(NORTH)
    result = build_block(core, read, tiles_for_bbox(tiles, read), crm, area_datum(test_region, Path("unused")), None)
    assert not result.fine_contours
    top = {(f["properties"]["depth_ft"], f["properties"]["minzoom"])
           for f in result.coarse_contours if f["tippecanoe"]["minzoom"] == 12}
    assert (250, 14) in top and (200, 13) in top and (110, 14) in top


def test_block_without_cudem_tile_skips_fine(sources, test_region, monkeypatch):
    """No CUDEM tile meets the read bounds: no fine merge, no fine features or grid; coarse builds as usual."""
    _, crm = sources(_cudem_elev())
    _, core, read = _block(NORTH)
    merges = []
    real = blocks.merge_to_mllw
    monkeypatch.setattr(blocks, "merge_to_mllw", lambda *a, **k: merges.append(k["res_deg"]) or real(*a, **k))
    result = build_block(core, read, [], crm, area_datum(test_region, Path("unused")), None)
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
    result = build_block(core, read, tiles_for_bbox(tiles, read), crm, area_datum(region, Path("unused")), None)
    grid = getattr(result, f"{kind}_grid")
    x0, dx, _, y0, _, dy = grid.transform
    lon = x0 + (np.arange(grid.data.shape[1]) + 0.5) * dx
    lat = y0 + (np.arange(grid.data.shape[0]) + 0.5) * dy
    inner = ((lon > w) & (lon < e))[None, :] & ((lat > s) & (lat < n))[:, None]
    assert np.isfinite(grid.data[inner]).all()
    np.testing.assert_allclose(grid.data[inner], 19.3, atol=1e-3)
    rim = [f for f in getattr(result, f"{kind}_contours") if f["properties"]["depth_ft"] == 80]
    assert rim and all(lake.boundary.distance(shape(f["geometry"])) < 0.005 for f in rim)


def test_clip_removes_water_in_block(sources, test_region):
    _, _, read = _block(NORTH)
    mid = (read[1] + read[3]) / 2
    clip = box(read[0] - 1, read[1] - 1, read[2] + 1, mid)  # the south half of the block
    core, result = _build(NORTH, sources, test_region, _cudem_elev(west_of=SPLIT_LON), clip=clip)
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
    (regions / "grid.toml").write_text('zoom = 10\norder = ["blk"]\n')
    (regions / "blk.toml").write_text(("overview = true\n" if overview else "") + f"""name = "blk"
charts_version = "0.1.0"
bathy_version = "0.1.0"
bbox = [-122.6, 47.8, -122.4, 47.95]

[enc]

[bathy]
sources = {'["crm"]' if overview else '["cudem", "crm"]'}
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
    grid = blocks.build_overview(bbox, crm, datum, None).coarse_grid
    x0, dx, _, y0, _, dy = grid.transform
    assert dx == pytest.approx(0.0025) and dy == pytest.approx(-0.0025)
    assert (x0 + 180) / 0.0025 == pytest.approx(round((x0 + 180) / 0.0025), abs=1e-6)
    assert (90 - y0) / 0.0025 == pytest.approx(round((90 - y0) / 0.0025), abs=1e-6)
    depth = grid.data + datum("crm", grid.transform, grid.data.shape)
    np.testing.assert_allclose(depth[:, : step // 9], 150.0, atol=100.0 / 81 + 1e-3)
    np.testing.assert_allclose(depth[:, step // 9 :], 300.0, atol=1e-3)


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
    real = blocks.merge_to_mllw
    monkeypatch.setattr(blocks, "merge_to_mllw", lambda *a, **k: merges.append(k["res_deg"]) or real(*a, **k))
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
