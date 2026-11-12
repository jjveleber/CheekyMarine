#!/usr/bin/env python3
"""Build regions/clip/canada-chs.geojson: the Canada polygon of plan 8 (spec 7.2).

From NOAA's ENC product catalog, downloads into a fresh temporary directory (from charts.noaa.gov only) the
seven band 3 cells that carry the CHS notice (bc.NOTICE_CELLS) and every Active band 1, 2, 4 and 5 cell whose
coverage meets bc.PLAN8_BOX. The polygon is the union of three parts:
- the CHS-notice areas of the notice cells;
- the Canadian areas (ADMARE, NATION=CA) of the band 1 cells, outside the notice cells' coverage;
- the Canadian areas of the band 4 and 5 cells.
Band 2 cells are read but not used: the script prints their Canadian area outside the band 1 Canadian areas.

Fails when the result is not a valid geometry, when a notice cell yields no notice area or names a text file
missing from its zip, when a band 4 or 5 cell adds beyond the other two parts a piece over 1 km2 that spec 7.2
does not list, or when the polygon covers more than 10 km2 of the undisputed Alaskan box ALASKA_BOX.

Usage: make-canada-chs.py [--out PATH]
"""

import argparse
import json
import tempfile
from pathlib import Path

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from chartpack.cache import download
from chartpack.enc.bc import JDF_STRIP_BOX, NOTICE_CELLS, PLAN8_BOX, area_km2, chs_notice_areas
from chartpack.enc.catalog import CATALOG_URL, cells_in_bbox, parse_catalog
from chartpack.enc.fetch import fetch_cells
from chartpack.enc.reader import read_canadian_area, read_cell, read_notes

PIECE_LIMIT_KM2 = 1.0
# The band 4 and 5 additions over PIECE_LIMIT_KM2 that spec 7.2 lists: cell -> the box (W, S, E, N) they lie in.
LISTED = {
    "US4WA1JA": JDF_STRIP_BOX,
    "US4WA1JB": JDF_STRIP_BOX,
    "US4WA1JC": JDF_STRIP_BOX,
    "US4AK5FO": (-132.05, 54.65, -131.35, 54.72),  # Dixon Entrance, just north of the band 3 notice line
}
# North of the A-B line in Dixon Entrance: undisputed Alaskan water, kept by US3AK1DY's notice. The trial build
# left 7.07 km2 of it inside the polygon (CHS-noticed water).
ALASKA_BOX = (-131.23, 54.69, -130.91, 54.77)
ALASKA_LIMIT_KM2 = 10.0


def _pieces(geom):
    return list(getattr(geom, "geoms", [geom])) if not geom.is_empty else []


def build(catalog: dict, work: Path) -> tuple[dict, list[str]]:
    """The GeoJSON Feature and the problems found (an empty list when it passes)."""
    names = {band: cells_in_bbox(catalog, PLAN8_BOX, band) for band in (1, 2, 4, 5)}
    every = sorted(set(NOTICE_CELLS).union(*names.values()))
    zips = dict(zip(every, fetch_cells(every, catalog, work)))
    problems = []

    notices, covers = [], []
    for name in NOTICE_CELLS:
        notes = read_notes(zips[name])
        if any(text is None for _, text in notes):
            problems.append(f"{name}: a note names a text file missing from the cell")
        area = chs_notice_areas(notes)
        if area.is_empty:
            problems.append(f"{name}: no CHS notice area")
        print(f"{name}: notice area {area_km2(area):.1f} km2")
        notices.append(area)
        covers.append(shape(read_cell(zips[name])[0].covr))
    notice = unary_union(notices)
    notice_cover = unary_union(covers)

    band1 = {name: read_canadian_area(zips[name]) for name in names[1]}
    band1_part = unary_union(list(band1.values())).difference(notice_cover)
    for name, area in band1.items():
        print(f"{name}: Canadian area {area_km2(area):.1f} km2")

    band1_all = unary_union(list(band1.values()))
    for name in names[2]:
        extra = read_canadian_area(zips[name]).difference(band1_all)
        if not extra.is_empty:
            print(f"{name} (band 2, not used): Canadian area outside the band 1 Canadian areas {area_km2(extra):.1f} km2")

    others = unary_union([notice, band1_part])
    fine = []
    for name in names[4] + names[5]:
        area = read_canadian_area(zips[name])
        if area.is_empty:
            continue
        fine.append(area)
        added = area.difference(others)
        print(f"{name}: adds {area_km2(added):.3f} km2")
        for piece in _pieces(added):
            km2 = area_km2(piece)
            if km2 > PIECE_LIMIT_KM2 and not (name in LISTED and box(*LISTED[name]).contains(piece)):
                w, s, e, n = piece.bounds
                problems.append(f"{name}: adds an unlisted piece of {km2:.2f} km2 at {w:.3f}, {s:.3f}, {e:.3f}, {n:.3f}")

    polygon = unary_union([notice, band1_part, *fine])
    if not polygon.is_valid or polygon.is_empty:
        problems.append("the polygon is not a valid geometry")
    alaska = area_km2(polygon.intersection(box(*ALASKA_BOX)))
    print(f"Alaskan box {ALASKA_BOX}: {alaska:.2f} km2 inside the polygon")
    if alaska > ALASKA_LIMIT_KM2:
        problems.append(f"the polygon covers {alaska:.2f} km2 of the Alaskan box {ALASKA_BOX}, over {ALASKA_LIMIT_KM2:g}")
    vertices = sum(len(ring.coords) for p in _pieces(polygon) for ring in [p.exterior, *p.interiors])
    print(f"polygon: {area_km2(polygon):.0f} km2, {len(_pieces(polygon))} parts, {vertices} vertices")

    cells = [{"cell": name, "band": catalog[name].band, "edition": catalog[name].edtn,
              "update": catalog[name].updn, "issued": catalog[name].isdt.isoformat(),
              "notice": name in NOTICE_CELLS} for name in every]
    feature = {
        "type": "Feature",
        "properties": {"name": "canada-chs", "source": "NOAA ENC cells (scripts/make-canada-chs.py)", "cells": cells},
        "geometry": mapping(polygon),
    }
    return feature, problems


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=root / "regions/clip/canada-chs.geojson")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="canada-chs-") as work:
        catalog = parse_catalog(download(CATALOG_URL, Path(work) / "ENCProdCat.xml").read_bytes())
        feature, problems = build(catalog, Path(work))
    if problems:
        raise SystemExit("make-canada-chs: " + "; ".join(problems))
    args.out.write_text(json.dumps(feature) + "\n")
    print(args.out)


if __name__ == "__main__":
    main()
