#!/usr/bin/env bash
# Usage: package-n2kd.sh BUILD_DIR VERSION ARCH
# Creates n2kd-VERSION-ARCH.tar.gz in the current directory.
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

rm -rf "$name"
mkdir -p "$name"
cp "$build_dir/n2kd/n2kd" "$name/n2kd"
cp "$root/n2kd/systemd/n2kd.service" "$name/n2kd.service"
cp "$root/third_party/canboat/canboat.json" "$name/canboat.json"
cp "$root/LICENSE" "$name/LICENSE"
cp "$root/third_party/canboat/LICENSE" "$name/canboat-LICENSE"
(cd "$name" && sha256sum n2kd n2kd.service canboat.json LICENSE canboat-LICENSE > SHA256SUMS)
tar -czf "${name}.tar.gz" "$name"
rm -rf "$name"
echo "${name}.tar.gz"
