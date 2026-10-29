import tarfile

import pytest

from chartpack.pack.archive import archive_pack


def test_archive(charts_pack_root, tmp_path):
    tar, sums = archive_pack(charts_pack_root, tmp_path)
    with tarfile.open(tar) as t:
        names = t.getnames()
    assert tar.name == "charts-test-cell-0.1.0.tar" and names[0].startswith("charts-test-cell-0.1.0/")
    assert sums.read_text().split()[1] == tar.name
    assert "charts-test-cell-0.1.0/manifest.json" in names and "charts-test-cell-0.1.0/enc.mbtiles" in names


def test_archive_needs_a_manifest(tmp_path):
    (tmp_path / "pack").mkdir()
    with pytest.raises(FileNotFoundError):
        archive_pack(tmp_path / "pack", tmp_path / "out")
