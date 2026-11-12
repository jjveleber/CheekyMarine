import numpy as np
import pytest
import shapely
from make_nonna import NODATA
from osgeo import gdal
from shapely.geometry import box
from test_bathy_blocks import _const, _write_nonna_over

from chartpack.enc.bc import area_km2
from chartpack.enc.nosurvey import mask, missing_in_100

BOX = (-124.40, 50.40, -124.38, 50.41)
WEST = (-124.41, 50.39, -124.39, 50.42)  # the west half of BOX, with room past its edges
EAST = box(-124.39, 50.40, -124.38, 50.41)
CELL_DEG = 0.0003  # a NONNA-10 cell here is about 0.00027 degree wide and 0.00017 high


def test_mask_is_water_without_nonna(tmp_path):
    n10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", BOX, _const(-10.0, WEST))
    n100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", BOX, _const(-10.0, WEST))
    land = box(-124.392, 50.402, -124.385, 50.406)
    expected = EAST.difference(land)
    for fine in (n10, None):  # at the NONNA-100 grid when there is no NONNA-10 (the offshore regions)
        got = mask(fine, n100, land, BOX)
        assert got.geom_type == "MultiPolygon"
        assert got.symmetric_difference(expected).within(expected.boundary.buffer(CELL_DEG * (1 if fine else 8)))
        assert got.intersection(land).area == 0 and got.difference(box(*BOX)).area == 0


def test_mask_never_overlaps_valid_cells(tmp_path):
    rng = np.random.default_rng(9)

    def raw(lon, lat):
        valid = (lon - BOX[0]) * 0.7 + (lat - BOX[1]) < 0.012  # a slanted, staircase edge
        valid &= rng.random(lon.shape) > 0.05  # and scattered one-cell holes
        return np.where(valid, -5.0, NODATA)

    n10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", BOX, raw)
    n100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", BOX, lambda lon, lat: np.full(lon.shape, NODATA))
    got = mask(n10, n100, shapely.Polygon(), BOX)
    assert not got.is_empty
    ds = gdal.Open(str(n10))
    x0, px, _, y0, _, py = ds.GetGeoTransform()
    data = ds.GetRasterBand(1).ReadAsArray()
    rows, cols = np.nonzero(data < 3e38)
    x = x0 + (cols + 0.5) * px
    y = y0 + (rows + 0.5) * py
    lon = np.degrees(x / 6378137.0)
    lat = np.degrees(2 * np.arctan(np.exp(y / 6378137.0)) - np.pi / 2)
    assert not shapely.contains_xy(got, lon, lat).any()


def test_missing_in_100_reports_area(tmp_path):
    n10 = _write_nonna_over(tmp_path / "n10.tif", "nonna10", BOX, _const(-10.0, (-124.41, 50.39, -124.37, 50.42)))
    n100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", BOX, _const(-10.0, WEST))
    # NONNA-100 cells are about 100 m wide here: the west half's edge may move by half of one
    assert missing_in_100(n10, n100, BOX) == pytest.approx(area_km2(EAST), abs=0.06)
    n100_all = _write_nonna_over(tmp_path / "all.tif", "nonna100", BOX, _const(-10.0, (-124.41, 50.39, -124.37, 50.42)))
    assert missing_in_100(n10, n100_all, BOX) == 0.0
