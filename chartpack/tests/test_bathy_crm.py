import pytest
from osgeo import gdal

from chartpack.bathy.crm import crm_wcs_url, fetch_crm
from chartpack.cache import DownloadError

BBOX = (-122.9, 47.5, -122.1, 48.3)


def _fake_download(fixtures_dir, out_type):
    def fake(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        gdal.Translate(str(dest), str(fixtures_dir / "cudem_possession_bar.tif"), outputType=out_type)
        return dest

    return fake


def test_wcs_url():
    assert crm_wcs_url(BBOX) == (
        "https://www.ngdc.noaa.gov/thredds/wcs/crm/cudem/crm_vol8_2025.nc?service=WCS&version=1.0.0"
        "&request=GetCoverage&coverage=z&crs=OGC:CRS84&bbox=-122.9,47.5,-122.1,48.3&format=GeoTIFF_Float"
    )


def test_truncated_tif_is_rejected(tmp_path, monkeypatch):
    def fake(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\0" * 100)
        return dest

    monkeypatch.setattr("chartpack.bathy.crm.download", fake)
    with pytest.raises(DownloadError):
        fetch_crm(BBOX, tmp_path)
    assert list((tmp_path / "crm").glob("*")) == []


def test_cut_strips_are_rejected(tmp_path, monkeypatch):
    import numpy as np

    def fake(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        ds = gdal.GetDriverByName("GTiff").Create(str(dest), 200, 200, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((-122.9, 0.001, 0, 48.3, 0, -0.001))
        ds.GetRasterBand(1).WriteArray(np.full((200, 200), -20.0, np.float32))
        ds = None
        dest.write_bytes(dest.read_bytes()[:-60000])  # header and tags intact, last strips cut
        return dest

    monkeypatch.setattr("chartpack.bathy.crm.download", fake)
    with pytest.raises(DownloadError):
        fetch_crm(BBOX, tmp_path)
    assert list((tmp_path / "crm").glob("*")) == []


def test_cache_path_name(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr("chartpack.bathy.crm.download", _fake_download(fixtures_dir, gdal.GDT_Float32))
    assert fetch_crm(BBOX, tmp_path) == tmp_path / "crm" / "crm_-122.9_47.5_-122.1_48.3.tif"


def test_non_float_band_is_rejected(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr("chartpack.bathy.crm.download", _fake_download(fixtures_dir, gdal.GDT_Int16))
    with pytest.raises(DownloadError):
        fetch_crm(BBOX, tmp_path)
    assert list((tmp_path / "crm").glob("*")) == []


@pytest.mark.online
def test_fetch_small_crm_box(tmp_path):
    path = fetch_crm((-122.40, 47.88, -122.35, 47.93), tmp_path)
    ds = gdal.Open(str(path))
    assert ds.RasterCount == 1
    assert ds.GetRasterBand(1).DataType == gdal.GDT_Float32


@pytest.mark.online
def test_fetch_crm_past_the_coverage_edge(tmp_path):
    """A request reaching past CRM volume 8's -127 W and 49 N edges, as wave 1's x=150 column, north-sound's top row
    and the overview read do: the WCS must answer with a readable file, and read_window must read the request."""
    import numpy as np

    from chartpack.bathy.cudem import read_window

    bbox = (-127.03, 48.97, -126.99, 49.01)
    g = read_window(str(fetch_crm(bbox, tmp_path)), bbox)
    assert np.isfinite(g.data).any() and (g.data != g.nodata).any()


def test_wcs_url_has_no_size(tmp_path):
    """The NCEI THREDDS WCS ignores width and height (it always serves native 1 arc-second), so no request
    asks for them: the url and cache name record what the server sends."""
    import inspect

    from chartpack.bathy.crm import crm_path

    url = crm_wcs_url((-125.0, 47.0, -124.0, 47.5))
    assert url.endswith("&bbox=-125.0,47.0,-124.0,47.5&format=GeoTIFF_Float")
    assert "width" not in url and "height" not in url
    for fn in (crm_wcs_url, crm_path, fetch_crm):
        assert "res_deg" not in inspect.signature(fn).parameters, fn.__name__


EDGE = (-127.03, 48.97, -126.99, 49.01)  # past CRM volume 8's west and north edges


def test_request_is_cut_to_crm_coverage(tmp_path):
    """A request is cut to CRM's coverage before it is sent, and one wholly outside sends nothing."""
    from chartpack.bathy.crm import crm_path, crm_request

    assert crm_request(EDGE) == (-127.0, 48.97, -126.99, 49.0)
    assert crm_request(BBOX) == BBOX
    assert crm_request((-127.3, 48.0, -127.1, 48.1)) is None
    assert crm_path(EDGE, tmp_path) == tmp_path / "crm" / "crm_-127.0_48.97_-126.99_49.0.tif"
    assert crm_path((-127.3, 48.0, -127.1, 48.1), tmp_path) is None
    assert fetch_crm((-127.3, 48.0, -127.1, 48.1), tmp_path) is None


def test_fetch_crm_fixes_the_west_edge_answer(tmp_path, monkeypatch):
    """At CRM's west edge the WCS (checked 2026-11-10) labels longitude from 0 to 360 (232.9999 for -127.0001)
    and its first column, the node on -127 W, holds junk heights. fetch_crm moves the file to -180 to 180 and
    blanks that column, so a read of the whole request is the overlap with nan past it."""
    import numpy as np

    from chartpack.bathy.cudem import read_window

    res = 1 / 3600
    sent = []

    def fake(url, dest, **kw):  # 37 by 108 cells: smaller than the request, labeled the WCS way
        sent.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        ds = gdal.GetDriverByName("GTiff").Create(str(dest), 37, 108, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((360 - 127.0 - res / 2, res, 0, 49.0, 0, -res))
        data = np.full((108, 37), -1000.0, np.float32)
        data[:, 0] = 1500.0  # the junk edge column
        ds.GetRasterBand(1).WriteArray(data)
        ds.GetRasterBand(1).SetNoDataValue(-1001.0)
        ds = None
        return dest

    monkeypatch.setattr("chartpack.bathy.crm.download", fake)
    path = fetch_crm(EDGE, tmp_path)
    assert sent == [crm_wcs_url((-127.0, 48.97, -126.99, 49.0))]
    g = read_window(str(path), EDGE)
    assert g.transform[0] == pytest.approx(-127.03, abs=res) and g.transform[3] == pytest.approx(49.01, abs=res)
    lon = g.transform[0] + (np.arange(g.data.shape[1]) + 0.5) * g.transform[1]
    lat = g.transform[3] + (np.arange(g.data.shape[0]) + 0.5) * g.transform[5]
    data = np.where(g.data == g.nodata, np.nan, g.data)
    assert np.isnan(data[:, lon < -127.0 + res / 2]).all() and np.isnan(data[lat > 49.0, :]).all()
    inside = data[np.ix_(lat < 48.999, lon > -126.9995)]
    assert inside.size and (inside == -1000.0).all()
