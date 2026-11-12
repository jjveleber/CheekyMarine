#!/usr/bin/env python3
"""Build tests/fixtures/bc-coast-tiles.json: the zoom-10 tiles that hold BC Freshwater Atlas coastline (plan 8 Task 15
Step 4), for test_no_offshore_tile_holds_coastline and test_no_unowned_tile_holds_coastline.

Reads the coast-<region>.geojson.gz assets of release sources-bc-1 (gzip GeoJSONSeq, written by fetch-sources), every
line as derive-sources reads them (_read_lines: the coastline and the river-mouth closing lines alike). A tile holds
coastline when a line meets its interior (an edge touch does not count). Prints the tile count of each file. Calls
no host.

Usage: make-coast-tiles.py OUT COAST_FILE...
"""

import argparse
import json
from pathlib import Path

import shapely
from shapely.geometry import box

from chartpack.cli import _read_lines
from chartpack.grid import GRID_ZOOM, tile_bounds, tiles_meeting


def coast_tiles(path: Path) -> set[tuple[int, int]]:
    lines = _read_lines(path)
    tree = shapely.STRtree(lines)
    found = set()
    for tile in tiles_meeting(shapely.total_bounds(lines)) if lines else ():
        cell = box(*tile_bounds(GRID_ZOOM, *tile))
        if any(not lines[i].touches(cell) for i in tree.query(cell, predicate="intersects")):
            found.add(tile)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("coast", type=Path, nargs="+")
    args = parser.parse_args()
    every = set()
    for path in args.coast:
        tiles = coast_tiles(path)
        print(f"{path.name}: {len(tiles)} tiles")
        every |= tiles
    args.out.write_text("[\n" + ",\n".join(f"  [{x}, {y}]" for x, y in sorted(every)) + "\n]\n")
    print(f"{args.out}: {len(every)} tiles")


if __name__ == "__main__":
    main()
