"""Vertical datums of the bathy sources, and the global grid their offsets are computed on (plan 7, #88).

Offsets are computed at the nodes of a global GRID_DEG grid anchored at (-180, 90) and bilinear-resampled
to each block's cells, so two blocks (or two packs) see the same offset along a shared edge.
"""

import math

import numpy as np

GRID_DEG = 0.05

# The height each source's elevations are given in (plan 8 spec 8): NONNA is on Canadian chart datum ("chart", no
# shift); ETOPO's EGM2008 heights are taken as mean sea level ("msl"), never through the CRM geoid and Washington
# station path.
SOURCE_VERTICAL = {"cudem": "navd88", "crm": "egm2008", "nonna10": "chart", "nonna100": "chart", "etopo": "msl"}

_ROWS_PER_CHUNK = 512


def _centers(origin: float, step: float, n: int) -> np.ndarray:
    return origin + (np.arange(n) + 0.5) * step


def node_axes(transform, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """(lons ascending, lats descending) of the global grid nodes around every cell center of the grid."""
    x0, dx, _, y0, _, dy = transform
    rows, cols = shape
    lon = _centers(x0, dx, cols)[[0, -1]]
    lat = _centers(y0, dy, rows)[[0, -1]]
    i0 = math.floor((lon.min() + 180) / GRID_DEG)
    i1 = max(math.ceil((lon.max() + 180) / GRID_DEG), i0 + 1)
    j0 = math.floor((90 - lat.max()) / GRID_DEG)
    j1 = max(math.ceil((90 - lat.min()) / GRID_DEG), j0 + 1)
    return -180 + GRID_DEG * np.arange(i0, i1 + 1), 90 - GRID_DEG * np.arange(j0, j1 + 1)


def _weights(f: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    i = np.clip(np.floor(f).astype(int), 0, n - 2)
    return i, f - i


def resample(nodes: np.ndarray, lons: np.ndarray, lats: np.ndarray, transform, shape: tuple[int, int]) -> np.ndarray:
    """Node values (lats by lons, from node_axes) bilinear at the grid's cell centers, as float32.
    Rows are filled in chunks, so memory beyond the result stays small for a whole block."""
    x0, dx, _, y0, _, dy = transform
    rows, cols = shape
    ix, wx = _weights((_centers(x0, dx, cols) - lons[0]) / GRID_DEG, len(lons))
    iy, wy = _weights((lats[0] - _centers(y0, dy, rows)) / GRID_DEG, len(lats))
    across = nodes[:, ix] * (1 - wx) + nodes[:, ix + 1] * wx
    out = np.empty(shape, np.float32)
    for r in range(0, rows, _ROWS_PER_CHUNK):
        part = slice(r, r + _ROWS_PER_CHUNK)
        w = wy[part, None]
        out[part] = across[iy[part]] * (1 - w) + across[iy[part] + 1] * w
    return out
