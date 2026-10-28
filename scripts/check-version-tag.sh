#!/usr/bin/env bash
# Usage: check-version-tag.sh TAG
# Fails if TAG (with optional leading "v") differs from the VERSION in the
# root CMakeLists.txt project() line.
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 TAG" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
cmake_version="$(sed -n -E 's/^[[:space:]]*project\(.*[[:space:]]VERSION[[:space:]]+([0-9]+\.[0-9]+\.[0-9]+).*$/\1/p' "$root/CMakeLists.txt" | head -n1)"
tag_version="${1#v}"

if [ -z "$cmake_version" ]; then
    echo "could not find project VERSION in $root/CMakeLists.txt" >&2
    exit 2
fi

echo "tag version:   $tag_version"
echo "cmake version: $cmake_version"
if [ "$tag_version" != "$cmake_version" ]; then
    echo "MISMATCH: tag does not match CMake project version" >&2
    exit 1
fi
echo "OK"
