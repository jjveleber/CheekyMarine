"""chartpack command line. Subcommands are stubs until their tasks land."""

import argparse
import re
from pathlib import Path

from chartpack import __version__
from chartpack.cache import download
from chartpack.enc.catalog import CATALOG_URL, cells_in_bbox, parse_catalog
from chartpack.enc.fetch import fetch_cells
from chartpack.enc.reader import read_cell
from chartpack.enc.tiles import build_enc_mbtiles
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
        if name in ("fetch-enc", "cells", "build-enc", "render"):
            continue
        sub.add_parser(name).set_defaults(func=_not_implemented)
    p = sub.add_parser("fetch-enc")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_enc)
    p = sub.add_parser("build-enc")
    p.add_argument("region", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.set_defaults(func=_build_enc)
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
