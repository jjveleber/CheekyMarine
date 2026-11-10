import pytest

from chartpack.region import RegionError, load_region


def test_load_test_cell_region(regions_dir):
    r = load_region(regions_dir / "test-cell.toml")
    assert r.name == "test-cell"
    assert r.cells == {4: ["US4WA1HK"]}
    assert r.bbox == (-122.4, 47.7, -122.1, 48.0)
    assert r.datum_file == regions_dir / "datum" / "wa-stations.toml"
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


def test_overview_must_be_a_boolean(tmp_path, regions_dir):
    path = tmp_path / "r.toml"
    path.write_text('overview = "false"\n' + (regions_dir / "test-cell.toml").read_text())
    with pytest.raises(RegionError, match="overview must be true or false"):
        load_region(path)


def test_overview_flag(tmp_path, regions_dir):
    assert load_region(regions_dir / "test-cell.toml").overview is False
    path = tmp_path / "ov.toml"
    path.write_text("overview = true\n" + (regions_dir / "test-cell.toml").read_text()
                    .replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    assert load_region(path).overview is True


@pytest.mark.parametrize("head, sources", [("", '["cudem", "crm"]'), ('coarse_fallback = "enc"\n', '["cudem"]')])
def test_overview_sources_must_be_crm_only(tmp_path, regions_dir, head, sources):
    """The overview is built from one CRM read: any other bathy.sources would be ignored, so it is an error."""
    path = _with_sources(tmp_path, regions_dir, sources)
    path.write_text("overview = true\n" + head + path.read_text())
    with pytest.raises(RegionError, match=r'overview region needs bathy.sources = \["crm"\]'):
        load_region(path)


def test_enc_fallback_with_crm_is_error(tmp_path, regions_dir):
    path = tmp_path / "r.toml"
    path.write_text('coarse_fallback = "enc"\n' + (regions_dir / "test-cell.toml").read_text())
    with pytest.raises(RegionError, match="coarse_fallback"):
        load_region(path)
    path.write_text(path.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["cudem"]'))
    assert load_region(path).coarse_fallback == "enc"


def _with_sources(tmp_path, regions_dir, sources):
    text = (regions_dir / "test-cell.toml").read_text()
    path = tmp_path / "r.toml"
    path.write_text(text.replace('sources = ["cudem", "crm"]', f"sources = {sources}"))
    assert f"sources = {sources}" in path.read_text()
    return path


def test_unknown_bathy_source_is_error(tmp_path, regions_dir):
    with pytest.raises(RegionError, match="unknown bathy source: gebco"):
        load_region(_with_sources(tmp_path, regions_dir, '["cudem", "gebco"]'))


def test_empty_bathy_sources_is_error(tmp_path, regions_dir):
    with pytest.raises(RegionError, match="bathy.sources"):
        load_region(_with_sources(tmp_path, regions_dir, "[]"))


def test_crm_fallback_without_crm_is_error(tmp_path, regions_dir):
    with pytest.raises(RegionError, match="coarse_fallback"):
        load_region(_with_sources(tmp_path, regions_dir, '["cudem"]'))
