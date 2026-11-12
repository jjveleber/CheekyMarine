"""Where neither NONNA grid has a value (plan 8 spec 7.1), read at a NONNA grid's native cells (EPSG:3857).

Also the NONNA readers the land polygons need: the water vote points and the wet cells.
"""

import math
from pathlib import Path

import numpy as np
import shapely
from osgeo import gdal, ogr
from shapely.geometry import MultiPolygon, box as make_box

gdal.UseExceptions()
ogr.UseExceptions()

_R = 6378137.0  # EPSG:3857 sphere
_NODATA = 3.4028234663852886e38  # Float32 max; compare with >= 3e38
_SIMPLIFY_CELLS = 0.45  # under half a cell, so no valid cell center ends up inside the mask


def _grid(path: Path, box) -> tuple[float, float, float, float, float, float]:
    """(xmin, ymin, xmax, ymax, pixel x, pixel y): the lon/lat box grown outward to the edges of path's cells."""
    x0, px, _, y0, _, py = gdal.Open(str(path)).GetGeoTransform()
    w, s, e, n = box
    x = [_R * math.radians(v) for v in (w, e)]
    y = [_R * math.log(math.tan(math.pi / 4 + math.radians(v) / 2)) for v in (s, n)]
    col0, col1 = math.floor((x[0] - x0) / px), math.ceil((x[1] - x0) / px)
    row0, row1 = math.floor((y[1] - y0) / py), math.ceil((y[0] - y0) / py)  # py < 0: row 0 is north
    return x0 + col0 * px, y0 + row1 * py, x0 + col1 * px, y0 + row0 * py, px, py


def _read(path: Path, grid) -> np.ndarray:
    """path's values on grid (nearest cell), nan where it has none."""
    xmin, ymin, xmax, ymax, px, py = grid
    ds = gdal.Warp("", str(path), format="MEM", dstSRS="EPSG:3857", outputBounds=(xmin, ymin, xmax, ymax),
                   xRes=px, yRes=abs(py), resampleAlg="near", dstNodata=_NODATA)
    data = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    data[data >= 3e38] = np.nan
    return data


def _lonlat(x, y):
    return np.degrees(x / _R), np.degrees(2 * np.arctan(np.exp(y / _R)) - np.pi / 2)


def _centers(grid, shape) -> tuple[np.ndarray, np.ndarray]:
    """Lon and lat of every cell center, as two 2D arrays."""
    xmin, _, _, ymax, px, py = grid
    lon, _ = _lonlat(xmin + (np.arange(shape[1]) + 0.5) * px, 0.0)
    _, lat = _lonlat(0.0, ymax + (np.arange(shape[0]) + 0.5) * py)
    return np.broadcast_arrays(lon[None, :], lat[:, None])


def _polygons(cells: np.ndarray, grid, simplify: bool = False) -> shapely.Geometry:
    """The cells (a boolean array on grid) as lon/lat polygons."""
    xmin, _, _, ymax, px, py = grid
    src = gdal.GetDriverByName("MEM").Create("", cells.shape[1], cells.shape[0], 1, gdal.GDT_Byte)
    src.SetGeoTransform((xmin, px, 0.0, ymax, 0.0, py))
    band = src.GetRasterBand(1)
    band.WriteArray(cells.astype(np.uint8))
    out = ogr.GetDriverByName("Memory").CreateDataSource("")
    layer = out.CreateLayer("cells")
    layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    gdal.Polygonize(band, band, layer, 0)
    parts = [shapely.from_wkb(bytes(f.GetGeometryRef().ExportToWkb())) for f in layer]
    merged = shapely.union_all(parts)
    if simplify:
        merged = merged.simplify(_SIMPLIFY_CELLS * min(px, abs(py)))
    return shapely.transform(merged, lambda xy: np.column_stack(_lonlat(xy[:, 0], xy[:, 1])))


def mask(nonna10: Path | None, nonna100: Path, land: shapely.Geometry, box) -> MultiPolygon:
    """Water in box (W, S, E, N) with no value in either grid: at the NONNA-10 native grid (the NONNA-100 grid when
    nonna10 is None), polygonized, simplified by under half a cell, cut to box, land removed."""
    grid = _grid(nonna10 or nonna100, box)
    empty = np.isnan(_read(nonna100, grid))
    if nonna10 is not None:
        empty &= np.isnan(_read(nonna10, grid))
    holes = _polygons(empty, grid, simplify=True).intersection(make_box(*box)).difference(land)
    return MultiPolygon([p for p in shapely.get_parts(holes) if p.geom_type == "Polygon"])


def missing_in_100(nonna10: Path, nonna100: Path, box) -> float:
    """Square kilometers of box where NONNA-10 has data and NONNA-100 has none, at the NONNA-10 grid."""
    grid = _grid(nonna10, box)
    missing = ~np.isnan(_read(nonna10, grid)) & np.isnan(_read(nonna100, grid))
    lon, lat = _centers(grid, missing.shape)
    w, s, e, n = box
    missing &= (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    _, _, _, _, px, py = grid
    cell_m2 = px * abs(py) * np.cos(np.radians(lat)) ** 2  # Web Mercator cells shrink by cos(lat) each way
    return float((cell_m2 * missing).sum() / 1e6)


def water_points(path: Path, box, deeper_than_m: float) -> shapely.MultiPoint:
    """The lon/lat centers of path's cells in box deeper than deeper_than_m (values are elevations: depth negative)."""
    grid = _grid(path, box)
    data = _read(path, grid)
    deep = data < -deeper_than_m  # nan compares False
    lon, lat = _centers(grid, data.shape)
    return shapely.MultiPoint(np.column_stack([lon[deep], lat[deep]]))


def wet_area(path: Path, box) -> shapely.Geometry:
    """path's cells in box with a value at or below chart datum, as lon/lat polygons."""
    grid = _grid(path, box)
    return _polygons(_read(path, grid) <= 0.0, grid)
