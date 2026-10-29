"""Fetch ENC cell zips into the cache and check their layout."""

import re
import tempfile
import zipfile
from pathlib import Path

from osgeo import gdal

from chartpack.cache import download
from chartpack.enc.catalog import CellInfo

gdal.UseExceptions()


class CellError(Exception):
    pass


def _edition(zf: zipfile.ZipFile, name: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.000"
        path.write_bytes(zf.read(f"ENC_ROOT/{name}/{name}.000"))
        ds = gdal.OpenEx(str(path), gdal.OF_VECTOR)
        feature = ds.GetLayerByName("DSID").GetNextFeature()
        return int(feature.GetField("DSID_EDTN"))


def check_zip_layout(zip_path: Path, name: str) -> tuple[int, int]:
    """Return (edition, highest update). Update continuity is judged from entry names only."""
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        prefix = f"ENC_ROOT/{name}/{name}."
        if prefix + "000" not in names:
            raise CellError(f"{name}: {prefix}000 missing from {zip_path}")
        updates = {
            int(m.group(1))
            for n in names
            if (m := re.fullmatch(re.escape(prefix) + r"(\d{3})", n))
        }
        updates.discard(0)
        highest = max(updates, default=0)
        missing = [f"{n:03d}" for n in range(1, highest + 1) if n not in updates]
        if missing:
            raise CellError(
                f"{name}: update(s) {', '.join(missing)} missing (have up to {highest:03d})"
            )
        return _edition(zf, name), highest


def fetch_cells(names: list[str], catalog: dict[str, CellInfo], cache_dir: Path) -> list[Path]:
    paths = []
    for name in names:
        if name not in catalog:
            raise CellError(f"{name}: not in the ENC catalog")
        info = catalog[name]
        path = Path(cache_dir) / "enc" / f"{name}-{info.edtn}.{info.updn}.zip"
        if not path.exists():
            download(info.zip_url, path, expected_size=info.zip_size)
            try:
                edtn, updn = check_zip_layout(path, name)
                if (edtn, updn) != (info.edtn, info.updn):
                    raise CellError(
                        f"{name}: zip is {edtn}.{updn}, catalog says {info.edtn}.{info.updn}"
                    )
            except Exception:
                path.unlink(missing_ok=True)
                raise
        paths.append(path)
    return paths
