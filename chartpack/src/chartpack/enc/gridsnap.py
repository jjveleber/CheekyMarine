"""The derived features snapped to the tile grid of each band's minzoom, the last geometry step before tiling
(plan8-gridsnap design).

Per block core and per band, the derived depth areas, nosurvey and land valid at that band are one polygonal
coverage of the core: every ring is snap-rounded to the integer tile units of the band's minzoom together, the
faces are polygonized and labeled with the class of the polygon under them, then simplified as a coverage. Every
vertex is then an integer at the minzoom, and so at every zoom of the band (a unit at zoom z + k is 2^-k of one
at z): tippecanoe, run without simplification (enc/tiles.py), draws the coverage exactly, so depth and nosurvey
meet on one line at every zoom and nothing is squashed into a square or a spike. A depth face where no disk of
one unit fits goes to nosurvey where it shares an edge with nosurvey (one pass). Contours are the edges between
depth faces on a level; soundings are kept only on the depth drawn at their zoom.
"""

import json
import math
import resource
import sys
import time

import numpy as np
import shapely
from shapely.geometry import box, mapping, shape

from chartpack.enc.reader import Feature

SIMPLIFY_UNITS = 1.0  # coverage_simplify tolerance, in minzoom units (tippecanoe's own simplification is about 1)
_AREAS = ("depare", "nosurvey", "lndare")
_DEEP_UNITS = 1.0  # a label point this far inside its face lies in the face's own original (snapping moves 0.71)


def _units(z: int):
    """(lon/lat to global tile units of zoom z, tile units to lon/lat), for shapely.transform: 4,096 units per
    tile, y down from the north edge of the Web Mercator world (pack/check.py _tile_units before its offset)."""
    n = 2**z * 4096

    def to_units(c):
        return np.column_stack([(c[:, 0] + 180.0) / 360.0 * n,
                                (1 - np.arcsinh(np.tan(np.radians(c[:, 1]))) / math.pi) / 2 * n])

    def to_lonlat(c):
        return np.column_stack([c[:, 0] / n * 360.0 - 180.0,
                                np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * c[:, 1] / n))))])

    return to_units, to_lonlat


def _coarser(a: str, b: str) -> str:
    from chartpack.bathy.blocks import LABELS  # here: bathy.blocks imports enc.tiles, which imports this module

    return a if LABELS[a]["resolution_m"] >= LABELS[b]["resolution_m"] else b


def _covers(tip: dict, lo: int, hi: int) -> bool:
    return tip["minzoom"] <= lo and hi <= tip["maxzoom"]


def _faces(polys: np.ndarray, frame: shapely.Geometry) -> np.ndarray:
    """The faces of the rings of polys and frame snap-rounded together on the integer grid (units)."""
    rings = shapely.get_parts(shapely.get_parts(shapely.boundary(polys)))
    lines = shapely.union_all(np.concatenate([rings, [frame.boundary]]), grid_size=1.0)
    faces = shapely.get_parts(shapely.polygonize(shapely.get_parts(lines)))
    return faces[shapely.covers(frame, shapely.point_on_surface(faces))] if len(faces) else faces


def _labels(faces: np.ndarray, polys: np.ndarray) -> np.ndarray:
    """The index into polys of the polygon under each face, -1 where none is (the NOAA or US side): the one holding
    a point _DEEP_UNITS inside the face, else (a thin face) the one with the largest overlap, unless more of the
    face lies under none. The overlaps are summed over pieces (_pieces) of the fallback faces and of the
    originals, found by one query, so no step costs a large mask or land polygon once per face (PR 137 review)."""
    label = np.full(len(faces), -1)
    if not len(faces):
        return label
    bad = ~shapely.is_valid(polys)  # an overlay output can cross itself once in tile units: test it made valid
    if bad.any():
        polys = polys.copy()
        polys[bad] = shapely.make_valid(polys[bad])
    points = shapely.point_on_surface(faces)
    deep = shapely.distance(points, shapely.boundary(faces)) >= _DEEP_UNITS
    index = np.flatnonzero(deep)
    # the points in a tree and each polygon queried against it: shapely prepares the query geometry, so a large
    # polygon is prepared once (the other way round, a 200,000-vertex mask took 4.5 s for 34,000 points)
    poly, at = shapely.STRtree(points[deep]).query(polys, predicate="contains")
    label[index[at[::-1]]] = poly[::-1]  # the first match wins (originals do not overlap)
    fall = np.flatnonzero(~deep | (label < 0))
    if not len(fall):
        return label
    face_pieces, face_of = _pieces(faces[fall])
    poly_pieces, poly_of = _pieces(polys)
    p, f = shapely.STRtree(face_pieces).query(poly_pieces, predicate="intersects")  # p into poly_pieces
    if not len(p):
        return label
    areas = shapely.area(shapely.intersection(poly_pieces[p], face_pieces[f]))
    pair = face_of[f].astype(np.int64) * len(polys) + poly_of[p]
    pair, inverse = np.unique(pair, return_inverse=True)
    summed = np.zeros(len(pair))
    np.add.at(summed, inverse, areas)
    face, owner = pair // len(polys), pair % len(polys)
    total = np.zeros(len(fall))
    np.add.at(total, face, summed)
    best, most = np.full(len(fall), -1), np.zeros(len(fall))
    for k in np.lexsort((owner, -summed)):  # largest overlap first; a tie goes to the lowest original index
        if best[face[k]] < 0:
            best[face[k]], most[face[k]] = owner[k], summed[k]
    take = (best >= 0) & (most > 0) & (most >= shapely.area(faces[fall]) - total)
    label[fall[take]] = best[take]
    return label


_PIECE_VERTICES = 256  # _pieces splits a polygon until each piece has at most this many vertices
_CUT_DEPTH = 40  # and cuts no piece more than this many times (2**20 pieces of a side: far past any mask)


def _pieces(geoms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The polygonal parts of geoms split into pieces of at most _PIECE_VERTICES vertices (halving a piece's bounds
    along its longer side), and the index in geoms of each piece's geometry: each large polygon is split once, in
    O(n log n), so a small face meets only the few pieces near it. Each cut is an overlay with the half's box:
    GEOS's fast clip_by_rect fails on a valid sliver that collapses in the box ("Invalid number of points in
    LinearRing found 3", PRs 130 and 135). A cut that leaves no piece with fewer vertices keeps its input, and no
    piece is cut more than _CUT_DEPTH times, so the split always ends."""
    out, owner = [], []
    for k, geom in enumerate(geoms):
        stack = [(p, 0) for p in shapely.get_parts(geom) if shapely.get_dimensions(p) == 2 and not p.is_empty]
        while stack:
            g, depth = stack.pop()
            size = shapely.get_num_coordinates(g)
            if size > _PIECE_VERTICES and depth < _CUT_DEPTH:
                w, s, e, n = g.bounds
                halves = ((w, s, (w + e) / 2, n), ((w + e) / 2, s, e, n)) if e - w >= n - s else \
                    ((w, s, e, (s + n) / 2), (w, (s + n) / 2, e, n))
                cut = [p for h in halves for p in shapely.get_parts(shapely.intersection(g, box(*h)))
                       if shapely.get_dimensions(p) == 2 and not p.is_empty]
                if any(shapely.get_num_coordinates(p) < size for p in cut):
                    stack += [(p, depth + 1) for p in cut]
                    continue
            out.append(g)
            owner.append(k)
    return np.array(out, object), np.array(owner, int)


def _thin_to_nosurvey(faces: np.ndarray, label: np.ndarray, depth: np.ndarray, nosurvey: np.ndarray) -> np.ndarray:
    """label with each thin depth face (no disk of 1 unit fits: buffer by -0.5 is empty) that shares an edge of
    positive length with a nosurvey face relabeled as nosurvey. One pass: a thin face beside a face sent is not
    sent for it."""
    is_ns = np.isin(label, nosurvey)
    if not is_ns.any():
        return label
    area, length = shapely.area(faces), shapely.length(faces)
    cand = np.flatnonzero(np.isin(label, depth) & (2 * area <= length))  # no 1-unit disk fits only if 2 A / P <= 1
    cand = cand[shapely.is_empty(shapely.buffer(faces[cand], -0.5))]
    if not len(cand):
        return label
    ns = np.flatnonzero(is_ns)
    # each boundary built once and indexed: per-pair copies held a large mask's boundary once per pair (PR 137
    # review: 1,016 pairs on a 168,683-vertex face took RSS from 574 to 3,899 MiB)
    edges, mine = shapely.boundary(faces[ns]), shapely.boundary(faces[cand])
    i, j = shapely.STRtree(edges).query(mine, predicate="intersects")  # i into cand, j into ns
    shared = shapely.length(shapely.intersection(mine[i], edges[j]))
    out = label.copy()
    out[cand[i[shared > 0]]] = label[ns[0]]
    return out


def _snap_band(core, feats: list[Feature], lo: int, hi: int, times: dict) -> tuple[list[Feature], shapely.Geometry]:
    """The band (lo, hi) of one core: feats are the derived depare, nosurvey and lndare valid at that band.
    Returns the snapped features and their depth (the depare union) in the units of zoom lo."""
    to_units, to_lonlat = _units(lo)
    polys = shapely.transform(np.array([shape(f.geometry) for f in feats], object), to_units)
    w, n = to_units(np.array([[core[0], core[3]]]))[0]
    e, s = to_units(np.array([[core[2], core[1]]]))[0]
    frame = box(round(w), round(n), round(e), round(s))
    t = time.perf_counter()
    faces = _faces(polys, frame)
    times["snap"] += time.perf_counter() - t
    t = time.perf_counter()
    label = _labels(faces, polys)
    times["label"] += time.perf_counter() - t
    t = time.perf_counter()
    faces = shapely.coverage_simplify(faces, SIMPLIFY_UNITS, simplify_boundary=False)
    times["simplify"] += time.perf_counter() - t
    t = time.perf_counter()
    layers = np.array([f.layer for f in feats])
    label = _thin_to_nosurvey(faces, label, np.flatnonzero(layers == "depare"), np.flatnonzero(layers == "nosurvey"))
    times["thin"] += time.perf_counter() - t
    t = time.perf_counter()
    tip = {"minzoom": lo, "maxzoom": hi}
    groups: dict[tuple, list[int]] = {}
    for i, k in enumerate(label):
        if k >= 0:
            props = {key: v for key, v in feats[k].props.items() if key != "tippecanoe"}
            groups.setdefault((feats[k].layer, json.dumps(props, sort_keys=True)), []).append(i)
    out, depth = [], []  # depth: (props, geometry in units) per depare group
    drawn = shapely.coverage_union_all(faces[np.isin(label, np.flatnonzero(layers == "depare"))])
    for (layer, props), at in groups.items():
        geom = shapely.coverage_union_all(faces[at])
        props = json.loads(props)
        if layer == "depare":
            depth.append((props, geom))
        out += [Feature(layer, mapping(shapely.transform(p, to_lonlat)), {**props, "tippecanoe": tip})
                for p in shapely.get_parts(geom) if shapely.get_type_id(p) == 3]
    levels = sorted({f.props[k] for f in feats if f.layer == "depare" for k in ("DRVAL1", "DRVAL2")}, key=float)
    out += _contours(depth, levels, tip, to_lonlat)
    times["emit"] += time.perf_counter() - t
    return out, drawn


def _contours(depth: list[tuple[dict, shapely.Geometry]], levels: list[str], tip: dict, to_lonlat) -> list[Feature]:
    """The depcnt of a band: on every edge shared by a shallower and a deeper depare (exact: both carry the same
    snapped vertices), one line per level L of levels with shallow DRVAL2 <= L <= deep DRVAL1, src the coarser
    of the two. levels: the DRVAL bounds of the band's depare before the snap, so a band the snap closed (under a
    unit wide, its neighbors now meet) still gives its levels there (Ruling 59); the usual edge, DRVAL2 equal to
    DRVAL1, gives one line."""
    out = []
    if len(depth) < 2:
        return out
    edges = [shapely.boundary(g) for _, g in depth]
    pairs = shapely.STRtree(edges).query(edges, predicate="intersects")
    for i, j in zip(*pairs):
        (shallow, a), (deep, b) = depth[i], depth[j]
        lo, hi = float(shallow["DRVAL2"]), float(deep["DRVAL1"])
        here = [v for v in levels if lo <= float(v) <= hi]
        if i == j or not here:
            continue
        lines = shapely.intersection(edges[i], edges[j])
        lines = [g for g in shapely.get_parts(lines) if shapely.get_dimensions(g) == 1]
        if not lines:
            continue
        lines = shapely.get_parts(shapely.line_merge(shapely.union_all(lines)))
        src = _coarser(shallow["src"], deep["src"])
        out += [Feature("depcnt", mapping(shapely.transform(g, to_lonlat)), {"VALDCO": v, "src": src,
                                                                           "tippecanoe": tip})
                for v in here for g in lines]
    return out


def _snap_core(core, feats: list[Feature], bands) -> list[Feature]:
    times = dict.fromkeys(("snap", "label", "simplify", "thin", "emit"), 0.0)
    start = time.perf_counter()
    out = []
    used = np.array([f.layer == "coalne" for f in feats])
    for f in feats:
        if f.layer == "coalne":
            tip = f.props["tippecanoe"]
            out.append(Feature(f.layer, f.geometry, {**f.props, "tippecanoe": {"minzoom": tip["minzoom"],
                                                                             "maxzoom": tip["maxzoom"]}}))
    for lo, hi, _ in bands:
        take = np.array([f.layer in _AREAS and _covers(f.props["tippecanoe"], lo, hi) for f in feats])
        sounds = np.array([f.layer == "soundg" and lo <= f.props["tippecanoe"]["minzoom"] <= hi for f in feats])
        used |= take | sounds
        if not take.any():
            continue
        band, depth = _snap_band(core, [f for f, t in zip(feats, take) if t], lo, hi, times)
        out += band
        shapely.prepare(depth)
        for f, t in zip(feats, sounds):
            if t:
                point = shapely.transform(shape(f.geometry), _units(lo)[0])
                if depth.covers(point):
                    tip = f.props["tippecanoe"]
                    out.append(Feature(f.layer, f.geometry, {**f.props, "tippecanoe": {
                        "minzoom": tip["minzoom"], "maxzoom": tip["maxzoom"]}}))
    if not used.all():
        f = feats[int(np.flatnonzero(~used)[0])]
        raise ValueError(f"snap_derived: a derived {f.layer} with zooms {f.props['tippecanoe']['minzoom']}-"
                         f"{f.props['tippecanoe']['maxzoom']} in core {core} is taken by no band of {bands}")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"gridsnap {','.join(format(c, '.6f') for c in core)}: {time.perf_counter() - start:.2f} s ("
          + ", ".join(f"{k} {v:.2f}" for k, v in times.items()) + f"), peak {rss:.0f} MiB", file=sys.stderr)
    return out


def snap_derived(features: list[Feature], bands) -> list[Feature]:
    """features with the derived ones (those whose tippecanoe zooms carry their block "core") replaced by their
    snapped coverage per core and band (bands: (minzoom, maxzoom, cell size) per band). The depare of a band, and
    the nosurvey and lndare whose zoom range holds it, are snapped together; depcnt is made from the snapped depth
    edges; soundg is kept on the snapped depth of its zoom's band; coalne passes as it is. The others pass
    unchanged. A derived feature no band takes (an area whose zooms hold no band, a sounding at a zoom of no band,
    or another layer, such as a depcnt) raises ValueError instead of being dropped. features is consumed: the list
    is emptied, so the unsnapped features are let go core by core."""
    by_core: dict[tuple, list[Feature]] = {}
    out = []
    for f in features:
        core = f.props.get("tippecanoe", {}).get("core")
        if core is None:
            out.append(f)
        else:
            by_core.setdefault(tuple(core), []).append(f)
    features.clear()  # consumed: each core's unsnapped features go once that core is snapped (memory peak)
    while by_core:
        core, feats = by_core.popitem()
        out += _snap_core(core, feats, bands)
    return out
