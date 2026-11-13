"""Filled depth bands between the contour levels. numpy, contourpy and shapely only."""

import contourpy
import numpy as np
from shapely.geometry import Polygon, box, mapping

from chartpack.bathy.contours import (
    BANDS,
    DEPTHS_FT,
    M_TO_FT,
    SIMPLIFY_DEG,
    axes,
    band_levels,
    center_lat,
    min_zoom,
    zoom_grids,
    zoom_tolerance_deg,
)

_BIG_M = 1e9
_ON_LEVEL_M = 1e-3  # a reading exactly on a level is drawn this much shallower (build_bands)


def build_bands(
    depth_m: np.ndarray, transform, *, levels_ft: list[int], simplify_deg: float = SIMPLIFY_DEG, core=None
) -> list[dict]:
    """GeoJSON Polygon features, one set per band between consecutive levels.

    A band from 0 m to the first level (depth_min_ft 0) and one above the last (depth_max_ft None)
    are included so the bands tile all water; cells at or above MLLW (including the fill_land
    plateau) are outside every band. Polygons are not smoothed. With `core` (W, S, E, N) each
    polygon is clipped to it before simplifying.

    contourpy draws a band for lower < depth <= upper, and pinches the band's rings to a point or a zero-width
    slit at a reading exactly on a level (a reading at 0 m, say), which makes the polygon invalid. Such a reading
    is drawn _ON_LEVEL_M shallower: it stays on the same, shallower side of every level, and the rings go round it.
    """
    core_box = None if core is None else box(*core)
    on_level = np.isin(depth_m, [0.0] + [ft / M_TO_FT for ft in levels_ft])
    if on_level.any():
        depth_m = depth_m.copy()  # one copy, and the caller's grid is left as it was
        depth_m[on_level] -= _ON_LEVEL_M
    del on_level
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
            poly = Polygon(rings[0], rings[1:])
            if core_box is not None:
                poly = poly.intersection(core_box)
            poly = poly.simplify(simplify_deg, preserve_topology=True)
            for part in getattr(poly, "geoms", [poly]):
                if part.is_empty or part.geom_type != "Polygon":
                    continue
                feats.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "depth_min_ft": lo,
                            "depth_max_ft": hi,
                            "minzoom": min_zoom(hi or 1000),
                        },
                        "geometry": mapping(part),
                    }
                )
    return feats


def bands_by_zoom(depth_m: np.ndarray, transform, *, bands=BANDS, core=None) -> list[dict]:
    """Bands per zoom band, the grids and zoom ranges of contours_by_zoom.

    Bands are disjoint, so dropping some leaves unfilled water; instead each zoom range gets a
    complete set between the DEPTHS_FT levels it draws (band_levels), simplified like the contours (at center_lat).
    The tippecanoe key carries the range and `minzoom` its low zoom. `core` clips the polygons.
    """
    lat = center_lat(depth_m, transform, core)
    feats = []
    for lo, hi, _, grid, tr in zoom_grids(depth_m, transform, bands):
        levels = band_levels(DEPTHS_FT, hi)
        for f in build_bands(grid, tr, levels_ft=levels, simplify_deg=zoom_tolerance_deg(hi, lat), core=core):
            f["properties"]["minzoom"] = lo
            f["tippecanoe"] = {"minzoom": lo, "maxzoom": hi}
            feats.append(f)
    return feats
