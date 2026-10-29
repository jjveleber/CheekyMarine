"""SCAMIN (minimum display scale) to web mercator zoom, the zoom span of each usage band, and the size rule
that thins seabed areas (R37)."""

import math

import numpy as np
import shapely
from shapely.geometry import shape

BAND_ZOOMS = {2: (6, 10), 3: (6, 10), 4: (11, 12), 5: (13, 16)}

_MAX_ZOOM = 16
_ZOOM0_SCALE = 559082264.028  # scale denominator at zoom 0 for 256 px tiles at the equator
_COS_LAT = math.cos(math.radians(48))  # the region sits near 48 N


def minzoom_for_scamin(scamin: int | None, band: int) -> int:
    low = BAND_ZOOMS[band][0]
    if scamin is None or scamin <= 0:
        return low
    zoom = round(math.log2(_ZOOM0_SCALE * _COS_LAT / scamin))
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
    """The first zoom at which a feature of this zoom-0 size is SEABED_MIN_PX across, clamped to 0..16."""
    if extent <= 0:
        return _MAX_ZOOM
    return max(0, min(math.ceil(math.log2(SEABED_MIN_PX / extent) - 1e-9), _MAX_ZOOM))
