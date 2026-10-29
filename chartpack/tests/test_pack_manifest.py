import hashlib
import json
from datetime import datetime, timezone

from chartpack.pack.manifest import write_manifest


def test_manifest_lists_every_file_with_sha(charts_pack_root):
    manifest = json.loads((charts_pack_root / "manifest.json").read_text())
    on_disk = {p.relative_to(charts_pack_root).as_posix() for p in charts_pack_root.rglob("*") if p.is_file()}
    assert {f["name"] for f in manifest["files"]} == on_disk - {"manifest.json"}
    for f in manifest["files"]:
        data = (charts_pack_root / f["name"]).read_bytes()
        assert f["bytes"] == len(data) and f["sha256"] == hashlib.sha256(data).hexdigest()
    assert (manifest["pack"], manifest["region"], manifest["version"], manifest["schema"]) == ("charts", "test-cell", "0.1.0", 1)
    assert "charts_schema" not in manifest
    assert manifest["sources"][0]["cell"] == "US4WA1HK" and "Not certified for navigation" in manifest["notice"]


def test_bathy_manifest_has_charts_schema(test_region, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    built = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    m = write_manifest(tmp_path, pack="bathy", region=test_region, sources=[], notice="n", built=built)
    assert m["charts_schema"] == 1 and m["built"] == "2026-10-29T12:00:00Z" and m["version"] == "0.1.0"
    assert [f["name"] for f in m["files"]] == ["a.txt"]
