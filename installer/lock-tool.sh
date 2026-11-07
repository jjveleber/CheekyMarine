#!/usr/bin/env bash
# lock-tool.sh check|fill LOCK, embed LOCK SCRIPT OUT. See installer/README.md.
set -euo pipefail

BASE="${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}"
PARTS="n2kd charts bathy plotter"

get() { # FILE KEY
  awk -F= -v k="$2" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$1"
}

sums_line() { # PART TAG ASSET -> sha256 on stdout
  local part=$1 tag=$2 asset=$3 sums
  sums=$(curl -fsSL "$BASE/$tag/SHA256SUMS") || { echo "lock-tool: $part: cannot fetch $BASE/$tag/SHA256SUMS" >&2; return 1; }
  printf '%s\n' "$sums" | awk -v a="$asset" '{n=$2; sub(/^\*/, "", n)} n==a {print $1; exit}'
}

cmd_check() {
  local lock=$1 part rc=0 min max sch want have key
  for key in charts.schema bathy.schema plotter.pack_schema_min plotter.pack_schema_max; do
    if ! [[ $(get "$lock" "$key") =~ ^[0-9]+$ ]]; then
      echo "lock-tool: $key is missing or not a whole number" >&2
      rc=1
    fi
  done
  [ "$rc" -eq 0 ] || return 1
  min=$(get "$lock" plotter.pack_schema_min); max=$(get "$lock" plotter.pack_schema_max)
  for part in charts bathy; do
    sch=$(get "$lock" "$part.schema")
    if [ "$sch" -lt "$min" ] || [ "$sch" -gt "$max" ]; then
      echo "lock-tool: $part: schema $sch outside plotter range $min..$max" >&2
      rc=1
    fi
  done
  [ "$rc" -eq 0 ] || return 1
  for part in $PARTS; do
    want=$(get "$lock" "$part.sha256")
    have=$(sums_line "$part" "$(get "$lock" "$part.tag")" "$(get "$lock" "$part.asset")") || return 1
    if [ -z "$have" ]; then
      echo "lock-tool: $part: asset $(get "$lock" "$part.asset") not in SHA256SUMS" >&2
      rc=1
    elif [ "$have" != "$want" ]; then
      echo "lock-tool: $part: sha256 mismatch (lock $want, release $have)" >&2
      rc=1
    fi
  done
  return "$rc"
}

cmd_fill() {
  local lock=$1 part have tmp
  tmp=$(mktemp)
  cp "$lock" "$tmp"
  for part in $PARTS; do
    have=$(sums_line "$part" "$(get "$lock" "$part.tag")" "$(get "$lock" "$part.asset")") || { rm -f "$tmp"; return 1; }
    if [ -z "$have" ]; then
      echo "lock-tool: $part: asset not in SHA256SUMS" >&2; rm -f "$tmp"; return 1
    fi
    awk -v k="$part.sha256" -v v="$have" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' "$tmp" > "$tmp.new"
    mv "$tmp.new" "$tmp"
  done
  cat "$tmp" > "$lock"
  rm -f "$tmp"
}

cmd_embed() {
  local lock=$1 script=$2 out=$3
  awk -v lockfile="$lock" '
    skip && $0 == "LOCK" { skip = 0 }
    !skip { print }
    $0 == "CM_LOCK=$(cat <<'"'"'LOCK'"'"'" { skip = 1; while ((getline l < lockfile) > 0) print l }
  ' "$script" > "$out"
}

case "${1:-}" in
  check) [ $# -eq 2 ] || { echo "usage: $0 check LOCK" >&2; exit 2; }; cmd_check "$2" ;;
  fill)  [ $# -eq 2 ] || { echo "usage: $0 fill LOCK" >&2; exit 2; }; cmd_fill "$2" ;;
  embed) [ $# -eq 4 ] || { echo "usage: $0 embed LOCK SCRIPT OUT" >&2; exit 2; }; cmd_embed "$2" "$3" "$4" ;;
  *) echo "usage: $0 check|fill LOCK | embed LOCK SCRIPT OUT" >&2; exit 2 ;;
esac
