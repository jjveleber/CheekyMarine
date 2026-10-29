"""Deterministic synthetic bathymetry for the merge tests; writes tests/fixtures/ridge.npy.

200 by 200 float32 elevation (NAVD88 metres, negative down), row 0 north, columns west to
east. A north-south ridge: -120 m at the west and east edges rising smoothly to -20 m at the
centre. Land (+5 m) in the easternmost 10 columns. A 10 by 10 NoData (-9999) hole at rows
50..59, cols 50..59.
"""

from pathlib import Path

import numpy as np

NODATA = -9999.0
ORIGIN = (-122.5, 48.0)  # west, north
PIXEL_DEG = 0.001
BBOX = (-122.5, 47.8, -122.3, 48.0)  # W, S, E, N


def make_ridge() -> np.ndarray:
    x = np.arange(200) / 199
    row = -120.0 + 100.0 * np.sin(np.pi * x)
    elev = np.tile(row, (200, 1)).astype(np.float32)
    elev[:, 190:] = 5.0
    elev[50:60, 50:60] = NODATA
    return elev


if __name__ == "__main__":
    np.save(Path(__file__).parent / "fixtures" / "ridge.npy", make_ridge())
