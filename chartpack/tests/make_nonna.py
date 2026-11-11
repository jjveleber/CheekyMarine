"""Synthetic NONNA WCS responses for the fetch tests; writes tests/fixtures/nonna/chunk-a.tif and chunk-b.tif.

The WCS answers a GetCoverage with an uncompressed single-band Float32 GeoTIFF in EPSG:3857 on the coverage's
native grid (plan 8 Task 1). The grid numbers below are the DescribeCoverage values recorded there, kept here
apart from chartpack.bathy.nonna so the tests check the code against them. The GML origin is the center of
cell (0, 0), so cell edges sit at origin - pixel / 2 + k * pixel.

chunk-a.tif and chunk-b.tif: 64 by 64 NONNA-10 cells near the head of Toba Inlet. Chunk b starts 62 columns east
and 10 rows south of chunk a, so they share 2 columns by 54 rows, with equal values there, as two outward-snapped
neighbor boxes do. Cell (c, r), counted from chunk a's north-west cell: -(1 + c + r / 100) meters (below chart
datum), +0.3048 * (c % 4) on row 0 (drying heights), NODATA where (c + r) % 7 == 0.

error.xml is the WCS exception body of a bad GetCoverage request, as recorded in Task 1.
"""

import io
import math
import zipfile
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

NODATA = 3.4028234663852886e38
# product: (origin x, origin y, pixel x, pixel y), origin = center of cell (0, 0), EPSG:3857 meters
GRID = {
    "nonna10": (-2.002636684067504e7, 2.0048994780289732e7, 19.098649920773468, -19.12019315728815),
    "nonna100": (-2.002629999514532e7, 2.004919554308374e7, 152.78970935710663, -152.96205582449275),
}
SIZE = 64
# Chunk a's north-west cell: the native cell whose west edge is the X subset start Task 1 sent for the
# NONNA-10 box -124.40, 50.40, -124.30, 50.50, and whose north edge is that request's Y subset end.
A_COL = round((-13848154.127129 - (GRID["nonna10"][0] - GRID["nonna10"][2] / 2)) / GRID["nonna10"][2])
A_ROW = round((6533322.201362 - (GRID["nonna10"][1] - GRID["nonna10"][3] / 2)) / GRID["nonna10"][3])
B_OFFSET = (62, 10)  # columns east, rows south of chunk a


def edge_transform(product: str, col: int, row: int) -> tuple[float, ...]:
    """GDAL geotransform of a raster whose north-west cell is native cell (col, row)."""
    ox, oy, px, py = GRID[product]
    return (ox - px / 2 + col * px, px, 0.0, oy - py / 2 + row * py, 0.0, py)


def write_nonna(path: Path, data: np.ndarray, product: str = "nonna10", col: int = A_COL, row: int = A_ROW) -> Path:
    """An uncompressed Float32 GeoTIFF of data (row 0 north) on the product's native grid, as the WCS sends."""
    rows, cols = data.shape
    ds = gdal.GetDriverByName("GTiff").Create(str(path), cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform(edge_transform(product, col, row))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    band.WriteArray(data.astype(np.float32))
    ds = None
    return Path(path)


def lonlat_box(product: str, col: int, row: int, cols: int, rows: int, inset: float = 1e-7):
    """The lon/lat box (W, S, E, N) of native cells col..col+cols-1, row..row+rows-1, shrunk by inset degrees on
    each side, so snapping it outward to cell edges gives back exactly those cells."""
    x0, px, _, y0, _, py = edge_transform(product, col, row)
    lon = [math.degrees(x / 6378137.0) for x in (x0, x0 + cols * px)]
    lat = [math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2) for y in (y0 + rows * py, y0)]
    return (lon[0] + inset, lat[0] + inset, lon[1] - inset, lat[1] - inset)


def write_request_chunk(path: Path, product: str, bbox_3857, value: float = -5.0) -> Path:
    """What the WCS answers for a subset snapped to native cell edges: a chunk covering exactly bbox_3857."""
    xmin, ymin, xmax, ymax = bbox_3857
    ex, ey = edge_transform(product, 0, 0)[0], edge_transform(product, 0, 0)[3]
    _, _, px, py = GRID[product]
    col, row = round((xmin - ex) / px), round((ymax - ey) / py)
    cols, rows = round((xmax - xmin) / px), round((ymin - ymax) / py)
    return write_nonna(path, np.full((rows, cols), value, np.float32), product, col, row)


def toba_values(rows: int, cols: int) -> np.ndarray:
    """The synthetic depths of the module docstring over cells (0..cols-1, 0..rows-1) from chunk a's corner."""
    r, c = np.mgrid[0:rows, 0:cols]
    v = -(1.0 + c + r / 100.0)
    v[0, :] = 0.3048 * (c[0, :] % 4)
    v[(c + r) % 7 == 0] = NODATA
    return v.astype(np.float32)


def chunk_box(which: str):
    """The lon/lat box whose WCS request chunk a (or b) answers."""
    dc, dr = (0, 0) if which == "a" else B_OFFSET
    return lonlat_box("nonna10", A_COL + dc, A_ROW + dr, SIZE, SIZE)


def chunk_values(which: str) -> np.ndarray:
    dc, dr = (0, 0) if which == "a" else B_OFFSET
    return toba_values(dr + SIZE, dc + SIZE)[dr:, dc:]


def write_index(path: Path, boxes: list[tuple[str, tuple[float, float, float, float]]]) -> Path:
    """A NONNA index shapefile (EPSG:4326, field OBJNAM) with one rectangle per (name, (W, S, E, N))."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(path))
    layer = ds.CreateLayer(Path(path).stem, srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("OBJNAM", ogr.OFTString))
    for name, (w, s, e, n) in boxes:
        f = ogr.Feature(layer.GetLayerDefn())
        f.SetField("OBJNAM", name)
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON(({w} {s},{w} {n},{e} {n},{e} {s},{w} {s}))"))
        layer.CreateFeature(f)
    ds = None
    return Path(path)


def index_zip(work: Path, name: str, boxes) -> bytes:
    """The bytes of a zip holding the index shapefile name.shp and its side files at the root, as DFO serves it."""
    shp = write_index(Path(work) / f"{name}.shp", boxes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for part in sorted(shp.parent.glob(f"{name}.*")):
            zf.write(part, part.name)
    return buf.getvalue()


if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures" / "nonna"
    write_nonna(out / "chunk-a.tif", chunk_values("a"))
    write_nonna(out / "chunk-b.tif", chunk_values("b"), col=A_COL + B_OFFSET[0], row=A_ROW + B_OFFSET[1])
