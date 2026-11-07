#!/usr/bin/env bash
# Usage: test_bundle_plotter.sh TARBALL [IMAGE...]
# Checks a plotter bundle made by scripts/bundle-plotter.sh:
#   (a) no denylisted (GPL-only Qt) path in the tarball,
#   (b) every file has a MANIFEST line with a license, and PACK_SCHEMA matches plotter/CMakeLists.txt,
#   (c) bin/cheekyplotter has the classic RPATH $ORIGIN/../lib and no RUNPATH,
#   (d) in a clean container per IMAGE (default ubuntu:24.04) with only CM_APT_PACKAGES from
#       installer/cheekymarine.sh installed (plus xvfb, xauth, libgl1-mesa-dri for the test), ldd
#       finds every library of the binary, the plugins and the QML plugins, and the plotter starts
#       under xvfb-run, logs "ready in" and exits 0.
# Exit 0 when every check passes; otherwise print each failure and exit 1.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 TARBALL [IMAGE...]" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/../.." && pwd)"
tarball="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
shift
images=("$@")
[ ${#images[@]} -gt 0 ] || images=(ubuntu:24.04)

DENY='VirtualKeyboard|virtualkeyboard|QtCharts|Charts|DataVisualization|Quick3DPhysics'
fail=0
bad() { echo "FAIL: $*"; fail=1; }
ok() { echo "ok: $*"; }

top="$(basename "$tarball" .tar.gz)"
case "$top" in
    cheekyplotter-*-x86_64) ;;
    *) echo "FAIL: $tarball is not named cheekyplotter-VERSION-x86_64.tar.gz"; exit 1 ;;
esac

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
tar -xzf "$tarball" -C "$work"
tops="$(ls -A "$work")"
if [ "$tops" != "$top" ]; then
    echo "FAIL: tarball top level is '$tops', expected exactly $top/"
    exit 1
fi
b="$work/$top"

# (a) denylist
denied="$(tar -tzf "$tarball" | grep -E "$DENY" || true)"
if [ -n "$denied" ]; then
    while read -r p; do bad "(a) denylisted path in the tarball: $p"; done <<< "$denied"
else
    ok "(a) no denylisted path"
fi

# (b) MANIFEST covers every file, each with a license; PACK_SCHEMA matches the CMake range
if [ ! -f "$b/MANIFEST" ]; then
    bad "(b) no MANIFEST"
else
    nolic="$(awk -F'\t' 'NF < 2 || $2 == "" {print NR": "$0}' "$b/MANIFEST")"
    [ -z "$nolic" ] || while read -r l; do bad "(b) MANIFEST line without a license: $l"; done <<< "$nolic"
    files="$(cd "$b" && find . \( -type f -o -type l \) | sed 's|^\./||' | LC_ALL=C sort)"
    listed="$(cut -f1 "$b/MANIFEST" | LC_ALL=C sort)"
    missing="$(LC_ALL=C comm -23 <(echo "$files") <(echo "$listed"))"
    extra="$(LC_ALL=C comm -13 <(echo "$files") <(echo "$listed"))"
    [ -z "$missing" ] || while read -r l; do bad "(b) file not in MANIFEST: $l"; done <<< "$missing"
    [ -z "$extra" ] || while read -r l; do bad "(b) MANIFEST names a missing file: $l"; done <<< "$extra"
    [ -n "$nolic$missing$extra" ] || ok "(b) MANIFEST lists all $(echo "$files" | wc -l) files with a license"
fi
want_min="$(sed -n 's/^set(PLOTTER_PACK_SCHEMA_MIN \([0-9]*\))$/\1/p' "$root/plotter/CMakeLists.txt")"
want_max="$(sed -n 's/^set(PLOTTER_PACK_SCHEMA_MAX \([0-9]*\))$/\1/p' "$root/plotter/CMakeLists.txt")"
want="$(printf 'min=%s\nmax=%s' "$want_min" "$want_max")"
got="$(cat "$b/PACK_SCHEMA" 2>/dev/null || true)"
if [ -n "$want_min" ] && [ -n "$want_max" ] && [ "$got" = "$want" ]; then
    ok "(b) PACK_SCHEMA is min=$want_min max=$want_max"
else
    bad "(b) PACK_SCHEMA is '$got', plotter/CMakeLists.txt says '$want'"
fi

# (c) RPATH
dyn="$(readelf -d "$b/bin/cheekyplotter" 2>/dev/null || true)"
rpath="$(sed -n 's/.*(RPATH).*\[\(.*\)\]$/\1/p' <<< "$dyn")"
if [ "$rpath" = '$ORIGIN/../lib' ] && ! grep -q '(RUNPATH)' <<< "$dyn"; then
    ok "(c) RPATH is \$ORIGIN/../lib"
else
    bad "(c) bin/cheekyplotter RPATH is '$rpath' (RUNPATH: $(grep -c '(RUNPATH)' <<< "$dyn" || true)), expected \$ORIGIN/../lib"
fi

# (d) clean container: ldd, then a launch under Xvfb
apt_list="$(sed -n 's/^CM_APT_PACKAGES="\(.*\)"$/\1/p' "$root/installer/cheekymarine.sh")"
[ -n "$apt_list" ] || bad "(d) no CM_APT_PACKAGES line in installer/cheekymarine.sh"
cat > "$work/in-container.sh" <<'EOF'
set -u
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update >/dev/null && apt-get -qq install -y --no-install-recommends $APT_LIST >/dev/null 2>&1 \
    || { echo "FAIL: apt-get install of CM_APT_PACKAGES failed"; exit 1; }
apt-get -qq install -y --no-install-recommends xvfb xauth libgl1-mesa-dri >/dev/null 2>&1 \
    || { echo "FAIL: apt-get install of the test packages failed"; exit 1; }
cd /bundle
rc=0
for f in bin/cheekyplotter $(find plugins qml -name '*.so' | sort); do
    nf="$(ldd "$f" 2>&1 | grep 'not found')"
    if [ -n "$nf" ]; then
        echo "$nf" | sed "s|^|FAIL: (d) ldd $f: |"
        rc=1
    fi
done
[ $rc -eq 0 ] && echo "ok: (d) ldd finds every library ($(find plugins qml -name '*.so' | wc -l) plugins)"
data="$(mktemp -d)"
xvfb-run -a bin/cheekyplotter --window 800x480 --data "$data" --exit-after-ms 3000 > /tmp/run.log 2>&1
code=$?
if [ $code -eq 0 ] && grep -q 'ready in' /tmp/run.log; then
    echo "ok: (d) launch exit 0, $(grep -o 'ready in [0-9]* ms' /tmp/run.log)"
else
    echo "FAIL: (d) launch exit $code, log:"
    sed 's/^/    /' /tmp/run.log
    rc=1
fi
exit $rc
EOF
for image in "${images[@]}"; do
    echo "== $image"
    if docker run --rm -e APT_LIST="$apt_list" -v "$b:/bundle:ro" -v "$work/in-container.sh:/t.sh:ro" \
        "$image" bash /t.sh; then
        :
    else
        fail=1
    fi
done

if [ $fail -ne 0 ]; then
    echo "bundle test FAILED"
    exit 1
fi
echo "bundle test passed"
