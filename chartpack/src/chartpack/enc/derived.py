"""Nav depth areas, contours and soundings derived from a NONNA depth grid (plan 8 spec 7.1).

Shoal-biased: every downsample keeps the shallowest value, each contoured grid first takes the shallowest value
of every cell's 3 by 3 neighborhood (so the surface contourpy interpolates between cell centers is nowhere deeper
than any cell under it), soundings are the shallowest value of their cell rounded toward shallow, and every
depth geometry is cut to the valid cells less the no-survey mask and the land before it is returned, so no depth
reaches into water with no survey value or onto land. Depth areas and contours are not simplified here:
tippecanoe simplifies them at tiling, as it does the NOAA features. The contours sit on the region's
fixed levels (regions/bc-valdco.toml), so they match the US ENC packs' VALDCO values.
"""

import math

import contourpy
import numpy as np
import shapely
from shapely import GeometryType
from shapely.geometry import Point, box, mapping

from chartpack.bathy.blocks import LABELS, SOURCE_NAMES
from chartpack.bathy.contours import BANDS, axes, block_factor
from chartpack.bathy.merge import _polygonize, clip_mask
from chartpack.enc.reader import Feature

SOUNDING_PX = 96  # one sounding per 96 by 96 pixel cell (256 px tiles) at each zoom
DEEPEST_M = 12000.0  # DRVAL2 of the area deeper than the last level
# The working cell size in meters (block_factor's measure): a finer input grid is first block-min reduced to about
# this, the ground size of a NONNA-10 native cell in BC (19 m in EPSG:3857, 12 to 13 m at 49 to 51 N). The fine
# nav_depth grid (1/9 arc-second, about 2.9 m by that measure) is reduced 4 times; the BANDS factors are then
# taken from the reduced grid, as zoom_grids takes them from the grid it is given.
NAV_BASE_M = 12.0
CUT_TILES = 16  # the cut is split CUT_TILES by CUT_TILES over the core (_tiles)
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


def _neighborhood_min(grid: np.ndarray, transform) -> tuple[np.ndarray, tuple]:
    """The shallowest value of each cell's 3 by 3 neighborhood (nan ignored, nan where all nine are), on the grid
    grown by one cell on every side, and its transform. Every quad contourpy interpolates then has corners no
    deeper than any cell whose square it crosses, and the outer cells' squares are covered to their edges."""
    h, w = grid.shape
    padded = np.pad(np.where(np.isnan(grid), np.inf, grid), 2, constant_values=np.inf)
    out = padded[:h + 2, :w + 2].copy()
    for dr in range(3):
        for dc in range(3):
            np.minimum(out, padded[dr:dr + h + 2, dc:dc + w + 2], out=out)
    out[np.isinf(out)] = np.nan
    x0, dx, rx, y0, ry, dy = transform
    return out, (x0 - dx, dx, rx, y0 - dy, ry, dy)


def _cells(mask: np.ndarray, transform) -> shapely.Geometry:
    """The True cells of mask as one geometry."""
    return shapely.coverage_union_all([g for _, g in _polygonize(mask.astype(np.uint8), transform)])


def _src_areas(src: np.ndarray, transform) -> list[tuple[str, shapely.Geometry]]:
    """(source name, area) per source present in src but the finest, coarsest first: the cells of that source
    grown by two cells, so a line or area drawn from values the neighborhood minimum carried one cell meets it."""
    present = sorted((i for i in np.unique(src) if i), key=lambda i: _RANK[i], reverse=True)
    areas = []
    for index in present[:-1]:
        grown = src == index
        for _ in range(2):
            step = grown.copy()
            step[1:] |= grown[:-1]
            step[:-1] |= grown[1:]
            grown = step.copy()
            grown[:, 1:] |= step[:, :-1]
            grown[:, :-1] |= step[:, 1:]
        area = _cells(grown, transform)
        shapely.prepare(area)
        areas.append((SOURCE_NAMES[index], area))
    return areas


def _tiles(cut, core) -> shapely.STRtree:
    """cut split on a CUT_TILES by CUT_TILES grid over core, in an STRtree: an overlay costs about the size of both
    inputs, and a land or mask cut can be large, so each geometry is cut by the pieces it meets only."""
    w, s, e, n = core
    xs, ys = np.linspace(w, e, CUT_TILES + 1), np.linspace(s, n, CUT_TILES + 1)
    pieces = shapely.get_parts([shapely.clip_by_rect(cut, x0, y0, x1, y1)
                                for x0, x1 in zip(xs, xs[1:]) for y0, y1 in zip(ys, ys[1:])])
    return shapely.STRtree(pieces[~shapely.is_empty(pieces) & (shapely.get_dimensions(pieces) == 2)])


def _cut(geoms: np.ndarray, tiles: shapely.STRtree, dim: int) -> np.ndarray:
    """The parts of geoms of dimension dim inside the cut (_tiles): each geometry is cut by the union of the pieces
    it meets (one union per set of pieces), so it is not split at tile edges."""
    if not len(geoms):
        return geoms
    g, t = tiles.query(geoms)
    order = np.lexsort((t, g))
    g, t = g[order], t[order]
    starts = np.flatnonzero(np.r_[True, g[1:] != g[:-1]]) if len(g) else np.array([], int)
    local, cache = [], {}
    for a, b in zip(starts, np.r_[starts[1:], len(g)]):
        key = tuple(t[a:b])
        if key not in cache:
            cache[key] = tiles.geometries[key[0]] if len(key) == 1 else shapely.union_all(tiles.geometries[list(key)])
        local.append(cache[key])
    parts = shapely.get_parts(shapely.intersection(geoms[g[starts]], np.array(local, object)))
    return parts[~shapely.is_empty(parts) & (shapely.get_dimensions(parts) == dim)]


def _depth_features(grid, src, transform, *, levels_m, drying_m, tiles, zooms) -> list[Feature]:
    """depare and depcnt of one band's grid (already neighborhood-min), cut to `cut`. src holds the source index of
    the cells before the neighborhood minimum (0 elsewhere). tiles: the cut (_tiles)."""
    valid = np.isfinite(grid)
    if min(grid.shape) < 2 or not valid.any():
        return []
    present = [i for i in np.unique(src) if i]
    finest = SOURCE_NAMES[min(present, key=lambda i: _RANK[i])]
    areas = _src_areas(src, transform)
    x, y = axes(grid.shape, transform)
    gen = contourpy.contour_generator(x, y, np.ma.masked_invalid(grid), line_type="ChunkCombinedOffset",
                                      fill_type="ChunkCombinedOffsetOffset")
    low, high = float(grid[valid].min()), float(grid[valid].max())
    bounds = ([(-drying_m, 0.0)] if drying_m else []) + list(zip(levels_m, levels_m[1:])) + [(levels_m[-1], DEEPEST_M)]
    tip = {"minzoom": zooms[0], "maxzoom": zooms[1]}

    def named(parts, layer, props):
        names = np.full(len(parts), finest, object)
        for name, area in reversed(areas):  # the coarsest last, so it wins
            names[shapely.intersects(parts, area)] = name
        return [Feature(layer, mapping(g), {**props, "src": n, "tippecanoe": tip}) for g, n in zip(parts, names)]

    out = []
    for i, (lo, hi) in enumerate(bounds):
        if hi < low or (lo >= high and i):
            continue
        # contourpy fills lower < z <= upper: the lowest band starts below the grid, so it holds its own bound
        points, offsets, outer = gen.filled(min(lo, low) - 1.0 if i == 0 else lo, hi)
        if points[0] is not None:
            polygons = shapely.from_ragged_array(GeometryType.POLYGON, points[0], (offsets[0], outer[0]))
            out += named(_cut(polygons, tiles, 2), "depare", {"DRVAL1": _fmt(lo), "DRVAL2": _fmt(hi)})
    for level in levels_m:
        if low <= level <= high:
            points, offsets = gen.lines(level)
            if points[0] is not None:
                lines = shapely.from_ragged_array(GeometryType.LINESTRING, points[0], (offsets[0],))
                out += named(_cut(lines, tiles, 1), "depcnt", {"VALDCO": _fmt(level)})
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
      depth_m rounded up to 0.1 m) and one from the last level to DEEPEST_M, and depcnt on levels_m (VALDCO),
      each with src: the source of its cells, the coarsest when it spans more than one. A grid finer than
      NAV_BASE_M is first block-min reduced to it, and each band grid takes its 3 by 3 neighborhood minimum
      (_neighborhood_min) before contouring; nothing is simplified (tippecanoe does that);
    - soundg per zoom (_soundings), from nonna10 and nonna100 cells only, src the source of the cell;
    - lndare and coalne from land, src "fwa", and nosurvey, each cut to core, over every BANDS zoom.

    Every depth geometry is cut to core and to the valid input cells, less nosurvey and land.
    lat is unused since nothing is simplified here (kept in the interface). For the offshore kind the caller passes the coarse merge and empty nosurvey and land."""
    core_box = box(*core)
    levels = sorted(float(v) for v in levels_m)
    # H from the whole input grid (the read area too), so it can only overstate the drying height
    with np.errstate(invalid="ignore"):
        dry = depth_m[depth_m < 0]
    drying_m = math.ceil(round(-float(dry.min()) * 10, 4)) / 10 if dry.size else 0.0
    zooms = (BANDS[0][0], BANDS[-1][1])
    out = []
    valid = np.isfinite(depth_m)
    if valid.any():
        k = block_factor(transform, NAV_BASE_M)
        base, base_tr = block_min(depth_m, transform, k) if k > 1 else (depth_m, transform)
        base_src = _coarsest(src, valid, transform, k) if k > 1 else np.where(valid, src, 0)
        if not src[valid].any():
            raise ValueError("derived_features: src is 0 (none) on every valid depth cell")
        base_valid = np.isfinite(base)  # a reduced cell is valid when any input cell under it is
        # the footprint is the input's own valid cells: no depth over a nan input cell, none missing from a valid one
        cut = core_box.intersection(_cells(valid, transform)).difference(shapely.union_all([nosurvey, land]))
        shapely.prepare(cut)
        if not cut.is_empty:
            tiles = _tiles(cut, core)
            for lo, hi, target in BANDS:
                k = block_factor(base_tr, target)
                grid, tr = block_min(base, base_tr, k) if k > 1 else (base, base_tr)
                band_src = _coarsest(base_src, base_valid, base_tr, k) if k > 1 else base_src
                grid, tr = _neighborhood_min(grid, tr)
                out += _depth_features(grid, np.pad(band_src, 1), tr, levels_m=levels, drying_m=drying_m,
                                       tiles=tiles, zooms=(lo, hi))
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
