#!/usr/bin/env bash
# Runs the plotter against n2kd replaying an N2K log. Builds nothing: build n2kd (build/) and the
# plotter (build-plotter/) first. Usage, from anywhere:
#   plotter/tools/run-dev.sh [FIXTURE] [extra cheekyplotter args...]
# PACKS: $CM_PACKS_DIR when set, else a temp dir of symlinks to the puget-north packs in
# chartpack/work (worktrees have no chartpack/work: set CM_PACKS_DIR there).
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
FIXTURE=${1:-$ROOT/plotter/tests/fixtures/n2k/everett-pt-townsend.log}
shift || true

TMP=$(mktemp -d)
N2KD_PID=
cleanup() {
    if [[ -n $N2KD_PID ]]; then kill "$N2KD_PID" 2>/dev/null || true; wait "$N2KD_PID" 2>/dev/null || true; fi
    rm -rf "$TMP"
}
trap cleanup EXIT

if [[ -n ${CM_PACKS_DIR:-} ]]; then
    PACKS=$CM_PACKS_DIR
else
    PACKS=$TMP/packs
    mkdir -p "$PACKS"
    ln -s "$ROOT/chartpack/work/charts/charts-puget-north-1.0.0" "$PACKS/"
    ln -s "$ROOT/chartpack/work/bathy/bathy-puget-north-1.0.0" "$PACKS/"
fi

"$ROOT/build/n2kd/n2kd" --replay "$FIXTURE" --speed 1 --socket "$TMP/n2k.sock" \
    --pgns "$ROOT/third_party/canboat/canboat.json" &
N2KD_PID=$!

"$ROOT/build-plotter/plotter/cheekyplotter" --socket "$TMP/n2k.sock" --packs "$PACKS" --data "$TMP/data" \
    --window 1024x600 "$@"
