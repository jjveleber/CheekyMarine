"""Tile coordinate helpers. Decoded tiles use y_coord_down=True: (px, py) in [0, extent],
py measured downward from the tile's north edge, like the tile grid itself."""

import math

EXTENT = 4096


def to_lonlat(z: int, x: int, y: int, px: float, py: float, extent: int = EXTENT) -> tuple[float, float]:
    n = 2**z
    lon = (x + px / extent) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n))))
    return lon, lat


def tile_of(z: int, lon: float, lat: float) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y
