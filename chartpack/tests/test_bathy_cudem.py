import time

import numpy as np
import pytest
from osgeo import gdal

from chartpack.bathy.cudem import CudemTile, Grid, parse_urllist, read_window, tiles_for_bbox

POSSESSION = (-122.39, 47.89, -122.37, 47.91)
SOURCE_URL = (
    "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_2014_8483/"
    "wash_pugetsound/ncei19_n48x00_w122x50_2023v1.tif"
)


def _tiles(fixtures_dir):
    return parse_urllist((fixtures_dir / "cudem_urllist_excerpt.txt").read_text())


def test_parse_and_bounds(fixtures_dir):
    t = next(t for t in _tiles(fixtures_dir) if t.name == "ncei19_n47x75_w122x50_2023v1")
    assert t.bounds == (-122.5, 47.5, -122.25, 47.75) and (t.year, t.version) == (2023, 1)
    assert t.url.endswith("/wash_pugetsound/ncei19_n47x75_w122x50_2023v1.tif")


def test_parse_ignores_other_lines():
    assert parse_urllist("\nhttps://x/readme.txt\n") == []


def test_tiles_for_puget_north(fixtures_dir):
    result = tiles_for_bbox(_tiles(fixtures_dir), (-122.9, 47.5, -122.1, 48.3))
    names = [t.name for t in result]
    assert {
        "ncei19_n48x00_w122x50_2023v1",
        "ncei19_n47x75_w122x50_2023v1",
        "ncei19_n48x25_w122x25_2024v1",
        "ncei19_n48x50_w122x75_2024v1",
    } <= set(names)
    assert "ncei19_n46x25_w124x25_2024v1" not in names
    assert names == sorted(names)


def test_touching_edge_is_not_overlap():
    a = CudemTile("ncei19_n48x00_w122x50_2023v1", "u", 48.0, -122.5, 2023, 1)
    assert tiles_for_bbox([a], (-122.25, 47.75, -122.0, 48.0)) == []
    assert tiles_for_bbox([a], (-122.3, 47.9, -122.0, 48.0)) == [a]


def test_newest_version_of_same_cell_wins():
    old = CudemTile("ncei19_n48x00_w122x50_2023v1", "u1", 48.0, -122.5, 2023, 1)
    new = CudemTile("ncei19_n48x00_w122x50_2024v1", "u2", 48.0, -122.5, 2024, 1)
    assert tiles_for_bbox([old, new], (-122.4, 47.8, -122.3, 47.9)) == [new]


def test_read_window_fixture(fixtures_dir):
    g = read_window(str(fixtures_dir / "cudem_possession_bar.tif"), POSSESSION)
    assert isinstance(g, Grid)
    assert g.data.dtype == np.float32 and g.nodata == -9999.0
    water = g.data[g.data != g.nodata]
    # Possession Bar: real depths, NAVD88 metres, negative down (fixture min is -98.5 m)
    assert water.min() < -50 and water.max() < 10
    assert len(g.transform) == 6 and g.transform[5] < 0
    assert "NAVD88" in g.crs


def test_read_window_subwindow(fixtures_dir):
    g = read_window(str(fixtures_dir / "cudem_possession_bar.tif"), (-122.385, 47.895, -122.38, 47.9))
    assert 0 < g.data.shape[0] < 300 and 0 < g.data.shape[1] < 300
    assert g.transform[0] == pytest.approx(-122.385, abs=1e-4)
    assert g.transform[3] == pytest.approx(47.9, abs=1e-4)


def test_read_window_outside_raises(fixtures_dir):
    with pytest.raises(ValueError):
        read_window(str(fixtures_dir / "cudem_possession_bar.tif"), (-100.0, 30.0, -99.9, 30.1))


@pytest.mark.online
def test_vsicurl_window_is_small(fixtures_dir):
    lon, lat = -122.38, 47.90
    bbox = (lon - 0.0015, lat - 0.0015, lon + 0.0015, lat + 0.0015)  # about 97 px
    t0 = time.monotonic()
    g = read_window("/vsicurl/" + SOURCE_URL, bbox)
    assert time.monotonic() - t0 < 60
    assert 90 <= g.data.shape[0] <= 105 and 90 <= g.data.shape[1] <= 105
    fx = gdal.Open(str(fixtures_dir / "cudem_possession_bar.tif"))
    fgt = fx.GetGeoTransform()
    fixture = fx.ReadAsArray()
    # centre pixel of the online window, looked up in the fixture at the same lon/lat
    r, c = g.data.shape[0] // 2, g.data.shape[1] // 2
    x = g.transform[0] + (c + 0.5) * g.transform[1]
    y = g.transform[3] + (r + 0.5) * g.transform[5]
    fr, fc = int((y - fgt[3]) / fgt[5]), int((x - fgt[0]) / fgt[1])
    assert g.data[r, c] == fixture[fr, fc]
