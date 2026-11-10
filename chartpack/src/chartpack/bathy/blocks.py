"""Fine and coarse bathy built block by block, one block per owned zoom-10 tile (plan 7).

Fine is CUDEM at 1/9 arc-second; coarse is CRM at 1 arc-second on every coarse cell with no CUDEM
value. Each block is read over its tile plus a margin and its features are clipped to the tile, so
memory stays at one tile (about 11k by 8k fine cells, under 3 GB) and lines meet across tile edges:
every grid sits on multiples of its own cell size from (-180, 90), so two blocks (or two packs) see
the same cells along their shared edge.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import box, mapping, shape

from chartpack.bathy.bands import bands_by_zoom
from chartpack.bathy.contours import BANDS, COARSE_BANDS, OVERVIEW_BANDS, block_mean, contours_by_zoom
from chartpack.bathy.cudem import CudemTile, Grid, read_window, tiles_for_bbox
from chartpack.bathy.merge import clip_mask, coverage_polygons, fill_land, merge_to_mllw
from chartpack.datum import SOURCE_VERTICAL, geoid, node_axes, resample
from chartpack.datum.offsets import load_datum, navd88_to_mllw_nodes
from chartpack.grid import GRID_ZOOM, tile_bounds
from chartpack.region import Region

FINE_RES_DEG = 1 / 32400  # CUDEM, 1/9 arc-second
COARSE_RES_DEG = 1 / 3600  # CRM, 1 arc-second
OVERVIEW_RES_DEG = 0.0025  # the overview block-means native CRM to this (9 by 9 arc-second cells)
BLOCK_MARGIN_DEG = 0.02  # each block is read this far past its tile
CRM_LABEL = {"source": "crm", "resolution_m": 30, "date": "2025"}


@dataclass
class BlockResult:
    """GeoJSON Features clipped to the block's core, and the depth grids (land kept) for the DEMs: depth by the
    station path, without the lake rule the features use (AreaDatum).

    fine_grid is the whole CUDEM-over-CRM merge so the fine DEM has no false cliff at the CUDEM edge;
    fine_cudem marks its CUDEM cells, the only ones the fine features and the fine DEM's skip_empty use.
    """

    fine_contours: list[dict]
    fine_bands: list[dict]
    fine_coverage: list[dict]
    coarse_contours: list[dict]
    coarse_bands: list[dict]
    coarse_coverage: list[dict]
    fine_grid: Grid | None  # None for the overview and for a block no CUDEM tile meets: no fine output
    coarse_grid: Grid
    fine_cudem: np.ndarray | None = None  # bool, the fine grid's shape


class AreaDatum:
    """The region's datum file as a callable: datum(source, transform, shape) is the offset in meters to subtract
    from -elevation for MLLW depth. It is the NAVD88 to MLLW offset per area for every source, plus the EGM2008
    to NAVD88 height change for EGM2008 sources (CRM), from the geoid grids fetch-bathy put in cache. Both are
    summed at the global grid nodes and resampled once (bilinear is linear), so a call allocates one
    block-size array.

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


def _coverage(valid: np.ndarray, transform, core, label: dict) -> list[dict]:
    feats = coverage_polygons(valid.astype(np.uint8), transform, {1: label})
    if core is None:
        return feats
    out = []
    for f in feats:
        geom = shape(f["geometry"]).intersection(box(*core))
        if not geom.is_empty and geom.geom_type in ("Polygon", "MultiPolygon"):
            out.append({**f, "geometry": mapping(geom)})
    return out


def _features(
    grid: Grid, core, bands, *, fine: bool, label: dict, cells: np.ndarray | None = None, overzoomed: bool = False
) -> tuple[list[dict], list[dict], list[dict]]:
    """Contours (tagged with the label's source), bands and coverage of one depth grid, clipped to core.
    `cells` (bool) limits them to those cells; by default every finite cell counts. overzoomed: see
    contours_by_zoom."""
    valid = np.isfinite(grid.data) if cells is None else cells
    filled = fill_land(grid.data)  # the grid itself keeps the real land heights for the hillshade
    filled[~valid] = np.nan
    contours = contours_by_zoom(filled, grid.transform, fine=fine, bands=bands, core=core, overzoomed=overzoomed)
    for f in contours:
        f["properties"]["source"] = label["source"]
    polygons = bands_by_zoom(filled, grid.transform, bands=bands, core=core)
    del filled
    return contours, polygons, _coverage(valid, grid.transform, core, label)


def build_block(
    core, read, cudem_tiles: Sequence[CudemTile], crm_path, datum: AreaDatum, clip: shapely.Geometry | None
) -> BlockResult:
    """Fine and coarse outputs of one block: features clipped to core, grids over read.

    Fine is the CUDEM-then-CRM merge; its features use the CUDEM cells (source index 1) only, its DEM the
    whole merge. Coarse is CRM on every coarse cell unless every fine cell in it holds CUDEM, decided per
    cell, so coarse overlaps fine by under one coarse cell instead of leaving a gap (the style draws coarse
    under fine). Cells inside clip are nan in both grids before anything is drawn. A block that no CUDEM
    tile meets skips the fine merge: its fine outputs are empty and fine_grid is None. The grids (the DEMs)
    are depth by the station path; the features add the lake rule (_with_lakes).
    """
    has_cudem = bool(tiles_for_bbox(list(cudem_tiles), read))
    meeting = cudem_tiles if has_cudem else []
    primary = [(read_window("/vsicurl/" + t.url, _overlap(t.bounds, read)), t.name) for t in meeting]
    crm = read_window(str(crm_path), read)
    fine = source = cudem = None
    if has_cudem:
        fine, source = merge_to_mllw(primary, crm, 0.0, 0.0, read, res_deg=FINE_RES_DEG)
        del primary
        for index, name in ((1, "cudem"), (2, "crm")):
            take = source == index
            fine.data[take] -= datum(name, fine.transform, fine.data.shape, lakes=False)[take]
            del take

    coarse, _ = merge_to_mllw([], crm, 0.0, 0.0, read, res_deg=COARSE_RES_DEG)
    del crm
    coarse.data -= datum("crm", coarse.transform, coarse.data.shape, lakes=False)
    _clip(coarse, clip)
    fine_out = ([], [], [])
    if fine is not None:
        k = round(COARSE_RES_DEG / FINE_RES_DEG)
        rows, cols = coarse.data.shape
        coarse.data[(source == 1).reshape(rows, k, cols, k).all(axis=(1, 3))] = np.nan
        _clip(fine, clip)
        cudem = (source == 1) & np.isfinite(fine.data)
        del source
        years = ",".join(sorted({str(t.year) for t in tiles_for_bbox(list(cudem_tiles), core)}))
        cudem_label = {"source": "cudem", "resolution_m": 3, "date": years}
        fine_out = _features(_with_lakes(fine, datum), core, BANDS, fine=True, label=cudem_label, cells=cudem)
    coarse_out = _features(_with_lakes(coarse, datum), core, COARSE_BANDS, fine=False, label=CRM_LABEL,
                           overzoomed=True)
    return BlockResult(*fine_out, *coarse_out, fine_grid=fine, coarse_grid=coarse, fine_cudem=cudem)


def build_overview(bbox, crm_path, datum: AreaDatum, clip: shapely.Geometry | None) -> BlockResult:
    """The overview's coarse outputs from one native CRM read over overview_bounds(bbox), block-meaned to
    OVERVIEW_RES_DEG on the global grid (the read is snapped to it, so every block is whole), with
    OVERVIEW_BANDS (major levels only). CUDEM adds no detail at 300 m cells, so there is no fine output."""
    read = overview_bounds(bbox)
    native, _ = merge_to_mllw([], read_window(str(crm_path), read), 0.0, 0.0, read, res_deg=COARSE_RES_DEG)
    mean, transform = block_mean(native.data, native.transform, round(OVERVIEW_RES_DEG / COARSE_RES_DEG))
    grid = Grid(mean.astype(np.float32), float("nan"), transform, native.crs)
    del native
    del mean
    grid.data -= datum("crm", grid.transform, grid.data.shape, lakes=False)
    _clip(grid, clip)
    return BlockResult([], [], [], *_features(_with_lakes(grid, datum), None, OVERVIEW_BANDS, fine=False,
                                              label=CRM_LABEL),
                       fine_grid=None, coarse_grid=grid)
