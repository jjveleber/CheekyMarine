"""SCAMIN (minimum display scale) to web mercator zoom, and the zoom span of each usage band."""

import math

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
