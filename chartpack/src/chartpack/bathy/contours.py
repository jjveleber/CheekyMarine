"""Fishing depth contours, ported from wa-creel's onwater/contours.py.

Same thresholds, same order (Chaikin smoothing, then Douglas-Peucker). The grid is metres
below approximate MLLW (positive down, nan = removed, land already filled by merge.fill_land).
numpy, contourpy and shapely only.
"""

import math

import contourpy
import numpy as np
import shapely
from shapely.geometry import LineString, box

# Every 10 ft to 300, every 50 to 600, every 100 to 1,000.
DEPTHS_FT = list(range(10, 301, 10)) + list(range(350, 601, 50)) + list(range(700, 1001, 100))
FINE_FT = list(range(5, 61, 10))  # 5, 15, ..., 55: the 5 ft steps between the 10 ft lines
MAJOR_FT = frozenset({60, 120, 180, 300, 400, 500, 600, 800, 1000})  # heavier line, labelled first, shown from z10
BASE_FT = frozenset({30, 60, 90, 120, 150, 180, 240, 300, 350, 400, 450, 550, 600, 700, 900})  # base levels, from z12
SMOOTH_PASSES = 1
SIMPLIFY_DEG = 0.0002  # the wa-creel default; the per-zoom builds use zoom_tolerance_deg
MIN_POINTS = 6
M_TO_FT = 3.28084
M_PER_DEG = 111320.0

# (tippecanoe minzoom, maxzoom, target cell size in metres; 0 = native grid)
BANDS = ((10, 11, 150.0), (12, 13, 30.0), (14, 16, 0.0))
COARSE_BANDS = ((10, 11, 150.0), (12, 12, 30.0))  # the CRM-only outputs, capped at zoom 12 (overzoomed past it)
OVERVIEW_BANDS = ((6, 9, 300.0),)  # the overview pack: major levels only
REF_LAT = 48.0  # downsample factors are fixed at this latitude so every block (and pack) uses the same ones


def zoom_tolerance_deg(zoom: int, lat: float) -> float:
    """Douglas-Peucker tolerance of one 256 px Web Mercator pixel (R33), which is about 2 screen pixels in
    MapLibre's 512 px world (R46, kept for pack size: a true 1 px measured 301.4 MB): the ground resolution
    at `lat` (at 48 N about 100 m at z10, 3 m at z15) in degrees of latitude; z16 uses the z15 value. `lat`
    is rounded to the nearest 0.25 degree, like minzoom_for_scamin's, so neighboring blocks on both sides of a
    pack seam use one value (#18)."""
    lat = round(lat * 4) / 4
    return 156543.03392804097 * math.cos(math.radians(lat)) / 2 ** min(zoom, 15) / M_PER_DEG


def center_lat(depth_m: np.ndarray, transform, core=None) -> float:
    """The latitude the per-zoom tolerances use (#18): the center of the block core, or of the grid without one."""
    if core is not None:
        return (core[1] + core[3]) / 2
    return transform[3] + transform[5] * depth_m.shape[0] / 2


def min_zoom(depth_ft: int) -> int:
    """Lowest map zoom that draws this depth."""
    if depth_ft in MAJOR_FT:
        return 10
    if depth_ft in BASE_FT:
        return 12
    if depth_ft % 20 == 0:
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


def _parts(raw: list[tuple[float, float]], core) -> list[list[tuple[float, float]]]:
    """The raw line, or its pieces inside `core` (W, S, E, N) when one is given."""
    if core is None:
        return [raw]
    clipped = shapely.intersection(LineString(raw), box(*core))
    lines = getattr(clipped, "geoms", [clipped])
    return [list(line.coords) for line in lines if line.geom_type == "LineString" and len(line.coords) >= 2]


def build_contours(
    depth_m: np.ndarray,
    transform,
    *,
    levels_ft: list[int],
    smooth_passes: int = SMOOTH_PASSES,
    simplify_deg: float = SIMPLIFY_DEG,
    min_points: int = MIN_POINTS,
    core=None,
) -> list[dict]:
    """GeoJSON LineString features, one per contour line, in `levels_ft` order.

    With `core` (W, S, E, N) the raw lines are clipped to it before smoothing and simplifying. Both keep the
    end points, so two blocks traced over the same cells end their lines at the same raw edge crossing.
    """
    x, y = axes(depth_m.shape, transform)
    gen = contourpy.contour_generator(x, y, np.ma.masked_invalid(depth_m), line_type="Separate")
    feats = []
    for ft in levels_ft:
        for raw in gen.lines(ft / M_TO_FT):
            if len(raw) < min_points:  # specks, judged on the raw line as wa-creel does
                continue
            for part in _parts([(float(a), float(b)) for a, b in raw], core):
                pts = simplify(chaikin_line(part, smooth_passes), simplify_deg)
                feats.append(
                    {
                        "type": "Feature",
                        "properties": {"depth_ft": ft, "major": ft in MAJOR_FT, "minzoom": min_zoom(ft)},
                        "geometry": {"type": "LineString", "coordinates": [[round(a, 5), round(b, 5)] for a, b in pts]},
                    }
                )
    return feats


def block_mean(depth_m: np.ndarray, transform, block: int):
    """Downsample by an integer block mean ignoring nan; returns (grid, transform).

    The blocks sit on multiples of their own size from (-180, 90): leading rows and columns of nan pad the
    grid to the nearest such origin, so blocks of a globally anchored grid line up across neighboring grids.
    """
    x0, dx, rx, y0, ry, dy = transform
    lead_c = round((x0 + 180.0) / dx) % block
    lead_r = round((90.0 - y0) / -dy) % block
    h, w = depth_m.shape
    ph, pw = -(h + lead_r) % block, -(w + lead_c) % block
    padded = np.pad(depth_m.astype(np.float32), ((lead_r, ph), (lead_c, pw)), constant_values=np.nan)
    blocks = padded.reshape(padded.shape[0] // block, block, padded.shape[1] // block, block)
    count = np.isfinite(blocks).sum(axis=(1, 3))
    np.nan_to_num(padded, copy=False)  # in place: one float32 copy of the grid at a time
    total = blocks.sum(axis=(1, 3), dtype=np.float64)
    out = np.full(total.shape, np.nan)
    np.divide(total, count, out=out, where=count > 0)
    return out, (x0 - lead_c * dx, dx * block, rx, y0 - lead_r * dy, ry, dy * block)


def block_factor(transform, target: float) -> int:
    """The block-mean factor zoom_grids uses to reach a target cell size in meters (0 = native) from this grid."""
    _, dx, _, _, _, dy = transform
    cell_m = (abs(dx) * np.cos(np.radians(REF_LAT)) + abs(dy)) * M_PER_DEG / 2
    return max(1, round(target / cell_m)) if target else 1


def zoom_grids(depth_m: np.ndarray, transform, bands=BANDS):
    """(minzoom, maxzoom, target, grid, transform) per entry of `bands`, block-mean downsampled to target.

    The block factor is the target over the cell size at REF_LAT, not at the grid's own latitude, so
    neighboring blocks downsample alike.
    """
    for lo, hi, target in bands:
        block = block_factor(transform, target)
        grid, tr = block_mean(depth_m, transform, block) if block > 1 else (depth_m, transform)
        yield lo, hi, target, grid, tr


def band_levels(levels_ft, hi: int) -> list[int]:
    """The levels a zoom range up to `hi` draws: min_zoom(ft) <= hi, and the major levels always (the overview,
    below zoom 10, draws the majors only)."""
    return [ft for ft in sorted(levels_ft) if ft in MAJOR_FT or min_zoom(ft) <= hi]


def contours_by_zoom(
    depth_m: np.ndarray, transform, *, fine: bool, bands=BANDS, core=None, overzoomed: bool = False
) -> list[dict]:
    """Contours per zoom band: with BANDS, z10-11 from ~150 m cells, z12-13 from ~30 m, z14-16 native, each
    simplified to about one pixel at the band's top zoom (zoom_tolerance_deg) at center_lat.

    The tippecanoe key carries the band's zoom range; the `minzoom` property carries
    max(min_zoom(depth), band low) for the style filter (the band low for a major line). Depths whose
    min_zoom exceeds the band's top are not emitted in it, except the majors (band_levels). Fine (5 ft)
    levels are added in the native band only. `core` clips the raw lines (build_contours).

    overzoomed: the file stops at the last band's top and the map overzooms it (bathy-coarse, z12), so the
    last band carries every DEPTHS_FT level; the style tiers show each from its `minzoom` property.
    """
    lat = center_lat(depth_m, transform, core)
    feats = []
    for i, (lo, hi, target, grid, tr) in enumerate(zoom_grids(depth_m, transform, bands)):
        top = max(min_zoom(ft) for ft in DEPTHS_FT) if overzoomed and i == len(bands) - 1 else hi
        levels = band_levels(DEPTHS_FT + FINE_FT if fine and not target else DEPTHS_FT, top)
        for f in build_contours(grid, tr, levels_ft=levels, simplify_deg=zoom_tolerance_deg(hi, lat), core=core):
            p = f["properties"]
            p["minzoom"] = lo if p["major"] else max(p["minzoom"], lo)
            f["tippecanoe"] = {"minzoom": lo, "maxzoom": hi}
            feats.append(f)
    return feats
