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

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        calls.append((url, expected_size))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "US5SEAKL.zip", dest)
        return dest

    monkeypatch.setattr(fetch, "download", fake_download)
    cat = _catalog(fixtures_dir)
    # the fixture zip's edition/update must match the catalog's for the check to pass
    paths = fetch_cells(["US5SEAKL"], cat, tmp_path)
    assert paths == [tmp_path / "enc" / "US5SEAKL-1.1.zip"] and paths[0].exists()
    assert len(calls) == 1 and calls[0][1] == cat["US5SEAKL"].zip_size
    fetch_cells(["US5SEAKL"], cat, tmp_path)
    assert len(calls) == 1


def test_fetch_rejects_unknown_cell(tmp_path, fixtures_dir):
    with pytest.raises(CellError, match="US9NOPE"):
        fetch_cells(["US9NOPE"], _catalog(fixtures_dir), tmp_path)


@pytest.mark.online
def test_live_catalog_lists_test_cell(tmp_path):
    from chartpack.cache import download
    from chartpack.enc.catalog import CATALOG_URL

    cat = parse_catalog(download(CATALOG_URL, tmp_path / "cat.xml").read_bytes())
    assert cat["US4WA1HK"].status == "Active"
