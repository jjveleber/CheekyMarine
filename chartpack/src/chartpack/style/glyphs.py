"""Glyph range PBFs (MapLibre glyphs.proto) rendered from a TrueType font, hand-encoded without protobuf."""

from pathlib import Path

import freetype
import numpy as np

from chartpack.style.sdf import bitmap_to_sdf

_SIZE = 24
_BUFFER = 3


def _varint(n: int) -> bytes:
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def _uint(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _sint(field: int, value: int) -> bytes:
    return _uint(field, _zigzag(value))


def _bytes(field: int, value: bytes) -> bytes:
    return _varint(field << 3 | 2) + _varint(len(value)) + value


def _render_glyph(face: freetype.Face, code: int, ascender: int) -> bytes | None:
    """One `glyphs` message (field 3 of a stack), or None when the font lacks the character."""
    index = face.get_char_index(code)
    if index == 0:
        return None
    face.load_glyph(index, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    slot = face.glyph
    bitmap = slot.bitmap
    width, height = bitmap.width, bitmap.rows
    msg = _uint(1, code)
    if width > 0:
        alpha = np.array(bitmap.buffer, np.uint8).reshape(height, bitmap.pitch)[:, :width]
        msg += _bytes(2, bitmap_to_sdf(alpha, buffer=_BUFFER).tobytes())
    # fontnik: left = bitmap_left, top = bitmap_top - ascender, advance = whole pixels (horiAdvance / 64)
    msg += _uint(3, width) + _uint(4, height) + _sint(5, slot.bitmap_left)
    msg += _sint(6, slot.bitmap_top - ascender) + _uint(7, slot.metrics.horiAdvance // 64)
    return _bytes(3, msg)


def build_glyphs(
    font_path: Path, fontstack: str, out_dir: Path, ranges: tuple[tuple[int, int], ...] = ((0, 255), (256, 511))
) -> list[Path]:
    face = freetype.Face(str(font_path))
    face.set_char_size(_SIZE * 64)
    ascender = face.size.ascender // 64
    stack_dir = Path(out_dir) / fontstack
    stack_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for start, end in ranges:
        stack = _bytes(1, fontstack.encode()) + _bytes(2, f"{start}-{end}".encode())
        for code in range(max(start, 32), end + 1):
            stack += _render_glyph(face, code, ascender) or b""
        path = stack_dir / f"{start}-{end}.pbf"
        path.write_bytes(_bytes(1, stack))
        paths.append(path)
    return paths


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7


def _fields(data: bytes):
    """Yield (field number, value) with value an int for varints or bytes for length-delimited fields."""
    pos = 0
    while pos < len(data):
        key, pos = _read_varint(data, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(data, pos)
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            value, pos = data[pos : pos + length], pos + length
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield field, value


def _unzigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def parse_glyph_pbf(data: bytes) -> dict:
    """Decode a glyph range PBF to {"name", "range", "glyphs": {id: {bitmap, width, height, left, top, advance}}}."""
    out = {"name": None, "range": None, "glyphs": {}}
    for field, stack in _fields(data):
        if field != 1:
            continue
        for sfield, value in _fields(stack):
            if sfield == 1:
                out["name"] = value.decode()
            elif sfield == 2:
                out["range"] = value.decode()
            elif sfield == 3:
                glyph = {"bitmap": b"", "width": 0, "height": 0, "left": 0, "top": 0, "advance": 0}
                for gfield, gvalue in _fields(value):
                    if gfield == 1:
                        glyph["id"] = gvalue
                    elif gfield == 2:
                        glyph["bitmap"] = gvalue
                    elif gfield in (3, 4, 7):
                        glyph[{3: "width", 4: "height", 7: "advance"}[gfield]] = gvalue
                    elif gfield in (5, 6):
                        glyph[{5: "left", 6: "top"}[gfield]] = _unzigzag(gvalue)
                out["glyphs"][glyph["id"]] = glyph
    return out
