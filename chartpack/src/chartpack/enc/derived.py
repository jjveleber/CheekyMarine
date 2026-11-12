"""Nav depth areas, contours and soundings derived from a NONNA depth grid (plan 8 spec 7.1).

Shoal-biased: every downsample keeps the shallowest value, soundings are the shallowest value of their cell
rounded toward shallow, and every depth geometry is cut by the no-survey mask and the land before it is
returned, so no depth reaches into water with no survey value or onto land. The contours sit on the region's
fixed levels (regions/bc-valdco.toml), so they match the US ENC packs' VALDCO values.
"""

import math

import contourpy
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box, mapping

from chartpack.bathy.blocks import LABELS, SOURCE_NAMES
from chartpack.bathy.contours import BANDS, axes, block_factor, zoom_tolerance_deg
from chartpack.bathy.merge import _polygonize, clip_mask
from chartpack.enc.reader import Feature

SOUNDING_PX = 96  # one sounding per 96 by 96 pixel cell (256 px tiles) at each zoom
_NONNA = [SOURCE_NAMES.index("nonna10"), SOURCE_NAMES.index("nonna100")]
# Coarseness rank per source index (0, "none", lowest): the native cell size of the source
_RANK = np.array([0] + [LABELS[name]["resolution_m"] for name in SOURCE_NAMES[1:]])


def _blocks(values: np.ndarray, transform, block: int, fill):
    """values padded with fill to whole blocks on multiples of block from (-180, 90) (as block_mean does),
    shaped (rows, block, cols, block), and the downsampled transform."""
    x0, dx, rx, y0, ry, dy = transform
    lead_c = round((x0 + 180.0) / dx) % block
    lead_r = round((90.0 - y0) / -dy) % block
    h, w = values.shape
    padded = np.pad(values, ((lead_r, -(h + lead_r) % block), (lead_c, -(w + lead_c) % block)),
                    constant_values=fill)
    shaped = padded.reshape(padded.shape[0] // block, block, padded.shape[1] // block, block)
    return shaped, (x0 - lead_c * dx, dx * block, rx, y0 - lead_r * dy, ry, dy * block)


def block_min(depth_m: np.ndarray, transform, block: int) -> tuple[np.ndarray, tuple]:
    """The shallowest (smallest) value per block, on blocks anchored like block_mean: a block takes the minimum of
    its valid cells, and a block with none is nan. Returns (grid, transform)."""
    shaped, out_transform = _blocks(np.where(np.isnan(depth_m), np.inf, depth_m).astype(np.float32), transform,
                                    block, np.inf)
    out = shaped.min(axis=(1, 3))
    out[np.isinf(out)] = np.nan
    return out, out_transform


def _coarsest(src: np.ndarray, valid: np.ndarray, transform, block: int) -> np.ndarray:
    """The coarsest source index per block among its valid cells (0 for a block with none)."""
    rank, _ = _blocks(np.where(valid, _RANK[src], 0), transform, block, 0)
    best = rank.max(axis=(1, 3))
    by_rank = np.zeros(_RANK.max() + 1, np.int8)
    by_rank[_RANK] = np.arange(len(_RANK))
    return by_rank[best]


def _fmt(value: float) -> str:
    return format(float(value), ".15g")


def _parts(geom, dim: int) -> list:
    return [g for g in shapely.get_parts(geom) if not g.is_empty and shapely.get_dimensions(g) == dim]


def _src_areas(src: np.ndarray, transform) -> list[tuple[str, shapely.Geometry]]:
    """(source name, area) per source present in src but the finest, coarsest first: the cells of that source
    grown by one cell, so a line or area drawn between its cell centers meets it."""
    present = sorted((i for i in np.unique(src) if i), key=lambda i: _RANK[i], reverse=True)
    areas = []
    for index in present[:-1]:
        cells = src == index
        grown = cells.copy()
        grown[1:] |= cells[:-1]
        grown[:-1] |= cells[1:]
        grown[:, 1:] |= grown[:, :-1].copy()
        grown[:, :-1] |= grown[:, 1:].copy()
        area = shapely.union_all([g for _, g in _polygonize(grown.astype(np.uint8), transform)])
        shapely.prepare(area)
        areas.append((SOURCE_NAMES[index], area))
    return areas


def _name(geom, areas, finest: str) -> str:
    return next((name for name, area in areas if area.intersects(geom)), finest)


def _depth_features(grid, src, transform, *, levels_m, drying_m, cut, tol, zooms) -> list[Feature]:
    """depare and depcnt of one band's grid, simplified by tol, then cut to `cut`."""
    if min(grid.shape) < 2:
        return []
    valid = np.isfinite(grid)
    present = [i for i in np.unique(src[valid]) if i]
    if not present:
        return []
    finest = SOURCE_NAMES[min(present, key=lambda i: _RANK[i])]
    areas = _src_areas(np.where(valid, src, 0), transform)
    x, y = axes(grid.shape, transform)
    gen = contourpy.contour_generator(x, y, np.ma.masked_invalid(grid), line_type="Separate",
                                      fill_type=contourpy.FillType.OuterOffset)
    tip = {"minzoom": zooms[0], "maxzoom": zooms[1]}
    out = []
    bounds = ([(-drying_m, 0.0)] if drying_m else []) + list(zip(levels_m, levels_m[1:]))
    for lo, hi in bounds:
        points, offsets = gen.filled(lo, hi)
        for pts, offs in zip(points, offsets):
            rings = [pts[a:b] for a, b in zip(offs, offs[1:])]
            poly = Polygon(rings[0], rings[1:]).simplify(tol, preserve_topology=True)
            for part in _parts(poly.intersection(cut), 2):
                props = {"DRVAL1": _fmt(lo), "DRVAL2": _fmt(hi), "src": _name(part, areas, finest), "tippecanoe": tip}
                out.append(Feature("depare", mapping(part), props))
    for level in levels_m:
        for line in gen.lines(level):
            simple = LineString(line).simplify(tol, preserve_topology=False)
            for part in _parts(simple.intersection(cut), 1):
                props = {"VALDCO": _fmt(level), "src": _name(part, areas, finest), "tippecanoe": tip}
                out.append(Feature("depcnt", mapping(part), props))
    return out


def _shoal_m(depth: float) -> float:
    """depth rounded toward shallow to 0.1 m (float32 noise on an exact tenth kept)."""
    return math.floor(round(depth * 10, 4)) / 10


def _soundings(depth_m, src, transform, allowed, cut, zooms) -> list[Feature]:
    """One sounding per SOUNDING_PX cell of the global Web Mercator pixel grid at each zoom of zooms: the
    shallowest NONNA value among the allowed cells under it, at its cell center. A zoom's cell holds exactly
    2 by 2 cells of the next zoom, so each zoom is taken from the next one's soundings."""
    lo, hi = zooms
    x0, dx, _, y0, _, dy = transform
    lon, lat = axes(depth_m.shape, transform)
    world = 256 * 2**hi
    kx = np.floor((lon + 180) / 360 * world / SOUNDING_PX).astype(np.int64)
    ky = np.floor((1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * world / SOUNDING_PX).astype(np.int64)
    take = allowed & np.isin(src, _NONNA) & np.isfinite(depth_m)
    values = np.where(take, depth_m, np.inf)
    col_starts = np.flatnonzero(np.diff(kx, prepend=kx[0] - 1))
    row_starts = np.flatnonzero(np.diff(ky, prepend=ky[0] - 1))
    found = []  # (kx, ky, depth, row, col) at the top zoom
    for r0, r1 in zip(row_starts, list(row_starts[1:]) + [len(ky)]):
        strip = values[r0:r1]
        best_row = strip.argmin(axis=0)
        col_min = strip[best_row, np.arange(strip.shape[1])]
        cell_min = np.minimum.reduceat(col_min, col_starts)
        lengths = np.diff(np.append(col_starts, len(kx)))
        first = np.minimum.reduceat(np.where(col_min == np.repeat(cell_min, lengths), np.arange(len(kx)), len(kx)),
                                    col_starts)
        for c, v in zip(first[np.isfinite(cell_min)], cell_min[np.isfinite(cell_min)]):
            found.append((kx[c], ky[r0], v, r0 + best_row[c], c))
    out = []
    cells = np.array(found, dtype=float).reshape(-1, 5)
    for z in range(hi, lo - 1, -1):
        shift = hi - z
        keys = (cells[:, 0].astype(np.int64) >> shift, cells[:, 1].astype(np.int64) >> shift)
        order = np.lexsort((cells[:, 2], keys[0], keys[1]))
        k0, k1 = keys[0][order], keys[1][order]
        first = order[np.r_[True, (np.diff(k0) != 0) | (np.diff(k1) != 0)]] if len(order) else order
        for _, _, v, row, col in cells[first]:
            row, col = int(row), int(col)
            point = Point(x0 + (col + 0.5) * dx, y0 + (row + 0.5) * dy)
            if cut.contains(point):
                props = {"depth": _fmt(_shoal_m(v)), "src": SOURCE_NAMES[src[row, col]],
                         "tippecanoe": {"minzoom": z, "maxzoom": z}}
                out.append(Feature("soundg", mapping(point), props))
    return out


def derived_features(depth_m: np.ndarray, src: np.ndarray, transform, *, core, levels_m: list[float],
                     nosurvey: shapely.Geometry, land: shapely.Geometry, lat: float) -> list[Feature]:
    """The Nav features of one block from depth_m (meters, positive down, a drying height negative, nan for no
    value; src its source index into SOURCE_NAMES), each carrying its tippecanoe zoom range:

    - per BANDS zoom range, from the grid block-min downsampled to the band's cell size: depare between
      consecutive levels_m (DRVAL1, DRVAL2), plus one drying area from -H to 0 (H the greatest drying height in
      depth_m rounded up to 0.1 m), and depcnt on levels_m (VALDCO), each with src: the source of its cells, the
      coarsest when it spans more than one; simplified to about a pixel at the band's top zoom (at lat);
    - soundg per zoom (_soundings), from nonna10 and nonna100 cells only, src the source of the cell;
    - lndare and coalne from land, src "fwa", and nosurvey, each cut to core, over every BANDS zoom.

    Every depth geometry is cut to core less nosurvey and land. For the offshore kind the caller passes the coarse
    merge and empty nosurvey and land."""
    core_box = box(*core)
    cut = core_box.difference(shapely.union_all([nosurvey, land]))
    shapely.prepare(cut)
    levels = sorted(float(v) for v in levels_m)
    with np.errstate(invalid="ignore"):
        dry = depth_m[depth_m < 0]
    drying_m = math.ceil(round(-float(dry.min()) * 10, 4)) / 10 if dry.size else 0.0
    zooms = (BANDS[0][0], BANDS[-1][1])
    out = []
    if not cut.is_empty:
        valid = np.isfinite(depth_m)
        for lo, hi, target in BANDS:
            k = block_factor(transform, target)
            grid, tr = block_min(depth_m, transform, k) if k > 1 else (depth_m, transform)
            band_src = _coarsest(src, valid, transform, k) if k > 1 else src
            out += _depth_features(grid, band_src, tr, levels_m=levels, drying_m=drying_m, cut=cut,
                                   tol=zoom_tolerance_deg(hi, lat), zooms=(lo, hi))
        allowed = clip_mask(transform, depth_m.shape, mapping(cut))
        out += _soundings(depth_m, src, transform, allowed, cut, zooms)
    tip = {"minzoom": zooms[0], "maxzoom": zooms[1]}
    for part in _parts(land.intersection(core_box), 2):
        out.append(Feature("lndare", mapping(part), {"src": "fwa", "tippecanoe": tip}))
    for part in _parts(land.boundary.intersection(core_box), 1):
        out.append(Feature("coalne", mapping(part), {"src": "fwa", "tippecanoe": tip}))
    for part in _parts(nosurvey.intersection(core_box), 2):
        out.append(Feature("nosurvey", mapping(part), {"tippecanoe": tip}))
    return out
