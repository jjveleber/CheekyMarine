#!/usr/bin/env bash
# Usage: check-plotter-tag.sh TAG
# Fails if TAG is not plotter-vX.Y.Z with X.Y.Z equal to PLOTTER_VERSION in plotter/CMakeLists.txt.
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 TAG" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
cmake_version="$(sed -n -E 's/^set\(PLOTTER_VERSION ([0-9]+\.[0-9]+\.[0-9]+)\).*$/\1/p' "$root/plotter/CMakeLists.txt" | head -n1)"

if [ -z "$cmake_version" ]; then
    echo "could not find PLOTTER_VERSION in $root/plotter/CMakeLists.txt" >&2
    exit 2
fi

case "$1" in
    plotter-v[0-9]*.[0-9]*.[0-9]*) ;;
    *)
        echo "tag $1 is not of the form plotter-vX.Y.Z" >&2
        exit 1
        ;;
esac
tag_version="${1#plotter-v}"

echo "tag version:   $tag_version"
echo "cmake version: $cmake_version"
if [ "$tag_version" != "$cmake_version" ]; then
    echo "MISMATCH: tag does not match PLOTTER_VERSION" >&2
    exit 1
fi
echo "OK"
