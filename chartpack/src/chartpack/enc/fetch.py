"""Fetch ENC cell zips into the cache and check their layout."""

import re
import tempfile
import zipfile
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from osgeo import gdal

from chartpack.cache import ZIP_ERRORS, SizeMismatch, download, download_with_modified
from chartpack.enc.catalog import CellInfo

gdal.UseExceptions()


class CellError(Exception):
    pass


def _edition(zf: zipfile.ZipFile, name: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.000"
        path.write_bytes(zf.read(f"ENC_ROOT/{name}/{name}.000"))
        ds = gdal.OpenEx(str(path), gdal.OF_VECTOR)
        try:
            feature = ds.GetLayerByName("DSID").GetNextFeature()
            return int(feature.GetField("DSID_EDTN"))
        finally:
            feature = ds = None  # release the file before the temp dir goes


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


def _read_zip(path: Path, name: str) -> tuple[int, int]:
    """Return (edition, update) of a zip that tests clean and has a sound layout; else raise CellError."""
    try:
        with zipfile.ZipFile(path) as zf:
            damaged = zf.testzip()
        edtn, updn = check_zip_layout(path, name)
    except ZIP_ERRORS as e:
        raise CellError(f"{name}: {path} is a damaged zip: {e!r}") from e
    if damaged is not None:
        raise CellError(f"{name}: {path}: {damaged} fails its CRC check")
    return edtn, updn


def _verify(path: Path, info: CellInfo) -> None:
    """Raise CellError unless the zip matches the catalog entry and every member reads back whole."""
    if path.stat().st_size != info.zip_size:
        raise CellError(f"{info.name}: {path} is {path.stat().st_size} bytes, catalog says {info.zip_size}")
    edtn, updn = _read_zip(path, info.name)
    if (edtn, updn) != (info.edtn, info.updn):
        raise CellError(f"{info.name}: zip is {edtn}.{updn}, catalog says {info.edtn}.{info.updn}")


def _newer_update(info: CellInfo, edtn: int, updn: int) -> bool:
    return edtn == info.edtn and updn > info.updn


def _cached_newer(cache_dir: Path, info: CellInfo) -> Path | None:
    """A cached zip accepted earlier because the catalog lagged the server: same edition, newer update."""
    found = []
    for path in (Path(cache_dir) / "enc").glob(f"{info.name}-{info.edtn}.*.zip"):
        m = re.fullmatch(rf"{re.escape(info.name)}-{info.edtn}\.(\d+)\.zip", path.name)
        if m and int(m[1]) > info.updn:
            found.append((int(m[1]), path))
    for updn, path in sorted(found, reverse=True):
        try:
            if _read_zip(path, info.name) == (info.edtn, updn):
                return path
        except CellError:
            path.unlink()  # damaged after download: refetch
    return None


def _modified_after(header: str | None, catalog_time: datetime | None) -> bool:
    if header is None or catalog_time is None:
        return False
    try:
        served = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return False
    if served.tzinfo is None:
        return False
    return served > catalog_time


def _fetch_lagging(info: CellInfo, path: Path) -> Path:
    """The catalog's size is stale: take the served zip if it is a newer update of the catalog's edition,
    the server dates it after the catalog entry, and it tests clean. Return where it is stored."""
    tmp = path.with_name(path.name + ".new")
    try:
        modified = download_with_modified(info.zip_url, tmp)
        size = tmp.stat().st_size
        edtn, updn = _read_zip(tmp, info.name)
        if edtn != info.edtn:
            raise CellError(f"{info.name}: served zip is edition {edtn}, catalog says edition {info.edtn}")
        if updn <= info.updn:
            raise CellError(f"{info.name}: served zip is {edtn}.{updn}, not newer than catalog {info.edtn}.{info.updn}")
        if not _modified_after(modified, info.zip_datetime):
            raise CellError(
                f"{info.name}: served zip is {edtn}.{updn} but its Last-Modified ({modified!r}) "
                f"is not later than the catalog's {info.zip_datetime}"
            )
        final = path.with_name(f"{info.name}-{edtn}.{updn}.zip")
        tmp.replace(final)
        print(
            f"warning: {info.name}: catalog is {info.edtn}.{info.updn} ({info.zip_size} bytes), "
            f"NOAA serves {edtn}.{updn} ({size} bytes); using the served file"
        )
        return final
    finally:
        tmp.unlink(missing_ok=True)


def fetch_cells(names: list[str], catalog: dict[str, CellInfo], cache_dir: Path) -> list[Path]:
    paths = []
    for name in names:
        if name not in catalog:
            raise CellError(f"{name}: not in the ENC catalog")
        info = catalog[name]
        path = Path(cache_dir) / "enc" / f"{name}-{info.edtn}.{info.updn}.zip"
        if path.exists():
            try:
                _verify(path, info)
            except CellError:
                path.unlink()  # damaged after download: refetch
        if not path.exists() and (cached := _cached_newer(cache_dir, info)) is not None:
            paths.append(cached)
            continue
        if not path.exists():
            try:
                download(info.zip_url, path, expected_size=info.zip_size)
            except SizeMismatch:
                paths.append(_fetch_lagging(info, path))
                continue
            try:
                _verify(path, info)
            except Exception:
                path.unlink(missing_ok=True)
                raise
        paths.append(path)
    return paths
