"""BC Freshwater Atlas coastline (WHSE_BASEMAPPING.FWA_COASTLINES_SP) from the BC Government WFS (plan 8).

Only the source-data fetch workflow calls the WFS, through a PoliteSession. Values recorded in plan 8 Task 1
(2026-11-11): WFS 2.0.0 with GeoJSON output, a lon/lat bbox with the EPSG:4326 suffix, at most 10000 features
per request, paging with count and startIndex sorted by OBJECTID (paging is not transaction safe without a
sort). License: Open Government Licence - British Columbia (see NOTICE).
"""

import gzip
import json
from collections import Counter, deque
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, box as make_box
from shapely.ops import nearest_points, polygonize, unary_union

from chartpack.cache import DownloadError
from chartpack.enc.bc import from_m, to_m, to_m_xy

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.FWA_COASTLINES_SP/ows"
LAYER = "pub:WHSE_BASEMAPPING.FWA_COASTLINES_SP"
PAGE_SIZE = 10000  # the server's CountDefault, its most features per request
# Where every FWA coastline position lies (BC and its islands, with room to spare): a line meeting the requested
# box can run far past it, so positions are checked against the source's range, not the box.
LON_RANGE = (-140.0, -113.0)
LAT_RANGE = (47.0, 61.0)


def page_url(bbox, start: int, count: int) -> str:
    w, s, e, n = bbox
    return (
        f"{WFS_BASE}?service=WFS&version=2.0.0&request=GetFeature&typeNames={LAYER}"
        f"&outputFormat=application/json&srsName=EPSG:4326&sortBy=OBJECTID"
        f"&count={count}&startIndex={start}&bbox={w},{s},{e},{n},EPSG:4326"
    )


def _page(body: bytes) -> dict:
    """The parsed page; DownloadError unless it is a GeoJSON FeatureCollection (a WFS exception, XML or JSON,
    is not an empty page)."""
    try:
        page = json.loads(body)
    except ValueError:
        page = None
    if not (isinstance(page, dict) and page.get("type") == "FeatureCollection" and isinstance(page.get("features"), list)):
        snippet = " ".join(body[:500].decode("utf-8", "replace").split())
        raise DownloadError(f"coastline: the response is not a GeoJSON FeatureCollection: {snippet}")
    return page


def _positions(coords):
    if coords and isinstance(coords[0], (int, float)):
        yield coords
    else:
        for c in coords or ():
            yield from _positions(c)


def _inside(x: float, y: float) -> bool:
    return LON_RANGE[0] <= x <= LON_RANGE[1] and LAT_RANGE[0] <= y <= LAT_RANGE[1]


def _check_axes(feature: dict) -> None:
    """DownloadError unless every position is lon, lat inside LON_RANGE and LAT_RANGE. A position that would be
    inside with x and y exchanged is reported as a swapped axis order."""
    for x, y, *_ in _positions((feature.get("geometry") or {}).get("coordinates")):
        if _inside(x, y):
            continue
        if _inside(y, x):
            raise DownloadError(f"coastline: position ({x}, {y}) reads as lat, lon: the axis order looks swapped, "
                                "expected lon, lat")
        raise DownloadError(f"coastline: position ({x}, {y}) is outside the expected range for this source "
                            f"(longitude {LON_RANGE}, latitude {LAT_RANGE})")


def fetch_coastline(bbox, out: Path, session, count: int = PAGE_SIZE) -> int:
    """Every coastline feature meeting bbox (W, S, E, N, degrees), paged until a page comes back short, written
    to out as gzip GeoJSONSeq (one feature per line). Returns the feature count.

    Nothing is written at out unless every page is a FeatureCollection, no OBJECTID repeats, every position is
    lon, lat in the source's range, and the total equals the first page's numberMatched when the server gives a number."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    total = 0
    matched = None
    seen = set()
    try:
        with gzip.open(part, "wt", encoding="utf-8") as f:
            while True:
                page = _page(session.get(page_url(bbox, total, count)))
                if total == 0 and isinstance(page.get("numberMatched"), int):
                    matched = page["numberMatched"]
                features = page["features"]
                for feature in features:
                    oid = (feature.get("properties") or {}).get("OBJECTID")
                    if oid is not None:
                        if oid in seen:
                            raise DownloadError(f"coastline: OBJECTID {oid} came twice (pages shifted while paging)")
                        seen.add(oid)
                    _check_axes(feature)
                    f.write(json.dumps(feature, separators=(",", ":")) + "\n")
                total += len(features)
                if len(features) < count:
                    break
        if matched is not None and total != matched:
            raise DownloadError(f"coastline: got {total} features, the server matched {matched}")
        part.rename(out)
    finally:
        part.unlink(missing_ok=True)  # no-op after a successful rename
    return total


# Land polygons from the coastline lines (plan 8 spec 7.1).
WATER_VOTE_M = 2.0  # a NONNA cell deeper than this votes water
RIVER_WATER_SHARE = 0.2  # a land face more than this share wet is water ...
RIVER_MIN_AREA_M2 = 50_000  # ... when it is at least this large
END_SNAP_M = 50.0  # a line end this close to the outline is moved onto it
# A retraced segment is a dangling edge (one free end, its tip) that the end check skips: no connector, no error.
# It must be at most RETRACE_MAX_M long, lie within RETRACE_M of other lines along its whole length, and have no
# other free line end within RETRACE_M of its tip, so the line that covers it runs on past the tip. That is a line
# going out and back over itself, as OBJECTID 32612852 near Seymour Inlet does over 20.03 m. A shore digitized twice
# that stops at a real gap has both copies ending there, so it still fails (PR 128 review). A dangle bounds no face,
# so skipping one changes no face.
RETRACE_M = 1.0
RETRACE_MAX_M = 100.0
_LAND_SHARE_LIMIT = 0.01  # the share of the water points near a line that land may hold before the corrections
# The guard counts only water points this close to an atlas line: a wrong land side or a misplaced coastline puts
# the deep water beside the line on land, while surveyed rivers and lakes deep inside a land face (the Fraser, Pitt
# Lake, Cowichan Lake) are not a coastline error. On bc-south-georgia (2026-11-12) land held 1.47% of all water
# points, almost all inland; of the points near a line it held 0.98% within 100 m, 0.43% within 200 m and 0.20%
# within 500 m (steep shores put a few deep cells a few meters inside the line).
GUARD_NEAR_M = 500.0
# ... and leaves out those within this many vote-grid cells of a line: a cell that close can hold the line, and
# NONNA-100's cells (about 100 m) carry depth up to about two cells past a right coastline. From NONNA-100 alone,
# land held 5.37% of the near points of bc-south-georgia (2026-11-12), 0.98% past 100 m and 0.13% past 200 m,
# against 0.20% from NONNA-10; bc-offshore-south 7.14%, 1.25% and 0.12%. On NONNA-10 two cells are about 25 m.
GUARD_SKIP_CELLS = 2.0
_NEAR_CHUNK = 200_000  # points tested against the coastline at a time
_OVERSHOOT_M = 1.0  # a moved end is carried this far past the outline, so the two lines cross
_CLIP_MARGIN_M = 1000.0  # lines are cut this far outside the box before noding
_ON_OUTLINE_M = 1e-6  # an edge whose middle is this close to the outline (or a connector) is part of it
_SEGMENT_DEG = 0.001  # the outline is densified to this before it goes to meters, so its edges keep their place


class CoastError(Exception):
    pass


def _segments(coords) -> list[tuple]:
    return [tuple(sorted((tuple(a), tuple(b)))) for a, b in zip(coords[:-1], coords[1:])]


def _ends(lines) -> list[tuple[Point, LineString, bool]]:
    """The dangling ends of the noded lines: (end, its edge, whether it is the edge's last point)."""
    edges = [e for e in getattr(lines, "geoms", [lines]) if not e.is_empty]
    count = Counter(c for e in edges for c in (e.coords[0], e.coords[-1]))
    return [(Point(e.coords[i]), e, i == -1) for e in edges for i in (0, -1) if count[e.coords[i]] == 1]


def _retraced(edge: LineString, pieces: list, tree) -> bool:
    """Whether the dangling edge lies within RETRACE_M of the other noded lines along its whole length."""
    others = [pieces[i] for i in tree.query(edge, predicate="dwithin", distance=RETRACE_M) if not pieces[i].equals(edge)]
    return bool(others) and edge.difference(unary_union(others).buffer(RETRACE_M)).length < 1e-3


def _connector(end: Point, edge: LineString, last: bool, outline) -> LineString:
    """A line from end onto the outline, carried _OVERSHOOT_M past it."""
    target = nearest_points(end, outline)[1]
    d = np.subtract(target.coords[0], end.coords[0])
    if np.hypot(*d) < 1e-3:  # already on the outline: go on in the line's own direction
        a, b = (edge.coords[-2], edge.coords[-1]) if last else (edge.coords[1], edge.coords[0])
        d = np.subtract(b, a)
    step = d / np.hypot(*d) * _OVERSHOOT_M
    return LineString([end.coords[0], tuple(np.add(target.coords[0], step))])


def _classes(faces, coast_keys: set) -> tuple[list[int], list[int]]:
    """Each face's class (0 or 1) and linked set (the index of its first face): faces sharing a coast segment are
    linked and of opposite classes. CoastError when the faces cannot be split into two classes."""
    by_segment = {}
    for i, face in enumerate(faces):
        for ring in [face.exterior, *face.interiors]:
            for key in _segments(ring.coords):
                if key in coast_keys:
                    by_segment.setdefault(key, []).append(i)
    neighbors = [set() for _ in faces]
    for owners in by_segment.values():
        if len(owners) == 2:
            neighbors[owners[0]].add(owners[1])
            neighbors[owners[1]].add(owners[0])
    parity, component = [None] * len(faces), [None] * len(faces)
    for start in range(len(faces)):
        if parity[start] is not None:
            continue
        parity[start], component[start] = 0, start
        queue = deque([start])
        while queue:
            i = queue.popleft()
            for j in neighbors[i]:
                if parity[j] is None:
                    parity[j], component[j] = 1 - parity[i], start
                    queue.append(j)
                elif parity[j] == parity[i]:
                    x, y = from_m(faces[i].representative_point()).coords[0]
                    raise CoastError(f"coastline: the faces near {x:.5f}, {y:.5f} cannot be split into land and water")
    return parity, component


def land_polygons(lines: Iterable[LineString], box: tuple[float, float, float, float], canada: shapely.Geometry,
                  water: shapely.MultiPoint, wet: shapely.Geometry, *,
                  cell_m: float) -> tuple[MultiPolygon, list[dict], int, list[dict]]:
    """Land inside box cut to canada, from the atlas coastline lines (river-mouth closing lines included), never
    from line direction (spec 7.1). Returns the land, the faces the river correction turned to water, each
    {"id", "area_km2", "wet_share"}, and the count of water points that fell in land faces before the corrections
    farther than GUARD_NEAR_M from every line (inland water: surveyed rivers and lakes the coastline leaves in land
    faces; the wet cut then removes the land from them), and the retraced segments skipped by the end check, each
    {"lon", "lat", "length_m"} (lon, lat of its free tip).

    The lines and the outline (the boundary of box cut to canada) split the area into faces; a line end within
    END_SNAP_M of the outline is moved onto it, a retraced segment (RETRACE_M, RETRACE_MAX_M: at most 100 m, covered
    within 1 m along its whole length by a line that runs on past its tip) is skipped, any other end raises
    CoastError. Faces sharing a coastline segment
    are of opposite kinds; in each set of faces so linked, the kind holding more water points (lon/lat centers of
    NONNA cells deeper than WATER_VOTE_M) is water. CoastError when the faces cannot be split into two kinds, when a
    linked set's water points do not decide, when no water point lies within GUARD_NEAR_M of a line and farther
    than GUARD_SKIP_CELLS cells of cell_m (the vote grid's cell width in meters) from every line, or when more
    than 1% of those water points fall in land. A separate
    piece of the area with no coastline is water. Then, with wet
    the NONNA cells at or below chart datum: a land face of at least RIVER_MIN_AREA_M2 more than RIVER_WATER_SHARE
    wet is water; a smaller face bounded by atlas lines alone (an islet) stays land whole; all other land is cut
    by wet."""
    area_ll = make_box(*box).intersection(canada)
    area = to_m(shapely.segmentize(area_ll, _SEGMENT_DEG))
    outline = area.boundary
    # Densified like the outline: four projected corners alone would put the south edge on a chord up to several
    # km north of the parallel on a wide box, past the margin, and cut the lines inside the box.
    clip = to_m(shapely.segmentize(make_box(*box), _SEGMENT_DEG)).buffer(_CLIP_MARGIN_M)
    coast = unary_union([to_m(line).intersection(clip) for line in lines])
    if coast.is_empty or area.is_empty:
        return MultiPolygon(), [], 0, []

    connectors, retraced, tree = [], [], None
    pieces = list(getattr(coast, "geoms", [coast]))
    ends = _ends(coast)
    tips = shapely.STRtree([e for e, _, _ in ends]) if ends else None
    for end, edge, last in ends:
        if not area.intersects(end):
            continue
        tree = tree or shapely.STRtree(pieces)
        alone = all(ends[i][0].equals(end) for i in tips.query(end, predicate="dwithin", distance=RETRACE_M))
        if alone and edge.length <= RETRACE_MAX_M and _retraced(edge, pieces, tree):
            x, y = from_m(end).coords[0]
            retraced.append({"lon": round(x, 6), "lat": round(y, 6), "length_m": round(edge.length, 2)})
            continue
        if outline.distance(end) > END_SNAP_M:
            x, y = from_m(end).coords[0]
            raise CoastError(f"coastline: the line end at {x:.5f}, {y:.5f} is more than {END_SNAP_M:g} m from the"
                             " box edge and the Canada polygon's boundary")
        connectors.append(_connector(end, edge, last, outline))
    edges = list(unary_union([coast, *connectors, outline]).geoms)
    middles = shapely.line_interpolate_point(edges, 0.5, normalized=True)
    shapely.prepare(outline)
    shapely.prepare(area)
    on_outline = shapely.dwithin(outline, middles, _ON_OUTLINE_M)
    on_connector = (shapely.dwithin(unary_union(connectors), middles, _ON_OUTLINE_M) if connectors
                    else np.zeros(len(edges), bool))
    coast_keys = {k for e, o in zip(edges, on_outline) if not o for k in _segments(e.coords)}
    atlas_keys = {k for e, o, c in zip(edges, on_outline, on_connector) if not (o or c) for k in _segments(e.coords)}
    faces = [f for f in polygonize(edges) if area.contains(f.representative_point())]
    parity, component = _classes(faces, coast_keys)

    # The vote: per linked set, the class holding more water points is water. A set of one face has no coastline.
    xy = to_m_xy(shapely.get_coordinates(water))
    xy = xy[shapely.contains_xy(area, xy[:, 0], xy[:, 1])]
    land_ids, on_land = [], np.zeros(len(xy), bool)
    for c in sorted(set(component)):
        members = [i for i in range(len(faces)) if component[i] == c]
        if len(members) == 1:
            continue
        inside = [shapely.contains_xy(unary_union([faces[i] for i in members if parity[i] == p]), xy[:, 0], xy[:, 1])
                  for p in (0, 1)]
        votes = [int(v.sum()) for v in inside]
        if votes[0] == votes[1]:
            x, y = from_m(faces[c].representative_point()).coords[0]
            raise CoastError(f"coastline: the water points do not tell land from water near {x:.5f}, {y:.5f}")
        land = 0 if votes[0] < votes[1] else 1
        land_ids += [i for i in members if parity[i] == land]
        on_land |= inside[land]
    # The guard, near the lines only (GUARD_NEAR_M, GUARD_SKIP_CELLS). The lines are prepared, so each point's test
    # uses their index.
    shapely.prepare(coast)
    near, skip = (np.concatenate([shapely.dwithin(coast, shapely.points(xy[k:k + _NEAR_CHUNK]), d)
                                  for k in range(0, len(xy), _NEAR_CHUNK)]) if len(xy) else np.zeros(0, bool)
                  for d in (GUARD_NEAR_M, GUARD_SKIP_CELLS * cell_m))
    judged = near & ~skip
    n_near, near_land = int(judged.sum()), int((judged & on_land).sum())
    band = f"within {GUARD_NEAR_M:g} m of the coastline and farther than {GUARD_SKIP_CELLS * cell_m:.0f} m"
    if n_near == 0:
        raise CoastError(f"coastline: no water point lies {band} (of {len(xy)} water points), so the land-share"
                         " guard cannot judge the land side")
    if near_land > _LAND_SHARE_LIMIT * n_near:
        raise CoastError(f"coastline: {near_land} of {n_near} water points {band} ({100 * near_land / n_near:.2f}%)"
                         " fall in land, over 1%: a wrong land side or a misplaced coastline")
    inland = int((on_land & ~near).sum())

    # Densified like the outline: the wet cells' edges run along parallels for tens of km, and projected by their
    # vertices alone such an edge becomes a chord that sags across the cells beside it (strait, 2026-11-12).
    wet_m = to_m(shapely.segmentize(wet, _SEGMENT_DEG))
    flipped, kept, islets = [], [], []
    for i in land_ids:
        face = faces[i]
        if face.area >= RIVER_MIN_AREA_M2:
            share = face.intersection(wet_m).area / face.area
            if share > RIVER_WATER_SHARE:
                flipped.append({"id": i, "area_km2": round(face.area / 1e6, 4), "wet_share": round(share, 4)})
                continue
        elif all(k in atlas_keys for k in _segments(face.exterior.coords)):
            islets.append(face)
            continue
        kept.append(face)
    # Back in lon/lat before the cuts, so land meets the Canada polygon and the wet cells exactly.
    land = from_m(unary_union(kept)).intersection(area_ll).difference(wet)
    land = land.union(from_m(unary_union(islets)).intersection(area_ll))
    return MultiPolygon([p for p in shapely.get_parts(land) if p.geom_type == "Polygon"]), flipped, inland, retraced
