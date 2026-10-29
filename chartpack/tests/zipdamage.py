"""Damage a zip member's compressed data in place, keeping the file size (an interrupted or bit-rotted
download that a size check cannot see)."""

import struct
import zipfile
import zlib
from pathlib import Path


def _data_span(path: Path, member: str) -> tuple[int, int]:
    """(offset, length) of member's compressed data in the file."""
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(member)
    raw = Path(path).read_bytes()
    name_len, extra_len = struct.unpack("<HH", raw[info.header_offset + 26:info.header_offset + 30])
    return info.header_offset + 30 + name_len + extra_len, info.compress_size


def _read_error(raw: bytes, member: str):
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.read(member)
    except Exception as e:  # noqa: BLE001 - the kind of failure is what the caller asks about
        return e
    return None


def flip_to_zlib_error(path: Path, member: str) -> None:
    """Flip one byte of member's deflate stream so that reading it raises zlib.error (not BadZipFile)."""
    raw = bytearray(Path(path).read_bytes())
    start, length = _data_span(path, member)
    for offset in range(start, start + length):
        raw[offset] ^= 0xFF
        if isinstance(_read_error(bytes(raw), member), zlib.error):
            Path(path).write_bytes(bytes(raw))
            return
        raw[offset] ^= 0xFF
    raise AssertionError(f"no single-byte flip in {member} gives zlib.error")
