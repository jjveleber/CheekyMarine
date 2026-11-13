"""Where neither NONNA grid has a value (plan 8 spec 7.1), read at a NONNA grid's native cells (EPSG:3857).

Also the NONNA readers the land polygons need: the water vote points and the wet cells. A region's NONNA-10 grid
can hold 4e8 cells, so each grid is read once into a float32 array (read_grids) that every step reuses, and no
step builds a Python object per cell.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from osgeo import gdal, gdal_array, ogr, osr
from shapely.geometry import MultiPolygon, box as make_box

gdal.UseExceptions()
ogr.UseExceptions()

_R = 6378137.0  # EPSG:3857 sphere
_NODATA = 3.4028234663852886e38  # Float32 max; compare with >= 3e38
_SIMPLIFY_CELLS = 0.45  # under half a cell, so no valid cell center ends up inside the mask
MAX_VOTE_POINTS = 2_000_000  # the water vote takes at most this many points (a regular sample)


@dataclass
class Grids:
    grid: tuple[float, float, float, float, float, float]  # (xmin, ymin, xmax, ymax, pixel x, pixel y), EPSG:3857
    values: np.ndarray  # float32 elevations on grid, nan where none: NONNA-10, else NONNA-100
    has100: np.ndarray  # bool: NONNA-100 has a value at the cell (nearest NONNA-100 cell)
    fine: bool  # values is NONNA-10


def _grid(path: Path, box) -> tuple[float, float, float, float, float, float]:
    """(xmin, ymin, xmax, ymax, pixel x, pixel y): the lon/lat box grown outward to the edges of path's cells."""
    x0, px, _, y0, _, py = gdal.Open(str(path)).GetGeoTransform()
    w, s, e, n = box
    x = [_R * math.radians(v) for v in (w, e)]
    y = [_R * math.log(math.tan(math.pi / 4 + math.radians(v) / 2)) for v in (s, n)]
    col0, col1 = math.floor((x[0] - x0) / px), math.ceil((x[1] - x0) / px)
    row0, row1 = math.floor((y[1] - y0) / py), math.ceil((y[0] - y0) / py)  # py < 0: row 0 is north
    return x0 + col0 * px, y0 + row1 * py, x0 + col1 * px, y0 + row0 * py, px, py


def _dataset(array: np.ndarray, grid):
    """A GDAL dataset over array's own memory (no copy), placed on grid."""
    xmin, _, _, ymax, px, py = grid
    ds = gdal_array.OpenArray(array)
    ds.SetGeoTransform((xmin, px, 0.0, ymax, 0.0, py))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())
    return ds


def _read(path: Path, grid) -> np.ndarray:
    """path's values on grid (nearest cell), float32, nan where it has none. Warped straight into the array."""
    xmin, ymin, xmax, ymax, px, py = grid
    data = np.full((round((ymin - ymax) / py), round((xmax - xmin) / px)), _NODATA, np.float32)
    ds = _dataset(data, grid)
    gdal.Warp(ds, str(path), resampleAlg="near", dstNodata=_NODATA, warpOptions=["INIT_DEST=NO_DATA"])
    ds = None
    data[data >= 3e38] = np.nan
    return data


def read_grids(nonna10: Path | None, nonna100: Path, box) -> Grids:
    """Both grids over box (W, S, E, N) on the NONNA-10 native grid (the NONNA-100 grid when nonna10 is None)."""
    grid = _grid(nonna10 or nonna100, box)
    values = _read(nonna100, grid)
    has100 = np.isnan(values)
    np.logical_not(has100, out=has100)
    if nonna10 is None:
        return Grids(grid, values, has100, False)
    del values  # before the NONNA-10 read, so only one float grid is held at a time
    return Grids(grid, _read(nonna10, grid), has100, True)


def _lonlat(x, y):
    return np.degrees(x / _R), np.degrees(2 * np.arctan(np.exp(y / _R)) - np.pi / 2)


def _axes(grid, rows: int, cols: int, step: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Lon of every step-th column center and lat of every step-th row center (1D)."""
    xmin, _, _, ymax, px, py = grid
    lon, _ = _lonlat(xmin + (np.arange(0, cols, step) + 0.5) * px, 0.0)
    _, lat = _lonlat(0.0, ymax + (np.arange(0, rows, step) + 0.5) * py)
    return lon, lat


def _polygons(cells: np.ndarray, grid, simplify: bool = False) -> shapely.Geometry:
    """The cells (a boolean array on grid) as lon/lat polygons, one geometry per run of joined cells."""
    _, _, _, _, px, py = grid
    src = _dataset(cells.view(np.uint8), grid)
    band = src.GetRasterBand(1)
    out = ogr.GetDriverByName("Memory").CreateDataSource("")
    layer = out.CreateLayer("cells")
    layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    gdal.Polygonize(band, band, layer, 0)
    parts = shapely.from_wkb([bytes(f.GetGeometryRef().ExportToWkb()) for f in layer])
    out = src = None
    # Each piece is one 4-connected run of cells, so no two share an edge (they meet at corners at most) and their
    # MultiPolygon is valid as it is. coverage_union_all returns the same pieces, in time that grows faster than
    # their count: 18 minutes for the 1.45 million wet runs of wa-coast, hours on haida-gwaii (2026-11-12). It is
    # kept where the result is simplified, since the simplification follows the rings as the union writes them
    # (another start and direction), and the no-value runs are fewer (9,385 on haida-gwaii, 24 s).
    merged = shapely.coverage_union_all(parts) if simplify else shapely.multipolygons(parts)
    if simplify:
        merged = merged.simplify(_SIMPLIFY_CELLS * min(px, abs(py)))
    return shapely.transform(merged, lambda xy: np.column_stack(_lonlat(xy[:, 0], xy[:, 1])))


def no_value(grids: Grids) -> np.ndarray:
    """bool: neither grid has a value at the cell."""
    return np.isnan(grids.values) & ~grids.has100


def mask_cells(empty: np.ndarray, grid, land: shapely.Geometry, box) -> MultiPolygon:
    """The empty cells (no_value) polygonized, simplified by under half a cell, cut to box, land removed."""
    holes = _polygons(empty, grid, simplify=True).intersection(make_box(*box)).difference(land)
    return MultiPolygon([p for p in shapely.get_parts(holes) if p.geom_type == "Polygon"])


def mask(nonna10: Path | None, nonna100: Path, land: shapely.Geometry, box) -> MultiPolygon:
    """Water in box (W, S, E, N) with no value in either grid: at the NONNA-10 native grid (the NONNA-100 grid when
    nonna10 is None), polygonized, simplified by under half a cell, cut to box, land removed."""
    grids = read_grids(nonna10, nonna100, box)
    return mask_cells(no_value(grids), grids.grid, land, box)


def missing_km2(grids: Grids, box) -> float:
    """Square kilometers of box where NONNA-10 has data and NONNA-100 has none (grids read with NONNA-10)."""
    rows, cols = grids.values.shape
    lon, lat = _axes(grids.grid, rows, cols)
    w, s, e, n = box
    in_cols = (lon >= w) & (lon <= e)
    in_rows = (lat >= s) & (lat <= n)
    per_row = np.zeros(rows)
    for r in np.nonzero(in_rows)[0]:  # one row at a time: no full-grid temporary
        per_row[r] = np.count_nonzero(~np.isnan(grids.values[r, in_cols]) & ~grids.has100[r, in_cols])
    _, _, _, _, px, py = grids.grid
    cell_m2 = px * abs(py) * np.cos(np.radians(lat)) ** 2  # Web Mercator cells shrink by cos(lat) each way
    return float((per_row * cell_m2).sum() / 1e6)


def missing_in_100(nonna10: Path, nonna100: Path, box) -> float:
    """Square kilometers of box where NONNA-10 has data and NONNA-100 has none, at the NONNA-10 grid."""
    return missing_km2(read_grids(nonna10, nonna100, box), box)


def water_points(grids: Grids, deeper_than_m: float) -> shapely.MultiPoint:
    """The lon/lat centers of the cells deeper than deeper_than_m (values are elevations: depth negative), taken on
    every k-th row and column, k the smallest stride that keeps at most MAX_VOTE_POINTS. The vote and the 1% guard
    of land_polygons are both shares of these points, so a regular sample keeps them."""
    deep = grids.values < -deeper_than_m  # nan compares False
    step = max(1, math.isqrt(int(np.count_nonzero(deep)) // MAX_VOTE_POINTS))
    while np.count_nonzero(deep[::step, ::step]) > MAX_VOTE_POINTS:
        step += 1
    sample = deep[::step, ::step]
    del deep
    lon, lat = _axes(grids.grid, *grids.values.shape, step)
    rows, cols = np.nonzero(sample)
    return shapely.MultiPoint(np.column_stack([lon[cols], lat[rows]]))


def wet_area(grids: Grids) -> shapely.Geometry:
    """The cells with a value at or below chart datum, as lon/lat polygons."""
    return _polygons(grids.values <= 0.0, grids.grid)
