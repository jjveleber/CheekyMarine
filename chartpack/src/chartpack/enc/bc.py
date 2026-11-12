"""The Canada polygon of plan 8 (spec 7.2): where nothing from the NOAA cells is shown.

regions/clip/canada-chs.geojson is built by scripts/make-canada-chs.py from the NOAA cells that meet PLAN8_BOX:
the CHS-notice areas of NOTICE_CELLS, the Canadian areas of the band 1 cells outside the notice cells'
coverage, and the Canadian areas of the band 4 and 5 cells.
"""

import json
from pathlib import Path

import numpy as np
import pyproj
import shapely
from shapely.geometry import box, shape
from shapely.ops import unary_union

# The text a CHS notice's file holds. Not "Canadian Hydrographic Service": the cell-wide general notes of US3WA1ED,
# US3WA1EE and seven band 4 cells hold those words and cover US water.
CHS_NOTICE_MARK = "Fisheries and Oceans Canada"
# The band 3 cells that carry the CHS notice (plan 8 Task 1 research).
NOTICE_CELLS = ("US3WA1ED", "US3WA1EE", "US3WA1EF", "US3AK1DW", "US3AK1DX", "US3AK1DY", "US3AK1EY")
PLAN8_BOX = (-137.0, 46.0, -120.0, 56.0)  # W, S, E, N
# The widest strip, in meters, by which canada-chs.geojson and canada-wa.geojson may disagree outside the
# Juan de Fuca strip (spec 7.2).
BORDER_TOLERANCE_M = 20.0
# The western entrance of the Strait of Juan de Fuca, where the two files differ on purpose (spec 7.2).
JDF_STRIP_BOX = (-125.40, 48.33, -124.70, 48.52)
_EDGE_INSET_DEG = 0.05  # away from canada-wa.geojson's artificial north, east and west edges

# BC Albers (equal area), for areas and distances in meters.
_TO_M = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3005", always_xy=True)
_FROM_M = pyproj.Transformer.from_crs("EPSG:3005", "EPSG:4326", always_xy=True)


class BcError(Exception):
    pass


def to_m(geom: shapely.Geometry) -> shapely.Geometry:
    """Lon/lat to BC Albers meters."""
    return shapely.transform(geom, to_m_xy)


def to_m_xy(xy: np.ndarray) -> np.ndarray:
    """Lon/lat coordinates (an n by 2 array) to BC Albers meters."""
    return _xy(_TO_M, xy)


def from_m(geom: shapely.Geometry) -> shapely.Geometry:
    """BC Albers meters to lon/lat."""
    return shapely.transform(geom, lambda xy: _xy(_FROM_M, xy))


def _xy(transformer, xy):
    x, y = transformer.transform(xy[:, 0], xy[:, 1])
    return np.column_stack([x, y])


def area_km2(geom: shapely.Geometry) -> float:
    return to_m(geom).area / 1e6


def chs_notice_areas(notes) -> shapely.Geometry:
    """The union of the note areas whose text holds CHS_NOTICE_MARK; empty when none."""
    return unary_union([area for area, text in notes if text is not None and CHS_NOTICE_MARK in text])


def _read(path: Path) -> shapely.Geometry:
    data = json.loads(Path(path).read_text())
    return shape(data.get("geometry", data))


def load_canada(regions_dir: Path) -> shapely.Geometry:
    """The Canada polygon (clip/canada-chs.geojson). BcError when, inside the bounds of clip/canada-wa.geojson
    shrunk by 0.05 degree and outside JDF_STRIP_BOX, the two polygons disagree by a strip wider than
    BORDER_TOLERANCE_M (what survives an inward buffer of half of it)."""
    canada = _read(Path(regions_dir) / "clip" / "canada-chs.geojson")
    wa = _read(Path(regions_dir) / "clip" / "canada-wa.geojson")
    w, s, e, n = wa.bounds
    inner = box(w + _EDGE_INSET_DEG, s + _EDGE_INSET_DEG, e - _EDGE_INSET_DEG, n - _EDGE_INSET_DEG)
    compared = inner.difference(box(*JDF_STRIP_BOX))
    wide = to_m(canada.symmetric_difference(wa).intersection(compared)).buffer(-BORDER_TOLERANCE_M / 2)
    if not wide.is_empty:
        x, y = from_m(wide.representative_point()).coords[0]
        raise BcError(f"canada-chs.geojson and canada-wa.geojson disagree by a strip wider than"
                      f" {BORDER_TOLERANCE_M:g} m near {x:.5f}, {y:.5f}")
    return canada
