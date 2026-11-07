#!/usr/bin/env bash
# CheekyMarine installer. Test hooks (environment): CM_SOURCE_ONLY (source without running),
# CM_LOCK_FILE (replaces the embedded lock).
set -euo pipefail

# BEGIN LOCK
CM_LOCK=$(cat <<'LOCK'
# CheekyMarine set lock. Format: see installer/README.md.
schema=1
set=0.1.0
n2kd.version=0.1.0
n2kd.tag=v0.1.0
n2kd.asset=n2kd-0.1.0-x86_64.tar.gz
n2kd.sha256=0000000000000000000000000000000000000000000000000000000000000000
charts.version=1.1.0
charts.tag=charts-puget-north-v1.1.0
charts.asset=charts-puget-north-1.1.0.tar
charts.sha256=0000000000000000000000000000000000000000000000000000000000000000
charts.schema=1
bathy.version=1.1.0
bathy.tag=bathy-puget-north-v1.1.0
bathy.asset=bathy-puget-north-1.1.0.tar
bathy.sha256=0000000000000000000000000000000000000000000000000000000000000000
bathy.schema=1
plotter.version=0.1.0
plotter.tag=plotter-v0.1.0
plotter.asset=cheekyplotter-0.1.0-x86_64.tar.gz
plotter.sha256=0000000000000000000000000000000000000000000000000000000000000000
plotter.pack_schema_min=1
plotter.pack_schema_max=1
LOCK
)
# END LOCK

# lock_get KEY: value of KEY from $CM_LOCK_FILE if set, else the embedded $CM_LOCK.
lock_get() {
  if [ -n "${CM_LOCK_FILE:-}" ]; then
    awk -F= -v k="$1" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$CM_LOCK_FILE"
  else
    printf '%s\n' "$CM_LOCK" | awk -F= -v k="$1" '$1==k {sub(/^[^=]*=/, ""); print; exit}'
  fi
}
