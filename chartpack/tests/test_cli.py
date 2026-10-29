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
    root = tmp_path / "out" / "charts-test-cell-0.1.0"
    with MBTiles.open(root / "enc.mbtiles") as m:
        assert m.metadata()["cheekymarine:region"] == "test-cell"
    assert (root / "manifest.json").exists() and (root / "styles" / "nav-day.json").exists()
    assert main(["check", str(root), "--enc-cache", str(tmp_path / "cache")]) == 0
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


def _bathy_region(tmp_path, regions_dir):
    toml = (regions_dir / "test-cell.toml").read_text().replace(
        "bbox = [-122.4, 47.7, -122.1, 48.0]", "bbox = [-122.3846, 47.8954, -122.3754, 47.9046]"
    ).replace("dem_maxzoom = 14", "dem_maxzoom = 12")
    path = tmp_path / "bathy-test.toml"
    path.write_text(toml)
    return path


def test_build_bathy_needs_fetch_bathy_first(tmp_path, regions_dir):
    args = ["build-bathy", str(_bathy_region(tmp_path, regions_dir)), str(tmp_path / "out"),
            "--cache", str(tmp_path / "cache"), "--work", str(tmp_path / "work")]
    with pytest.raises(SystemExit, match="fetch-bathy"):
        main(args)


def test_build_bathy_end_to_end(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import json
    import shutil

    from chartpack import cli
    from chartpack.bathy.cudem import read_window as real_read_window
    from chartpack.mbtiles import MBTiles

    region = _bathy_region(tmp_path, regions_dir)
    cache = tmp_path / "cache"
    (cache / "enc").mkdir(parents=True)
    (cache / "cudem").mkdir()
    (cache / "crm").mkdir()
    shutil.copy(fixtures_dir / "US4WA1HK.zip", cache / "enc" / "US4WA1HK-1.3.zip")
    shutil.copy(fixtures_dir / "cudem_possession_bar.tif", cache / "crm" / "crm_-122.3846_47.8954_-122.3754_47.9046.tif")
    (cache / "cudem" / "urllist8483.txt").write_text(
        "https://example.test/ncei19_n48x00_w122x50_2023v1.tif\nhttps://example.test/ncei19_n48x00_w122x50_2017v1.tif\n"
    )
    opened = []

    def fake_read_window(src, bbox):
        opened.append(src)
        return real_read_window(str(fixtures_dir / "cudem_possession_bar.tif"), bbox)

    monkeypatch.setattr(cli, "read_window", fake_read_window)
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")]) == 0
    root = tmp_path / "out" / "bathy-test-cell-0.1.0"
    assert capsys.readouterr().out.strip() == str(root)
    assert opened[0] == "/vsicurl/https://example.test/ncei19_n48x00_w122x50_2023v1.tif" and len(opened) == 2  # tile, then CRM
    assert (root / "styles" / "fish-day.json").exists() and (root / "dem.mbtiles").exists()
    assert json.loads((root / "manifest.json").read_text())["charts_schema"] == 1
    assert main(["check", str(root)]) == 0
    with MBTiles.open(root / "bathy.mbtiles") as m:
        md = m.metadata()
        assert [t["year"] for t in json.loads(md["cheekymarine:sources"])["cudem"]] == [2023]
        assert any(True for _ in m.tiles_at(12))


def test_build_bathy_enc_fallback_drops_crm_contours(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    """coarse_fallback = "enc": where CUDEM is absent the ENC lines are the only contours, not CRM."""
    import json
    import shutil

    from shapely.geometry import box, shape

    from chartpack import cli
    from chartpack.bathy.cudem import read_window as real_read_window

    region = _bathy_region(tmp_path, regions_dir)
    region.write_text('coarse_fallback = "enc"\n' + region.read_text())
    cache = tmp_path / "cache"
    (cache / "enc").mkdir(parents=True)
    (cache / "cudem").mkdir()
    (cache / "crm").mkdir()
    shutil.copy(fixtures_dir / "US4WA1HK.zip", cache / "enc" / "US4WA1HK-1.3.zip")
    shutil.copy(fixtures_dir / "cudem_possession_bar.tif", cache / "crm" / "crm_-122.3846_47.8954_-122.3754_47.9046.tif")
    (cache / "cudem" / "urllist8483.txt").write_text("https://example.test/ncei19_n48x00_w122x50_2023v1.tif\n")

    def fake_read_window(src, bbox):
        grid = real_read_window(str(fixtures_dir / "cudem_possession_bar.tif"), bbox)
        if src.startswith("/vsicurl/"):  # the CUDEM tile covers only the east half; CRM is everywhere
            grid.data[:, : grid.data.shape[1] // 2] = grid.nodata
        return grid

    monkeypatch.setattr(cli, "read_window", fake_read_window)
    work = tmp_path / "work"
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(work)]) == 0
    capsys.readouterr()
    contours = [json.loads(line) for line in (work / "tippecanoe" / "contour.geojsonseq").read_text().splitlines()]
    sources = {f["properties"]["source"] for f in contours}
    assert "crm" not in sources and {"cudem", "enc"} <= sources
    west = box(-122.3846, 47.8954, -122.382, 47.9046)  # well inside the CRM-only half
    assert any(shape(f["geometry"]).intersects(west) for f in contours if f["properties"]["source"] == "enc")


def test_manifest_and_archive_commands(charts_pack_root_copy, regions_dir, tmp_path, capsys):
    (charts_pack_root_copy / "manifest.json").unlink()
    assert main(["check", str(charts_pack_root_copy)]) == 1
    assert "manifest" in capsys.readouterr().out
    assert main(["manifest", str(charts_pack_root_copy), "--region", str(regions_dir / "test-cell.toml")]) == 0
    assert main(["check", str(charts_pack_root_copy)]) == 0
    capsys.readouterr()
    assert main(["archive", str(charts_pack_root_copy), str(tmp_path / "dist")]) == 0
    assert capsys.readouterr().out.split() == [str(tmp_path / "dist" / "charts-test-cell-0.1.0.tar"), str(tmp_path / "dist" / "SHA256SUMS")]


def test_check_reports_problems_as_errors_not_tracebacks(charts_pack_root_copy, tmp_path, capsys):
    assert main(["check", str(charts_pack_root_copy), "--enc-cache", str(tmp_path / "empty")]) == 1
    assert "US4WA1HK-1.3.zip" in capsys.readouterr().out
    (charts_pack_root_copy / "manifest.json").unlink()
    assert main(["check", str(charts_pack_root_copy), "--enc-cache", str(tmp_path / "empty")]) == 1
    assert "manifest.json" in capsys.readouterr().out
