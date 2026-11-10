"""NOAA Coastal Relief Model (CUDEM volume 8) subset through the THREDDS WCS service.

The nc2geotiff writer sets the GeoTIFF NoData tag to the data minimum minus 1 of each
request, so the tag differs per request and no real cell equals it. Read the NoData value
from the file as GDAL reports it; never hard-code one.
"""

import math
from pathlib import Path

from osgeo import gdal

from chartpack.cache import DownloadError, download

gdal.UseExceptions()

WCS_BASE = "https://www.ngdc.noaa.gov/thredds/wcs/crm/cudem/crm_vol8_2025.nc"
CRM_BOUNDS = (-127.0, 44.0, -121.75, 49.0)  # W, S, E, N that volume 8 fills (spec 7)


def crm_wcs_url(bbox) -> str:
    """GetCoverage url for coverage z as Float32 GeoTIFF over bbox (W, S, E, N) in OGC:CRS84.

    The coverage comes at its native 1 arc-second. The server ignores WCS width and height (checked
    2026-11-10: a 40 by 40 request over 0.1 degree returns 361 by 361 cells), so none is sent.
    """
    w, s, e, n = bbox
    return (
        f"{WCS_BASE}?service=WCS&version=1.0.0&request=GetCoverage&coverage=z"
        f"&crs=OGC:CRS84&bbox={w},{s},{e},{n}&format=GeoTIFF_Float"
    )


def crm_tile_requests(margin_deg: float) -> str:
    """What a region build requests from CRM: one GetCoverage per owned zoom-10 tile, the url template."""
    url = crm_wcs_url(("W", "S", "E", "N"))
    return (f"{url} (one request per owned zoom-10 tile: W, S, E, N are the tile bounds plus {margin_deg} degree,"
            " snapped outward to 1 arc-second, cut to CRM's coverage)")


def crm_request(bbox) -> tuple[float, float, float, float] | None:
    """What is asked of the WCS for bbox: its overlap with CRM_BOUNDS, or None when bbox is wholly outside.
    Past the coverage the WCS answers with a file that does not cover the request (checked 2026-11-09), so
    nothing past it is asked for; a read of the whole bbox gets nan there."""
    w, s, e, n = bbox
    cw, cs, ce, cn = CRM_BOUNDS
    w, s, e, n = max(w, cw), max(s, cs), min(e, ce), min(n, cn)
    return (w, s, e, n) if w < e and s < n else None


def crm_path(bbox, cache_dir: Path) -> Path | None:
    """Where fetch_crm caches the request for bbox; None when bbox is wholly outside CRM."""
    request = crm_request(bbox)
    if request is None:
        return None
    w, s, e, n = request
    return Path(cache_dir) / "crm" / f"crm_{w}_{s}_{e}_{n}.tif"


def _fix_west_edge(path: Path) -> None:
    """At CRM's west edge the WCS labels longitude from 0 to 360 and its first column, the node on CRM's west
    edge, holds junk heights (checked 2026-11-09 at -127 W). Move such a file to -180 to 180 and set every column
    whose center is at or west of the edge to nodata."""
    ds = gdal.Open(str(path), gdal.GA_Update)
    x0, dx, rx, y0, ry, dy = ds.GetGeoTransform()
    if x0 > 180:
        x0 -= 360
        ds.SetGeoTransform((x0, dx, rx, y0, ry, dy))
    edge = int(math.floor((CRM_BOUNDS[0] - x0) / dx - 0.5 + 1e-6)) + 1  # columns with center <= the west edge
    if edge > 0:
        band = ds.GetRasterBand(1)
        data = band.ReadAsArray()
        data[:, :edge] = band.GetNoDataValue()
        band.WriteArray(data)
    ds = None


def _check_float_tif(path: Path) -> None:
    try:
        ds = gdal.Open(str(path))
    except RuntimeError as e:
        raise DownloadError(f"{path}: not a readable GeoTIFF: {e}") from e
    if ds.RasterCount != 1 or ds.GetRasterBand(1).DataType != gdal.GDT_Float32:
        raise DownloadError(f"{path}: expected one Float32 band")
    try:
        ds.GetRasterBand(1).ReadAsArray()  # a cut file keeps its header; only the strips fail
    except RuntimeError as e:
        raise DownloadError(f"{path}: raster data is cut short: {e}") from e


def fetch_crm(bbox, cache_dir: Path) -> Path | None:
    """The cached CRM file for bbox (crm_request), or None when bbox is wholly outside CRM."""
    dest = crm_path(bbox, cache_dir)
    if dest is None:
        return None
    download(crm_wcs_url(crm_request(bbox)), dest)
    try:
        _check_float_tif(dest)
        _fix_west_edge(dest)
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise
    return dest
