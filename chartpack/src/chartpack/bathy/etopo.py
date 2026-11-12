"""NOAA ETOPO 2022 15 arc-second surface elevation, in 15 degree tiles named by their north-west corner (#92).

Elevations are meters above the EGM2008 geoid, positive up like CRM, read with read_window. The geoid is taken
as mean sea level and chart datum as a fixed CD_BELOW_MSL_M below it, so ETOPO needs no geoid grid and no tide
station (plan 8 spec 8). Plan 8 uses two tiles: N60W135 (45 to 60 N, 135 to 120 W) and N60W150 (150 to 135 W).
A read never asks a tile for anything past its extent (clip_to_tile), so no cell is padding.
"""

import math
from pathlib import Path

from osgeo import gdal

from chartpack.bathy.crm import check_float_tif
from chartpack.cache import DownloadError, download

gdal.UseExceptions()

ETOPO_URL = ("https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_surface_elev_gtif/"
             "ETOPO_2022_v1_15s_N60W135_surface.tif")  # the N60W135 tile
CD_BELOW_MSL_M = 4.0  # how far chart datum is taken to lie below mean sea level, one value wherever ETOPO is used
TILE_DEG = 15
PLAN8_TILES = ("N60W135", "N60W150")


def _tile_url(name: str) -> str:
    return ETOPO_URL.replace("N60W135", name)


def etopo_tiles(bbox) -> list[str]:
    """The tile names (north-west corner) whose area meets bbox (W, S, E, N), west to east. A tile other than the
    two plan 8 uses is an error naming it."""
    w, s, e, n = bbox
    names = []
    for j in range(math.floor(s / TILE_DEG), math.ceil(n / TILE_DEG)):
        for i in range(math.floor(w / TILE_DEG), math.ceil(e / TILE_DEG)):
            lat, lon = (j + 1) * TILE_DEG, i * TILE_DEG
            name = f"{'N' if lat >= 0 else 'S'}{abs(lat)}{'E' if lon >= 0 else 'W'}{abs(lon)}"
            if name not in PLAN8_TILES:
                raise ValueError(f"ETOPO tile {name} is needed for {tuple(bbox)} but plan 8 uses only "
                                 f"{' and '.join(PLAN8_TILES)}")
            names.append(name)
    return names


def etopo_paths(bbox, cache_dir: Path) -> list[Path]:
    """Where fetch_etopo caches the tiles that meet bbox."""
    return [Path(cache_dir) / "etopo" / f"ETOPO_2022_v1_15s_{name}_surface.tif" for name in etopo_tiles(bbox)]


def fetch_etopo(bbox, cache_dir: Path) -> list[Path]:
    """The cached ETOPO tiles that meet bbox; each downloaded once (the download renames only a whole file)."""
    paths = etopo_paths(bbox, cache_dir)
    for name, dest in zip(etopo_tiles(bbox), paths):
        if not dest.exists():
            download(_tile_url(name), dest)
            try:
                check_float_tif(dest)
            except DownloadError:
                dest.unlink(missing_ok=True)
                raise
    return paths


def clip_to_tile(path: Path, bbox) -> tuple[float, float, float, float] | None:
    """bbox cut to the extent of the tile file at path; None when they do not overlap."""
    ds = gdal.Open(str(path))
    gt = ds.GetGeoTransform()
    tw, tn = gt[0], gt[3]
    te, ts = tw + gt[1] * ds.RasterXSize, tn + gt[5] * ds.RasterYSize
    w, s, e, n = bbox
    w, s, e, n = max(w, tw), max(s, ts), min(e, te), min(n, tn)
    return (w, s, e, n) if w < e and s < n else None
