"""Filled depth bands between the contour levels. numpy, contourpy and shapely only."""

import contourpy
import numpy as np
from shapely.geometry import Polygon, mapping

from chartpack.bathy.contours import DEPTHS_FT, M_TO_FT, SIMPLIFY_DEG, axes, min_zoom, zoom_grids

_BIG_M = 1e9


def build_bands(depth_m: np.ndarray, transform, *, levels_ft: list[int], simplify_deg: float = SIMPLIFY_DEG) -> list[dict]:
    """GeoJSON Polygon features, one set per band between consecutive levels.

    A band from 0 m to the first level (depth_min_ft 0) and one above the last (depth_max_ft None)
    are included so the bands tile all water; cells at or above MLLW (including the fill_land
    plateau) are outside every band. Polygons are not smoothed.
    """
    x, y = axes(depth_m.shape, transform)
    gen = contourpy.contour_generator(
        x, y, np.ma.masked_invalid(depth_m), fill_type=contourpy.FillType.OuterOffset
    )
    bounds = [(0, levels_ft[0])] + list(zip(levels_ft, levels_ft[1:])) + [(levels_ft[-1], None)]
    feats = []
    for lo, hi in bounds:
        lo_m = lo / M_TO_FT
        hi_m = _BIG_M if hi is None else hi / M_TO_FT
        points, offsets = gen.filled(lo_m, hi_m)
        for pts, offs in zip(points, offsets):
            rings = [pts[a:b] for a, b in zip(offs, offs[1:])]
            poly = Polygon(rings[0], rings[1:]).simplify(simplify_deg, preserve_topology=True)
            for part in getattr(poly, "geoms", [poly]):
                if part.is_empty or part.geom_type != "Polygon":
                    continue
                feats.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "depth_min_ft": lo,
                            "depth_max_ft": hi,
                            "minzoom": min_zoom(hi or 600),
                        },
                        "geometry": mapping(part),
                    }
                )
    return feats


def bands_by_zoom(depth_m: np.ndarray, transform) -> list[dict]:
    """Bands per zoom band, the grids and zoom ranges of contours_by_zoom.

    Bands are disjoint, so dropping some leaves unfilled water; instead each zoom range gets a
    complete set between the DEPTHS_FT levels it draws (min_zoom <= its top). The tippecanoe key
    carries the range and `minzoom` its low zoom.
    """
    feats = []
    for lo, hi, _, grid, tr in zoom_grids(depth_m, transform):
        for f in build_bands(grid, tr, levels_ft=[ft for ft in DEPTHS_FT if min_zoom(ft) <= hi]):
            f["properties"]["minzoom"] = lo
            f["tippecanoe"] = {"minzoom": lo, "maxzoom": hi}
            feats.append(f)
    return feats
