"""NOAA Coastal Relief Model (CUDEM volume 8) subset through the THREDDS WCS service.

The nc2geotiff writer sets the GeoTIFF NoData tag to the data minimum minus 1 of each
request, so the tag differs per request and no real cell equals it. Read the NoData value
from the file as GDAL reports it; never hard-code one.
"""

from pathlib import Path

from osgeo import gdal

from chartpack.cache import DownloadError, download

gdal.UseExceptions()

WCS_BASE = "https://www.ngdc.noaa.gov/thredds/wcs/crm/cudem/crm_vol8_2025.nc"


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
            " snapped outward to 1 arc-second)")


def crm_path(bbox, cache_dir: Path) -> Path:
    """Where fetch_crm caches the request for bbox."""
    w, s, e, n = bbox
    return Path(cache_dir) / "crm" / f"crm_{w}_{s}_{e}_{n}.tif"


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


def fetch_crm(bbox, cache_dir: Path) -> Path:
    dest = crm_path(bbox, cache_dir)
    download(crm_wcs_url(bbox), dest)
    try:
        _check_float_tif(dest)
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise
    return dest
