"""Signed distance fields in the MapLibre/fontnik convention (SDF stored as an 8-bit value, edge near 191)."""

import numpy as np
from scipy.ndimage import distance_transform_edt


def bitmap_to_sdf(alpha: np.ndarray, *, buffer: int = 3, radius: float = 8.0, cutoff: float = 0.25) -> np.ndarray:
    """Pad `alpha` by `buffer` and return 255 - 255 * clamp(d / radius + cutoff, 0, 1) with d positive outside.

    The edge is taken at the centre of the outermost inside pixel (d = 0 there), so the edge maps to
    255 * (1 - cutoff) = 191, deep inside to 255 and far outside to 0.
    """
    inside = np.pad(alpha >= 128, buffer)
    outside_dist = distance_transform_edt(~inside) # distance to the nearest inside pixel
    inside_dist = distance_transform_edt(inside)  # distance to the nearest outside pixel
    d = np.where(inside, 1.0 - inside_dist, outside_dist)
    return np.round(255 - 255 * np.clip(d / radius + cutoff, 0, 1)).astype(np.uint8)
