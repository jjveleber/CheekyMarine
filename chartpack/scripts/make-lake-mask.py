#!/usr/bin/env python3
"""Build regions/datum/lake-mask.geojson: the inland lakes of wave 1 that have no datum rule (#88, PR #105).

The build draws no bathy (contours, bands, coverage) inside these polygons, as for the clipped Canadian water:
a lake bottom is not on a tidal datum, so the station path would put its depth off by the lake's surface height.
Lake Union and Lake Washington are not in the mask; they keep their datum rule (lakes.geojson).

Input:
- USGS National Hydrography Dataset (public domain), the Waterbody - Large Scale layer of the National Map
  service (NHD_URL), LakePond waterbodies (FType 390) of MIN_AREA_KM2 or more meeting the extent of the owned
  tiles, read in pages of PAGE features about one request a second into .cache/lake-mask-nhd/ (or --nhd-dir).
- The NOAA ENC cells of bands 3 to 5 the wave 1 region files name (public domain), from
  https://www.charts.noaa.gov/ENCs/<cell>.zip into .cache/lake-mask-enc/ (or --enc-dir, a folder holding
  ENC_ROOT/<cell>/<cell>.000), for their depth areas (DEPARE).

Method: every such LakePond, less any that meets a lakes.geojson polygon (the datum lakes and the ship canal),
less any that meets an ENC depth area (NOAA charts depths there, so it is chart datum water: Jetty Lagoon, Capitol
Lake), less TIDAL (tidal or tide-gated water NOAA does not chart, ruled on PR #105). The rest is cut to the owned
zoom-10 tiles of all wave 1 regions (grid.toml) less the Canada clip, holes (islands) filled, simplified at
SIMPLIFY_DEG (about 4 m) and rounded to PRECISION_DEG, one Feature per waterbody with its GNIS name and NHD id.

After a region file's cell list or the grid changes, or an NHD refresh: rerun this script, review the diff of
lake-mask.geojson and run the chartpack tests.

Usage: make-lake-mask.py [--nhd-dir PATH] [--enc-dir PATH] [--out PATH] [--retrieved YYYY-MM-DD]
"""

import argparse
import datetime
import json
import time
import urllib.parse
import zipfile
from pathlib import Path

import shapely
from osgeo import gdal, ogr
from shapely.geometry import Polygon, mapping, shape

from chartpack.cache import download
from chartpack.grid import load_grid, owned_tiles, tiles_area
from chartpack.region import load_region

NHD_URL = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/12/query"
LAKE_POND = 390
MIN_AREA_KM2 = 0.05
PAGE = 200
ENC_URL = "https://www.charts.noaa.gov/ENCs/{cell}.zip"
BANDS = (3, 4, 5)
TIDAL = {  # NHD Permanent_Identifier: tidal or tide-gated water NOAA does not chart (PR #105, rounds 2 and 3)
    "155195574": "Crockett Lake, tide-gated behind Keystone",
    "152293421": "Old Channel, a slough off Padilla Bay",
    "147684000": "pond at Alder and Tansy creeks, Chinook",
    "{363F4F32-27A1-4295-AAE1-6DE16987E7C7}": "Keyport Lagoon, tidal",
    "4a04fc42-32f6-4e5a-b188-06f9c23f9295": "Little Clam Bay, tidal",
    "155197835": "Whiteman Cove, diked behind a tide gate",
}
SIMPLIFY_DEG = 0.00005
PRECISION_DEG = 0.000001

gdal.UseExceptions()


def _query(envelope, offset: int) -> str:
    return NHD_URL + "?" + urllib.parse.urlencode({
        "where": f"FTYPE={LAKE_POND} AND AREASQKM>={MIN_AREA_KM2}", "geometry": ",".join(str(v) for v in envelope),
        "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
        "outFields": "PERMANENT_IDENTIFIER,GNIS_NAME,AREASQKM,FTYPE,FDATE", "outSR": "4326",
        "orderByFields": "OBJECTID", "resultOffset": str(offset), "resultRecordCount": str(PAGE), "f": "geojson"})


def fetch_nhd(envelope, cache: Path) -> Path:
    offset = 0
    while True:
        page = cache / f"page-{offset}.geojson"
        if not page.exists():
            download(_query(envelope, offset), page, timeout=180)
            time.sleep(1)
        if len(json.loads(page.read_text())["features"]) < PAGE:
            return cache
        offset += PAGE


def fetch_enc(cells: list[str], cache: Path) -> Path:
    for cell in cells:
        zip_path = cache / f"{cell}.zip"
        if not zip_path.exists():
            download(ENC_URL.format(cell=cell), zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(cache)
    return cache


def depth_areas(cells: list[str], enc_dir: Path) -> shapely.Geometry:
    parts = []
    for cell in cells:
        ds = ogr.Open(str(enc_dir / "ENC_ROOT" / cell / f"{cell}.000"))
        for f in ds.GetLayerByName("DEPARE") or []:
            g = f.GetGeometryRef()
            geom = None if g is None else shape(json.loads(g.ExportToJson()))
            if geom is not None and geom.geom_type in ("Polygon", "MultiPolygon"):
                parts.append(geom.buffer(0))
    return shapely.union_all(parts)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    regions = root / "regions"
    ap = argparse.ArgumentParser()
    ap.add_argument("--nhd-dir", type=Path)
    ap.add_argument("--enc-dir", type=Path)
    ap.add_argument("--out", type=Path, default=regions / "datum/lake-mask.geojson")
    ap.add_argument("--retrieved", default=datetime.date.today().isoformat())
    args = ap.parse_args()

    names = load_grid(regions / "grid.toml")
    tiles = set().union(*(owned_tiles(load_region(regions / f"{n}.toml"), regions) for n in names))
    clip = json.loads((regions / "clip/canada-wa.geojson").read_text())
    owned = tiles_area(tiles)
    area = owned.difference(shape(clip.get("geometry", clip)))
    cells = sorted({c for n in names for band, cs in load_region(regions / f"{n}.toml").cells.items()
                    if band in BANDS for c in cs})

    nhd_dir = args.nhd_dir or fetch_nhd(owned.bounds, root / ".cache/lake-mask-nhd")
    enc_dir = args.enc_dir or fetch_enc(cells, root / ".cache/lake-mask-enc")
    lakes = {f["properties"]["PERMANENT_IDENTIFIER"]: f for p in sorted(nhd_dir.glob("page-*.geojson"))
             for f in json.loads(p.read_text())["features"]}
    datum_lakes = shapely.union_all([shape(f["geometry"]) for f in
                                     json.loads((regions / "datum/lakes.geojson").read_text())["features"]])
    charted = depth_areas(cells, enc_dir)
    for g in (datum_lakes, charted, area):
        shapely.prepare(g)

    features, left_out = [], []
    for pid, f in sorted(lakes.items()):
        p, geom = f["properties"], shape(f["geometry"]).buffer(0)
        name = p["GNIS_NAME"] or "unnamed"
        if p["FTYPE"] != LAKE_POND or p["AREASQKM"] < MIN_AREA_KM2 or not area.intersects(geom):
            continue
        why = ("datum lake" if datum_lakes.intersects(geom) else "charted depths" if charted.intersects(geom)
               else TIDAL.get(pid))
        if why:
            left_out.append(f"{name} ({pid}): {why}")
            continue
        filled = shapely.union_all([Polygon(g.exterior) for g in getattr(geom, "geoms", [geom])])
        # Cut after simplifying and rounding, so the simplified edge never crosses into the clip
        g = shapely.set_precision(filled.simplify(SIMPLIFY_DEG), PRECISION_DEG).intersection(area)
        if not g.is_empty:
            features.append({"type": "Feature", "properties": {"name": name, "nhd_id": pid,
                                                               "area_km2": round(p["AREASQKM"], 3)},
                             "geometry": mapping(g)})
    collection = {
        "type": "FeatureCollection",
        "source": {
            "dataset": "USGS National Hydrography Dataset (public domain), Waterbody - Large Scale, FType 390 "
                       f"(LakePond), AREASQKM {MIN_AREA_KM2} or more",
            "url": NHD_URL,
            "license": "public domain (USGS)",
            "retrieved": args.retrieved,
            "script": "chartpack/scripts/make-lake-mask.py",
            "method": "every such waterbody meeting the owned zoom-10 tiles of all wave 1 regions, less those "
                      "meeting a lakes.geojson polygon (Lake Union and Lake Washington keep their datum rule), "
                      "less those meeting a DEPARE of the wave 1 ENC cells of bands 3 to 5 (charted water), less "
                      "TIDAL (tide-gated or tidal water, ruled on PR #105); cut to the owned tiles less "
                      f"clip/canada-wa.geojson, holes filled, simplified (shapely) at {SIMPLIFY_DEG:f} degrees "
                      f"(about 4 m), coordinates rounded to {PRECISION_DEG:f} degrees",
            "left_out": left_out,
        },
        "features": features,
    }
    args.out.write_text(json.dumps(collection, separators=(",", ":")) + "\n")
    print(f"{len(features)} lakes masked, {len(left_out)} left out")
    for line in left_out:
        print("left out:", line)


if __name__ == "__main__":
    main()
