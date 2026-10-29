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


def test_archive_keeps_other_packs_sums(charts_pack_root, tmp_path):
    """Both packs of a region archived into one directory: SHA256SUMS lists both tars, the newest sum each."""
    from chartpack.pack.manifest import sha256_of

    (tmp_path / "SHA256SUMS").write_text(f"{'0' * 64}  bathy-test-cell-0.1.0.tar\n{'1' * 64}  charts-test-cell-0.1.0.tar\n")
    tar, sums = archive_pack(charts_pack_root, tmp_path)
    assert sums.read_text() == f"{'0' * 64}  bathy-test-cell-0.1.0.tar\n{sha256_of(tar)}  charts-test-cell-0.1.0.tar\n"


def test_archive_needs_a_manifest(tmp_path):
    (tmp_path / "pack").mkdir()
    with pytest.raises(FileNotFoundError):
        archive_pack(tmp_path / "pack", tmp_path / "out")


def test_archive_names_come_from_the_manifest(charts_pack_root, tmp_path):
    import shutil

    renamed = shutil.copytree(charts_pack_root, tmp_path / "somewhere-else")
    tar, _ = archive_pack(renamed, tmp_path / "out")
    with tarfile.open(tar) as t:
        names = t.getnames()
    assert tar.name == "charts-test-cell-0.1.0.tar"
    assert all(n.startswith("charts-test-cell-0.1.0/") for n in names)
