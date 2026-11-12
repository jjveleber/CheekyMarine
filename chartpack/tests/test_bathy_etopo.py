import numpy as np
import pytest
from osgeo import gdal
from test_bathy_blocks import AREA, NORTH, _block, _cell, _sources, _write_grid, small_grids  # noqa: F401

from chartpack.bathy import blocks, etopo
from chartpack.bathy.blocks import area_datum, build_block
from chartpack.bathy.cudem import Grid
from chartpack.bathy.etopo import CD_BELOW_MSL_M, ETOPO_URL, fetch_etopo
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


def test_fetch_etopo_uses_cache(tmp_path, monkeypatch, fixtures_dir):
    calls = []

    def fake_download(url, dest, **kw):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        gdal.Translate(str(dest), str(fixtures_dir / "cudem_possession_bar.tif"), outputType=gdal.GDT_Float32)
        return dest

    monkeypatch.setattr(etopo, "download", fake_download)
    path = fetch_etopo(tmp_path)
    assert fetch_etopo(tmp_path) == path and path.exists()
    assert calls == [ETOPO_URL]
