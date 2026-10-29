"""Terrarium-encoded raster-dem tiles (dem.mbtiles) for on-device hillshade."""

import io
import math
from pathlib import Path

import numpy as np
from osgeo import gdal, osr
from PIL import Image

from chartpack.mbtiles import MBTiles

gdal.UseExceptions()

_EARTH_CIRC = 2 * math.pi * 6378137
_ORIGIN = _EARTH_CIRC / 2
_M_PER_DEG = 111320.0
_MAX_V = 65535.996


def terrarium_encode(elev_m: np.ndarray) -> np.ndarray:
    """(h, w) metres to (h, w, 3) uint8: v = elev + 32768; R = v // 256, G = v % 256, B = frac * 256."""
    v = np.clip(np.nan_to_num(elev_m.astype(np.float64)) + 32768.0, 0.0, _MAX_V)
    whole = np.floor(v)
    rgb = np.empty(v.shape + (3,), np.uint8)
    rgb[..., 0] = whole // 256
    rgb[..., 1] = whole % 256
    rgb[..., 2] = np.floor((v - whole) * 256)
    return rgb


def terrarium_decode(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.float64) for i in range(3))
    return (r * 256 + g + b / 256 - 32768).astype(np.float32)


def build_dem_mbtiles(
    depth_m: np.ndarray, transform, out: Path, *, minzoom: int = 10, maxzoom: int = 14, tile_size: int = 256
) -> Path:
    """Write a complete terrarium PNG pyramid over the grid's bbox.

    Elevation is -depth (nan becomes 0 so hillshade is flat there). The grid is warped to
    EPSG:3857 once per zoom over the bbox snapped outward to tile edges, so memory is one
    zoom-level raster (about 2 GB at z14 for a 26k by 26k region); blocking by tile rows is
    not done. Resampling is bilinear, switching to average when the zoom's pixel is more than
    2x the grid's native pixel (bilinear would alias when decimating that much).
    """
    elev = -np.nan_to_num(depth_m.astype(np.float32), nan=0.0)
    h, w = elev.shape
    west, dx, _, north, _, dy = transform
    east, south = west + dx * w, north + dy * h
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    src = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Float32)
    src.SetGeoTransform(transform)
    src.SetProjection(srs.ExportToWkt())
    src.GetRasterBand(1).WriteArray(elev)

    def to_m(lon, lat):
        return (
            lon / 360 * _EARTH_CIRC,
            math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137,
        )

    (x0, y0), (x1, y1) = to_m(west, south), to_m(east, north)
    native_m = abs(dy) * _M_PER_DEG

    with MBTiles.create(out, fmt="png") as m:
        for z in range(minzoom, maxzoom + 1):
            span = _EARTH_CIRC / 2**z  # metres per tile
            res = span / tile_size
            tx0, tx1 = math.floor((x0 + _ORIGIN) / span), math.ceil((x1 + _ORIGIN) / span)
            ty0, ty1 = math.floor((_ORIGIN - y1) / span), math.ceil((_ORIGIN - y0) / span)
            bounds = (tx0 * span - _ORIGIN, _ORIGIN - ty1 * span, tx1 * span - _ORIGIN, _ORIGIN - ty0 * span)
            warped = gdal.Warp(
                "", src, format="MEM", dstSRS="EPSG:3857", xRes=res, yRes=res, outputBounds=bounds,
                resampleAlg="average" if res > 2 * native_m else "bilinear", outputType=gdal.GDT_Float32,
            )
            arr = warped.GetRasterBand(1).ReadAsArray()
            for ty in range(ty0, ty1):
                for tx in range(tx0, tx1):
                    r, c = (ty - ty0) * tile_size, (tx - tx0) * tile_size
                    buf = io.BytesIO()
                    Image.fromarray(terrarium_encode(arr[r : r + tile_size, c : c + tile_size])).save(
                        buf, "PNG", optimize=False
                    )
                    m.put_tile(z, tx, ty, buf.getvalue())
        m.set_metadata(
            {
                "name": "dem",
                "type": "baselayer",
                "minzoom": str(minzoom),
                "maxzoom": str(maxzoom),
                "bounds": ",".join(str(round(v, 6)) for v in (west, south, east, north)),
                "cheekymarine:encoding": "terrarium",
                "cheekymarine:pack": "bathy",
                "cheekymarine:schema": "1",
            }
        )
    return Path(out)
