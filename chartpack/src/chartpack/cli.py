"""chartpack command line. Subcommands are stubs until their tasks land."""

import argparse
import json
import re
from pathlib import Path

import numpy as np

from chartpack import __version__
from chartpack.bathy.bands import bands_by_zoom
from chartpack.bathy.contours import FINE_FT, contours_by_zoom
from chartpack.bathy.crm import fetch_crm
from chartpack.bathy.cudem import URLLIST, parse_urllist, read_window, tiles_for_bbox
from chartpack.bathy.dem import build_dem_mbtiles
from chartpack.bathy.merge import (
    clip_mask,
    coverage_polygons,
    fill_land,
    merge_to_mllw,
    tag_source,
    uncovered_area,
)
from chartpack.bathy.tiles import build_bathy_mbtiles, enc_fallback_contours
from chartpack.cache import download
from chartpack.enc.catalog import CATALOG_URL, cells_in_bbox, parse_catalog
from chartpack.enc.fetch import fetch_cells
from chartpack.enc.reader import read_cell
from chartpack.enc.tiles import build_enc_mbtiles
from chartpack.pack.assemble import assemble_bathy_pack
from chartpack.region import load_region

SUBCOMMANDS = (
    "fetch-enc",
    "build-enc",
    "fetch-bathy",
    "build-bathy",
    "check",
    "manifest",
    "archive",
    "render",
    "cells",
)


def _not_implemented(args: argparse.Namespace) -> int:
    raise NotImplementedError(args.command)


def _load_catalog(cache: Path):
    # The catalog changes nightly, so it is fetched on every run.
    return parse_catalog(download(CATALOG_URL, cache / "ENCProdCat.xml").read_bytes())


def _fetch_enc(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    catalog = _load_catalog(args.cache)
    names = [n for band in sorted(region.cells) for n in region.cells[band]]
    for name, _ in zip(names, fetch_cells(names, catalog, args.cache)):
        c = catalog[name]
        print(f"{name} {c.edtn}.{c.updn} {c.isdt.isoformat()}")
    return 0


def _cells(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    for name in cells_in_bbox(_load_catalog(args.cache), region.bbox, args.band):
        print(name)
    return 0


def _newest_cached_zip(cache: Path, name: str) -> Path:
    """The cached zip of the newest edition.update for a cell; fail if there is none."""
    found = []
    for path in (cache / "enc").glob(f"{name}-*.zip"):
        m = re.fullmatch(rf"{re.escape(name)}-(\d+)\.(\d+)\.zip", path.name)
        if m:
            found.append(((int(m[1]), int(m[2])), path))
    if not found:
        raise SystemExit(f"{name}: no cached zip under {cache / 'enc'}; run fetch-enc first")
    return max(found)[1]


def _build_enc(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    names = [n for band in sorted(region.cells) for n in region.cells[band]]
    cells = [read_cell(_newest_cached_zip(args.cache, name)) for name in names]
    out = build_enc_mbtiles(cells, args.out / "enc.mbtiles", region=region, work=args.work)
    print(out)
    return 0


def _fetch_bathy(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    # The tile list changes as NCEI adds tiles, so it is fetched on every run.
    text = download(URLLIST, args.cache / "cudem" / "urllist8483.txt").read_text()
    for tile in tiles_for_bbox(parse_urllist(text), region.bbox):
        print(tile.name)
    print(fetch_crm(region.bbox, args.cache))
    return 0


def _build_bathy(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    urllist = args.cache / "cudem" / "urllist8483.txt"
    w, s, e, n = region.bbox
    crm = args.cache / "crm" / f"crm_{w}_{s}_{e}_{n}.tif"
    for path in (urllist, crm):
        if not path.exists():
            raise SystemExit(f"{path} not found; run fetch-bathy first")
    tiles = tiles_for_bbox(parse_urllist(urllist.read_text()), region.bbox)
    primary = []
    for t in tiles:
        tw, ts, te, tn = t.bounds
        window = (max(w, tw), max(s, ts), min(e, te), min(n, tn))
        primary.append((read_window("/vsicurl/" + t.url, window), t.name))
    fallback = read_window(str(crm), region.bbox)
    grid, source = merge_to_mllw(primary, fallback, region.msl_to_mllw_m, region.navd88_to_mllw_m, region.bbox)
    del primary, fallback
    depth, transform = grid.data, grid.transform
    if region.clip is not None:
        mask = clip_mask(transform, depth.shape, json.loads(region.clip.read_text()))
        depth[mask] = np.nan
        source[mask] = 0
        del mask
    args.work.mkdir(parents=True, exist_ok=True)
    dem = build_dem_mbtiles(depth, transform, args.work / "dem.mbtiles", maxzoom=region.dem_maxzoom)
    depth = fill_land(depth)  # after the DEM, which keeps the real land heights for hillshade
    del grid

    names = {1: "cudem", 2: "crm"}
    enc_fallback = region.coarse_fallback == "enc"
    contours = [
        f for f in tag_source(contours_by_zoom(depth, transform, fine=True), source, transform, names)
        if not (f["properties"]["depth_ft"] in FINE_FT and f["properties"]["source"] != "cudem")
        and not (enc_fallback and f["properties"]["source"] == "crm")  # ENC lines are drawn there instead
    ]
    bands = bands_by_zoom(depth, transform)
    del depth
    years = ",".join(sorted({str(t.year) for t in tiles}))
    labels = {1: {"source": "cudem", "resolution_m": 3, "date": years},
              2: {"source": "crm", "resolution_m": 30, "date": "2025"}}
    coverage = coverage_polygons(source, transform, labels)
    uncovered = uncovered_area(source, transform, treat_fallback_as_uncovered=enc_fallback)
    cells = [read_cell(_newest_cached_zip(args.cache, name)) for band in sorted(region.cells) for name in region.cells[band]]
    contours += enc_fallback_contours(cells, uncovered)

    bathy = build_bathy_mbtiles(contours, bands, coverage, args.work / "bathy.mbtiles", region=region,
                                work=args.work / "tippecanoe", cudem_tiles=tiles)
    print(assemble_bathy_pack(region, bathy, dem, args.out))
    return 0


def _render(args: argparse.Namespace) -> int:
    from chartpack.render.render import render_views

    if args.styles:
        styles = args.styles.split(",")
    else:
        styles = sorted({p.stem for pack in args.packdirs for p in (pack / "styles").glob("*.json")})
    for path in render_views(args.packdirs, load_region(args.views).views, styles, args.out):
        print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chartpack")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    for name in SUBCOMMANDS:
        if name in ("fetch-enc", "cells", "build-enc", "render", "fetch-bathy", "build-bathy"):
            continue
        sub.add_parser(name).set_defaults(func=_not_implemented)
    p = sub.add_parser("fetch-enc")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_enc)
    p = sub.add_parser("fetch-bathy")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_bathy)
    p = sub.add_parser("build-enc")
    p.add_argument("region", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.set_defaults(func=_build_enc)
    p = sub.add_parser("build-bathy")
    p.add_argument("region", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.set_defaults(func=_build_bathy)
    p = sub.add_parser("render")
    p.add_argument("packdirs", type=Path, nargs="+", metavar="PACKDIR")
    p.add_argument("--views", type=Path, required=True, help="region file whose render views are drawn")
    p.add_argument("--styles", help="comma-separated style names (default: every styles/*.json)")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_render)
    p = sub.add_parser("cells")
    p.add_argument("region", type=Path)
    p.add_argument("--band", type=int, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_cells)
    args = parser.parse_args(argv)
    if args.version:
        print(f"chartpack {__version__}")
        return 0
    if args.command is None:
        parser.error("a command is required")
    return args.func(args)
