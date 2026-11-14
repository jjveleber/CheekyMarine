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
    face lies under none."""
    label = np.full(len(faces), -1)
    if not len(faces):
        return label
    bad = ~shapely.is_valid(polys)  # an overlay output can cross itself once in tile units: test it made valid
    if bad.any():
        polys = polys.copy()
        polys[bad] = shapely.make_valid(polys[bad])
    tree = shapely.STRtree(polys)
    points = shapely.point_on_surface(faces)
    deep = shapely.distance(points, shapely.boundary(faces)) >= _DEEP_UNITS
    at, poly = tree.query(points[deep], predicate="within")
    index = np.flatnonzero(deep)
    label[index[at[::-1]]] = poly[::-1]  # the first match wins (originals do not overlap)
    for i in np.flatnonzero(~deep | (label < 0)):
        near = tree.query(faces[i], predicate="intersects")
        if not len(near):
            continue
        areas = shapely.area(shapely.intersection(polys[near], faces[i]))
        best = int(np.argmax(areas))
        if areas[best] > 0 and areas[best] >= shapely.area(faces[i]) - areas.sum():
            label[i] = near[best]
    return label


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
    a, b = shapely.STRtree(faces[ns]).query(faces[cand], predicate="intersects")
    shared = shapely.length(shapely.intersection(shapely.boundary(faces[cand[a]]), shapely.boundary(faces[ns[b]])))
    out = label.copy()
    out[cand[a[shared > 0]]] = label[ns[0]]
    return out


def _snap_band(core, feats: list[Feature], lo: int, hi: int, times: dict) -> list[Feature]:
    """The band (lo, hi) of one core: feats are the derived depare, nosurvey and lndare valid at that band."""
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
    for (layer, props), at in groups.items():
        geom = shapely.coverage_union_all(faces[at])
        props = json.loads(props)
        if layer == "depare":
            depth.append((props, geom))
        out += [Feature(layer, mapping(shapely.transform(p, to_lonlat)), {**props, "tippecanoe": tip})
                for p in shapely.get_parts(geom) if shapely.get_type_id(p) == 3]
    out += _contours(depth, tip, to_lonlat)
    times["emit"] += time.perf_counter() - t
    return out


def _contours(depth: list[tuple[dict, shapely.Geometry]], tip: dict, to_lonlat) -> list[Feature]:
    """The depcnt of a band: on each level L, the edges shared by a depare with DRVAL2 L and one with DRVAL1 L
    (exact: both carry the same snapped vertices), src the coarser of the two."""
    out = []
    for shallow, a in depth:
        for deep, b in depth:
            if shallow["DRVAL2"] != deep["DRVAL1"]:
                continue
            lines = shapely.intersection(shapely.boundary(a), shapely.boundary(b))
            lines = [g for g in shapely.get_parts(lines) if shapely.get_dimensions(g) == 1]
            if not lines:
                continue
            props = {"VALDCO": shallow["DRVAL2"], "src": _coarser(shallow["src"], deep["src"]), "tippecanoe": tip}
            out += [Feature("depcnt", mapping(shapely.transform(g, to_lonlat)), props)
                    for g in shapely.get_parts(shapely.line_merge(shapely.union_all(lines)))]
    return out


def _snap_core(core, feats: list[Feature], bands) -> list[Feature]:
    times = dict.fromkeys(("snap", "label", "simplify", "thin", "emit"), 0.0)
    start = time.perf_counter()
    out = []
    for f in feats:
        if f.layer == "coalne":
            tip = f.props["tippecanoe"]
            out.append(Feature(f.layer, f.geometry, {**f.props, "tippecanoe": {"minzoom": tip["minzoom"],
                                                                             "maxzoom": tip["maxzoom"]}}))
    for lo, hi, _ in bands:
        areas = [f for f in feats if f.layer in _AREAS and _covers(f.props["tippecanoe"], lo, hi)]
        if not areas:
            continue
        band = _snap_band(core, areas, lo, hi, times)
        out += band
        depth = shapely.union_all([shapely.transform(shape(f.geometry), _units(lo)[0]) for f in band
                                   if f.layer == "depare"])
        shapely.prepare(depth)
        for f in feats:
            if f.layer == "soundg" and lo <= f.props["tippecanoe"]["minzoom"] <= hi:
                point = shapely.transform(shape(f.geometry), _units(lo)[0])
                if depth.covers(point):
                    tip = f.props["tippecanoe"]
                    out.append(Feature(f.layer, f.geometry, {**f.props, "tippecanoe": {
                        "minzoom": tip["minzoom"], "maxzoom": tip["maxzoom"]}}))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"gridsnap {','.join(format(c, '.6f') for c in core)}: {time.perf_counter() - start:.2f} s ("
          + ", ".join(f"{k} {v:.2f}" for k, v in times.items()) + f"), peak {rss:.0f} MiB", file=sys.stderr)
    return out


def snap_derived(features: list[Feature], bands) -> list[Feature]:
    """features with the derived ones (those whose tippecanoe zooms carry their block "core") replaced by their
    snapped coverage per core and band (bands: (minzoom, maxzoom, cell size) per band). The depare of a band, and
    the nosurvey and lndare whose zoom range holds it, are snapped together; depcnt is made from the snapped depth
    edges (any derived depcnt given is replaced); soundg is kept on the snapped depth of its zoom's band; coalne
    passes as it is. The others pass unchanged."""
    by_core: dict[tuple, list[Feature]] = {}
    out = []
    for f in features:
        core = f.props.get("tippecanoe", {}).get("core")
        if core is None:
            out.append(f)
        else:
            by_core.setdefault(tuple(core), []).append(f)
    for core, feats in by_core.items():
        out += _snap_core(core, feats, bands)
    return out
