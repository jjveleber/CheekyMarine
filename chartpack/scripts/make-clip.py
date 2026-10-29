#!/usr/bin/env python3
"""Build regions/clip/canada-wa.geojson: the Canadian side of the US/Canada maritime boundary.

Reads NOAA's US Maritime Limits and Boundaries shapefile (public domain), takes the
"US/Canada" boundary lines inside lon -125.5..-122, lat 48..49.1 (the 49th parallel
line, which is land, is left out), joins them east to west into one line, and closes it
westward to -125.5 and northward to 49.5 N into a polygon. Features inside it are removed
from the charts and the bathymetry (see bathy.merge.clip_mask).

Usage: make-clip.py [--zip PATH] [--out PATH]
"""

import argparse
import json
from pathlib import Path

from osgeo import ogr

from chartpack.cache import download

URL = "https://maritimeboundaries.noaa.gov/downloads/USMaritimeLimitsAndBoundariesSHP.zip"
WINDOW = (-125.5, -122.0, 48.0, 49.1)  # W, E, S, N (OGR SetSpatialFilterRect order)
WEST, NORTH = -125.5, 49.5

ogr.UseExceptions()


def boundary_lines(zip_path: Path) -> list[list[tuple[float, float]]]:
    ds = ogr.Open(f"/vsizip/{zip_path}/USMaritimeLimitsNBoundaries.shp")
    layer = ds.GetLayer(0)
    layer.SetAttributeFilter("NOTE LIKE '%US/Canada%' AND NOTE NOT LIKE '%49th Parallel%'")
    layer.SetSpatialFilterRect(WINDOW[0], WINDOW[2], WINDOW[1], WINDOW[3])
    lines = []
    for feature in layer:
        pts = [(x, y) for x, y, *_ in feature.GetGeometryRef().GetPoints()]
        lines.append(pts if pts[0][0] > pts[-1][0] else pts[::-1])  # east end first
    if not lines:
        raise SystemExit("no US/Canada boundary lines found in the window")
    return sorted(lines, key=lambda pts: -pts[0][0])


def canadian_polygon(lines: list[list[tuple[float, float]]]) -> list[list[float]]:
    joined = [p for pts in lines for p in pts]
    (east_lon, east_lat), (_, west_lat) = joined[0], joined[-1]
    ring = joined + [(WEST, west_lat), (WEST, NORTH), (east_lon, NORTH), (east_lon, east_lat)]
    return [list(p) for p in ring]


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path)
    ap.add_argument("--out", type=Path, default=root / "regions/clip/canada-wa.geojson")
    args = ap.parse_args()
    zip_path = args.zip or download(URL, root / ".cache/USMaritimeLimitsAndBoundariesSHP.zip")
    feature = {
        "type": "Feature",
        "properties": {"name": "canada-wa", "source": "NOAA US Maritime Limits and Boundaries"},
        "geometry": {"type": "Polygon", "coordinates": [canadian_polygon(boundary_lines(zip_path))]},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(feature, indent=1) + "\n")


if __name__ == "__main__":
    main()
