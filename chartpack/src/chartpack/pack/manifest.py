"""manifest.json: every file of a pack with its size and sha256, plus provenance."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from chartpack.enc.schema import SCHEMA_VERSION
from chartpack.mbtiles import MBTiles
from chartpack.region import Region

MANIFEST = "manifest.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    pack_root: Path, *, pack: str, region: Region, sources: list[dict], notice: str, built: datetime
) -> dict:
    root = Path(pack_root)
    files = [
        {"name": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_of(p)}
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).as_posix() != MANIFEST
    ]
    manifest = {
        "pack": pack,
        "region": region.name,
        "version": region.charts_version if pack == "charts" else region.bathy_version,
        "schema": SCHEMA_VERSION,
        "built": built.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "sources": sources,
        "notice": notice,
    }
    if pack == "bathy":
        manifest["charts_schema"] = SCHEMA_VERSION
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def describe_pack(pack_root: Path) -> tuple[str, list[dict], str]:
    """(pack, sources, notice) of an assembled pack, read from its mbtiles metadata and a shipped style."""
    root = Path(pack_root)
    mbtiles = "enc.mbtiles" if (root / "enc.mbtiles").exists() else "bathy.mbtiles"
    with MBTiles.open(root / mbtiles) as m:
        metadata = m.metadata()
    pack = metadata["cheekymarine:pack"]
    sources = json.loads(metadata["cheekymarine:sources"])
    if pack == "bathy":  # a dict of provenance blocks, flattened to a list
        sources = [
            *({"source": "cudem", **tile} for tile in sources["cudem"]),
            {"source": "crm", "request": sources["crm"]},
            {"source": "datum", **sources["datum"]},
        ]
    style = json.loads(sorted((root / "styles").glob("*-day.json"))[0].read_text())
    return pack, sources, style["metadata"]["cheekymarine"]["notice"]
