"""Download helper: stream to a .part file, verify size, rename on success."""

import urllib.request
from pathlib import Path

# NOAA's server may answer a default Python User-Agent with 403 (see README, Downloads).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)


class DownloadError(Exception):
    pass


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
