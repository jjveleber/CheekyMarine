#!/usr/bin/env bash
# Usage: package-n2kd.sh BUILD_DIR VERSION ARCH
# Creates n2kd-VERSION-ARCH.tar.gz in the current directory from the install
# tree of BUILD_DIR, which must be configured with CMAKE_INSTALL_PREFIX=/usr and
# N2K_SOURCE_PGNS_FALLBACK=OFF. Binaries are stripped.
# Layout: n2kd-VERSION-ARCH/{usr/...,LICENSE,canboat-LICENSE,nlohmann_json-LICENSE.MIT,
#         THIRD_PARTY_NOTICES,SHA256SUMS}
set -euo pipefail

if [ $# -ne 3 ]; then
    echo "usage: $0 BUILD_DIR VERSION ARCH" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(cd "$1" && pwd)"
version="$2"
arch="$3"
name="n2kd-${version}-${arch}"

prefix="$(sed -n 's/^CMAKE_INSTALL_PREFIX:PATH=//p' "$build_dir/CMakeCache.txt")"
if [ "$prefix" != "/usr" ]; then
    echo "$0: $build_dir has CMAKE_INSTALL_PREFIX=$prefix, expected /usr" >&2
    exit 1
fi

if ! grep -qx 'N2K_SOURCE_PGNS_FALLBACK:BOOL=OFF' "$build_dir/CMakeCache.txt"; then
    echo "$0: $build_dir must be configured with -DN2K_SOURCE_PGNS_FALLBACK=OFF" >&2
    exit 1
fi

rm -rf "$name"
mkdir -p "$name"
DESTDIR="$PWD/$name" cmake --install "$build_dir" --strip >/dev/null
cp "$root/LICENSE" "$name/LICENSE"
cp "$root/third_party/canboat/LICENSE" "$name/canboat-LICENSE"
cp "$root/third_party/nlohmann_json-LICENSE.MIT" "$name/nlohmann_json-LICENSE.MIT"
cp "$root/THIRD_PARTY_NOTICES" "$name/THIRD_PARTY_NOTICES"
(cd "$name" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)
tar -czf "${name}.tar.gz" --owner=0 --group=0 "$name"
rm -rf "$name"
echo "${name}.tar.gz"
