import io
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
import shutil
import zipfile

import pytest

from chartpack.enc import fetch
from chartpack.enc.catalog import parse_catalog
from chartpack.enc.fetch import CellError, check_zip_layout, fetch_cells


def test_layout_of_fixture(fixtures_dir):
    assert check_zip_layout(fixtures_dir / "US5SEAKL.zip", "US5SEAKL") == (1, 1)
    assert check_zip_layout(fixtures_dir / "US4WA1HK.zip", "US4WA1HK") == (1, 3)


def test_update_gap_is_an_error(tmp_path, fixtures_dir):
    gapped = tmp_path / "gapped.zip"
    with zipfile.ZipFile(fixtures_dir / "US5SEAKL.zip") as src, zipfile.ZipFile(gapped, "w") as dst:
        for info in src.infolist():
            name = info.filename.replace(".001", ".003")
            dst.writestr(name, src.read(info))
    with pytest.raises(CellError, match="US5SEAKL.*002"):
        check_zip_layout(gapped, "US5SEAKL")


def test_missing_base_cell_is_an_error(tmp_path, fixtures_dir):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(fixtures_dir / "US5SEAKL.zip") as src, zipfile.ZipFile(bad, "w") as dst:
        for info in src.infolist():
            if not info.filename.endswith(".000"):
                dst.writestr(info.filename, src.read(info))
    with pytest.raises(CellError, match="US5SEAKL.*000"):
        check_zip_layout(bad, "US5SEAKL")


def _catalog(fixtures_dir):
    return parse_catalog((fixtures_dir / "ENCProdCat_excerpt.xml").read_bytes())


def test_fetch_uses_cache(tmp_path, fixtures_dir, monkeypatch):
    calls = []

    def fake_download(url, dest, *, timeout=120):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "US5SEAKL.zip", dest)
        return None

    monkeypatch.setattr(fetch, "download_with_modified", fake_download)
    cat = _catalog(fixtures_dir)
    # the fixture zip's edition/update must match the catalog's for the check to pass
    paths = fetch_cells(["US5SEAKL"], cat, tmp_path)
    assert paths == [tmp_path / "enc" / "US5SEAKL-1.1.zip"] and paths[0].exists()
    assert len(calls) == 1
    fetch_cells(["US5SEAKL"], cat, tmp_path)
    assert len(calls) == 1


def test_fetch_replaces_corrupt_cache_entry(tmp_path, fixtures_dir, monkeypatch):
    calls = []

    def fake_download(url, dest, *, timeout=120):
        calls.append(url)
        shutil.copy(fixtures_dir / "US5SEAKL.zip", dest)
        return None

    monkeypatch.setattr(fetch, "download_with_modified", fake_download)
    cached = tmp_path / "enc" / "US5SEAKL-1.1.zip"
    cached.parent.mkdir()
    cached.write_bytes((fixtures_dir / "US5SEAKL.zip").read_bytes()[:1000])
    (path,) = fetch_cells(["US5SEAKL"], _catalog(fixtures_dir), tmp_path)
    assert len(calls) == 1
    assert check_zip_layout(path, "US5SEAKL") == (1, 1)


@pytest.mark.parametrize("member", ["ENC_ROOT/US5SEAKL/US5SEAKL.000", "ENC_ROOT/US5SEAKL/US5SEAKL.001"])
def test_fetch_refetches_same_size_zip_with_corrupt_deflate(tmp_path, fixtures_dir, monkeypatch, member):
    """Review Focus 5: a cached cell zip of the catalog size with a damaged deflate stream in the base cell
    or an update file is rejected and fetched again, not read and not a traceback."""
    from zipdamage import flip_to_zlib_error

    calls = []

    def fake_download(url, dest, *, timeout=120):
        calls.append(url)
        shutil.copy(fixtures_dir / "US5SEAKL.zip", dest)
        return None

    monkeypatch.setattr(fetch, "download_with_modified", fake_download)
    cached = tmp_path / "enc" / "US5SEAKL-1.1.zip"
    cached.parent.mkdir()
    shutil.copy(fixtures_dir / "US5SEAKL.zip", cached)
    flip_to_zlib_error(cached, member)
    (path,) = fetch_cells(["US5SEAKL"], _catalog(fixtures_dir), tmp_path)
    assert len(calls) == 1 and path.read_bytes() == (fixtures_dir / "US5SEAKL.zip").read_bytes()


def test_fetch_rejects_unknown_cell(tmp_path, fixtures_dir):
    with pytest.raises(CellError, match="US9NOPE"):
        fetch_cells(["US9NOPE"], _catalog(fixtures_dir), tmp_path)


@pytest.mark.online
def test_live_catalog_lists_test_cell(tmp_path):
    from chartpack.cache import download
    from chartpack.enc.catalog import CATALOG_URL

    cat = parse_catalog(download(CATALOG_URL, tmp_path / "cat.xml").read_bytes())
    assert cat["US4WA1HK"].status == "Active"


# A catalog that lags the server: the catalog entry's size differs from the served zip (US5SEAKL fixture,
# which is edition 1 update 1), so fetch_cells must judge the served file itself.
def _lagging(fixtures_dir, *, edtn=1, updn=0):
    info = _catalog(fixtures_dir)["US5SEAKL"]
    return {"US5SEAKL": replace(info, edtn=edtn, updn=updn, zip_size=info.zip_size + 10)}


def _patch_lagging(monkeypatch, fixtures_dir, *, modified="Thu, 12 Nov 2026 05:50:17 GMT", zip_bytes=None):
    calls = {"gets": 0}

    def fake_get(url, dest, *, timeout=120):
        calls["gets"] += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zip_bytes if zip_bytes is not None else (fixtures_dir / "US5SEAKL.zip").read_bytes())
        return modified

    monkeypatch.setattr(fetch, "download_with_modified", fake_get)
    return calls


def test_fetch_accepts_newer_update_under_its_own_name(tmp_path, fixtures_dir, monkeypatch, capsys):
    calls = _patch_lagging(monkeypatch, fixtures_dir)
    cat = _lagging(fixtures_dir)
    (path,) = fetch_cells(["US5SEAKL"], cat, tmp_path)
    assert path == tmp_path / "enc" / "US5SEAKL-1.1.zip" and path.exists()
    out = capsys.readouterr().out
    assert "US5SEAKL" in out and "1.0" in out and "1.1" in out
    # the pack-facing lookup (the manifest names edtn.updn from the cell itself) finds it
    from chartpack.cli import _newest_cached_zip

    assert _newest_cached_zip(tmp_path, "US5SEAKL") == path
    # next run: the cached newer zip still verifies, no refetch
    assert fetch_cells(["US5SEAKL"], cat, tmp_path) == [path]
    assert calls == {"gets": 1}


def test_fetch_rejects_older_update(tmp_path, fixtures_dir, monkeypatch):
    _patch_lagging(monkeypatch, fixtures_dir)
    with pytest.raises(CellError, match="1.1.*1.3|older|newer"):
        fetch_cells(["US5SEAKL"], _lagging(fixtures_dir, updn=3), tmp_path)
    assert not list((tmp_path / "enc").glob("*.zip"))


def test_fetch_rejects_different_edition(tmp_path, fixtures_dir, monkeypatch):
    _patch_lagging(monkeypatch, fixtures_dir)
    with pytest.raises(CellError, match="edition"):
        fetch_cells(["US5SEAKL"], _lagging(fixtures_dir, edtn=2, updn=0), tmp_path)
    assert not list((tmp_path / "enc").glob("*.zip"))


@pytest.mark.parametrize(
    "modified", ["Wed, 28 Oct 2026 04:31:25 GMT", "Tue, 27 Oct 2026 00:00:00 GMT", None, "yesterday-ish"]
)
def test_fetch_rejects_modified_not_newer_or_unusable(tmp_path, fixtures_dir, monkeypatch, modified):
    _patch_lagging(monkeypatch, fixtures_dir, modified=modified)
    with pytest.raises(CellError, match="Last-Modified"):
        fetch_cells(["US5SEAKL"], _lagging(fixtures_dir), tmp_path)
    assert not list((tmp_path / "enc").glob("*.zip"))


def test_fetch_rejects_damaged_zip_of_other_size(tmp_path, fixtures_dir, monkeypatch):
    _patch_lagging(monkeypatch, fixtures_dir, zip_bytes=(fixtures_dir / "US5SEAKL.zip").read_bytes()[:1000])
    with pytest.raises(CellError, match="damaged"):
        fetch_cells(["US5SEAKL"], _lagging(fixtures_dir), tmp_path)
    assert not list((tmp_path / "enc").glob("*.zip"))


def test_fetch_other_download_errors_still_raise(tmp_path, fixtures_dir, monkeypatch):
    from chartpack.cache import DownloadError

    def fake_get(url, dest, *, timeout=120):
        raise DownloadError("boom")

    monkeypatch.setattr(fetch, "download_with_modified", fake_get)
    with pytest.raises(DownloadError, match="boom"):
        fetch_cells(["US5SEAKL"], _lagging(fixtures_dir), tmp_path)


def test_fetch_catalog_time_without_zone_is_a_clean_error(tmp_path, fixtures_dir, monkeypatch):
    _patch_lagging(monkeypatch, fixtures_dir)
    cat = _lagging(fixtures_dir)
    cat["US5SEAKL"] = replace(cat["US5SEAKL"], zip_datetime=datetime(2026, 10, 28, 4, 31, 25))
    with pytest.raises(CellError, match="time zone"):
        fetch_cells(["US5SEAKL"], cat, tmp_path)
    assert not list((tmp_path / "enc").glob("*.zip*"))


def test_fetch_enc_log_names_the_stored_file(tmp_path, fixtures_dir, monkeypatch, capsys):
    from chartpack import cli

    _patch_lagging(monkeypatch, fixtures_dir)
    cat = _lagging(fixtures_dir)
    monkeypatch.setattr(cli, "_load_catalog", lambda cache: cat)
    monkeypatch.setattr(cli, "load_region", lambda p: SimpleNamespace(cells={5: ["US5SEAKL"]}))
    assert cli._fetch_enc(SimpleNamespace(region="r", cache=tmp_path)) == 0
    assert f"US5SEAKL 1.1 {cat['US5SEAKL'].isdt.isoformat()}" in capsys.readouterr().out


def test_fetch_real_download_path_one_get_and_header(tmp_path, fixtures_dir, monkeypatch):
    """No patched download: urlopen is faked, so the size check, Last-Modified and the single GET are real."""
    body = (fixtures_dir / "US5SEAKL.zip").read_bytes()
    gets = []

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(body)), "Last-Modified": "Thu, 12 Nov 2026 05:50:17 GMT"}

        def __enter__(self):
            return self

    def fake_urlopen(request, timeout=None):
        gets.append(request.full_url)
        return Response(body)

    monkeypatch.setattr("chartpack.cache.urllib.request.urlopen", fake_urlopen)
    (path,) = fetch_cells(["US5SEAKL"], _lagging(fixtures_dir), tmp_path)
    assert path.name == "US5SEAKL-1.1.zip" and len(gets) == 1
    assert not list((tmp_path / "enc").glob("*.new")) and not list((tmp_path / "enc").glob("*.part"))
