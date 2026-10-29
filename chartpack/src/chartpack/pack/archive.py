"""Tar a pack directory (uncompressed: mbtiles do not shrink) and write its SHA256SUMS."""

import tarfile
from pathlib import Path

from chartpack.pack.manifest import MANIFEST, sha256_of


def _reproducible(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    return info


def archive_pack(pack_root: Path, out_dir: Path) -> tuple[Path, Path]:
    root = Path(pack_root)
    if not (root / MANIFEST).exists():
        raise FileNotFoundError(f"{root / MANIFEST}: run `chartpack manifest` first")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tar_path = out / f"{root.name}.tar"
    with tarfile.open(tar_path, "w") as tar:
        for path in sorted(root.rglob("*")):
            arcname = f"{root.name}/{path.relative_to(root).as_posix()}"
            tar.add(path, arcname=arcname, recursive=False, filter=_reproducible)
    sums = out / "SHA256SUMS"
    sums.write_text(f"{sha256_of(tar_path)}  {tar_path.name}\n")
    return tar_path, sums
