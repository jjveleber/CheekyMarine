import pytest

from chartpack import __version__
from chartpack.cli import main


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"chartpack {__version__}"


def test_cells_and_fetch_enc(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import shutil

    from chartpack import cli

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = fixtures_dir / ("ENCProdCat_excerpt.xml" if url.endswith(".xml") else "US4WA1HK.zip")
        shutil.copy(src, dest)
        return dest

    monkeypatch.setattr(cli, "download", fake_download)
    region = str(regions_dir / "test-cell.toml")
    assert main(["cells", region, "--band", "4", "--cache", str(tmp_path)]) == 0
    assert "US4WA1HK" in capsys.readouterr().out.split()
    assert main(["fetch-enc", region, "--cache", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "US4WA1HK 1.3 2026-09-09\n"


def test_build_enc_uses_cached_zip(tmp_path, fixtures_dir, regions_dir):
    import shutil

    from chartpack.mbtiles import MBTiles

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    args = ["build-enc", str(regions_dir / "test-cell.toml"), str(tmp_path / "out"),
            "--cache", str(tmp_path / "cache"), "--work", str(tmp_path / "work")]
    assert main(args) == 0
    with MBTiles.open(tmp_path / "out" / "enc.mbtiles") as m:
        assert m.metadata()["cheekymarine:region"] == "test-cell"
    (tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip").unlink()
    with pytest.raises(SystemExit):
        main(args)


def test_fetch_bathy_prints_tiles_and_crm(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import shutil

    from chartpack import cli

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "cudem_urllist_excerpt.txt", dest)
        return dest

    def fake_fetch_crm(bbox, cache_dir):
        assert bbox == (-122.4, 47.7, -122.1, 48.0)
        return cache_dir / "crm" / "crm_x.tif"

    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "fetch_crm", fake_fetch_crm)
    assert main(["fetch-bathy", str(regions_dir / "test-cell.toml"), "--cache", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert (tmp_path / "cudem" / "urllist8483.txt").exists()
    assert "ncei19_n48x00_w122x50_2023v1" in lines
    assert lines[-1] == str(tmp_path / "crm" / "crm_x.tif")
