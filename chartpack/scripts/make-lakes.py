#!/usr/bin/env python3
"""Build regions/datum/lakes.geojson: Lake Union and Lake Washington, east of the Hiram M. Chittenden Locks.

Input: the NOAA ENC band 5 cells over the lakes (CELLS, public domain), downloaded from
https://www.charts.noaa.gov/ENCs/<cell>.zip into .cache/lakes-enc/ and unzipped there (or read from --enc-dir,
a folder holding ENC_ROOT/<cell>/<cell>.000 and its update files). GDAL applies the updates on open.

Method: every M_SDAT area with VERDAT 24 (INFORM "Referenced to Low Water of the Lakes ...") is the water where
the chart's soundings are on the lakes' low water. Their union is one polygon from the locks east. It is split
by a thin meridian strip across the Montlake Cut (SPLIT_LON): west of it (Salmon Bay, the ship canal, Lake Union,
Portage Bay) is "Lake Union", the strip and east (Union Bay, Lake Washington) is "Lake Washington". Both are one
pool, so the split only names the halves. Each half is simplified at SIMPLIFY_DEG (about 0.5 m), rounded to
PRECISION_DEG, and holes under MIN_HOLE_M2 (piers, floats, small islands) are filled, so only Mercer Island
stays a hole. The names must match the [[lakes]] entries of regions/datum/wa-stations.toml.

After a new ENC edition or update of these cells: rerun this script (it re-downloads unless --enc-dir is given),
review the diff of lakes.geojson (the cells block records edition, update, issue date and the M_SDAT LNAMs) and
run the chartpack tests. If NOAA renames or re-schemes the cells, update CELLS from the ENC product catalog
(https://charts.noaa.gov/ENCs/ENCProdCat.xml).

Usage: make-lakes.py [--enc-dir PATH] [--out PATH] [--retrieved YYYY-MM-DD]
"""

import argparse
import datetime
import json
import zipfile
from pathlib import Path

import shapely
from osgeo import gdal, ogr
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

from chartpack.cache import download

CELLS = ["US5SEAEM", "US5SEAEN", "US5SEAFM", "US5SEAFN", "US5SEAGL", "US5SEAGM", "US5SEAGN", "US5SEAHM", "US5SEAHN"]
URL = "https://www.charts.noaa.gov/ENCs/{cell}.zip"
LAKE_VERDAT = 24  # local datum: "Low Water of the Lakes"
SPLIT_LON = -122.305  # across the Montlake Cut
SPLIT_LAT = (47.64, 47.66)
STRIP_DEG = 0.0001
SIMPLIFY_DEG = 0.000005
PRECISION_DEG = 0.000001
MIN_HOLE_M2 = 100_000
M2_PER_DEG2 = 111200**2 * 0.674  # cos(47.6 degrees)

gdal.UseExceptions()


def fetch(cache: Path) -> Path:
    for cell in CELLS:
        zip_path = download(URL.format(cell=cell), cache / f"{cell}.zip")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(cache)
    return cache


def lake_areas(enc_dir: Path) -> tuple[shapely.Geometry, list[dict]]:
    """The union of the M_SDAT lake-datum areas, and per cell the provenance of what was used."""
    parts, cells = [], []
    for cell in CELLS:
        ds = ogr.Open(str(enc_dir / "ENC_ROOT" / cell / f"{cell}.000"))
        dsid = ds.GetLayerByName("DSID").GetNextFeature()
        layer = ds.GetLayerByName("M_SDAT")
        lnams = []
        for f in layer or []:
            if f.GetField("VERDAT") == LAKE_VERDAT:
                parts.append(shape(json.loads(f.GetGeometryRef().ExportToJson())).buffer(0))
                lnams.append(f.GetField("LNAM"))
        if lnams:
            cells.append({"cell": cell, "edition": dsid.GetField("DSID_EDTN"), "update": dsid.GetField("DSID_UPDN"),
                          "issue_date": dsid.GetField("DSID_ISDT"), "m_sdat_lnam": sorted(lnams)})
    union = unary_union(parts)
    if union.geom_type != "Polygon":
        raise SystemExit(f"expected one lake polygon, got {union.geom_type}")
    return union, cells


def split(union: shapely.Geometry) -> dict[str, Polygon]:
    strip = box(SPLIT_LON, SPLIT_LAT[0], SPLIT_LON + STRIP_DEG, SPLIT_LAT[1])
    rest = union.difference(strip)
    pieces = list(getattr(rest, "geoms", [rest]))
    west = unary_union([g for g in pieces if g.representative_point().x < SPLIT_LON])
    east = unary_union([g for g in pieces if g.representative_point().x >= SPLIT_LON] + [union.intersection(strip)])
    out = {}
    for name, g in (("Lake Union", west), ("Lake Washington", east)):
        g = shapely.set_precision(g.simplify(SIMPLIFY_DEG, preserve_topology=True), PRECISION_DEG)
        if g.geom_type != "Polygon":
            raise SystemExit(f"{name}: expected one polygon, got {g.geom_type}")
        holes = [ring for ring in g.interiors if Polygon(ring).area * M2_PER_DEG2 >= MIN_HOLE_M2]
        g = Polygon(g.exterior, holes)
        if not g.is_valid:
            raise SystemExit(f"{name}: invalid polygon")
        out[name] = g
    return out


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--enc-dir", type=Path)
    ap.add_argument("--out", type=Path, default=root / "regions/datum/lakes.geojson")
    ap.add_argument("--retrieved", default=datetime.date.today().isoformat())
    args = ap.parse_args()
    enc_dir = args.enc_dir or fetch(root / ".cache/lakes-enc")
    union, cells = lake_areas(enc_dir)
    lakes = split(union)
    collection = {
        "type": "FeatureCollection",
        "source": {
            "dataset": f"NOAA ENC (public domain), band 5 cells US5SEA*, object M_SDAT with VERDAT {LAKE_VERDAT}, "
                       "INFORM 'Referenced to Low Water of the Lakes which is 20 feet \\ 6.1 metres above Mean "
                       "Lower Low Water'",
            "url": URL.format(cell="<cell>"),
            "retrieved": args.retrieved,
            "script": "chartpack/scripts/make-lakes.py",
            "method": "union of every M_SDAT VERDAT 24 area of the cells below (the water east of the Hiram M. "
                      "Chittenden Locks where soundings are on the lakes' low water); split by a "
                      f"{STRIP_DEG} degree strip at longitude {SPLIT_LON} across the Montlake Cut (Salmon Bay, the "
                      "ship canal, Lake Union and Portage Bay are Lake Union; Union Bay and east are Lake "
                      f"Washington); simplified (shapely, preserve_topology) at {SIMPLIFY_DEG:f} degrees (about "
                      f"0.5 m), coordinates rounded to {PRECISION_DEG:f} degrees; holes under {MIN_HOLE_M2:,} "
                      "square meters (piers, floats, small islands) filled, so only Mercer Island remains a hole",
            "cells": cells,
        },
        "features": [{"type": "Feature", "properties": {"name": name}, "geometry": mapping(g)}
                     for name, g in lakes.items()],
    }
    args.out.write_text(json.dumps(collection, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
