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
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from chartpack.enc.reader import Feature

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
# The src values of derived features (plan 8 spec 7.1): the only features, with the nosurvey areas, drawn inside
# the Canada polygon.
DERIVED_SRC = ("nonna10", "nonna100", "crm", "etopo", "fwa")
_NOAA_COVER = ("depare", "lndare")  # the kept NOAA areas that win over derived depth outside the polygon (rule 3)

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


def _outside_m(area: shapely.Geometry, grown_m: shapely.Geometry) -> shapely.Geometry:
    """The part of area (lon/lat) outside grown_m (meters), in meters."""
    return to_m(area).difference(grown_m)


def check_notices(cells: list[tuple[str, list[tuple[shapely.Geometry, str | None]]]], canada: shapely.Geometry) -> None:
    """The notice guards of spec 7.2 over the loaded cells, each (name, read_notes): BcError naming the cell when a
    NOTICE_CELLS cell yields no CHS notice area, when a note names a text file missing from the cell, or when any
    point of a cell's notice area lies more than BORDER_TOLERANCE_M from canada."""
    grown = None
    for name, notes in cells:
        if any(text is None for _, text in notes):
            raise BcError(f"{name}: a note names a text file missing from the cell")
        area = chs_notice_areas(notes)
        if area.is_empty:
            if name in NOTICE_CELLS:
                raise BcError(f"{name}: listed as carrying the CHS notice, but no note holds {CHS_NOTICE_MARK!r}")
            continue
        grown = to_m(canada).buffer(BORDER_TOLERANCE_M) if grown is None else grown
        if not (outside := _outside_m(area, grown)).is_empty:
            raise BcError(f"{name}: its CHS notice area reaches more than {BORDER_TOLERANCE_M:g} m past the Canada"
                          f" polygon ({outside.area / 1e6:.6f} km2 outside); run scripts/make-canada-chs.py again")


def check_canadian_areas(cells: list[tuple[str, int, shapely.Geometry, shapely.Geometry]], canada: shapely.Geometry,
                         owned: shapely.Geometry) -> None:
    """The Canadian-area guard of spec 7.2. cells: (name, band, read_canadian_area, coverage) of the loaded cells.
    The Canadian area of each band 1, 4 or 5 cell within owned (for band 1, less the coverage of the loaded
    NOTICE_CELLS, whose notices decide there) must lie within canada grown by BORDER_TOLERANCE_M; else BcError
    naming the cell and the area outside in km2."""
    notice = unary_union([coverage for name, _, _, coverage in cells if name in NOTICE_CELLS])
    grown = None
    for name, band, area, _ in cells:
        if band not in (1, 4, 5):
            continue
        part = area.intersection(owned)
        if band == 1:
            part = part.difference(notice)
        if part.is_empty:
            continue
        grown = to_m(canada).buffer(BORDER_TOLERANCE_M) if grown is None else grown
        if not (outside := _outside_m(part, grown)).is_empty:
            raise BcError(f"{name}: {outside.area / 1e6:.3f} km2 of its Canadian area in the owned tiles lies more"
                          f" than {BORDER_TOLERANCE_M:g} m outside the Canada polygon; run"
                          " scripts/make-canada-chs.py again")


def _keep(feature: Feature, geom: shapely.Geometry) -> list[Feature]:
    """The parts of geom of the feature's own dimension, each a copy of the feature."""
    dim = shapely.get_dimensions(shape(feature.geometry))
    return [Feature(feature.layer, mapping(part), feature.props)
            for part in shapely.get_parts(geom) if not part.is_empty and shapely.get_dimensions(part) == dim]


def apply_rules(cut: list[Feature], derived: list[Feature], canada: shapely.Geometry) -> list[Feature]:
    """The rules of spec 7.2, by geometry. cut (the quilt output, every band and layer, and the bottom samples of
    every source): areas and lines cut to the outside of canada, points inside it dropped. derived (made for the
    charts side only): kept inside canada; outside it, depare, depcnt, soundg and nosurvey are cut away wherever a
    kept NOAA depare or lndare covers the place, and lndare and coalne are dropped. Both sides are cut from the same
    geometry, so they meet on one line. A feature that needs no cut is returned as it is."""
    shapely.prepare(canada)
    out = []
    for feature in cut:
        geom = shape(feature.geometry)
        if geom.geom_type == "Point":  # dropped inside; one on the boundary is not inside (the pack check agrees)
            if not shapely.contains(canada, geom):
                out.append(feature)
        elif not shapely.intersects(canada, geom):
            out.append(feature)
        elif not shapely.covers(canada, geom):
            w, s, e, n = geom.bounds  # canada near the feature only: a straight line's bounds have no area
            out += _keep(feature, geom.difference(canada.intersection(box(w - 1e-6, s - 1e-6, e + 1e-6, n + 1e-6))))
    tree = shapely.STRtree([shape(f.geometry) for f in out if f.layer in _NOAA_COVER])
    for feature in derived:
        geom = shape(feature.geometry)
        if shapely.covers(canada, geom):
            out.append(feature)
        elif feature.layer in ("lndare", "coalne"):
            out += _keep(feature, geom.intersection(canada))
        elif len(near := tree.query(geom, predicate="intersects")) == 0:
            out.append(feature)
        else:
            out += _keep(feature, geom.difference(shapely.union_all(tree.geometries[near])))
    return out
