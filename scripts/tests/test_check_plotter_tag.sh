#!/usr/bin/env bash
# Tests scripts/check-plotter-tag.sh against PLOTTER_VERSION in plotter/CMakeLists.txt.
set -uo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
check="$root/scripts/check-plotter-tag.sh"
ver="$(sed -n -E 's/^set\(PLOTTER_VERSION ([0-9]+\.[0-9]+\.[0-9]+)\).*/\1/p' "$root/plotter/CMakeLists.txt" | head -n1)"
fail=0
expect() { # want_status tag
    "$check" "$2" >/dev/null 2>&1
    got=$?
    if [ "$got" -eq "$1" ]; then echo "ok: $2 -> $got"; else echo "FAIL: $2 -> $got, want $1"; fail=1; fi
}
expect 0 "plotter-v$ver"
expect 1 "plotter-v9.9.9"
expect 1 "v$ver"
expect 1 "$ver"
exit "$fail"
