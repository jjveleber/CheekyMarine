import pytest

from chartpack.region import RegionError, load_region


def test_load_test_cell_region(regions_dir):
    r = load_region(regions_dir / "test-cell.toml")
    assert r.name == "test-cell"
    assert r.cells == {4: ["US4WA1HK"]}
    assert r.bbox == (-122.4, 47.7, -122.1, 48.0)
    assert r.navd88_to_mllw_m == 0.715 and r.msl_to_mllw_m == 2.02
    assert r.dem_maxzoom == 14 and r.coarse_fallback == "crm"
    assert r.charts_version == "0.1.0"


def test_missing_key_is_an_error(tmp_path):
    (tmp_path / "bad.toml").write_text('name = "x"\n')
    with pytest.raises(RegionError, match="charts_version"):
        load_region(tmp_path / "bad.toml")
