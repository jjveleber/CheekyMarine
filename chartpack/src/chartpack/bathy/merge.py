"""Merge CUDEM windows over a coarse fallback into one MLLW depth grid, with coverage and clip helpers.

Pure numpy: to_mllw_depth, fill_land, tag_source (shapely only). GDAL only in the warp,
polygonize and rasterize steps.
"""

import json

import numpy as np
from osgeo import gdal, ogr, osr
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from chartpack.bathy.cudem import Grid

gdal.UseExceptions()
ogr.UseExceptions()

COVERAGE_CELL_DEG = 1 / 120


def to_mllw_depth(elev: np.ndarray, nodata: float, offset_m: float) -> np.ndarray:
    """Depth in metres below MLLW: -elev - offset_m. NoData (and nan) become nan."""
    bad = ~np.isfinite(elev) | (elev == nodata)
    depth = (-elev.astype(np.float32) - np.float32(offset_m)).astype(np.float32)
    depth[bad] = np.nan
    return depth


def _warp_depth(grid: Grid, offset_m: float, bbox, res_deg: float, alg: str) -> np.ndarray:
    """One grid warped onto the target lon/lat grid, as MLLW depth (one target-size float32 array)."""
    h, w = grid.data.shape
    src = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Float32)
    src.SetGeoTransform(grid.transform)
    src.SetProjection(grid.crs)
    band = src.GetRasterBand(1)
    band.SetNoDataValue(grid.nodata)
    band.WriteArray(grid.data)
    out = gdal.Warp(
        "",
        src,
        format="MEM",
        outputBounds=tuple(bbox),
        xRes=res_deg,
        yRes=res_deg,
        dstSRS="EPSG:4326",
        dstNodata=float("nan"),
        outputType=gdal.GDT_Float32,
        resampleAlg=alg,
    )
    elev = out.GetRasterBand(1).ReadAsArray()
    return to_mllw_depth(elev, float("nan"), offset_m)


def merge_to_mllw(
    primary: list[tuple[Grid, str]],
    fallback: Grid,
    fallback_offset_m: float,
    primary_offset_m: float,
    bbox,
    *,
    res_deg: float = 1 / 3600 / 3,
) -> tuple[Grid, np.ndarray]:
    """Depth below MLLW on a regular lon/lat grid over bbox (W, S, E, N) at res_deg.

    Primary grids (nearest resampling) win where finite, earlier entries over later ones;
    the fallback (bilinear) fills the rest; cells with neither are nan. The second result is
    the source index: 0 none, 1 primary, 2 fallback. The primary names are not used here.

    Memory: one target-size float32 depth array is held for the result, one for the grid being
    merged, plus the uint8 index; each input is warped, merged and freed in turn. At the default
    1/9 arc-second a 26k by 26k region is about 2.7 GB per float32 array.
    """
    depth = None
    source = None
    for grid, _name in primary:
        warped = _warp_depth(grid, primary_offset_m, bbox, res_deg, "near")
        if depth is None:
            depth, source = warped, np.zeros(warped.shape, np.uint8)
        else:
            take = np.isnan(depth) & np.isfinite(warped)
            depth[take] = warped[take]
            del take
        source[np.isfinite(depth)] = 1
        del warped
    warped = _warp_depth(fallback, fallback_offset_m, bbox, res_deg, "bilinear")
    if depth is None:
        depth, source = warped, np.zeros(warped.shape, np.uint8)
    take = np.isnan(depth) & np.isfinite(warped)
    depth[take] = warped[take]
    source[take] = 2
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    transform = (bbox[0], res_deg, 0.0, bbox[3], 0.0, -res_deg)
    return Grid(depth, float("nan"), transform, srs.ExportToWkt()), source


def fill_land(depth: np.ndarray, land_depth_m: float = -0.3) -> np.ndarray:
    """Cells above water by more than |land_depth_m| are set to land_depth_m so contours close at the shore."""
    out = depth.copy()
    with np.errstate(invalid="ignore"):
        out[out < land_depth_m] = land_depth_m
    return out


def _coarsen(source: np.ndarray, transform) -> tuple[np.ndarray, tuple[float, ...]]:
    """Max of the source index per block of about 1/120 degree, and the coarse geotransform."""
    factor = max(1, round(COVERAGE_CELL_DEG / abs(transform[1])))
    rows, cols = source.shape
    pad = ((0, -rows % factor), (0, -cols % factor))
    padded = np.pad(source, pad)
    coarse = padded.reshape(padded.shape[0] // factor, factor, padded.shape[1] // factor, factor).max(axis=(1, 3))
    gt = (transform[0], transform[1] * factor, 0.0, transform[3], 0.0, transform[5] * factor)
    return coarse, gt


def _polygonize(values: np.ndarray, transform) -> list[tuple[int, object]]:
    """(value, shapely geometry) for each polygon of nonzero cells of a uint8 array."""
    h, w = values.shape
    ds = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(transform)
    band = ds.GetRasterBand(1)
    band.WriteArray(values.astype(np.uint8))
    vec = ogr.GetDriverByName("Memory").CreateDataSource("")
    layer = vec.CreateLayer("p", geom_type=ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    gdal.Polygonize(band, band, layer, 0)
    return [(f.GetField("v"), shape(json.loads(f.GetGeometryRef().ExportToJson()))) for f in layer]


def coverage_polygons(source: np.ndarray, transform, labels: dict[int, dict]) -> list[dict]:
    """GeoJSON Features of the source index (1 and 2 only) polygonized at about 1/120 degree.

    Each Feature's properties are a copy of labels[index]. Blocks take the highest index in them.
    """
    coarse, gt = _coarsen(source, transform)
    return [
        {"type": "Feature", "geometry": mapping(geom), "properties": dict(labels[v])}
        for v, geom in _polygonize(coarse, gt)
        if v in (1, 2)
    ]


def clip_mask(transform, shape, clip_geojson: dict) -> np.ndarray:
    """True where a cell centre is inside the clip polygon (a Feature or a geometry, lon/lat)."""
    geometry = clip_geojson.get("geometry", clip_geojson)
    rows, cols = shape
    ds = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(transform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds.SetProjection(srs.ExportToWkt())
    vec = ogr.GetDriverByName("Memory").CreateDataSource("")
    layer = vec.CreateLayer("clip", srs=srs, geom_type=ogr.wkbPolygon)
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(geometry)))
    layer.CreateFeature(feature)
    gdal.RasterizeLayer(ds, [1], layer, burn_values=[1])
    return ds.GetRasterBand(1).ReadAsArray().astype(bool)


def tag_source(features: list[dict], source: np.ndarray, transform, names: dict[int, str]) -> list[dict]:
    """Copies of the features with props["source"] = names[source index at the representative point].

    Features whose representative point is over index 0 (or off the grid) are dropped.
    """
    tagged = []
    for feature in features:
        point = shape(feature["geometry"]).representative_point()
        col = int(np.floor((point.x - transform[0]) / transform[1]))
        row = int(np.floor((point.y - transform[3]) / transform[5]))
        if not (0 <= row < source.shape[0] and 0 <= col < source.shape[1]):
            continue
        idx = int(source[row, col])
        if idx == 0:
            continue
        tagged.append({**feature, "properties": {**feature.get("properties", {}), "source": names[idx]}})
    return tagged


def uncovered_area(source: np.ndarray, transform, *, treat_fallback_as_uncovered: bool):
    """Polygon of index 0 cells (plus index 2 when treat_fallback_as_uncovered), coarsened like coverage_polygons.

    A coarse block counts as uncovered only when no primary cell is in it (fallback
    counts as uncovered when the flag is set).
    """
    coarse, gt = _coarsen(source, transform)
    wanted = (coarse == 0) | (coarse == 2) if treat_fallback_as_uncovered else coarse == 0
    return unary_union([geom for _, geom in _polygonize(wanted.astype(np.uint8), gt)])
