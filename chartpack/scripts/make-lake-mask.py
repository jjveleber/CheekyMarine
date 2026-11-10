#!/usr/bin/env python3
"""Build regions/datum/lake-mask.geojson: the inland lakes of wave 1 that have no datum rule (#88, PR #105).

The build draws no bathy (contours, bands, coverage) inside these polygons, as for the clipped Canadian water:
a lake bottom is not on a tidal datum, so the station path would put its depth off by the lake's surface height.
Lake Union and Lake Washington are not in the mask; they keep their datum rule (lakes.geojson).

Input: the NOAA ENC cells of bands 3 to 5 that the wave 1 region files name (public domain), downloaded from
https://www.charts.noaa.gov/ENCs/<cell>.zip into .cache/lake-mask-enc/ and unzipped there (or read from --enc-dir,
a folder holding ENC_ROOT/<cell>/<cell>.000 and its update files). GDAL applies the updates on open.

Method: every LAKARE (lake) area of those cells, less any LAKARE that meets a drying DEPARE (DRVAL1 below 0) of
any of the cells, which marks tidal water charted as a lake (lagoons behind dikes and trestles), and less any
LAKARE that meets a lakes.geojson polygon. Their union is cut to the owned zoom-10 tiles of all wave 1 regions
(grid.toml) less the Canada clip, split into polygons, holes (islands) filled, simplified at SIMPLIFY_DEG (about
1 m) and rounded to PRECISION_DEG. Each polygon is named by the OBJNAMs of the LAKARE in it.

The ENC charts only the land near the shore: inland lakes past the cells' data (Lake Sammamish, Lake Whatcom, Lake
Crescent, Lake Ozette, Lake Quinault) are in no LAKARE, so they are not in this mask.

After a region file's cell list or the grid changes, or a new ENC edition: rerun this script, review the diff of
lake-mask.geojson (the cells block records edition, update and issue date) and run the chartpack tests.

Usage: make-lake-mask.py [--enc-dir PATH] [--out PATH] [--retrieved YYYY-MM-DD]
"""

import argparse
import datetime
import json
import zipfile
from pathlib import Path

import shapely
from osgeo import gdal, ogr
from shapely.geometry import Polygon, mapping, shape

from chartpack.cache import download
from chartpack.grid import content_tiles, load_grid, tiles_area
from chartpack.region import load_region

URL = "https://www.charts.noaa.gov/ENCs/{cell}.zip"
BANDS = (3, 4, 5)
SIMPLIFY_DEG = 0.00001
PRECISION_DEG = 0.000001

gdal.UseExceptions()


def wave1_cells(regions: Path) -> list[str]:
    names = set()
    for name in load_grid(regions / "grid.toml"):
        for band, cells in load_region(regions / f"{name}.toml").cells.items():
            if band in BANDS:
                names.update(cells)
    return sorted(names)


def fetch(cells: list[str], cache: Path) -> Path:
    for cell in cells:
        zip_path = cache / f"{cell}.zip"
        if not zip_path.exists():
            download(URL.format(cell=cell), zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(cache)
    return cache


def _polygons(layer) -> list[tuple[ogr.Feature, shapely.Geometry]]:
    out = []
    for f in layer or []:
        g = f.GetGeometryRef()
        if g is None:
            continue
        geom = shape(json.loads(g.ExportToJson()))
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            out.append((f, geom.buffer(0)))
    return out


def read_cells(cells: list[str], enc_dir: Path) -> tuple[list[tuple[str, shapely.Geometry]], shapely.Geometry, list[dict]]:
    """(OBJNAM, polygon) of every LAKARE, the union of the drying DEPARE, and per cell its provenance."""
    lakes, drying, provenance = [], [], []
    for cell in cells:
        ds = ogr.Open(str(enc_dir / "ENC_ROOT" / cell / f"{cell}.000"))
        dsid = ds.GetLayerByName("DSID").GetNextFeature()
        found = [(f.GetField("OBJNAM") or "", g) for f, g in _polygons(ds.GetLayerByName("LAKARE"))]
        drying += [g for f, g in _polygons(ds.GetLayerByName("DEPARE"))
                   if f.GetField("DRVAL1") is not None and f.GetField("DRVAL1") < 0]
        lakes += found
        if found:
            provenance.append({"cell": cell, "edition": dsid.GetField("DSID_EDTN"), "update": dsid.GetField("DSID_UPDN"),
                               "issue_date": dsid.GetField("DSID_ISDT"), "lakare": len(found)})
    return lakes, shapely.union_all(drying), provenance


def mask(lakes, drying, keep_out: shapely.Geometry, area: shapely.Geometry) -> list[tuple[str, Polygon]]:
    """The named mask polygons: LAKARE less tidal ones and those meeting keep_out, cut to area."""
    shapely.prepare(drying)
    shapely.prepare(keep_out)
    kept = [(name, g) for name, g in lakes if not drying.intersects(g) and not keep_out.intersects(g)]
    union = shapely.union_all([g for _, g in kept]).intersection(area)
    out = []
    for part in getattr(union, "geoms", [union]):
        if part.geom_type != "Polygon" or part.is_empty:
            continue
        g = shapely.set_precision(Polygon(part.exterior).simplify(SIMPLIFY_DEG), PRECISION_DEG)
        if g.is_empty or g.geom_type != "Polygon":
            continue
        names = sorted({name for name, lake in kept if name and lake.intersects(part)})
        out.append((", ".join(names) or "unnamed", g))
    return sorted(out, key=lambda item: (item[0], item[1].bounds))


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    regions = root / "regions"
    ap = argparse.ArgumentParser()
    ap.add_argument("--enc-dir", type=Path)
    ap.add_argument("--out", type=Path, default=regions / "datum/lake-mask.geojson")
    ap.add_argument("--retrieved", default=datetime.date.today().isoformat())
    args = ap.parse_args()
    cells = wave1_cells(regions)
    enc_dir = args.enc_dir or fetch(cells, root / ".cache/lake-mask-enc")
    lakes, drying, provenance = read_cells(cells, enc_dir)
    datum_lakes = json.loads((regions / "datum/lakes.geojson").read_text())
    keep_out = shapely.union_all([shape(f["geometry"]) for f in datum_lakes["features"]])
    tiles = set().union(*(content_tiles(load_region(regions / f"{n}.toml"), regions)
                          for n in load_grid(regions / "grid.toml")))
    clip = json.loads((regions / "clip/canada-wa.geojson").read_text())
    area = tiles_area(tiles).difference(shape(clip.get("geometry", clip)))
    polygons = mask(lakes, drying, keep_out, area)
    collection = {
        "type": "FeatureCollection",
        "source": {
            "dataset": "NOAA ENC (public domain), the band 3 to 5 cells the wave 1 region files name, object LAKARE",
            "url": URL.format(cell="<cell>"),
            "retrieved": args.retrieved,
            "script": "chartpack/scripts/make-lake-mask.py",
            "method": "every LAKARE area of the cells below, less any that meets a drying DEPARE (DRVAL1 below 0) "
                      "of the cells (tidal water charted as a lake) and less any that meets a lakes.geojson polygon "
                      "(Lake Union and Lake Washington keep their datum rule); the union cut to the owned zoom-10 "
                      "tiles of all wave 1 regions less clip/canada-wa.geojson, split into polygons, holes filled, "
                      f"simplified (shapely) at {SIMPLIFY_DEG:f} degrees (about 1 m), coordinates rounded to "
                      f"{PRECISION_DEG:f} degrees; each polygon named by the OBJNAMs of its LAKARE",
            "cells": provenance,
        },
        "features": [{"type": "Feature", "properties": {"name": name}, "geometry": mapping(g)} for name, g in polygons],
    }
    args.out.write_text(json.dumps(collection, separators=(",", ":")) + "\n")
    for name, g in polygons:
        print(f"{name}: {g.area * 111200**2 * 0.67 / 1e6:.3f} km2 at {g.centroid.x:.3f}, {g.centroid.y:.3f}")


if __name__ == "__main__":
    main()
