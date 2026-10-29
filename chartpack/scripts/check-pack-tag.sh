#!/usr/bin/env bash
# Usage: check-pack-tag.sh TAG
# TAG is charts-<region>-vX.Y.Z or bathy-<region>-vX.Y.Z. Succeeds only if
# regions/<region>.toml has <pack>_version = "X.Y.Z"; then prints
# PACK=<pack> REGION=<region> VERSION=<version>.
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 TAG" >&2
    exit 2
fi

tag="$1"
re='^(charts|bathy)-([a-z0-9-]+)-v([0-9]+\.[0-9]+\.[0-9]+)$'
if [[ ! "$tag" =~ $re ]]; then
    echo "tag $tag does not match charts-<region>-vX.Y.Z or bathy-<region>-vX.Y.Z" >&2
    exit 1
fi
pack="${BASH_REMATCH[1]}"
region="${BASH_REMATCH[2]}"
tag_version="${BASH_REMATCH[3]}"

file="$(cd "$(dirname "$0")/.." && pwd)/regions/$region.toml"
if [ ! -f "$file" ]; then
    echo "no region file $file for tag $tag" >&2
    exit 1
fi

file_version="$(sed -n -E "s/^[[:space:]]*${pack}_version[[:space:]]*=[[:space:]]*\"([0-9]+\.[0-9]+\.[0-9]+)\".*$/\1/p" "$file" | head -n1)"
if [ -z "$file_version" ]; then
    echo "no ${pack}_version in $file" >&2
    exit 1
fi

if [ "$tag_version" != "$file_version" ]; then
    echo "MISMATCH: tag $tag is version $tag_version but $file has ${pack}_version $file_version" >&2
    exit 1
fi
echo "PACK=$pack REGION=$region VERSION=$file_version"
