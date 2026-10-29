"""chartpack command line. Subcommands are stubs until their tasks land."""

import argparse

from chartpack import __version__

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chartpack")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    for name in SUBCOMMANDS:
        sub.add_parser(name).set_defaults(func=_not_implemented)
    args = parser.parse_args(argv)
    if args.version:
        print(f"chartpack {__version__}")
        return 0
    if args.command is None:
        parser.error("a command is required")
    return args.func(args)
