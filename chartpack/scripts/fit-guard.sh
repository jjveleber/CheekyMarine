#!/usr/bin/env bash
# Usage: fit-guard.sh OUT_JSON -- CMD...
# Runs CMD under `time -v` while a background loop samples the free space of the work volume,
# then writes {"max_rss_kb", "elapsed_s", "min_disk_free_kb"} to OUT_JSON. Exits 1 with
# "runner fit: <what> over the limit" when max RSS > 12 GiB, free disk dropped under 2 GiB,
# or elapsed > 5 h. Otherwise exits with CMD's status.
# Env: CM_WORK volume to sample (default .), CM_SAMPLE_S sample interval in seconds (default 10),
# CM_TIME time binary (default /usr/bin/time), CM_DF df binary (default df); the last three
# exist for the tests.
set -uo pipefail

if [ $# -lt 3 ] || [ "$2" != "--" ]; then
    echo "usage: $0 OUT_JSON -- CMD..." >&2
    exit 2
fi
out="$1"
shift 2

MAX_RSS_KB=12582912
MIN_FREE_KB=2097152
MAX_ELAPSED_S=18000
work="${CM_WORK:-.}"
tmp="$(mktemp -d)"
trap '[ -n "${sampler:-}" ] && kill "$sampler" 2>/dev/null; rm -rf "$tmp"' EXIT

free_kb() { "${CM_DF:-df}" -Pk "$work" | awk 'NR==2 {print $4}'; }
sample() {
    local f
    f="$(free_kb)"
    if [ -n "$f" ] && { [ ! -s "$tmp/min" ] || [ "$f" -lt "$(cat "$tmp/min")" ]; }; then
        echo "$f" > "$tmp/min"
    fi
}

sample
# The sleep runs in the background and the TERM trap kills it, so no orphan holds the step's output open.
(
    trap '[ -n "${nap:-}" ] && kill "$nap" 2>/dev/null; exit 0' TERM
    while :; do
        sleep "${CM_SAMPLE_S:-10}" &
        nap=$!
        wait "$nap"
        sample
    done
) &
sampler=$!

start=$SECONDS
"${CM_TIME:-/usr/bin/time}" -v -o "$tmp/time" "$@"
rc=$?
elapsed=$((SECONDS - start))
kill "$sampler" 2>/dev/null
wait "$sampler" 2>/dev/null
sample

rss="$(awk -F: '/Maximum resident set size/ {gsub(/[ \t]/, "", $2); print $2}' "$tmp/time" 2>/dev/null)"
rss="${rss:-0}"
min_free="$(cat "$tmp/min" 2>/dev/null || echo 0)"
printf '{"max_rss_kb": %s, "elapsed_s": %s, "min_disk_free_kb": %s}\n' "$rss" "$elapsed" "$min_free" > "$out"

cat "$out"
bad=0
[ "$rss" -gt "$MAX_RSS_KB" ] && { echo "runner fit: max RSS over the limit ($rss kB > $MAX_RSS_KB kB)" >&2; bad=1; }
[ "$min_free" -lt "$MIN_FREE_KB" ] && { echo "runner fit: disk use over the limit (free fell to $min_free kB < $MIN_FREE_KB kB)" >&2; bad=1; }
[ "$elapsed" -gt "$MAX_ELAPSED_S" ] && { echo "runner fit: elapsed time over the limit ($elapsed s > $MAX_ELAPSED_S s)" >&2; bad=1; }
[ "$bad" -eq 1 ] && exit 1
exit "$rc"
