"""Download helper: stream to a .part file, verify size, rename on success."""

import urllib.request
import zipfile
import zlib
from pathlib import Path

# NOAA's server may answer a default Python User-Agent with 403 (see README, Downloads).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)


class DownloadError(Exception):
    pass


# What reading a damaged zip can raise: testzip reports a CRC mismatch, but a corrupt deflate stream
# raises zlib.error and a cut one EOFError.
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, OSError)


def download(
    url: str, dest: Path, *, expected_size: int | None = None, timeout: float = 120
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                received = 0
                with part.open("wb") as f:
                    while chunk := response.read(1 << 16):
                        f.write(chunk)
                        received += len(chunk)
        except Exception as e:  # URLError, HTTPError, IncompleteRead, timeouts, OSError
            raise DownloadError(f"{url}: {e}") from e
        if length is not None and received != int(length):
            raise DownloadError(f"{url}: got {received} bytes, Content-Length said {length}")
        if expected_size is not None and received != expected_size:
            raise DownloadError(f"{url}: got {received} bytes, expected {expected_size}")
        part.rename(dest)
    finally:
        part.unlink(missing_ok=True)  # no-op after a successful rename
    return dest


def _check_zip(path: Path, size: int, member: str) -> None:
    """Raise DownloadError unless path is a whole zip of the published size holding member."""
    if path.stat().st_size != size:
        raise DownloadError(f"{path} is {path.stat().st_size} bytes, the published file is {size}")
    try:
        with zipfile.ZipFile(path) as zf:
            if member not in zf.namelist() or zf.testzip() is not None:
                raise DownloadError(f"{path}: {member} missing or damaged")
    except ZIP_ERRORS as e:
        raise DownloadError(f"{path}: damaged zip: {e!r}") from e


def fetch_zip(url: str, dest: Path, *, size: int, member: str) -> Path:
    """A published zip in the cache: a cached copy is checked (size, zip structure, member) and refetched
    when damaged; a fresh download is checked the same way and removed if it fails."""
    dest = Path(dest)
    if dest.exists():
        try:
            _check_zip(dest, size, member)
            return dest
        except DownloadError:
            dest.unlink()
    download(url, dest, expected_size=size)
    try:
        _check_zip(dest, size, member)
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise
    return dest
