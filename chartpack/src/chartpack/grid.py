"""Zoom-10 tile ownership (plan 7): every zoom-10 tile has exactly one owner pack, so packs merge without duplicates."""

import json
import math
import sqlite3
import tomllib
from pathlib import Path

import shapely
from shapely.geometry import box, shape

from chartpack.region import Region, RegionError, load_region

GRID_ZOOM = 10
_EPS = 1e-9  # in tile units: an edge touch within float noise is still an edge touch
_MAX_LAT = 85.0511287798066


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(W, S, E, N) of the XYZ tile."""
    n = 2**z

    def lat(row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return x / n * 360.0 - 180.0, lat(y + 1), (x + 1) / n * 360.0 - 180.0, lat(y)


def _tx(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * 2**z


def _ty(lat: float, z: int) -> float:
    lat = max(-_MAX_LAT, min(_MAX_LAT, lat))
    return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2**z


def tiles_meeting(bbox, z: int = GRID_ZOOM) -> set[tuple[int, int]]:
    """XYZ tiles whose interior meets the bbox interior (an edge touch does not count)."""
    w, s, e, n = bbox
    x0, x1 = math.floor(_tx(w, z) + _EPS), math.ceil(_tx(e, z) - _EPS) - 1
    y0, y1 = math.floor(_ty(n, z) + _EPS), math.ceil(_ty(s, z) - _EPS) - 1
    x1, y1 = max(x0, x1), max(y0, y1)  # a zero-width or zero-height box still sits in one tile
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def assign(regions: list[Region], order: list[str], clip: shapely.Geometry | None) -> dict[tuple[int, int], str]:
    """Each zoom-10 tile meeting a region box goes to the first name in `order` whose box meets it;
    a tile fully inside `clip` goes to no one."""
    by_name = {r.name: r for r in regions if not r.overview}
    if unlisted := sorted(set(by_name) - set(order)):
        raise RegionError(f"region(s) not in the grid order: {', '.join(unlisted)}")
    if unknown := [n for n in order if n not in by_name]:
        raise RegionError(f"grid order names region(s) that were not given: {', '.join(unknown)}")
    owner: dict[tuple[int, int], str] = {}
    for name in order:
        for tile in tiles_meeting(by_name[name].bbox):
            owner.setdefault(tile, name)
    if clip is not None:
        shapely.prepare(clip)
        owner = {t: n for t, n in owner.items() if not clip.contains(box(*tile_bounds(GRID_ZOOM, *t)))}
    return owner


def load_grid(path: Path) -> list[str]:
    with Path(path).open("rb") as f:
        data = tomllib.load(f)
    if data.get("zoom") != GRID_ZOOM:
        raise RegionError(f"{path}: grid zoom must be {GRID_ZOOM}, not {data.get('zoom')!r}")
    if "order" not in data:
        raise RegionError(f"{path}: missing key order")
    return list(data["order"])


def owned_tiles(region: Region, regions_dir: Path) -> set[tuple[int, int]] | None:
    """The zoom-10 tiles this region pack owns; None for the overview, which owns no zoom-10 tile."""
    if region.overview:
        return None
    regions_dir = Path(regions_dir)
    order = load_grid(regions_dir / "grid.toml")
    if region.name not in order:
        raise RegionError(f"region {region.name} is not in {regions_dir / 'grid.toml'}")
    regions = []
    for name in order:
        if name == region.name:
            regions.append(region)
            continue
        path = regions_dir / f"{name}.toml"
        if not path.is_file():
            raise RegionError(f"grid order names {name} but {path} does not exist")
        regions.append(load_region(path))
    clips = {r.clip for r in regions if r.clip is not None}
    geoms = []
    for p in sorted(clips):
        data = json.loads(p.read_text())
        geoms.append(shape(data.get("geometry", data)))
    clip = shapely.union_all(geoms) if geoms else None
    owner = assign(regions, order, clip)
    return {tile for tile, name in owner.items() if name == region.name}


def content_tiles(region: Region, regions_dir: Path) -> set[tuple[int, int]]:
    """The zoom-10 tiles a pack's content is selected and cropped over: a region pack's owned tiles
    (owned_tiles); for the overview, every tile a region pack in grid.toml owns."""
    owned = owned_tiles(region, regions_dir)
    if owned is not None:
        return owned
    regions_dir = Path(regions_dir)
    return set().union(*(owned_tiles(load_region(regions_dir / f"{name}.toml"), regions_dir)
                         for name in load_grid(regions_dir / "grid.toml")))


def tiles_area(tiles: set[tuple[int, int]], margin_deg: float = 0.0) -> shapely.Geometry:
    """The union of the zoom-10 tiles, each grown by margin_deg."""
    return shapely.union_all([box(w - margin_deg, s - margin_deg, e + margin_deg, n + margin_deg)
                              for w, s, e, n in (tile_bounds(GRID_ZOOM, x, y) for x, y in tiles)])


def keep_tiles(path: Path, owned: set[tuple[int, int]] | None, *, minzoom: int, maxzoom: int,
               content: set[tuple[int, int]] | None = None) -> None:
    """Prune an enc.mbtiles to the zoom range and, when `owned` is set, to the owned zoom-10 tiles and
    their descendants. Stored rows are TMS: flip to XYZ before taking the zoom-10 ancestor. For the overview
    (`owned` None), `content` (its content_tiles) is recorded as cheekymarine:content, the area the pack
    check compares against the source cells."""
    if owned is not None and not owned:
        raise RegionError("no owned zoom-10 tiles: the region box is empty or entirely clipped")
    conn = sqlite3.connect(path)
    try:
        # tile-join writes `map` and `images` tables with `tiles` a view over them; rows go from `map`.
        view = conn.execute("select 1 from sqlite_master where name = 'tiles' and type = 'view'").fetchone()
        table = "map" if view else "tiles"
        conn.execute(f"delete from {table} where zoom_level < ? or zoom_level > ?", (minzoom, maxzoom))
        if owned is not None:
            conn.execute("create temp table owned (x integer, y integer, primary key (x, y))")
            conn.executemany("insert into owned values (?, ?)", sorted(owned))
            conn.execute(
                f"delete from {table} where zoom_level >= ? and not exists (select 1 from owned where"
                " x = tile_column >> (zoom_level - ?) and y = ((1 << zoom_level) - 1 - tile_row) >> (zoom_level - ?))",
                (GRID_ZOOM, GRID_ZOOM, GRID_ZOOM),
            )
        meta = {"minzoom": str(minzoom), "maxzoom": str(maxzoom),
                "cheekymarine:owned": json.dumps(None if owned is None else sorted([x, y] for x, y in owned))}
        if owned is None and content is not None:
            meta["cheekymarine:content"] = json.dumps(sorted([x, y] for x, y in content))
        if owned is not None:
            boxes = [tile_bounds(GRID_ZOOM, x, y) for x, y in owned]
            meta["bounds"] = ",".join(str(v) for v in (
                min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)))
        if view:
            conn.execute("delete from images where tile_id not in (select tile_id from map)")
        conn.executemany("insert or replace into metadata values (?, ?)", list(meta.items()))
        conn.commit()
        conn.execute("vacuum")
    finally:
        conn.close()


Line = tuple[tuple[float, float], tuple[float, float]]


def seams(owned: dict[str, set[tuple[int, int]]]) -> dict[tuple[str, str], list[Line]]:
    """The zoom-10 tile edges each pair of regions shares, as straight lines ((W, S), (E, N)): along a tile row
    S == N, along a column W == E. Runs of edges on one row or column are merged. `owned` maps region names to
    their owned tiles (owned_tiles); a pair is keyed in the order the names come in `owned`."""
    owner = {tile: name for name, tiles in owned.items() for tile in tiles}
    rank = {name: i for i, name in enumerate(owned)}
    rows: dict[tuple[str, str, int], set[int]] = {}  # (a, b, row edge y) -> x of each shared unit edge
    cols: dict[tuple[str, str, int], set[int]] = {}  # (a, b, column edge x) -> y of each shared unit edge
    for (x, y), a in owner.items():
        for (nx, ny), edges, key, unit in (((x + 1, y), cols, x + 1, y), ((x, y + 1), rows, y + 1, x)):
            b = owner.get((nx, ny))
            if b is not None and b != a:
                pair = (a, b) if rank[a] < rank[b] else (b, a)
                edges.setdefault((*pair, key), set()).add(unit)

    def lon(tx: int) -> float:  # west edge of tile column tx
        return tile_bounds(GRID_ZOOM, tx, 0)[0]

    def lat(ty: int) -> float:  # north edge of tile row ty
        return tile_bounds(GRID_ZOOM, 0, ty)[3]

    def runs(units: set[int]) -> list[tuple[int, int]]:
        out = []
        for u in sorted(units):
            if out and out[-1][1] == u:
                out[-1] = (out[-1][0], u + 1)
            else:
                out.append((u, u + 1))
        return out

    result: dict[tuple[str, str], list[Line]] = {}
    for (a, b, y), xs in sorted(rows.items()):
        result.setdefault((a, b), []).extend(((lon(x0), lat(y)), (lon(x1), lat(y))) for x0, x1 in runs(xs))
    for (a, b, x), ys in sorted(cols.items()):
        result.setdefault((a, b), []).extend(((lon(x), lat(y1)), (lon(x), lat(y0))) for y0, y1 in runs(ys))
    return dict(sorted(result.items(), key=lambda kv: (rank[kv[0][0]], rank[kv[0][1]])))
