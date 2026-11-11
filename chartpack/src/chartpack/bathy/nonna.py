"""CHS NONNA-10 and NONNA-100 depth grids from the CHS GeoServer WCS (plan 8).

Only the source-data fetch workflow calls the WCS (fetch_nonna, through a PoliteSession); pack builds read the
stored mosaic (read_nonna). Values recorded in plan 8 Task 1 (2026-11-11): native CRS EPSG:3857; the GML origin
is the center of cell (0, 0), so cell edges sit at origin - pixel / 2 + k * pixel and a subset snapped to those
edges comes back on the native grid; nodata is Float32 max; values are elevations above chart datum (depths
negative, drying heights positive); responses are uncompressed single-band Float32 GeoTIFFs.
"""

import math
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import numpy as np
from osgeo import gdal, ogr

from chartpack.bathy.cudem import Grid
from chartpack.cache import DownloadError

gdal.UseExceptions()
ogr.UseExceptions()

WCS_BASE = "https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs"
COVERAGE = {"nonna10": "nonna__NONNA 10 Coverage", "nonna100": "nonna__NONNA 100 Coverage"}
# Tile index shapefiles (EPSG:4326, tile name field OBJNAM), zipped with the shapefile at the root.
_INDEX_BASE = "https://api-proxy.edh-cde.dfo-mpo.gc.ca/catalogue/records/d3881c4c-650d-4070-bf9b-1e00aabf0a1d/attachments"
INDEX_URL = {"nonna10": f"{_INDEX_BASE}/NONNA10.zip", "nonna100": f"{_INDEX_BASE}/NONNA100.zip"}
# product: (origin x, origin y, pixel x, pixel y) from DescribeCoverage; origin = center of cell (0, 0)
GRID = {
    "nonna10": (-2.002636684067504e7, 2.0048994780289732e7, 19.098649920773468, -19.12019315728815),
    "nonna100": (-2.002629999514532e7, 2.004919554308374e7, 152.78970935710663, -152.96205582449275),
}
NODATA = 3.4028234663852886e38  # Float32 max; compare with >= 3e38, never equality
_EARTH_RADIUS = 6378137.0  # EPSG:3857 sphere


def _edges(product: str) -> tuple[float, float, float, float]:
    """(west edge x, north edge y, pixel x, pixel y) of native cell (0, 0)."""
    ox, oy, px, py = GRID[product]
    return ox - px / 2, oy - py / 2, px, py


def snap_box(product: str, bbox) -> tuple[float, float, float, float]:
    """The lon/lat box (W, S, E, N) in EPSG:3857 meters, grown outward to the product's native cell edges."""
    w, s, e, n = bbox
    x = [_EARTH_RADIUS * math.radians(lon) for lon in (w, e)]
    y = [_EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) for lat in (s, n)]
    x0, y0, px, py = _edges(product)
    col0, col1 = math.floor((x[0] - x0) / px), math.ceil((x[1] - x0) / px)
    row0, row1 = math.floor((y[1] - y0) / py), math.ceil((y[0] - y0) / py)  # py < 0: row 0 is north
    return (x0 + col0 * px, y0 + row1 * py, x0 + col1 * px, y0 + row0 * py)


def wcs_url(product: str, bbox_3857: tuple[float, float, float, float]) -> str:
    """WCS 2.0.1 GetCoverage of the product over bbox_3857 (xmin, ymin, xmax, ymax), native CRS and grid."""
    xmin, ymin, xmax, ymax = bbox_3857
    return (
        f"{WCS_BASE}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={quote(COVERAGE[product])}"
        f"&subset=X({xmin!r},{xmax!r})&subset=Y({ymin!r},{ymax!r})&format=image/tiff"
    )


def fetch_index(product: str, session, work: Path) -> Path:
    """The product's tile index shapefile, downloaded and unzipped under work."""
    dest = Path(work) / f"{product}-index"
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "index.zip"
    archive.write_bytes(session.get(INDEX_URL[product]))
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)
    (shp,) = sorted(dest.glob("*.shp"))
    return shp


def index_boxes(index_shp: Path, bbox) -> list[tuple[float, float, float, float]]:
    """Lon/lat boxes (W, S, E, N) of the index tiles whose interior meets bbox, sorted. A tile that only
    touches the box's edge is left out."""
    w, s, e, n = bbox
    ds = ogr.Open(str(index_shp))
    layer = ds.GetLayer(0)
    layer.SetSpatialFilterRect(w, s, e, n)
    boxes = set()
    for feature in layer:
        minx, maxx, miny, maxy = feature.GetGeometryRef().GetEnvelope()
        if minx < e and maxx > w and miny < n and maxy > s:
            boxes.add((minx, miny, maxx, maxy))
    return sorted(boxes)


def _on_grid(value: float, edge: float, pixel: float) -> bool:
    k = (value - edge) / pixel
    return abs(k - round(k)) < 1e-3


class _Unreadable(DownloadError):
    """A chunk body that is not a whole GeoTIFF (an XML error body, a cut file): worth asking once more."""


_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")  # TIFF and BigTIFF, both byte orders


def _check_chunk(product: str, path: Path, body: bytes, box, request) -> None:
    """Raise DownloadError naming the box unless path is one Float32 band in EPSG:3857 on the product's native
    grid covering exactly the snapped request (xmin, ymin, xmax, ymax). An unreadable body raises _Unreadable."""
    try:
        ds = gdal.Open(str(path))
        ds.GetRasterBand(1).ReadAsArray()  # a cut file keeps its header; only the strips fail
    except RuntimeError as e:
        if body[:4] in _TIFF_MAGIC:
            raise _Unreadable(f"{product} box {box}: the response is a damaged or truncated TIFF: {e}") from e
        snippet = " ".join(body[:1000].decode("utf-8", "replace").split())
        raise _Unreadable(f"{product} box {box}: the response is not a GeoTIFF: {snippet}") from e
    if ds.RasterCount != 1 or ds.GetRasterBand(1).DataType != gdal.GDT_Float32:
        raise DownloadError(f"{product} box {box}: expected one Float32 band")
    srs = ds.GetSpatialRef()
    if srs is None or (srs.GetAuthorityName(None), srs.GetAuthorityCode(None)) != ("EPSG", "3857"):
        raise DownloadError(f"{product} box {box}: the response is not in EPSG:3857")
    gx0, gpx, _, gy0, _, gpy = ds.GetGeoTransform()
    x0, y0, px, py = _edges(product)
    if not (math.isclose(gpx, px, rel_tol=1e-9) and math.isclose(gpy, py, rel_tol=1e-9)
            and _on_grid(gx0, x0, px) and _on_grid(gy0, y0, py)):
        raise DownloadError(f"{product} box {box}: the response is not on the native grid: {(gx0, gpx, gy0, gpy)}")
    xmin, ymin, xmax, ymax = request
    cols, rows = round((xmax - xmin) / px), round((ymin - ymax) / py)
    if (round((gx0 - xmin) / px), round((gy0 - ymax) / py), ds.RasterXSize, ds.RasterYSize) != (0, 0, cols, rows):
        raise DownloadError(f"{product} box {box}: the response does not cover the requested box {request}: origin "
                            f"{(gx0, gy0)}, {ds.RasterXSize} by {ds.RasterYSize} cells, asked {cols} by {rows}")


def fetch_nonna(product: str, boxes: list[tuple], out: Path, session) -> dict:
    """One WCS request per lon/lat box (snapped to native cell edges), each checked, mosaicked into one tiled,
    DEFLATE-compressed GeoTIFF at out on the native grid. Nothing is written at out unless every chunk passes.

    A chunk whose body is not a whole GeoTIFF (an XML error body, a cut file) is asked for once more after the
    session's back-off, without the session's own retry, so one url is asked for at most three times; a readable
    chunk that is wrong (grid, CRS, extent) cannot get better and fails at once. Either failure names the box."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=f".{out.name}.") as tmp:
        chunks = []
        for i, box in enumerate(boxes):
            path = Path(tmp) / f"chunk-{i:05d}.tif"
            request = snap_box(product, box)
            url = wcs_url(product, request)
            body = session.get(url)
            path.write_bytes(body)
            try:
                _check_chunk(product, path, body, box, request)
            except _Unreadable:
                session.backoff()
                body = session.get(url, retry=False)
                path.write_bytes(body)
                _check_chunk(product, path, body, box, request)
            chunks.append(str(path))
        if not chunks:
            raise DownloadError(f"{product}: no index tile meets the fetch extent")
        part = out.with_name(out.name + ".part")
        try:
            vrt_path = Path(tmp) / "mosaic.vrt"
            vrt = gdal.BuildVRT(str(vrt_path), chunks)
            try:
                used = [f for f in vrt.GetFileList() if Path(f) != vrt_path]
                if len(used) != len(chunks):  # BuildVRT skips a source it cannot place, with a warning only
                    raise DownloadError(f"{product}: the mosaic holds {len(used)} of {len(chunks)} chunks")
                gdal.Translate(str(part), vrt, format="GTiff",
                               creationOptions=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
            finally:
                vrt = None  # closed while the temporary directory still exists
            part.rename(out)
        finally:
            part.unlink(missing_ok=True)  # no-op after a successful rename
    return {"chunks": len(used), "bytes": out.stat().st_size, "seconds": round(time.monotonic() - start, 3)}


def read_nonna(path: Path, bbox, res_deg: float) -> Grid:
    """The mosaic over bbox (W, S, E, N) in EPSG:4326 at res_deg, nearest neighbor so each cell keeps a native
    value: depth in meters, positive down (a drying height reads negative), nan where the grid has no data."""
    w, s, e, n = bbox
    ds = gdal.Warp("", str(path), format="MEM", dstSRS="EPSG:4326", outputBounds=(w, s, e, n),
                   xRes=res_deg, yRes=res_deg, resampleAlg="near", dstNodata=NODATA)
    data = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    data[data >= 3e38] = np.nan
    return Grid(data=-data, nodata=float("nan"), transform=tuple(ds.GetGeoTransform()), crs=ds.GetProjection())
