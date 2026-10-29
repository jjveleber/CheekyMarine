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
