#!/usr/bin/env python3
"""Build regions/clip/canada-wa.geojson: the Canadian side of the US/Canada maritime boundary.

Reads NOAA's US Maritime Limits and Boundaries shapefile (public domain) and takes, inside lon
-129.5..-122, lat 46..49.1, the US/Canada boundary lines through the Strait of Georgia and the Strait
of Juan de Fuca and the US maritime boundary claim that carries them out to sea past Cape Flattery
(to the edge of the US zone, about -129.1 W, 46.5 N). It joins them east to west into one line, closes
it north from its west end to 49.5 N, east to -121.8 W, and back west along the 49th parallel boundary
(a land line except in Boundary Bay and Semiahmoo Bay), so the polygon holds all non-US water inside the
wave 1 boxes (west to -127 W, north to 49.05 N) and their zoom-10 tiles. Features inside it are removed
from the charts and the bathymetry (see bathy.merge.clip_mask).

Usage: make-clip.py [--zip PATH] [--out PATH]
"""

import argparse
import json
from pathlib import Path

from osgeo import ogr

from chartpack.cache import download

URL = "https://maritimeboundaries.noaa.gov/downloads/USMaritimeLimitsAndBoundariesSHP.zip"
WINDOW = (-129.5, -122.0, 46.0, 49.1)  # W, E, S, N (OGR SetSpatialFilterRect order)
EAST, NORTH = -121.8, 49.5  # past the east edge (-121.99 W) of the zoom-10 tiles of the wave 1 boxes
PARALLEL = "NOTE LIKE '%US/Canada%' AND NOTE LIKE '%49th Parallel%'"
BOUNDARY = ("(NOTE LIKE '%US/Canada%' AND NOTE NOT LIKE '%49th Parallel%')"
            " OR NOTE = 'Unilateral US maritime boundary claim'")

ogr.UseExceptions()


def _lines(zip_path: Path, where: str) -> list[list[tuple[float, float]]]:
    ds = ogr.Open(f"/vsizip/{zip_path}/USMaritimeLimitsNBoundaries.shp")
    layer = ds.GetLayer(0)
    layer.SetAttributeFilter(where)
    layer.SetSpatialFilterRect(WINDOW[0], WINDOW[2], WINDOW[1], WINDOW[3])
    lines = []
    for feature in layer:
        pts = [(x, y) for x, y, *_ in feature.GetGeometryRef().GetPoints()]
        lines.append(pts if pts[0][0] > pts[-1][0] else pts[::-1])  # east end first
    return sorted(lines, key=lambda pts: -pts[0][0])


def boundary_lines(zip_path: Path) -> list[list[tuple[float, float]]]:
    lines = _lines(zip_path, BOUNDARY)
    if not lines:
        raise SystemExit("no US/Canada boundary lines found in the window")
    return lines


def parallel_line(zip_path: Path) -> list[tuple[float, float]]:
    """The 49th parallel boundary from EAST west to its west end, where the Strait of Georgia line starts."""
    lines = _lines(zip_path, PARALLEL)
    if len(lines) != 1:
        raise SystemExit(f"expected one 49th parallel line in the window, found {len(lines)}")
    return [p for p in lines[0] if p[0] <= EAST]


def canadian_polygon(lines: list[list[tuple[float, float]]], parallel: list[tuple[float, float]]) -> list[list[float]]:
    joined = [p for pts in lines for p in pts]
    if parallel[-1] != joined[0]:
        raise SystemExit("the 49th parallel line does not meet the Strait of Georgia line")
    west_lon = joined[-1][0]
    ring = parallel + joined[1:] + [(west_lon, NORTH), (parallel[0][0], NORTH), parallel[0]]
    return [list(p) for p in ring]


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path)
    ap.add_argument("--out", type=Path, default=root / "regions/clip/canada-wa.geojson")
    args = ap.parse_args()
    zip_path = args.zip or download(URL, root / ".cache/USMaritimeLimitsAndBoundariesSHP.zip")
    ring = canadian_polygon(boundary_lines(zip_path), parallel_line(zip_path))
    feature = {
        "type": "Feature",
        "properties": {"name": "canada-wa", "source": "NOAA US Maritime Limits and Boundaries"},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(feature, indent=1) + "\n")


if __name__ == "__main__":
    main()
