# Sourced by every shim. Shims stand in for system commands in installer tests: each logs
# `name args` to $CM_ROOT/calls and keeps tiny state in $CM_ROOT/shim-state. They refuse to run
# without CM_ROOT so a test can never touch the real system.
[ -n "${CM_ROOT:-}" ] || { echo "shim: CM_ROOT is not set" >&2; exit 99; }
SHIM_NAME=$(basename "$0")
SHIM_DIR=$(cd "$(dirname "$0")" && pwd)
STATE="$CM_ROOT/shim-state"
mkdir -p "$STATE"
printf '%s\n' "$SHIM_NAME${*:+ $*}" >> "$CM_ROOT/calls"

# real_path: PATH without the shim dir, to reach the real command.
real_path() {
  local IFS=: d out=
  for d in $PATH; do [ "$d" = "$SHIM_DIR" ] || out="${out:+$out:}$d"; done
  printf '%s\n' "$out"
}
