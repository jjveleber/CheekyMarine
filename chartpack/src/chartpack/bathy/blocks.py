"""Fine and coarse bathy built block by block, one block per owned zoom-10 tile (plan 7, plan 8 spec 6).

Fine is the survey tier at 1/9 arc-second (CUDEM; NONNA-10 on the Canadian side); coarse is at 1 arc-second
on every coarse cell the fine tier does not wholly hold (CRM then ETOPO; NONNA-100 first on the Canadian side).
Each block is read over its tile plus a margin and its features are clipped to the tile, so memory stays at
one tile (about 11k by 8k fine cells, under 3 GB) and lines meet across tile edges: every grid sits on
multiples of its own cell size from (-180, 90), so two blocks (or two packs) see the same cells along their
shared edge.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from scipy.ndimage import binary_dilation
from shapely.geometry import box, mapping, shape

from chartpack.bathy.bands import bands_by_zoom
from chartpack.bathy.contours import (
    BANDS,
    COARSE_BANDS,
    OVERVIEW_BANDS,
    REF_LAT,
    block_factor,
    block_mean,
    contours_by_zoom,
    zoom_tolerance_deg,
)
from chartpack.bathy.cudem import CudemTile, Grid, read_window, tiles_for_bbox
from chartpack.bathy.etopo import CD_BELOW_MSL_M, clip_to_tile
from chartpack.bathy.merge import clip_mask, coverage_polygons, fill_land, merge_ordered, warp_depth
from chartpack.bathy.nonna import read_nonna
from chartpack.bathy.tiles import COARSE_ZOOMS
from chartpack.datum import SOURCE_VERTICAL, geoid, node_axes, resample
from chartpack.datum.offsets import load_datum, navd88_to_mllw_nodes
from chartpack.grid import GRID_ZOOM, tile_bounds
from chartpack.region import Region

FINE_RES_DEG = 1 / 32400  # CUDEM, 1/9 arc-second
COARSE_RES_DEG = 1 / 3600  # CRM, 1 arc-second
OVERVIEW_RES_DEG = 0.0025  # the overview block-means native CRM to this (9 by 9 arc-second cells)
BLOCK_MARGIN_DEG = 0.02  # each block is read this far past its tile
OVERVIEW_STRIP_DEG = 0.5  # build_overview reads this much latitude at a time: a whole number of overview cells
CRM_LABEL = {"source": "crm", "resolution_m": 30, "date": "2025"}
DEM_OWNER_ZOOM = COARSE_ZOOMS[1]  # DEM tile ownership is decided per tile of the coarse max zoom
SOURCE_NAMES = ("none", "cudem", "crm", "nonna10", "nonna100", "etopo")  # the source index of the merged grids
_INDEX = {name: i for i, name in enumerate(SOURCE_NAMES)}
FINE_TIER = (_INDEX["cudem"], _INDEX["nonna10"])  # the sources the fine features draw
LABELS = {  # the coverage properties per source, plus "grade" (grade)
    "cudem": {"source": "cudem", "resolution_m": 3, "date": ""},  # date: the years of the CUDEM tiles in the core
    "crm": CRM_LABEL,
    "nonna10": {"source": "nonna10", "resolution_m": 10, "date": "2026"},
    "nonna100": {"source": "nonna100", "resolution_m": 100, "date": "2026"},
    "etopo": {"source": "etopo", "resolution_m": 460, "date": "2022"},
}


def grade(source: str, canadian: bool) -> str:
    """The depth grade of plan 8 spec 6: "survey" (CUDEM, NONNA-10, CRM on the US side), "coarse-survey"
    (NONNA-100) or "rough" (ETOPO, CRM on the Canadian side)."""
    if source == "nonna100":
        return "coarse-survey"
    return "rough" if source == "etopo" or (source == "crm" and canadian) else "survey"


@dataclass
class BlockSources:
    """The depth sources of one block; None (no tiles for CUDEM) for a source the region does not list."""

    cudem_tiles: Sequence[CudemTile]
    crm_path: Path | None
    nonna10: Path | None
    nonna100: Path | None
    etopo: Path | Sequence[Path] | None  # the ETOPO tile files that meet the region; a lone Path is one tile


@dataclass
class BlockResult:
    """GeoJSON Features clipped to the block's core, and the depth grids (land kept) for the DEMs: depth by the
    station path, without the lake rule the features use (AreaDatum).

    fine_grid is the whole merge (the fine tier over the coarse sources) so the fine DEM has no false cliff at
    the fine tier's edge; fine_cudem marks its fine-tier cells (CUDEM or NONNA-10), the only ones the fine
    features use and the ones that decide which zoom-12 tiles the fine DEM owns (fine_owned_z12). fine_source
    and coarse_source give each cell's source as an index into SOURCE_NAMES (0: none).

    nav_depth is NONNA-10, then NONNA-100, on the Canadian column at the fine grid's cells, each the shallowest
    native value under the cell (read_nonna "min"), so a shoal cell keeps its value, on the cells whose center
    lies in a native cell with a value (no fill-in, _nav_values); nan elsewhere. nav_src is its source index and
    nonna_valid marks the cells holding a NONNA value. All three are None when the block has no Canadian column
    or the region lists no NONNA.
    """

    fine_contours: list[dict]
    fine_bands: list[dict]
    fine_coverage: list[dict]
    coarse_contours: list[dict]
    coarse_bands: list[dict]
    coarse_coverage: list[dict]
    fine_grid: Grid | None  # None for the overview and for a block with no fine-tier value: no fine output
    coarse_grid: Grid | None  # None when the region has no coarse source
    fine_cudem: np.ndarray | None = None  # bool, the fine grid's shape
    fine_source: np.ndarray | None = None  # int8, the fine grid's shape
    coarse_source: np.ndarray | None = None  # int8, the coarse grid's shape
    nonna_valid: np.ndarray | None = None  # bool, the fine grid's shape
    nav_depth: Grid | None = None
    nav_src: np.ndarray | None = None  # int8, nav_depth's shape


class AreaDatum:
    """The region's datum file as a callable: datum(source, transform, shape) is the offset in meters to subtract
    from -elevation for MLLW depth. It is the NAVD88 to MLLW offset per area for every source, plus the EGM2008
    to NAVD88 height change for EGM2008 sources (CRM), from the geoid grids fetch-bathy put in cache. Both are
    summed at the global grid nodes and resampled once (bilinear is linear), so a call allocates one
    block-size array. It is zero for a "chart" source (NONNA, already on Canadian chart datum) and the fixed
    CD_BELOW_MSL_M for the "msl" source (ETOPO: no geoid grid, no station).

    Lakes (#88): with lakes=True a cell whose center is inside a lake polygon of the datum file takes the lake's
    offset instead, -low_level_navd88_m plus the height change, so its depth is the lake's low level minus the
    NAVD88 height of the bottom whatever the source. The mask comes from the polygons, so it does not depend on
    the block. The lake rule is a depth datum, not terrain: the DEM grids use lakes=False, and lake_delta is
    what the rule adds to such a depth."""

    def __init__(self, region: Region, cache: Path):
        datum_file = load_datum(region.datum_file)
        self.stations = datum_file.stations
        self.lakes = [(lake.low_level_navd88_m, datum_file.lake_areas[lake.name],
                       shape(datum_file.lake_areas[lake.name])) for lake in datum_file.lakes]
        self.cache = cache

    def __call__(self, source: str, transform, grid_shape: tuple[int, int], *, lakes: bool = True) -> np.ndarray:
        if SOURCE_VERTICAL[source] == "chart":  # NONNA is on chart datum
            return np.zeros(grid_shape, np.float32)
        if SOURCE_VERTICAL[source] == "msl":  # ETOPO: chart datum lies a fixed distance below mean sea level
            return np.full(grid_shape, CD_BELOW_MSL_M, np.float32)
        lons, lats = node_axes(transform, grid_shape)
        nodes = navd88_to_mllw_nodes(self.stations, lons, lats)
        if SOURCE_VERTICAL[source] == "egm2008":  # NAVD88 height = EGM2008 height + the change
            nodes += geoid.egm2008_to_navd88_nodes(lons, lats, self.cache)
        offset = resample(nodes, lons, lats, transform, grid_shape)
        delta = self.lake_delta(transform, grid_shape) if lakes else None
        if delta is not None:
            offset -= delta
        return offset

    def lake_delta(self, transform, grid_shape: tuple[int, int]) -> np.ndarray | None:
        """Lake depth minus station-path depth per cell, the same for every source: low_level_navd88_m plus the
        NAVD88 to MLLW offset inside a lake polygon, 0 elsewhere. None when no lake meets the grid."""
        x0, dx, _, y0, _, dy = transform
        grid = box(x0, y0 + grid_shape[0] * dy, x0 + grid_shape[1] * dx, y0)
        delta = station = None
        for low, area, polygon in self.lakes:
            if not polygon.intersects(grid):
                continue
            inside = clip_mask(transform, grid_shape, area)
            if delta is None:
                lons, lats = node_axes(transform, grid_shape)
                station = resample(navd88_to_mllw_nodes(self.stations, lons, lats), lons, lats, transform, grid_shape)
                delta = np.zeros(grid_shape, np.float32)
            delta[inside] = low + station[inside]
            del inside
        return delta


def area_datum(region: Region, cache: Path) -> AreaDatum:
    """The region's datum (AreaDatum), with the geoid grids fetch-bathy put in cache."""
    return AreaDatum(region, cache)


def _with_lakes(grid: Grid, datum: AreaDatum) -> Grid:
    """A depth grid (station path) with the lake rule added; the grid itself when no lake meets it."""
    delta = datum.lake_delta(grid.transform, grid.data.shape)
    return grid if delta is None else Grid(grid.data + delta, grid.nodata, grid.transform, grid.crs)


def snap_out(bbox, cell: float) -> tuple[float, float, float, float]:
    """bbox (W, S, E, N) grown outward to multiples of cell from (-180, 90)."""
    w, s, e, n = bbox
    eps = 1e-9  # an edge already on a multiple, within float noise, stays put
    return (
        round(math.floor((w + 180) / cell + eps) * cell - 180, 10),
        round(90 - math.ceil((90 - s) / cell - eps) * cell, 10),
        round(math.ceil((e + 180) / cell - eps) * cell - 180, 10),
        round(90 - math.floor((90 - n) / cell + eps) * cell, 10),
    )


def iter_blocks(owned: set[tuple[int, int]], margin_deg: float = BLOCK_MARGIN_DEG) -> Iterator[
    tuple[tuple[int, int], tuple[float, float, float, float], tuple[float, float, float, float]]
]:
    """Per owned zoom-10 tile (in x, y order): the tile, its core bounds and its read bounds (the core plus
    margin_deg, snapped outward to the coarse cell, which is a whole number of fine cells)."""
    for x, y in sorted(owned):
        core = tile_bounds(GRID_ZOOM, x, y)
        w, s, e, n = core
        yield (x, y), core, snap_out((w - margin_deg, s - margin_deg, e + margin_deg, n + margin_deg), COARSE_RES_DEG)


def overview_bounds(bbox) -> tuple[float, float, float, float]:
    """The overview's CRM read: the region bbox snapped outward to the overview cell."""
    return snap_out(bbox, OVERVIEW_RES_DEG)


def _overlap(a, b) -> tuple[float, float, float, float]:
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def _clip(grid: Grid, clip: shapely.Geometry | None) -> None:
    """Cells whose center is inside clip (water to remove) become nan, in place."""
    if clip is not None:
        grid.data[clip_mask(grid.transform, grid.data.shape, mapping(clip))] = np.nan


def _side(canada: shapely.Geometry | None, read, res: float) -> np.ndarray | None:
    """The cells of the grid over read at res whose center is in the Canadian column `canada`; None when none is."""
    if canada is None:
        return None
    area = canada.intersection(box(*read))
    area = shapely.union_all([g for g in shapely.get_parts(area) if g.geom_type in ("Polygon", "MultiPolygon")])
    if area.is_empty:
        return None
    w, s, e, n = read
    grid_shape = (round((n - s) / res), round((e - w) / res))
    if area.covers(box(*read)):
        return np.ones(grid_shape, bool)
    side = clip_mask((w, res, 0.0, n, 0.0, -res), grid_shape, mapping(area))
    return side if side.any() else None


def _nav_values(path: Path, read, res: float, near: np.ndarray | None = None) -> np.ndarray:
    """NONNA depths for nav_depth: the shallowest native value under each cell ("min"), only on the cells whose
    center lies in a native cell with a value (nearest), so no depth reaches into a hole (spec 7.1, no fill-in).
    near: the nearest read at res when the caller already has it."""
    values = read_nonna(path, read, res, "min").data
    values[np.isnan(read_nonna(path, read, res).data if near is None else near)] = np.nan
    return values


def _coarse_layers(sources: BlockSources, read, res: float, side: np.ndarray | None, window) -> list:
    """The coarse sources as merge_ordered layers at res, in the order of plan 8 spec 6: NONNA-100 (Canadian
    column only), CRM, ETOPO. window(path) gives a source's native window over read."""
    layers = []
    if sources.nonna100 is not None and side is not None:  # nearest: each native cell keeps its surveyed value
        layers.append((_INDEX["nonna100"], lambda: read_nonna(sources.nonna100, read, res).data, side))
    if sources.crm_path is not None:
        layers.append((_INDEX["crm"], lambda: warp_depth(window(sources.crm_path), read, res, "bilinear"), None))
    etopo = [sources.etopo] if isinstance(sources.etopo, Path) else list(sources.etopo or [])
    for path in etopo:  # one layer per tile, each read cut to the tile's extent (no padding); cells no tile covers stay nan
        if (clip := clip_to_tile(path, read)) is not None:
            layers.append((_INDEX["etopo"], lambda path=path, clip=clip: warp_depth(window(path, clip), read, res,
                                                                                   "bilinear"), None))
    return layers


def _present(source: np.ndarray) -> list[int]:
    """The source indices (not 0) that occur in source, in SOURCE_NAMES order."""
    return [int(i) for i in np.flatnonzero(np.bincount(source.ravel(), minlength=len(SOURCE_NAMES))) if i]


def _shift(grid: Grid, source: np.ndarray, datum: AreaDatum) -> None:
    """Each cell's depth shifted by its own source's datum offset (the station path, no lake rule), in place:
    CUDEM and CRM to MLLW, NONNA left on chart datum, ETOPO by its fixed shift. A water cell (depth above 0) of
    a mean sea level source that the shift would take below 0 gets 0.0: it never makes a drying area."""
    for index in _present(source):
        take = source == index
        was = grid.data[take]
        now = was - datum(SOURCE_NAMES[index], grid.transform, grid.data.shape, lakes=False)[take]
        if SOURCE_VERTICAL[SOURCE_NAMES[index]] == "msl":
            now = np.where((was > 0) & (now < 0), np.float32(0.0), now)
        grid.data[take] = now
        del take


def _coverage(valid: np.ndarray, transform, core, label: dict, within: shapely.Geometry | None = None) -> list[dict]:
    """Coverage polygons of the valid cells, cut to core and to `within` (one side of the border) when given."""
    feats = coverage_polygons(valid.astype(np.uint8), transform, {1: label})
    if core is None and within is None:
        return feats
    area = box(*core) if within is None else within if core is None else within.intersection(box(*core))
    out = []
    for f in feats:
        geom = shape(f["geometry"]).intersection(area)
        parts = [g for g in shapely.get_parts(geom) if g.geom_type in ("Polygon", "MultiPolygon")]
        if parts:  # a cut along the border can leave lines and points beside the polygons
            out.append({**f, "geometry": mapping(shapely.union_all(parts))})
    return out


def _tag_sources(contours: list[dict], src: np.ndarray, transform, valid: np.ndarray) -> None:
    """Each contour's "source": the source of the cell under its representative point when that cell is one of
    `valid`, else the source of most `valid` cells (a smoothed line can sit just past them)."""
    counts = np.bincount(src[valid], minlength=len(SOURCE_NAMES))
    common, mixed = SOURCE_NAMES[int(counts.argmax())], np.count_nonzero(counts) > 1
    x0, dx, _, y0, _, dy = transform
    rows, cols = src.shape
    for f in contours:
        name = common
        if mixed:
            point = shape(f["geometry"]).representative_point()
            row = min(max(int((point.y - y0) / dy), 0), rows - 1)
            col = min(max(int((point.x - x0) / dx), 0), cols - 1)
            if valid[row, col]:
                name = SOURCE_NAMES[src[row, col]]
        f["properties"]["source"] = name


def _graded_coverage(valid: np.ndarray, src: np.ndarray, side: np.ndarray | None, transform, core,
                     labels: dict, canada: shapely.Geometry | None = None) -> list[dict]:
    """Coverage of the `valid` cells, one set of polygons per source (CRM split by side of the border), each with
    its label and grade. The two CRM sets are cut at `canada`, so a coverage block the border crosses is "rough"
    only on the Canadian side and "survey" only on the US side; the NONNA sets (Canadian side only) are cut to
    `canada` too, so they never reach onto US water."""
    out = []
    for index in _present(src[valid]):
        name = SOURCE_NAMES[index]
        cells = valid & (src == index)
        if name in ("nonna10", "nonna100"):
            parts = [(True, cells, canada)]
        elif name != "crm" or side is None:
            parts = [(False, cells, None)]
        else:
            parts = [(False, cells & ~side, None if canada is None else box(*core).difference(canada)),
                     (True, cells & side, canada)]
        for canadian, part, within in parts:
            if part.any():
                out += _coverage(part, transform, core, {**labels[name], "grade": grade(name, canadian)}, within)
    return out


def _features(
    grid: Grid, core, bands, *, fine: bool, src: np.ndarray, side: np.ndarray | None, labels: dict,
    cells: np.ndarray | None = None, band_cells: np.ndarray | None = None, overzoomed: bool = False,
    canada: shapely.Geometry | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    """Contours (tagged with their source, _tag_sources), bands and coverage (per source and grade) of one depth
    grid, clipped to core. src is the grid's source index, side its Canadian column (None: all US), labels the
    coverage labels by source. `cells` (bool) limits the features to those cells; by default every finite cell
    counts. `band_cells` (bool, holding `cells`) gives the bands more cells than the contours and coverage.
    overzoomed: see contours_by_zoom. canada (the Canadian column) cuts the coverage grades at the border."""
    valid = np.isfinite(grid.data) if cells is None else cells
    filled = fill_land(grid.data)  # the grid itself keeps the real land heights for the hillshade
    filled[~(valid if band_cells is None else band_cells)] = np.nan
    polygons = bands_by_zoom(filled, grid.transform, bands=bands, core=core)
    filled[~valid] = np.nan
    contours = contours_by_zoom(filled, grid.transform, fine=fine, bands=bands, core=core, overzoomed=overzoomed)
    _tag_sources(contours, src, grid.transform, valid)
    del filled
    return contours, polygons, _graded_coverage(valid, src, side, grid.transform, core, labels, canada)


def _under_cells() -> int:
    """Coarse cells the coarse bands run on past the coarse cells that fine owns, under the fine bands, so at every
    zoom no point between them lacks a band. Each band edge stops at the last cell center of its zoom's
    block-meaned grid, up to half a block short of the coarse data or past the CUDEM edge on the fine side,
    simplifying moves it up to its tolerance, and tippecanoe moves it up to 1.5 units of its 4096-unit tile (one
    unit of its own simplification, half a unit of rounding to the grid) at the zoom of the tile drawn; the
    coarse bands draw their last range past its top zoom. The tolerance is the one at REF_LAT: wider than at
    any latitude north of it, and the count it gives holds down to 40 N (#18)."""
    def reach(res, bands, zoom):
        _, hi, target = next((b for b in bands if b[0] <= zoom <= b[1]), bands[-1])
        tile_units = 1.5 * 360 / 2 ** min(zoom, bands[-1][1]) / 4096
        return block_factor((0, res, 0, 0, 0, -res), target) * res / 2 + zoom_tolerance_deg(hi, REF_LAT) + tile_units

    zooms = range(BANDS[0][0], BANDS[-1][1] + 1)
    worst = max(reach(COARSE_RES_DEG, COARSE_BANDS, z) + reach(FINE_RES_DEG, BANDS, z) for z in zooms)
    return math.ceil(worst / COARSE_RES_DEG)


def build_block(
    core, read, sources: BlockSources, datum: AreaDatum, canada: shapely.Geometry | None, *,
    lake_mask: shapely.Geometry | None = None
) -> BlockResult:
    """Fine and coarse outputs of one block: features clipped to core, grids over read.

    Per cell the first source with data wins (plan 8 spec 6). canada is the Canadian column over read (None:
    all US). US side: fine CUDEM, coarse CRM then ETOPO. Canadian side: fine NONNA-10 then CUDEM, coarse
    NONNA-100 then CRM then ETOPO. NONNA is warped from its native grid by nearest for the Fish grids (each
    native cell drawn as an exact square of its surveyed value, owner 2026-11-12) and by the shallowest value
    for nav_depth.

    Fine is the fine tier over the coarse sources; its features use the fine-tier cells only, its DEM the whole
    merge. Coarse is drawn on every coarse cell unless every fine cell in it is fine tier, decided per cell; its
    contours and coverage stop there, while its grid and bands keep _under_cells more coarse cells under fine
    so the bands overlap instead of leaving a gap (the style draws coarse under fine), each only where its own
    fine cells include fine-tier water, so no coarse depth is drawn under dry fine-tier cells. A region with no
    coarse source leaves the coarse outputs empty. A block with no fine-tier value (no CUDEM tile meets it and
    no NONNA-10 value on its Canadian column) skips the fine merge: its fine outputs are empty and fine_grid is
    None. Cells inside lake_mask (lakes with no datum rule) are nan in both grids before anything is drawn. The
    grids (the DEMs) are depth by the station path; the features add the lake rule (_with_lakes).
    """
    native = {}  # CRM and ETOPO windows over read, each read once for both grids

    def window(path: Path, box=None) -> Grid:  # box: the part of read a tile file holds (default all of read)
        if path not in native:
            native[path] = read_window(str(path), read if box is None else box)
        return native[path]

    def merged(layers, res):  # the merge, each source on its datum (_shift), less the masked lakes
        grid, source = merge_ordered(layers, read, res)
        _shift(grid, source, datum)
        _clip(grid, lake_mask)
        return grid, source

    fine_side, coarse_side = _side(canada, read, FINE_RES_DEG), _side(canada, read, COARSE_RES_DEG)
    cudem_tiles = list(sources.cudem_tiles)
    meeting = cudem_tiles if tiles_for_bbox(cudem_tiles, read) else []
    near10 = None  # NONNA-10 by nearest on the Canadian column: the Fish values, its mask and nav_depth's mask
    if sources.nonna10 is not None and fine_side is not None:
        near10 = read_nonna(sources.nonna10, read, FINE_RES_DEG).data
        near10[~fine_side] = np.nan
    fine = fine_source = cells = None
    if meeting or (near10 is not None and np.isfinite(near10).any()):
        layers = [] if near10 is None else [(_INDEX["nonna10"], lambda: near10, None)]
        layers += [(_INDEX["cudem"], lambda t=t: warp_depth(
            read_window("/vsicurl/" + t.url, _overlap(t.bounds, read)), read, FINE_RES_DEG, "near"), None)
            for t in meeting]
        fine, fine_source = merged(layers + _coarse_layers(sources, read, FINE_RES_DEG, fine_side, window),
                                   FINE_RES_DEG)
        del layers
        cells = np.isin(fine_source, FINE_TIER) & np.isfinite(fine.data)
    coarse_layers = _coarse_layers(sources, read, COARSE_RES_DEG, coarse_side, window)
    coarse, coarse_source = merged(coarse_layers, COARSE_RES_DEG) if coarse_layers else (None, None)
    del native

    fine_out = ([], [], [])
    coarse_cells = None
    if fine is not None:
        fine_depth = _with_lakes(fine, datum)  # the depths the fine bands draw
        if coarse is not None:
            k = round(COARSE_RES_DEG / FINE_RES_DEG)
            rows, cols = coarse.data.shape
            owned = np.isin(fine_source, FINE_TIER).reshape(rows, k, cols, k).all(axis=(1, 3))
            with np.errstate(invalid="ignore"):
                wet = (cells & (fine_depth.data > 0)).reshape(rows, k, cols, k).any(axis=(1, 3))
            under = binary_dilation(~owned, np.ones((3, 3), bool), iterations=_under_cells()) & (~owned | wet)
            coarse.data[~under] = np.nan
            coarse_cells = np.isfinite(coarse.data) & ~owned
            del owned, wet, under
        years = ",".join(sorted({str(t.year) for t in tiles_for_bbox(cudem_tiles, core)}))
        labels = {**LABELS, "cudem": {**LABELS["cudem"], "date": years}}
        fine_out = _features(fine_depth, core, BANDS, fine=True, src=fine_source, side=fine_side, labels=labels,
                             cells=cells, canada=canada)
        del fine_depth
    coarse_out = ([], [], []) if coarse is None else _features(
        _with_lakes(coarse, datum), core, COARSE_BANDS, fine=False, src=coarse_source, side=coarse_side,
        labels=LABELS, cells=coarse_cells, band_cells=None if coarse_cells is None else np.isfinite(coarse.data),
        overzoomed=True, canada=canada)

    nav = nav_src = nonna_valid = None
    nonna = (("nonna10", sources.nonna10, near10), ("nonna100", sources.nonna100, None))
    nav_layers = [(_INDEX[name], lambda path=path, near=near: _nav_values(path, read, FINE_RES_DEG, near), fine_side)
                  for name, path, near in nonna if path is not None]
    if fine_side is not None and nav_layers:
        nav, nav_src = merge_ordered(nav_layers, read, FINE_RES_DEG)  # chart datum: no shift
        nonna_valid = np.isfinite(nav.data)
    return BlockResult(*fine_out, *coarse_out, fine_grid=fine, coarse_grid=coarse, fine_cudem=cells,
                       fine_source=fine_source, coarse_source=coarse_source, nonna_valid=nonna_valid, nav_depth=nav,
                       nav_src=nav_src)


def fine_owned_z12(cudem: np.ndarray, transform, tile: tuple[int, int]) -> set[tuple[int, int]]:
    """The zoom-12 tiles (x, y) of the owned zoom-10 tile that hold a fine-tier cell, CUDEM or NONNA-10 (cudem:
    bool over the fine grid, BlockResult.fine_cudem, after the lake mask), each cell placed by its center. Only
    the tile's own zoom-12 tiles are decided, and from the global cell index, so the block that owns a zoom-12
    tile is the only one that decides it and a patch in another block's read margin never counts."""
    zoom = DEM_OWNER_ZOOM
    x0, dx, _, y0, _, dy = transform
    rows, cols = cudem.shape
    lon = -180 + (round((x0 + 180) / dx) + np.arange(cols) + 0.5) * dx
    lat = 90 + (round((90 - y0) / -dy) + np.arange(rows) + 0.5) * dy
    n = 2**zoom
    tx = np.floor((lon + 180) / 360 * n).astype(np.int64)
    ty = np.floor((1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n).astype(np.int64)
    k = 2 ** (zoom - GRID_ZOOM)
    owned = set()
    for x in range(tile[0] * k, (tile[0] + 1) * k):
        c = np.flatnonzero(tx == x)
        for y in range(tile[1] * k, (tile[1] + 1) * k):
            r = np.flatnonzero(ty == y)
            if c.size and r.size and cudem[r[0] : r[-1] + 1, c[0] : c[-1] + 1].any():
                owned.add((x, y))
    return owned


def dem_tiles(owned12: set[tuple[int, int]], tile: tuple[int, int], maxzoom: int
              ) -> tuple[set[tuple[int, int, int]], set[tuple[int, int, int]]]:
    """(fine, coarse) DEM tiles (z, x, y) of an owned zoom-10 tile, one source per place per zoom: the fine DEM
    writes the fine-owned zoom-12 tiles, their zoom-10 and 11 ancestors and their descendants to maxzoom; the
    coarse DEM writes the other zoom-10 to 12 tiles of the tile (the map overzooms its z12 tiles past 12)."""
    fine = set()
    for x, y in owned12:
        for z in range(GRID_ZOOM, DEM_OWNER_ZOOM + 1):
            shift = DEM_OWNER_ZOOM - z
            fine.add((z, x >> shift, y >> shift))
        for z in range(DEM_OWNER_ZOOM + 1, maxzoom + 1):
            k = 2 ** (z - DEM_OWNER_ZOOM)
            fine.update((z, x * k + i, y * k + j) for i in range(k) for j in range(k))
    coarse = set()
    for z in range(GRID_ZOOM, DEM_OWNER_ZOOM + 1):
        k = 2 ** (z - GRID_ZOOM)
        coarse.update((z, x, y) for x in range(tile[0] * k, (tile[0] + 1) * k)
                      for y in range(tile[1] * k, (tile[1] + 1) * k) if (z, x, y) not in fine)
    return {t for t in fine if t[0] <= maxzoom}, coarse


def _per_cell(values: np.ndarray, k: int) -> np.ndarray:
    """values (rows and columns whole multiples of k) shaped (rows / k, k, cols / k, k): one entry per k by k cell."""
    return values.reshape(values.shape[0] // k, k, values.shape[1] // k, k)


def build_overview(bbox, sources: BlockSources, datum: AreaDatum, canada: shapely.Geometry | None,
                   nosurvey: shapely.Geometry, *, lake_mask: shapely.Geometry | None = None) -> BlockResult:
    """The overview's outputs over overview_bounds(bbox) on the global grid at OVERVIEW_RES_DEG (the read is snapped
    to it, so every cell is whole), from the coarse sources at their native 1 arc-second: per native cell the first
    source with data wins, as in build_block (NONNA-100 on the Canadian column `canada` only, then CRM, then ETOPO),
    each on its datum, less lake_mask. The read goes in strips of OVERVIEW_STRIP_DEG, so the memory stays at one
    strip over the whole plan 8 area. CUDEM and NONNA-10 add no detail at this cell size, so there is no fine output.

    coarse_grid is each overview cell's mean (the Fish grid: its features use OVERVIEW_BANDS, major levels only);
    coarse_source is the coarsest source among the cell's native cells. nav_depth, the Nav grid (plan 8 spec 7.1),
    is on the Canadian column only: the shallowest NONNA-100 value under the cell, else the shallowest value of the
    other sources (nav_src says which: the charts build draws CRM and ETOPO in the offshore area only), and nan on
    the cells whose center is in nosurvey (the stored no-survey masks)."""
    read = overview_bounds(bbox)
    w, s, e, n = read
    k = round(OVERVIEW_RES_DEG / COARSE_RES_DEG)
    rank = np.array([0] + [LABELS[name]["resolution_m"] for name in SOURCE_NAMES[1:]], np.int16)
    by_rank = np.zeros(rank.max() + 1, np.int8)
    by_rank[rank] = np.arange(len(rank))
    means, srcs, navs, nav_srcs = [], [], [], []
    transform = crs = None
    top = n
    while top > s + 1e-9:
        strip = (w, max(s, round(top - OVERVIEW_STRIP_DEG, 10)), e, top)
        top = strip[1]
        native = {}

        def window(path: Path, box=None, strip=strip) -> Grid:  # as in build_block, over the strip
            if path not in native:
                native[path] = read_window(str(path), strip if box is None else box)
            return native[path]

        crm = sources.crm_path if sources.crm_path is not None and clip_to_tile(sources.crm_path, strip) else None
        side = _side(canada, strip, COARSE_RES_DEG)
        layers = _coarse_layers(BlockSources([], crm, None, sources.nonna100, sources.etopo), strip,
                                COARSE_RES_DEG, side, window)
        grid, source = merge_ordered(layers, strip, COARSE_RES_DEG)
        del native
        _shift(grid, source, datum)
        _clip(grid, lake_mask)
        source[np.isnan(grid.data)] = 0
        mean, mean_transform = block_mean(grid.data, grid.transform, k)
        transform, crs = transform or mean_transform, grid.crs
        means.append(mean.astype(np.float32))
        srcs.append(by_rank[_per_cell(rank[source], k).max(axis=(1, 3))])
        on = np.isfinite(grid.data) & (side if side is not None else False)
        survey = _per_cell(np.where(on & (source == _INDEX["nonna100"]), grid.data, np.inf), k).min(axis=(1, 3))
        other = _per_cell(np.where(on, grid.data, np.inf), k).min(axis=(1, 3))
        coarsest = by_rank[_per_cell(np.where(on, rank[source], 0), k).max(axis=(1, 3))]
        nav = np.where(np.isfinite(survey), survey, other).astype(np.float32)
        nav_srcs.append(np.where(np.isfinite(survey), np.int8(_INDEX["nonna100"]),
                                 np.where(np.isfinite(other), coarsest, np.int8(0))).astype(np.int8))
        nav[np.isinf(nav)] = np.nan
        navs.append(nav)
        del grid, source, on, survey, other
    grid = Grid(np.vstack(means), float("nan"), transform, crs)
    src = np.vstack(srcs)
    nav = Grid(np.vstack(navs), float("nan"), transform, crs)
    nav_src = np.vstack(nav_srcs)
    if nosurvey is not None and not nosurvey.is_empty:
        hole = clip_mask(transform, nav.data.shape, mapping(nosurvey))
        nav.data[hole] = np.nan
        nav_src[hole] = 0
    side = _side(canada, read, OVERVIEW_RES_DEG)
    return BlockResult([], [], [], *_features(_with_lakes(grid, datum), read, OVERVIEW_BANDS, fine=False, src=src,
                                              side=side, labels=LABELS, canada=canada),
                       fine_grid=None, coarse_grid=grid, coarse_source=src, nav_depth=nav, nav_src=nav_src)
