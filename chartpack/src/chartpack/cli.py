"""chartpack command line. Subcommands are stubs until their tasks land."""

import argparse
from pathlib import Path

from chartpack import __version__
from chartpack.cache import download
from chartpack.enc.catalog import CATALOG_URL, cells_in_bbox, parse_catalog
from chartpack.enc.fetch import fetch_cells
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chartpack")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    for name in SUBCOMMANDS:
        if name in ("fetch-enc", "cells"):
            continue
        sub.add_parser(name).set_defaults(func=_not_implemented)
    p = sub.add_parser("fetch-enc")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_enc)
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
