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
from shapely.geometry import Point, box, mapping, shape

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
# A depth area part thinner than this, in tile units at its band's minzoom (mean width 2 A / P in Web Mercator), is
# dropped and drawn as nosurvey: tippecanoe turns a part under about one unit into a square of the same area at its
# center, half over its neighbor (plan8-checkfix, check-hypotheses R.0).
THIN_UNITS = 2.0
PATCH_UNITS = 8.0  # each band's nosurvey patch takes the nosurvey this far round its thin parts (minzoom units)
# A thin part goes to nosurvey only when at least this share of its perimeter lies along nosurvey (or along parts
# already sent): a contour band strip between two depth bands that meets the mask at its tip stays depth, since
# its patch would be as thin as itself (dry run 3, Ruling 48).
SHARE_MIN = 0.25
# A thin part sharing an edge at least this long (degrees, about 1 cm: an edge, not a corner) with the nosurvey
# but under SHARE_MIN of its perimeter goes too, inside the nosurvey piece it meets rather than as a patch of its
# own (Ruling 55 C).
_JOIN_DEG = 1e-7
# A thin part kept as depth goes after all when tippecanoe's square of it (same area, at its centroid) would reach
# more than this into the nosurvey: the pack check's NOSURVEY_TOLERANCE_UNITS (PR 134 review, a curved strip
# ringing a small mask pocket).
_SQUARE_REACH_UNITS = 4.5
_VERTEX_ROUNDS = 4  # derived_features shares vertices between depth and nosurvey in at most this many rounds
_EDGE_DEG = 1e-9  # about 0.1 mm: an edge this close counts as shared (two overlays of one edge differ in float noise)
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
    inputs, and a land or mask cut can be large, so each geometry is cut by the pieces it meets only. Each piece
    is an overlay with its tile's box: GEOS's fast clip_by_rect fails on a valid sliver that collapses in the tile
    ("Invalid number of points in LinearRing") and can return a self-touching, invalid ring."""
    w, s, e, n = core
    xs, ys = np.linspace(w, e, CUT_TILES + 1), np.linspace(s, n, CUT_TILES + 1)
    pieces = shapely.get_parts([shapely.intersection(cut, box(x0, y0, x1, y1))
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


def _thin(parts: np.ndarray, z: int) -> np.ndarray:
    """Whether each lon/lat polygon of parts is thinner than THIN_UNITS: its mean width (2 A / P) in the tile units
    of zoom z (Web Mercator, 4,096 per tile)."""
    n = 2**z * 4096

    def to_units(c):
        return np.column_stack([(c[:, 0] + 180.0) / 360.0 * n,
                                (1 - np.arcsinh(np.tan(np.radians(c[:, 1]))) / math.pi) / 2 * n])

    units = shapely.transform(parts, to_units)
    return 2 * shapely.area(units) < THIN_UNITS * shapely.length(units)


def _segments(geoms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Every boundary segment of the polygons geoms, each a LineString, and the index of its polygon."""
    rings, owner = shapely.get_parts(shapely.boundary(geoms), return_index=True)
    coords, which = shapely.get_coordinates(rings, return_index=True)
    same = which[1:] == which[:-1]
    return shapely.linestrings(np.stack([coords[:-1][same], coords[1:][same]], axis=1)), owner[which[:-1][same]]


def _shared(parts: np.ndarray, reach: np.ndarray) -> np.ndarray:
    """The length of each part's boundary lying along the boundary of the polygons reach (within _EDGE_DEG),
    segment against segment (_Shares)."""
    return _Shares(parts).along(reach, np.ones(len(parts), bool))


class _Shares:
    """The boundary segments of parts, segmented once in an STRtree, to measure against reach after reach: each
    call costs the reach's own segments and the part segments near them (an STRtree query), not every part."""

    def __init__(self, parts: np.ndarray):
        self.n = len(parts)
        self.mine, self.owner = _segments(parts) if len(parts) else (np.array([], object), np.array([], int))
        self.tree = shapely.STRtree(self.mine)

    def along(self, reach: np.ndarray, open_: np.ndarray) -> np.ndarray:
        """The length of each part's boundary along the boundary of the polygons reach, for the parts open_ (0 for
        the others)."""
        out = np.zeros(self.n)
        if not self.n or not len(reach):
            return out
        theirs, _ = _segments(reach)
        b, a = self.tree.query(theirs, predicate="dwithin", distance=_EDGE_DEG)
        keep = open_[self.owner[a]]
        a, b = a[keep], b[keep]
        if len(a):
            along = shapely.intersection(self.mine[a], shapely.buffer(theirs[b], _EDGE_DEG, quad_segs=1))
            np.add.at(out, self.owner[a], shapely.length(along))
        return out


def _meeting(parts: np.ndarray, area: shapely.Geometry) -> np.ndarray:
    """Whether each part meets area, testing against area prepared (the large mask first, so its index is used)."""
    if area.is_empty or not len(parts):
        return np.zeros(len(parts), bool)
    shapely.prepare(area)
    return shapely.intersects(area, parts)


def _to_nosurvey(parts: np.ndarray, thin: np.ndarray, area: shapely.Geometry, z: int | None = None, *,
                 share: float = SHARE_MIN, least: float = 0.0, sent: np.ndarray | None = None) -> np.ndarray:
    """Which parts go to nosurvey: the thin ones with at least SHARE_MIN of their perimeter along area (the
    nosurvey of the band) or along thin parts already sent, until none is added. A thin part meeting them at a
    corner only, or along a short stretch (a contour band strip that meets the mask at its tip), stays depth: sent,
    it would be a nosurvey patch as thin as itself, which tippecanoe draws as a square over the depth beside it.
    With z (the band's minzoom), a thin part kept so goes after all when its square (_square_in) would reach into
    area, and the share rule runs on from it. share: the share of the perimeter needed (SHARE_MIN by default);
    least: a shared length (degrees) needed as well; sent: parts already gone (kept so, and measured against
    from the start)."""
    out = np.zeros(len(parts), bool) if sent is None else sent.copy()
    index = np.flatnonzero(thin & ~out)
    if not len(index) or area.is_empty:
        return out
    need = np.maximum(share * shapely.length(parts[index]), least)
    shares = _Shares(parts[index])  # segmented once; each round measures only the open parts near the new reach
    shared = np.zeros(len(index))
    reach = np.concatenate([shapely.get_parts(area), parts[out]])
    cache = {}  # the mask's pieces for the square test (_subdivide), built at its first use
    while True:
        while len(reach):
            open_ = ~out[index]
            shared += shares.along(reach, open_)
            new = index[open_ & (shared >= need)]
            out[new] = True
            reach = parts[new]
        if z is None:
            return out
        left = index[~out[index]]
        new = left[_square_in(parts[left], area, z, cache)]
        if not len(new):
            return out
        out[new] = True
        reach = parts[new]


def _units(z: int):
    """(lon/lat to tile units of zoom z, tile units to lon/lat), for shapely.transform."""
    n = 2**z * 4096

    def to_units(c):
        return np.column_stack([(c[:, 0] + 180.0) / 360.0 * n,
                                (1 - np.arcsinh(np.tan(np.radians(c[:, 1]))) / math.pi) / 2 * n])

    def to_lonlat(c):
        return np.column_stack([c[:, 0] / n * 360.0 - 180.0,
                                np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * c[:, 1] / n))))])

    return to_units, to_lonlat


_PIECE_VERTICES = 256  # _subdivide splits a polygon until each piece has at most this many vertices
_CUT_DEPTH = 40  # and cuts no piece more than this many times (2**20 pieces of a side: far past any mask)


def _subdivide(area: shapely.Geometry) -> shapely.STRtree:
    """area split into pieces of at most _PIECE_VERTICES vertices (halving a piece's bounds along its longer side),
    in an STRtree. Built once per mask, it lets a box meet only the few pieces near it instead of the whole mask.
    Each cut is an overlay with the half's box, as in _tiles: GEOS's fast clip_by_rect fails on a valid sliver
    that collapses in the box ("Invalid number of points in LinearRing found 3", haida-gwaii-south at 18a474f). A
    cut that leaves no piece with fewer vertices keeps its input, and no piece is cut more than _CUT_DEPTH times,
    so the split always ends."""
    out, stack = [], [(g, 0) for g in _parts(area, 2)]
    while stack:
        g, depth = stack.pop()
        size = shapely.get_num_coordinates(g)
        if size <= _PIECE_VERTICES or depth >= _CUT_DEPTH:
            out.append(g)
            continue
        w, s, e, n = g.bounds
        halves = ((w, s, (w + e) / 2, n), ((w + e) / 2, s, e, n)) if e - w >= n - s else \
            ((w, s, e, (s + n) / 2), (w, (s + n) / 2, e, n))
        cut = [p for h in halves for p in _parts(shapely.intersection(g, box(*h)), 2)]
        if all(shapely.get_num_coordinates(p) >= size for p in cut):
            out.append(g)
            continue
        stack += [(p, depth + 1) for p in cut]
    return shapely.STRtree(out)


def _square_in(parts: np.ndarray, area: shapely.Geometry, z: int, cache: dict | None = None) -> np.ndarray:
    """Whether the square tippecanoe draws for each part when it collapses (its area, at its centroid, in the tile
    units of zoom z) reaches more than _SQUARE_REACH_UNITS into area. The area near each square is put together
    from the mask's pieces (_subdivide, built at the first square that meets the mask and kept in cache for the
    caller's later rounds), so after that one split the test costs the squares and the pieces near them, not the
    whole mask per square."""
    out = np.zeros(len(parts), bool)
    if not len(parts) or area.is_empty:
        return out
    to_units, to_lonlat = _units(z)
    units = shapely.transform(parts, to_units)
    x, y = shapely.get_x(shapely.centroid(units)), shapely.get_y(shapely.centroid(units))
    half = np.sqrt(shapely.area(units)) / 2
    squares = shapely.box(x - half, y - half, x + half, y + half)
    hit = np.flatnonzero(_meeting(shapely.transform(squares, to_lonlat), area))
    if not len(hit):
        return out
    cache = {} if cache is None else cache
    if "pieces" not in cache:
        cache["pieces"] = _subdivide(area)
    pieces = cache["pieces"]
    m = half[hit] + _SQUARE_REACH_UNITS + 1  # the area within this of a square's center is all that counts
    near = shapely.transform(shapely.box(x[hit] - m, y[hit] - m, x[hit] + m, y[hit] + m), to_lonlat)
    box_i, piece_i = pieces.query(near, predicate="intersects")
    order = np.argsort(box_i, kind="stable")
    box_i, clipped = box_i[order], shapely.intersection(pieces.geometries[piece_i[order]], near[box_i[order]])
    starts = np.flatnonzero(np.r_[True, box_i[1:] != box_i[:-1]]) if len(box_i) else np.array([], int)
    local = np.array([shapely.union_all(clipped[a:b]) for a, b in zip(starts, np.r_[starts[1:], len(box_i)])],
                     object)
    if len(local):
        at = hit[box_i[starts]]
        out[at] = shapely.intersects(shapely.buffer(shapely.transform(local, to_units), -_SQUARE_REACH_UNITS),
                                     squares[at])
    return out


def _fingers(parts: np.ndarray, which: np.ndarray, z: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The fingers of parts[which]: the pieces an opening by THIN_UNITS (in the tile units of zoom z) takes off,
    each under THIN_UNITS wide by construction, and of at least 1 unit2 or more than THIN_UNITS across (not the
    crumbs the opening cuts off a corner; a hairline finger is long but of little area, dry run 4 north). Returns (pieces, the index of each piece's part, whether the opening leaves a core of each part:
    False for the parts not in which). The opening is taken in tile units and cut back
    out of the lon/lat part, so the pieces and what is left share their edges exactly."""
    index = np.flatnonzero(which)
    if not len(index):
        return np.array([], object), np.array([], int), np.zeros(len(parts), bool)
    n = 2**z * 4096

    def to_units(c):
        return np.column_stack([(c[:, 0] + 180.0) / 360.0 * n,
                                (1 - np.arcsinh(np.tan(np.radians(c[:, 1]))) / math.pi) / 2 * n])

    def to_lonlat(c):
        return np.column_stack([c[:, 0] / n * 360.0 - 180.0,
                                np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * c[:, 1] / n))))])

    half = THIN_UNITS / 2
    opened = shapely.buffer(shapely.buffer(shapely.transform(parts[index], to_units), -half, quad_segs=2), half,
                            quad_segs=2)
    pieces, at = shapely.get_parts(shapely.difference(parts[index], shapely.transform(opened, to_lonlat)),
                                   return_index=True)
    units = shapely.transform(pieces, to_units)
    w, s, e, n = shapely.bounds(units).T if len(pieces) else (np.zeros(0),) * 4
    # a crumb the opening cuts off a corner is under 1 unit2 and about a unit across; a finger is longer
    keep = (shapely.get_type_id(pieces) == 3) & ((shapely.area(units) >= 1.0) | (np.hypot(e - w, n - s) > THIN_UNITS))
    cored = np.zeros(len(parts), bool)
    cored[index] = ~shapely.is_empty(opened)
    return pieces[keep], index[at[keep]], cored


def _select(every: np.ndarray, nosurvey: shapely.Geometry, z: int, reach: float) -> tuple:
    """Which of one band's depare parts every (and of their pieces) go to nosurvey. Candidates: the thin parts
    (_thin at z), and the pieces an opening takes off the parts, wide or thin, that meet the nosurvey or meet the
    parts sent to it (_fingers): the fingers of a wide part, and the ragged edge of a part thin by 2 A / P only, whose core stays
    depth. _to_nosurvey picks among them; then any patch (_patches with reach, degrees) still under THIN_UNITS at
    z gives its candidates back to depth. Returns (candidates: every then the pieces, which go, the pieces, the
    index of each piece's part, what goes as one geometry, the patches)."""
    thin0 = _thin(every, z)
    opened = _meeting(every, nosurvey)
    todo = opened.copy()
    pieces, parent, cored = np.array([], object), np.array([], int), np.zeros(len(every), bool)
    while True:
        more, at, has = _fingers(every, todo, z)
        pieces, parent, cored = np.concatenate([pieces, more]), np.concatenate([parent, at]), cored | has
        keep = ~thin0[parent] | cored[parent]  # a thin part with no core goes (or stays) whole, not in pieces
        cand = np.concatenate([every, pieces[keep]])
        drop = _to_nosurvey(cand, np.concatenate([thin0 & ~cored, np.ones(int(keep.sum()), bool)]), nosurvey, z)
        # a part not opened yet that meets what goes: open it too, so a thin part's core stays depth and a wide
        # part's fingers into what goes go with it
        todo = ~opened & _meeting(every, shapely.union_all(cand[drop])) if drop.any() else opened & False
        if not todo.any():
            break
        opened |= todo
    pieces, parent = pieces[keep], parent[keep]
    flags = np.concatenate([thin0 & ~cored, np.ones(len(pieces), bool)])
    # the thin candidates kept by the share rule that still meet the nosurvey, or what goes, along an edge: they
    # go too, inside the nosurvey piece they meet (joined), never as thin depth beside it (Ruling 55 C)
    joined = _to_nosurvey(cand, flags, nosurvey, share=0.0, least=_JOIN_DEG, sent=drop) & ~drop
    while True:
        gone = shapely.union_all(cand[drop]) if drop.any() else shapely.Polygon()
        patches = _patches(gone, nosurvey, reach)
        bad = patches[_thin(patches, z)] if len(patches) else patches
        if not len(bad):
            break
        back = drop & (shapely.area(shapely.intersection(cand, shapely.union_all(bad))) > 0)
        if not back.any():
            break
        drop &= ~back  # a patch too thin to draw alone: its parts go inside the nosurvey they border instead
        joined |= back
    if joined.any():
        patches = _joined(cand[joined], nosurvey, patches)
    drop |= joined
    gone = shapely.union_all(cand[drop]) if drop.any() else shapely.Polygon()
    return cand, drop, pieces, parent, gone, patches


def _joined(parts: np.ndarray, outside: shapely.Geometry, patches: np.ndarray) -> np.ndarray:
    """patches with the joined parts added: each joined part goes in one nosurvey part with the pieces of outside
    and the patches it meets, so it is never a thin nosurvey part alone. Returns the band's patches."""
    pool = np.concatenate([np.array(_parts(outside, 2), object), patches])
    tree = shapely.STRtree(pool)
    group = shapely.union_all(parts)
    near = pool[np.unique(tree.query(shapely.get_parts(group), predicate="intersects")[1])] if len(pool) else pool
    merged = np.array(_parts(shapely.union_all(np.concatenate([[group], near])), 2), object)
    held = shapely.area(shapely.intersection(merged, group)) > 0
    patches = patches[~shapely.intersects(patches, group)] if len(patches) else patches  # now inside merged
    return np.concatenate([patches, merged[held]])


def _patches(gone: shapely.Geometry, outside: shapely.Geometry, reach: float) -> np.ndarray:
    """A band's nosurvey patch: its thin parts gone with the outside within reach (degrees) of them, as the parts
    holding some of gone (a slice of a mask piece across depth within reach is left out)."""
    if gone.is_empty:
        return np.array([], object)
    patch = np.array(_parts(shapely.union_all([gone, outside.intersection(gone.buffer(reach))]), 2), object)
    return patch[shapely.area(shapely.intersection(patch, gone)) > 0] if len(patch) else patch


def _lines_off(lines: np.ndarray, gone: shapely.Geometry) -> np.ndarray:
    """lines less gone, and less their parts along gone's edge (within _EDGE_DEG: a contour on a dropped part's
    edge differs from it in float noise)."""
    if gone.is_empty or not len(lines):
        return lines
    near = gone.buffer(_EDGE_DEG)
    shapely.prepare(near)
    hit = shapely.intersects(lines, near)
    if not hit.any():
        return lines
    return np.concatenate([lines[~hit], np.array(_parts(shapely.difference(lines[hit], near), 1), object)])


def _depth_features(grid, src, transform, *, levels_m, drying_m, tiles, zooms, nosurvey: shapely.Geometry,
                    reach: float) -> tuple[list[Feature], shapely.Geometry, np.ndarray]:
    """depare and depcnt of one band's grid (already neighborhood-min), cut to `cut`; the depare parts that go to
    nosurvey (_thin at zooms[0], _to_nosurvey with nosurvey, the band's nosurvey area so far), as one geometry;
    and the band's nosurvey patches (_patches with reach, degrees). A patch still thinner than THIN_UNITS at
    zooms[0] gives its parts back to depth. The depcnt leave the parts that go (_lines_off). src holds the source
    index of the cells before the neighborhood minimum (0 elsewhere). tiles: the cut (_tiles)."""
    valid = np.isfinite(grid)
    if min(grid.shape) < 2 or not valid.any():
        return [], shapely.Polygon(), np.array([], object)
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

    filled = []  # (parts, (DRVAL1, DRVAL2)) per depth range
    for i, (lo, hi) in enumerate(bounds):
        if hi < low or (lo >= high and i):
            continue
        # contourpy fills lower < z <= upper: the lowest band starts below the grid, so it holds its own bound
        points, offsets, outer = gen.filled(min(lo, low) - 1.0 if i == 0 else lo, hi)
        if points[0] is not None:
            polygons = shapely.from_ragged_array(GeometryType.POLYGON, points[0], (offsets[0], outer[0]))
            filled.append((_cut(polygons, tiles, 2), (lo, hi)))
    every = np.concatenate([parts for parts, _ in filled]) if filled else np.array([], object)
    cand, drop, pieces, parent, gone, patches = _select(every, nosurvey, zooms[0], reach)
    shapely.prepare(gone)
    shaped = every.copy()  # a wide part less its fingers that go
    for i in np.unique(parent[drop[len(every):]]):
        shaped[i] = shapely.difference(every[i], shapely.union_all(pieces[(parent == i) & drop[len(every):]]))
    out, start = [], 0
    for parts, (lo, hi) in filled:
        keep = ~drop[start:start + len(parts)]
        kept = [p for g in shaped[start:start + len(parts)][keep] for p in _parts(g, 2)]
        start += len(parts)
        out += named(np.array(kept, object), "depare", {"DRVAL1": _fmt(lo), "DRVAL2": _fmt(hi)})
    for level in levels_m:
        if low <= level <= high:
            points, offsets = gen.lines(level)
            if points[0] is not None:
                lines = _cut(shapely.from_ragged_array(GeometryType.LINESTRING, points[0], (offsets[0],)), tiles, 1)
                out += named(_lines_off(lines, gone), "depcnt", {"VALDCO": _fmt(level)})
    return out, gone, patches


def _with_vertices(polys: list, others: list) -> list:
    """polys with every vertex of others that lies on one of their edges (within _EDGE_DEG, and not within it of
    a vertex already there) put into that edge, at its place on the edge (within _EDGE_DEG of the other's vertex,
    so on tippecanoe's integer grid they are one point): the two sides of a common edge then carry the same
    vertices, which tippecanoe's --detect-shared-borders needs to simplify them as one line (dry run 4 north,
    16/8556/20962). The shapes do not change. A polygon the insertion makes invalid is made valid (_valid_like).
    """
    if not polys or not others:
        return polys
    if any(g.geom_type != "Polygon" for g in polys):  # a multipolygon (a part made valid): its polygons, one by one
        flat, owner = shapely.get_parts(np.array(polys, object), return_index=True)
        done = _with_vertices(list(flat), others)
        return [done[np.flatnonzero(owner == i)[0]] if (owner == i).sum() == 1
                else shapely.MultiPolygon([q for j in np.flatnonzero(owner == i) for q in _parts(done[j], 2)])
                for i in range(len(polys))]
    rings, ring_of = shapely.get_rings(np.array(polys, object), return_index=True)
    coords, at = shapely.get_coordinates(rings, return_index=True)
    first = np.r_[True, at[1:] != at[:-1]]
    pos = np.arange(len(at)) - np.flatnonzero(first)[np.cumsum(first) - 1]  # index of each coordinate in its ring
    seg = np.flatnonzero(~first[1:]) if len(at) > 1 else np.array([], int)  # a segment starts at seg, ends at seg+1
    seg = seg[at[seg] == at[seg + 1]]
    lines = shapely.linestrings(np.stack([coords[seg], coords[seg + 1]], axis=1))
    pts = np.unique(shapely.get_coordinates(np.array(others, object)), axis=0)
    p, k = shapely.STRtree(lines).query(shapely.points(pts), predicate="dwithin", distance=_EDGE_DEG)
    a, b, q = coords[seg[k]], coords[seg[k] + 1], pts[p]
    off_ends = (np.hypot(*(q - a).T) > _EDGE_DEG) & (np.hypot(*(q - b).T) > _EDGE_DEG)
    k, q, p = k[off_ends], q[off_ends], p[off_ends]
    if not len(k):
        return polys
    ab = coords[seg[k] + 1] - coords[seg[k]]
    t = np.einsum("ij,ij->i", q - coords[seg[k]], ab) / np.einsum("ij,ij->i", ab, ab)
    # every coordinate, old and new, keyed by (ring, place along it); a new one goes between its segment's ends
    ring_all = np.concatenate([at, at[seg[k]]])
    key = np.concatenate([pos.astype(float), pos[seg[k]] + t])
    t = np.clip(t, 1e-9, 1 - 1e-9)
    xy = np.concatenate([coords, coords[seg[k]] + t[:, None] * ab])  # on the segment itself: the shape is unchanged
    order = np.lexsort((key, ring_all))
    ring_all, key, xy = ring_all[order], key[order], xy[order]
    keep = np.r_[True, (ring_all[1:] != ring_all[:-1]) | (key[1:] != key[:-1])]  # one copy of a point per place
    ring_all, xy = ring_all[keep], xy[keep]
    starts = np.flatnonzero(np.r_[True, ring_all[1:] != ring_all[:-1]])
    by_poly = {}  # every ring keeps at least its own coordinates, so ring k is the k-th group, in ring order
    for ring, c in zip(ring_of, np.split(xy, starts[1:])):
        by_poly.setdefault(int(ring), []).append(c)
    out = [shapely.Polygon(rs[0], rs[1:]) for rs in (by_poly[i] for i in range(len(polys)))]
    return [_valid_like(new, old) for new, old in zip(out, polys)]


def _valid_like(new: shapely.Geometry, old: shapely.Geometry) -> shapely.Geometry:
    """new, or when invalid its valid form (a spike of a ring running back along itself, which a vertex put on
    both of its sides makes cross, collapses to nothing), or old when even that changes the area."""
    if shapely.is_valid(new) or not shapely.is_valid(old):
        return new
    fixed = shapely.union_all(_parts(shapely.make_valid(new, method="structure", keep_collapsed=False), 2))
    return fixed if abs(fixed.area - old.area) <= 1e-9 * old.area and not fixed.is_empty else old


def _shoal_m(depth: float) -> float:
    """depth rounded toward shallow to 0.1 m (float32 noise on an exact tenth kept)."""
    return math.floor(round(depth * 10, 4)) / 10


def _owns(core, kx: int, ky: int, z: int) -> bool:
    """Whether the center of sounding cell (kx, ky) at zoom z lies in core (W <= lon < E, S < lat <= N). At zoom 10
    and up a zoom-10 tile edge is a multiple of 256 px and a cell center an odd multiple of 48 px, so a center is at
    least 16 px from an edge: two adjacent cores never both own a cell, nor both miss it. (Below zoom 10 a tile edge
    can fall on a center; the derived soundings start at zoom 10.)"""
    world = 256 * 2**z
    lon = (kx + 0.5) * SOUNDING_PX / world * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ky + 0.5) * SOUNDING_PX / world))))
    w, s, e, n = core
    return w <= lon < e and s < lat <= n


def _soundings(depth_m, src, transform, allowed, cut, zooms, core) -> list[Feature]:
    """One sounding per SOUNDING_PX cell of the global Web Mercator pixel grid at each zoom of zooms: the
    shallowest NONNA value among the allowed cells under it, at its cell center. A zoom's cell holds exactly
    2 by 2 cells of the next zoom, so each zoom is taken from the next one's soundings. Only the cells whose center
    lies in core (_owns) are drawn, so a cell across a block edge gets one sounding, from the block holding its
    center: the shallowest value of that block's part of the cell, which may be deeper than a shoal in the other
    block's part. A pass across blocks was not done: a zoom-10 cell (0.13 degree) is wider than a block's read
    margin, so no block sees a whole edge cell, and a second pass would need every block's soundings at once. The
    depth areas and contours, cut at the core from grids that reach past it, carry the safety at the seam."""
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
        for i, (_, _, v, row, col) in zip(first, cells[first]):
            if not _owns(core, int(keys[0][i]), int(keys[1][i]), z):
                continue
            row, col = int(row), int(col)
            point = Point(x0 + (col + 0.5) * dx, y0 + (row + 0.5) * dy)
            if cut.contains(point):
                props = {"depth": _fmt(_shoal_m(v)), "src": SOURCE_NAMES[src[row, col]],
                         "tippecanoe": {"minzoom": z, "maxzoom": z}}
                out.append(Feature("soundg", mapping(point), props))
    return out


def derived_features(depth_m: np.ndarray, src: np.ndarray, transform, *, core, levels_m: list[float],
                     nosurvey: shapely.Geometry, land: shapely.Geometry, lat: float, bands=BANDS,
                     soundings: bool = True) -> list[Feature]:
    """The Nav features of one block from depth_m (meters, positive down, a drying height negative, nan for no
    value; src its source index into SOURCE_NAMES), each carrying its tippecanoe zoom range:

    - per zoom range of bands, from the grid block-min downsampled to the band's cell size: depare between
      consecutive levels_m (DRVAL1, DRVAL2), plus one drying area from -H to 0 (H the greatest drying height in
      depth_m rounded up to 0.1 m) and one from the last level to DEEPEST_M, and depcnt on levels_m (VALDCO),
      each with src: the source of its cells, the coarsest when it spans more than one. A grid finer than
      NAV_BASE_M is first block-min reduced to it, and each band grid takes its 3 by 3 neighborhood minimum
      (_neighborhood_min) before contouring; nothing is simplified (tippecanoe does that);
    - soundg per zoom (_soundings), from nonna10 and nonna100 cells only, src the source of the cell, in the
      sounding cells whose center lies in core;
    - lndare and coalne from land, src "fwa", cut to core, over every zoom of bands;
    - nosurvey, at each zoom range of bands the core less land less that band's depare (the water with no depth
      at any band once over every zoom, plus a patch per band round that band's thin parts), so depth and nosurvey
      meet on one line and every water place not drawn as depth is nosurvey: the stored mask, the water with no
      value, and the depth too thin to draw at the band's minzoom that lies along it (_select): parts thin by
      2 A / P with no 2-unit core, and the pieces an opening by 2 units takes off the parts that meet the
      nosurvey or what goes to it (fingers, ragged edges; their cores stay depth), each sent only when a quarter
      of its perimeter lies along the nosurvey or along what goes (_to_nosurvey), and given back to depth when
      its patch would still be under 2 units wide (the guard). The depcnt and soundg on what goes are dropped.

    Every depth geometry is cut to core and to the valid input cells, less nosurvey and land. bands gives the zoom
    ranges and cell sizes (BANDS for a region pack, OVERVIEW_BANDS for the overview, which passes soundings=False:
    below zoom 10 a sounding cell can straddle two blocks, _owns).
    lat is unused since nothing is simplified here (kept in the interface). For the offshore kind the caller passes the coarse merge and empty nosurvey and land."""
    core_box = box(*core)
    levels = sorted(float(v) for v in levels_m)
    # H from the whole input grid (the read area too), so it can only overstate the drying height
    with np.errstate(invalid="ignore"):
        dry = depth_m[depth_m < 0]
    drying_m = math.ceil(round(-float(dry.min()) * 10, 4)) / 10 if dry.size else 0.0
    zooms = (bands[0][0], bands[-1][1])
    out = []
    gone = {lo: shapely.Polygon() for lo, _, _ in bands}  # per band minzoom: its depare parts sent to nosurvey
    patches = {lo: [] for lo, _, _ in bands}  # per band minzoom: its nosurvey patches (_patches)
    mid = math.cos(math.radians((core[1] + core[3]) / 2))
    outside = core_box.difference(land)  # the core less land less the cut: no depth is drawn there at any band
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
            outside = outside.difference(cut)
            tiles = _tiles(cut, core)
            for lo, hi, target in bands:
                k = block_factor(base_tr, target)
                grid, tr = block_min(base, base_tr, k) if k > 1 else (base, base_tr)
                band_src = _coarsest(base_src, base_valid, base_tr, k) if k > 1 else base_src
                grid, tr = _neighborhood_min(grid, tr)
                reach = PATCH_UNITS * 360.0 / (2**lo * 4096) * mid  # degrees, the smaller (latitude) way
                feats, gone[lo], patches[lo] = _depth_features(grid, np.pad(band_src, 1), tr, levels_m=levels,
                                                               drying_m=drying_m, tiles=tiles, zooms=(lo, hi),
                                                               nosurvey=outside, reach=reach)
                out += feats
            if soundings:
                allowed = clip_mask(transform, depth_m.shape, mapping(cut))
                band_of = {z: lo for lo, hi, _ in bands for z in range(lo, hi + 1)}
                out += [f for f in _soundings(depth_m, src, transform, allowed, cut, zooms, core)
                        if not gone[band_of[f.props["tippecanoe"]["minzoom"]]].intersects(shapely.Point(
                            f.geometry["coordinates"]))]
    tip = {"minzoom": zooms[0], "maxzoom": zooms[1]}
    for part in _parts(land.intersection(core_box), 2):
        out.append(Feature("lndare", mapping(part), {"src": "fwa", "tippecanoe": tip}))
    for part in _parts(land.boundary.intersection(core_box), 1):
        out.append(Feature("coalne", mapping(part), {"src": "fwa", "tippecanoe": tip}))
    # nosurvey: outside once over every zoom; per band its patches (_patches: its thin depth with the outside within
    # PATCH_UNITS of it, each at least THIN_UNITS wide). A patch overlaps the whole nosurvey, so the nosurvey at
    # each zoom is the core less land less that band's depth.
    # both sides of every depth / nosurvey edge get the same vertices (_with_vertices): first the nosurvey drawn
    # over every zoom those of every band's depth, then each band's depth those of that nosurvey and of the band's
    # patches, then the patches those of the band's depth
    depth = {lo: [i for i, f in enumerate(out) if f.layer == "depare" and f.props["tippecanoe"]["minzoom"] == lo]
             for lo, _, _ in bands}
    shapes = {i: shape(out[i].geometry) for ids in depth.values() for i in ids}
    whole = _parts(outside, 2)
    for _ in range(_VERTEX_ROUNDS):  # again while a round adds vertices (another band's, or a made-valid node)
        before = sum(shapely.get_num_coordinates(g) for g in whole + list(shapes.values()))
        whole = _with_vertices(whole, list(shapes.values()))
        for lo, _, _ in bands:
            mine = _with_vertices([shapes[i] for i in depth[lo]], whole + list(patches[lo]))
            shapes.update(zip(depth[lo], mine))
            patches[lo] = _with_vertices(list(patches[lo]), mine)
        if sum(shapely.get_num_coordinates(g) for g in whole + list(shapes.values())) == before:
            break
    for i, g in shapes.items():
        out[i] = Feature("depare", mapping(g), out[i].props)
    for part in whole:
        out.append(Feature("nosurvey", mapping(part), {"tippecanoe": tip}))
    for lo, hi, _ in bands:
        out += [Feature("nosurvey", mapping(part), {"tippecanoe": {"minzoom": lo, "maxzoom": hi}})
                for part in patches[lo]]
    return out
