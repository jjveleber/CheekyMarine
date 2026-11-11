"""SCAMIN (minimum display scale) to web mercator zoom, the zoom span of each usage band, and the size rule
that thins seabed areas (R37)."""

import math

import numpy as np
import shapely
from shapely.geometry import shape

BAND_ZOOMS = {1: (6, 10), 2: (6, 10), 3: (6, 10), 4: (11, 12), 5: (13, 16)}

_MAX_ZOOM = 16
# Scale denominator at zoom 0 for 256 px tiles at the equator. MapLibre GL draws a 512 px world, so its map
# zoom z has the ground resolution of 256 px zoom z+1: map zooms are one earlier than this constant implies (R44).
_ZOOM0_SCALE = 559082264.028


def minzoom_for_scamin(scamin: int | None, band: int, lat: float) -> int:
    """The MapLibre zoom (512 px world, R44) from which a feature of this SCAMIN is shown, clamped to the band.
    `lat` is the feature's latitude: the ground under a scale shrinks with cos(lat) (#18). It is rounded to the
    nearest 0.25 degree, so features near one another on both sides of a pack seam use one value."""
    low = BAND_ZOOMS[band][0]
    if scamin is None or scamin <= 0:
        return low
    lat = round(lat * 4) / 4
    zoom = round(math.log2(_ZOOM0_SCALE * math.cos(math.radians(lat)) / scamin) - 1)
    return max(low, min(zoom, _MAX_ZOOM))


SEABED_MIN_PX = 48  # a seabed area or line shows from the first zoom at which it is about this many px across


def _to_mercator_px(coords: np.ndarray) -> np.ndarray:
    lon, lat = coords[:, 0], np.radians(coords[:, 1])
    return np.column_stack(((lon + 180) / 360 * 256, (1 - np.log(np.tan(np.pi / 4 + lat / 2)) / np.pi) / 2 * 256))


def extent_z0(geometry: dict) -> float:
    """Size of a lon/lat geometry in 256 px Web Mercator pixels at zoom 0: sqrt(area) of a polygon, the
    length of a line. Six significant digits, as stored in the tiles."""
    geom = shapely.transform(shape(geometry), _to_mercator_px)
    size = math.sqrt(geom.area) if geom.geom_type in ("Polygon", "MultiPolygon") else geom.length
    return float(f"{size:.6g}")


def minzoom_for_extent(extent: float) -> int:
    """The first MapLibre zoom z (512 px world, R44) at which extent * 2**(z+1) >= SEABED_MIN_PX, clamped to 0..16."""
    if extent <= 0:
        return _MAX_ZOOM
    return max(0, min(math.ceil(math.log2(SEABED_MIN_PX / extent) - 1e-9) - 1, _MAX_ZOOM))
