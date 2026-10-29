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
