import numpy as np
import pytest
from osgeo import gdal
from test_bathy_blocks import AREA, NORTH, _block, _cell, _sources, _write_grid, small_grids  # noqa: F401

from chartpack.bathy import blocks, etopo
from chartpack.bathy.blocks import area_datum, build_block
from chartpack.bathy.cudem import Grid, read_window
from chartpack.bathy.merge import merge_ordered
from chartpack.bathy.etopo import CD_BELOW_MSL_M, ETOPO_URL, etopo_tiles, fetch_etopo
from chartpack.datum import geoid, offsets


def _coarse(tmp_path, test_region, elevation):
    _, core, read = _block(NORTH)
    path = _write_grid(tmp_path / "etopo.tif", elevation, AREA)
    result = build_block(core, read, _sources(etopo=path), area_datum(test_region, tmp_path), None)
    grid = result.coarse_grid
    lon, lat = (core[0] + core[2]) / 2, (core[1] + core[3]) / 2
    assert _cell(grid.transform, result.coarse_source, lon, lat) == blocks.SOURCE_NAMES.index("etopo")
    return _cell(grid.transform, grid.data, lon, lat)


def test_etopo_depth_is_msl_depth_minus_fixed_shift(small_grids, test_region, tmp_path):
    assert CD_BELOW_MSL_M == 4.0
    assert _coarse(tmp_path, test_region, -100.0) == pytest.approx(96.0)


def test_etopo_shallow_water_clamps_to_zero(small_grids, test_region, tmp_path):
    assert _coarse(tmp_path, test_region, -2.0) == 0.0


def test_etopo_land_is_shifted_not_clamped():
    """A land cell (elevation 5, depth -5) is shifted like a CRM land cell; a water cell the shift would take
    below 0 is the only one clamped."""
    depth = np.array([[-5.0, 0.0, 2.0, 10.0]], np.float32)
    grid = Grid(depth.copy(), np.nan, (0.0, 0.1, 0, 1.0, 0, -0.1), None)
    blocks._shift(grid, np.full(depth.shape, blocks.SOURCE_NAMES.index("etopo"), np.int8), _FixedDatum())
    assert grid.data.tolist() == [[-9.0, -4.0, 0.0, 6.0]]


class _FixedDatum:
    def __call__(self, source, transform, shape, *, lakes=True):
        return np.full(shape, CD_BELOW_MSL_M, np.float32)


def test_etopo_does_not_use_geoid_or_wa_stations(small_grids, test_region, tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the CRM geoid or station path ran for ETOPO")

    monkeypatch.setattr(geoid, "egm2008_to_navd88_nodes", refuse)
    monkeypatch.setattr(blocks.geoid, "egm2008_to_navd88_nodes", refuse)
    monkeypatch.setattr(blocks, "navd88_to_mllw_nodes", refuse)
    monkeypatch.setattr(offsets, "navd88_to_mllw_nodes", refuse)
    assert _coarse(tmp_path, test_region, -100.0) == pytest.approx(96.0)


def test_etopo_url_is_the_n60w135_tile():
    assert ETOPO_URL.endswith("/ETOPO_2022_v1_15s_N60W135_surface.tif")
    assert etopo._tile_url("N60W150").endswith("/ETOPO_2022_v1_15s_N60W150_surface.tif")


def test_tiles_meeting_a_bbox():
    assert etopo_tiles((-135.59, 53.0, -131.0, 55.0)) == ["N60W150", "N60W135"]
    assert etopo_tiles((-130.0, 48.0, -125.0, 50.0)) == ["N60W135"]
    assert etopo_tiles((-140.0, 48.0, -135.0, 50.0)) == ["N60W150"]  # an edge at 135 W does not meet the east tile


@pytest.mark.parametrize("bbox, name", [((-160.0, 48.0, -155.0, 50.0), "N60W165"), ((-130.0, 20.0, -125.0, 30.0), "N30W135")])
def test_tile_outside_the_two_is_error_naming_it(bbox, name):
    with pytest.raises(ValueError, match=name):
        etopo_tiles(bbox)


def test_fetch_etopo_uses_cache(tmp_path, monkeypatch, fixtures_dir):
    calls = []

    def fake_download(url, dest, **kw):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        gdal.Translate(str(dest), str(fixtures_dir / "cudem_possession_bar.tif"), outputType=gdal.GDT_Float32)
        return dest

    monkeypatch.setattr(etopo, "download", fake_download)
    bbox = (-136.0, 50.0, -134.0, 51.0)
    paths = fetch_etopo(bbox, tmp_path)
    assert fetch_etopo(bbox, tmp_path) == paths and all(p.exists() for p in paths)
    assert [p.name for p in paths] == ["ETOPO_2022_v1_15s_N60W150_surface.tif", "ETOPO_2022_v1_15s_N60W135_surface.tif"]
    assert calls == [etopo._tile_url("N60W150"), ETOPO_URL]


def _tile(path, box, value, nodata=None):
    """A 0.01 degree tile file over box holding value everywhere; nodata=None sets no NoData value."""
    w, s, e, n = box
    ds = gdal.GetDriverByName("GTiff").Create(str(path), round((e - w) / 0.01), round((n - s) / 0.01), 1, gdal.GDT_Float32)
    ds.SetGeoTransform((w, 0.01, 0, n, 0, -0.01))
    ds.SetProjection("EPSG:4326")
    band = ds.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    band.Fill(value)
    ds = None
    return path


def _merged(tiles, read):
    res = 0.0025
    window = lambda path, box=None: read_window(str(path), read if box is None else box)  # noqa: E731
    layers = blocks._coarse_layers(_sources(etopo=tiles), read, res, None, window)
    grid, source = merge_ordered(layers, read, res)
    return grid.data, source


def _two_tiles(tmp_path):
    west = _tile(tmp_path / "west.tif", (-135.2, 47.0, -135.0, 47.2), -50.0)  # no NoData value set
    east = _tile(tmp_path / "east.tif", (-135.0, 47.0, -134.8, 47.2), -80.0)
    return [west, east]


def test_block_straddling_the_tile_edge_has_both_and_no_gap(tmp_path):
    depth, source = _merged(_two_tiles(tmp_path), (-135.1, 47.05, -134.9, 47.15))
    assert np.isfinite(depth).all()  # no seam gap
    values = set(np.unique(depth))  # both tiles, no zero elevation padding; the seam blends them (one mosaic)
    assert {50.0, 80.0} <= values and min(values) == 50.0 and max(values) == 80.0
    assert (source == blocks.SOURCE_NAMES.index("etopo")).all()


def test_block_west_of_the_edge_reads_the_west_tile_only(tmp_path):
    depth, _ = _merged(_two_tiles(tmp_path), (-135.15, 47.05, -135.05, 47.15))
    assert (depth == 50.0).all()


def test_overhang_past_every_tile_stays_empty_not_land(tmp_path):
    depth, source = _merged(_two_tiles(tmp_path), (-135.3, 47.05, -135.1, 47.15))  # west half past the west tile
    cols = depth.shape[1]
    assert (depth[:, : cols // 2 - 2] != depth[:, : cols // 2 - 2]).all()  # nan, not 0.0 elevation
    assert (depth[:, cols // 2 + 2 :] == 50.0).all()
    assert (source[:, : cols // 2 - 2] == 0).all()


def test_block_outside_every_tile_adds_no_layer(tmp_path):
    assert _merged_layers(_two_tiles(tmp_path), (-134.0, 47.05, -133.9, 47.15)) == []


def _merged_layers(tiles, read):
    return blocks._coarse_layers(_sources(etopo=tiles), read, 0.0025, None, lambda *a: pytest.fail("read a tile"))


def test_etopo_land_cell_stays_land_through_build_block(small_grids, test_region, tmp_path):
    assert _coarse(tmp_path, test_region, 5.0) == pytest.approx(-9.0)  # land: shifted like CRM land, never clamped to a water 0.0


def test_block_across_the_tile_seam_has_no_empty_column(tmp_path):
    """Two ETOPO stand-ins at the real 15 arc-second grid meeting at -135.0, read for a block at 1 arc-second: the
    per-tile warp left up to 22 columns at the seam (-135.004 to -135.0) with no value for some block windows, as
    bc-offshore-north's blocks cross it (plan8-checkfix F4, fix round 1). One mosaic leaves none."""
    from test_bathy_blocks import _write_tif

    res_etopo, tiles = 1 / 240, []
    for name, (w, e) in (("west", (-135.5, -135.0)), ("east", (-135.0, -134.5))):
        cols, rows = round((e - w) / res_etopo), round(0.5 / res_etopo)
        lon = w + (np.arange(cols) + 0.5) * res_etopo
        _write_tif(tmp_path / f"{name}.tif", np.broadcast_to(-(200 + 100 * (lon + 135.5)), (rows, cols)),
                   (w, 47.0, e, 47.5))
        tiles.append(tmp_path / f"{name}.tif")
    res = blocks.COARSE_RES_DEG
    read = (-135.2727777778, 47.1, -134.8825, 47.3)  # a block read box on the 1 arc-second grid
    window = lambda path, box=None: read_window(str(path), read if box is None else box)  # noqa: E731
    grid, _ = merge_ordered(blocks._coarse_layers(_sources(etopo=tiles), read, res, None, window), read, res)
    lon = read[0] + (np.arange(grid.data.shape[1]) + 0.5) * res
    near = np.abs(lon + 135.0) < 0.05
    assert near.any() and np.isfinite(grid.data[:, near]).all()
