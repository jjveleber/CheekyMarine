"""CUDEM 1/9 arc-second tiles: pick tiles from the NCEI url list, read windows by range request."""

import re
from dataclasses import dataclass

import numpy as np
from osgeo import gdal

from chartpack.cache import USER_AGENT

gdal.UseExceptions()

URLLIST = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_2014_8483/urllist8483.txt"

TILE_SIZE_DEG = 0.25
_NAME = re.compile(r"ncei19_n(\d+)x(\d+)_w(\d+)x(\d+)_(\d{4})v(\d)")


@dataclass(frozen=True)
class CudemTile:
    name: str
    url: str
    north: float  # tiles are named by their north-west corner
    west: float
    year: int
    version: int

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """W, S, E, N."""
        return (self.west, self.north - TILE_SIZE_DEG, self.west + TILE_SIZE_DEG, self.north)


def parse_urllist(text: str) -> list[CudemTile]:
    """Tiles from urllist8483.txt; lines that are not CUDEM tile urls are skipped."""
    tiles = []
    for line in text.splitlines():
        url = line.strip()
        m = _NAME.search(url.rsplit("/", 1)[-1])
        if not m:
            continue
        n_deg, n_frac, w_deg, w_frac, year, version = m.groups()
        tiles.append(
            CudemTile(
                name=m.group(0),
                url=url,
                north=float(f"{n_deg}.{n_frac}"),
                west=-float(f"{w_deg}.{w_frac}"),
                year=int(year),
                version=int(version),
            )
        )
    return tiles


def tiles_for_bbox(tiles: list[CudemTile], bbox) -> list[CudemTile]:
    """Tiles whose bounds overlap the bbox (W, S, E, N) with positive area, sorted by name.

    Where several tiles cover the same cell (for example 2023v1 and 2024v1 of one corner),
    only the newest (year, version) is kept.
    """
    w, s, e, n = bbox
    newest: dict[tuple[float, float], CudemTile] = {}
    for t in tiles:
        tw, ts, te, tn = t.bounds
        if tw < e and te > w and ts < n and tn > s:
            key = (t.north, t.west)
            if key not in newest or (t.year, t.version) > (newest[key].year, newest[key].version):
                newest[key] = t
    return sorted(newest.values(), key=lambda t: t.name)


@dataclass
class Grid:
    data: np.ndarray  # float32, row 0 = north
    nodata: float
    transform: tuple[float, ...]  # GDAL geotransform
    crs: str  # WKT


def read_window(src: str, bbox) -> Grid:
    """Read bbox (W, S, E, N, in the source CRS units) from a local path or a /vsicurl/ URL."""
    w, s, e, n = bbox
    options = {}
    if src.startswith("/vsicurl/"):
        options = {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
            "GDAL_HTTP_USERAGENT": USER_AGENT,
        }
    with gdal.config_options(options):
        ds = gdal.Open(src)
        gt = ds.GetGeoTransform()
        sw, sn = gt[0], gt[3]
        se, ss = sw + gt[1] * ds.RasterXSize, sn + gt[5] * ds.RasterYSize
        if not (w < se and e > sw and s < sn and n > ss):
            raise ValueError(f"bbox {tuple(bbox)} is outside {src}")
        out = gdal.Translate("", ds, projWin=[w, n, e, s], format="MEM")
    if out.RasterXSize == 0 or out.RasterYSize == 0:
        raise ValueError(f"empty window for bbox {tuple(bbox)}")
    band = out.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    return Grid(
        data=band.ReadAsArray().astype(np.float32, copy=False),
        nodata=float("nan") if nodata is None else float(nodata),
        transform=tuple(out.GetGeoTransform()),
        crs=out.GetProjection(),
    )
