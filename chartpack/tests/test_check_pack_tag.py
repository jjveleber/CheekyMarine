import subprocess

import pytest


@pytest.mark.parametrize("tag,ok", [
    ("charts-test-cell-v0.1.0", True),
    ("bathy-test-cell-v0.1.0", True),
    ("charts-test-cell-v9.9.9", False),
    ("v0.2.0", False),
    ("charts-nowhere-v0.1.0", False),
])
def test_check_pack_tag(tag, ok, chartpack_dir):
    r = subprocess.run([chartpack_dir / "scripts/check-pack-tag.sh", tag], capture_output=True, text=True, cwd=chartpack_dir)
    assert (r.returncode == 0) == ok, r.stdout + r.stderr
    if ok:
        assert "VERSION=0.1.0" in r.stdout
