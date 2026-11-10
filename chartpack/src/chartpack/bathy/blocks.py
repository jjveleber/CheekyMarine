"""Fine and coarse bathy built block by block, one block per owned zoom-10 tile (plan 7).

Fine is CUDEM at 1/9 arc-second; coarse is CRM at 1 arc-second on every coarse cell with no CUDEM
value. Each block is read over its tile plus a margin and its features are clipped to the tile, so
memory stays at one tile (about 11k by 8k fine cells, under 3 GB) and lines meet across tile edges:
every grid sits on multiples of its own cell size from (-180, 90), so two blocks (or two packs) see
the same cells along their shared edge.
"""

import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import box, mapping, shape

from chartpack.bathy.bands import bands_by_zoom
from chartpack.bathy.contours import BANDS, COARSE_BANDS, OVERVIEW_BANDS, contours_by_zoom
from chartpack.bathy.cudem import CudemTile, Grid, read_window, tiles_for_bbox
from chartpack.bathy.merge import clip_mask, coverage_polygons, fill_land, merge_to_mllw
from chartpack.datum import SOURCE_VERTICAL, geoid, node_axes, resample
from chartpack.datum.offsets import load_datum, navd88_to_mllw_nodes
from chartpack.grid import GRID_ZOOM, tile_bounds
from chartpack.region import Region

FINE_RES_DEG = 1 / 32400  # CUDEM, 1/9 arc-second
COARSE_RES_DEG = 1 / 3600  # CRM, 1 arc-second
OVERVIEW_RES_DEG = 0.0025  # the overview reads CRM resampled to this by the server
BLOCK_MARGIN_DEG = 0.02  # each block is read this far past its tile
CRM_LABEL = {"source": "crm", "resolution_m": 30, "date": "2025"}

# (source name, geotransform, grid shape) -> offset in meters to subtract from -elevation for MLLW depth
DatumFn = Callable[[str, tuple, tuple[int, int]], np.ndarray]


@dataclass
class BlockResult:
    """GeoJSON Features clipped to the block's core, and the depth grids (land kept) for the DEMs.

    fine_grid is the whole CUDEM-over-CRM merge so the fine DEM has no false cliff at the CUDEM edge;
    fine_cudem marks its CUDEM cells, the only ones the fine features and the fine DEM's skip_empty use.
    """

    fine_contours: list[dict]
    fine_bands: list[dict]
    fine_coverage: list[dict]
    coarse_contours: list[dict]
    coarse_bands: list[dict]
    coarse_coverage: list[dict]
    fine_grid: Grid | None  # None for the overview, which has no fine output
    coarse_grid: Grid
    fine_cudem: np.ndarray | None = None  # bool, the fine grid's shape


def area_datum(region: Region, cache: Path) -> DatumFn:
    """The region's datum file as a DatumFn: the NAVD88 to MLLW offset per area for every source, plus the
    EGM2008 to NAVD88 height change for EGM2008 sources (CRM), from the geoid grids fetch-bathy put in cache.
    Both are summed at the global grid nodes and resampled once (bilinear is linear), so a call allocates one
    block-size array."""
    stations = load_datum(region.datum_file).stations

    def datum(source: str, transform, shape: tuple[int, int]) -> np.ndarray:
        lons, lats = node_axes(transform, shape)
        nodes = navd88_to_mllw_nodes(stations, lons, lats)
        if SOURCE_VERTICAL[source] == "egm2008":  # NAVD88 height = EGM2008 height + the change
            nodes += geoid.egm2008_to_navd88_nodes(lons, lats, cache)
        return resample(nodes, lons, lats, transform, shape)

    return datum


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
    grid: Grid, core, bands, *, fine: bool, label: dict, cells: np.ndarray | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    """Contours (tagged with the label's source), bands and coverage of one depth grid, clipped to core.
    `cells` (bool) limits them to those cells; by default every finite cell counts."""
    valid = np.isfinite(grid.data) if cells is None else cells
    filled = fill_land(grid.data)  # the grid itself keeps the real land heights for the hillshade
    filled[~valid] = np.nan
    contours = contours_by_zoom(filled, grid.transform, fine=fine, bands=bands, core=core)
    for f in contours:
        f["properties"]["source"] = label["source"]
    polygons = bands_by_zoom(filled, grid.transform, bands=bands, core=core)
    del filled
    return contours, polygons, _coverage(valid, grid.transform, core, label)


def build_block(
    core, read, cudem_tiles: Sequence[CudemTile], crm_path, datum: DatumFn, clip: shapely.Geometry | None
) -> BlockResult:
    """Fine and coarse outputs of one block: features clipped to core, grids over read.

    Fine is the CUDEM-then-CRM merge; its features use the CUDEM cells (source index 1) only, its DEM the
    whole merge. Coarse is CRM on every coarse cell unless every fine cell in it holds CUDEM, decided per
    cell, so coarse overlaps fine by under one coarse cell instead of leaving a gap (the style draws coarse
    under fine). Cells inside clip are nan in both grids before anything is drawn.
    """
    primary = [(read_window("/vsicurl/" + t.url, _overlap(t.bounds, read)), t.name) for t in cudem_tiles]
    crm = read_window(str(crm_path), read)
    fine, source = merge_to_mllw(primary, crm, 0.0, 0.0, read, res_deg=FINE_RES_DEG)
    del primary
    for index, name in ((1, "cudem"), (2, "crm")):
        take = source == index
        fine.data[take] -= datum(name, fine.transform, fine.data.shape)[take]
        del take

    coarse, _ = merge_to_mllw([], crm, 0.0, 0.0, read, res_deg=COARSE_RES_DEG)
    del crm
    coarse.data -= datum("crm", coarse.transform, coarse.data.shape)
    k = round(COARSE_RES_DEG / FINE_RES_DEG)
    rows, cols = coarse.data.shape
    coarse.data[(source == 1).reshape(rows, k, cols, k).all(axis=(1, 3))] = np.nan
    _clip(fine, clip)
    _clip(coarse, clip)
    cudem = (source == 1) & np.isfinite(fine.data)
    del source

    years = ",".join(sorted({str(t.year) for t in tiles_for_bbox(list(cudem_tiles), core)}))
    cudem_label = {"source": "cudem", "resolution_m": 3, "date": years}
    fine_out = _features(fine, core, BANDS, fine=True, label=cudem_label, cells=cudem)
    coarse_out = _features(coarse, core, COARSE_BANDS, fine=False, label=CRM_LABEL)
    return BlockResult(*fine_out, *coarse_out, fine_grid=fine, coarse_grid=coarse, fine_cudem=cudem)


def build_overview(bbox, crm_path, datum: DatumFn, clip: shapely.Geometry | None) -> BlockResult:
    """The overview's coarse outputs from one CRM read over overview_bounds(bbox) at OVERVIEW_RES_DEG, with
    OVERVIEW_BANDS (major levels only). CUDEM adds no detail at 300 m cells, so there is no fine output."""
    read = overview_bounds(bbox)
    grid, _ = merge_to_mllw([], read_window(str(crm_path), read), 0.0, 0.0, read, res_deg=OVERVIEW_RES_DEG)
    grid.data -= datum("crm", grid.transform, grid.data.shape)
    _clip(grid, clip)
    return BlockResult([], [], [], *_features(grid, None, OVERVIEW_BANDS, fine=False, label=CRM_LABEL),
                       fine_grid=None, coarse_grid=grid)
