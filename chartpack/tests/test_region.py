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


def test_seabed_defaults_to_enc_only(regions_dir):
    r = load_region(regions_dir / "test-cell.toml")
    assert r.seabed_sources == ("enc",) and r.cmecs_blocks == ()


def _with_seabed(tmp_path, regions_dir, table):
    path = tmp_path / "r.toml"
    path.write_text((regions_dir / "test-cell.toml").read_text() + "\n[seabed]\n" + table)
    return path


def test_seabed_table(tmp_path, regions_dir):
    r = load_region(_with_seabed(tmp_path, regions_dir,
                                 'sources = ["enc", "usseabed", "usgs-cmecs"]\ncmecs_blocks = ["admiralty-inlet", "seattle"]\n'))
    assert r.seabed_sources == ("enc", "usseabed", "usgs-cmecs") and r.cmecs_blocks == ("admiralty-inlet", "seattle")


@pytest.mark.parametrize("table, match", [
    ('sources = ["enc", "shorezone"]\n', "shorezone"),
    ('sources = ["usseabed"]\n', "enc"),
    ('sources = ["enc", "usgs-cmecs"]\n', "cmecs_blocks"),
    ('sources = ["enc", "usgs-cmecs"]\ncmecs_blocks = ["everett"]\n', "everett"),
    ('sources = ["enc"]\ncmecs_blocks = ["seattle"]\n', "usgs-cmecs"),
])
def test_seabed_table_errors(tmp_path, regions_dir, table, match):
    with pytest.raises(RegionError, match=match):
        load_region(_with_seabed(tmp_path, regions_dir, table))
