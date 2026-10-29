"""Fishing depth contours, ported from wa-creel's onwater/contours.py.

Same thresholds, same order (Chaikin smoothing, then Douglas-Peucker). The grid is metres
below approximate MLLW (positive down, nan = removed, land already filled by merge.fill_land).
numpy, contourpy and shapely only.
"""

import math

import contourpy
import numpy as np
from shapely.geometry import LineString

# Every 10 ft to 300, then 400/500/600.
DEPTHS_FT = list(range(10, 301, 10)) + [400, 500, 600]
FINE_FT = list(range(5, 61, 10))  # 5, 15, ..., 55: the 5 ft steps between the 10 ft lines
MAJOR_FT = frozenset({60, 120, 180, 300, 600})  # heavier line, labelled first, shown from z10
BASE_FT = frozenset({30, 60, 90, 120, 150, 180, 240, 300, 400, 600})  # the original ten levels, from z12
SMOOTH_PASSES = 1
SIMPLIFY_DEG = 0.0002  # the wa-creel default; the per-zoom builds use zoom_tolerance_deg
MIN_POINTS = 6
M_TO_FT = 3.28084
M_PER_DEG = 111320.0

# (tippecanoe minzoom, maxzoom, target cell size in metres; 0 = native grid)
BANDS = ((10, 11, 150.0), (12, 13, 30.0), (14, 16, 0.0))


def zoom_tolerance_deg(zoom: int) -> float:
    """Douglas-Peucker tolerance of one 256 px Web Mercator pixel (R33), which is about 2 screen pixels in
    MapLibre's 512 px world (R46, kept for pack size: a true 1 px measured 301.4 MB): the ground resolution
    at latitude 48 (about 100 m at z10, 3 m at z15) in degrees of latitude; z16 uses the z15 value."""
    return 156543.03392804097 * math.cos(math.radians(48)) / 2 ** min(zoom, 15) / M_PER_DEG


def min_zoom(depth_ft: int) -> int:
    """Lowest map zoom that draws this depth."""
    if depth_ft in MAJOR_FT:
        return 10
    if depth_ft in BASE_FT:
        return 12
    if depth_ft % 20 == 0 or depth_ft == 500:
        return 13
    if depth_ft % 10 == 0:
        return 14
    return 15


def chaikin_line(points, passes=1) -> list[tuple[float, float]]:
    """Chaikin corner cutting on an open polyline; first and last points are kept."""
    pts = [tuple(p) for p in points]
    for _ in range(passes):
        if len(pts) < 3:
            break
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        out[0], out[-1] = pts[0], pts[-1]
        pts = out
    return pts


def simplify(points, tol_deg) -> list[tuple[float, float]]:
    """Douglas-Peucker; endpoints are always kept."""
    if len(points) < 3:
        return [tuple(p) for p in points]
    return [(x, y) for x, y in LineString(points).simplify(tol_deg, preserve_topology=False).coords]


def axes(shape, transform) -> tuple[np.ndarray, np.ndarray]:
    """Pixel-centre longitudes and latitudes of a grid with a GDAL geotransform."""
    x0, dx, _, y0, _, dy = transform
    return x0 + (np.arange(shape[1]) + 0.5) * dx, y0 + (np.arange(shape[0]) + 0.5) * dy


def build_contours(
    depth_m: np.ndarray,
    transform,
    *,
    levels_ft: list[int],
    smooth_passes: int = SMOOTH_PASSES,
    simplify_deg: float = SIMPLIFY_DEG,
    min_points: int = MIN_POINTS,
) -> list[dict]:
    """GeoJSON LineString features, one per contour line, in `levels_ft` order."""
    x, y = axes(depth_m.shape, transform)
    gen = contourpy.contour_generator(x, y, np.ma.masked_invalid(depth_m), line_type="Separate")
    feats = []
    for ft in levels_ft:
        for raw in gen.lines(ft / M_TO_FT):
            if len(raw) < min_points:  # specks, judged on the raw line as wa-creel does
                continue
            pts = simplify(chaikin_line([(float(a), float(b)) for a, b in raw], smooth_passes), simplify_deg)
            feats.append(
                {
                    "type": "Feature",
                    "properties": {"depth_ft": ft, "major": ft in MAJOR_FT, "minzoom": min_zoom(ft)},
                    "geometry": {"type": "LineString", "coordinates": [[round(a, 5), round(b, 5)] for a, b in pts]},
                }
            )
    return feats


def block_mean(depth_m: np.ndarray, transform, block: int):
    """Downsample by an integer block mean ignoring nan; returns (grid, transform)."""
    h, w = depth_m.shape
    ph, pw = -h % block, -w % block
    padded = np.pad(depth_m.astype(np.float64), ((0, ph), (0, pw)), constant_values=np.nan)
    blocks = padded.reshape((h + ph) // block, block, (w + pw) // block, block)
    valid = np.isfinite(blocks)
    total = np.where(valid, blocks, 0.0).sum(axis=(1, 3))
    count = valid.sum(axis=(1, 3))
    out = np.full(total.shape, np.nan)
    np.divide(total, count, out=out, where=count > 0)
    x0, dx, rx, y0, ry, dy = transform
    return out, (x0, dx * block, rx, y0, ry, dy * block)


def zoom_grids(depth_m: np.ndarray, transform):
    """(minzoom, maxzoom, target, grid, transform) per entry of BANDS, block-mean downsampled to target."""
    _, dx, _, y0, _, dy = transform
    mid_lat = y0 + dy * depth_m.shape[0] / 2
    cell_m = (abs(dx) * np.cos(np.radians(mid_lat)) + abs(dy)) * M_PER_DEG / 2
    for lo, hi, target in BANDS:
        block = max(1, round(target / cell_m)) if target else 1
        grid, tr = block_mean(depth_m, transform, block) if block > 1 else (depth_m, transform)
        yield lo, hi, target, grid, tr


def contours_by_zoom(depth_m: np.ndarray, transform, *, fine: bool) -> list[dict]:
    """Contours per zoom band: z10-11 from ~150 m cells, z12-13 from ~30 m, z14-16 native, each simplified
    to about one pixel at the band's top zoom (zoom_tolerance_deg).

    The tippecanoe key carries the band's zoom range; the `minzoom` property carries
    max(min_zoom(depth), band low) for the style filter. Depths whose min_zoom exceeds the
    band's top are not emitted in it. Fine (5 ft) levels are added in the native band only.
    """
    feats = []
    for lo, hi, target, grid, tr in zoom_grids(depth_m, transform):
        levels = DEPTHS_FT + FINE_FT if fine and not target else DEPTHS_FT
        levels = [ft for ft in sorted(levels) if min_zoom(ft) <= hi]
        for f in build_contours(grid, tr, levels_ft=levels, simplify_deg=zoom_tolerance_deg(hi)):
            f["properties"]["minzoom"] = max(f["properties"]["minzoom"], lo)
            f["tippecanoe"] = {"minzoom": lo, "maxzoom": hi}
            feats.append(f)
    return feats
