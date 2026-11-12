"""NOAA ETOPO 2022 15 arc-second surface elevation, the one tile that covers 45 to 60 N, 135 to 120 W (#92).

Elevations are meters above the EGM2008 geoid, positive up like CRM, read with read_window. The geoid is taken
as mean sea level and chart datum as a fixed CD_BELOW_MSL_M below it, so ETOPO needs no geoid grid and no tide
station (plan 8 spec 8).
"""

from pathlib import Path

from chartpack.bathy.crm import _check_float_tif
from chartpack.cache import DownloadError, download

ETOPO_URL = ("https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_surface_elev_gtif/"
             "ETOPO_2022_v1_15s_N60W135_surface.tif")
CD_BELOW_MSL_M = 4.0  # how far chart datum is taken to lie below mean sea level, one value wherever ETOPO is used


def etopo_path(cache_dir: Path) -> Path:
    return Path(cache_dir) / "etopo" / "ETOPO_2022_v1_15s_N60W135_surface.tif"


def fetch_etopo(cache_dir: Path) -> Path:
    """The cached ETOPO tile; downloaded once (the download renames only a whole file into place)."""
    dest = etopo_path(cache_dir)
    if not dest.exists():
        download(ETOPO_URL, dest)
        try:
            _check_float_tif(dest)
        except DownloadError:
            dest.unlink(missing_ok=True)
            raise
    return dest
