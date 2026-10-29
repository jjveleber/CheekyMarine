#!/usr/bin/env bash
# Build tippecanoe (felt fork, BSD-2) at a pinned tag and install tippecanoe and tile-join.
# Build deps: g++, make, zlib1g-dev, libsqlite3-dev.
set -euo pipefail

TAG="${TIPPECANOE_TAG:-2.79.0}"
PREFIX="${PREFIX:-$HOME/.local}"

src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT

git clone --depth 1 --branch "$TAG" https://github.com/felt/tippecanoe "$src/tippecanoe"
make -C "$src/tippecanoe" -j"$(nproc)"
mkdir -p "$PREFIX/bin"
install -m 0755 "$src/tippecanoe/tippecanoe" "$src/tippecanoe/tile-join" "$PREFIX/bin/"
"$PREFIX/bin/tippecanoe" --version
