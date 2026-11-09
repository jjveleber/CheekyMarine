#!/usr/bin/env bash
# lock-tool.sh check|fill LOCK, embed LOCK SCRIPT OUT. See installer/README.md.
set -euo pipefail

BASE="${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}"

lock_packs() { # LOCK -> pack ids on stdout, in lock order
  awk -F= '$1 ~ /^pack\..+\.version$/ {id=$1; sub(/^pack\./, "", id); sub(/\.version$/, "", id); print id}' "$1"
}

lock_parts() { # LOCK -> lock key prefixes of every part: n2kd, pack.<id>..., plotter
  local id
  echo n2kd
  for id in $(lock_packs "$1"); do echo "pack.$id"; done
  echo plotter
}

get() { # FILE KEY
  awk -F= -v k="$2" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$1"
}

sums_line() { # PART TAG ASSET -> sha256 on stdout
  local part=$1 tag=$2 asset=$3 sums
  sums=$(curl -fsSL "$BASE/$tag/SHA256SUMS") || { echo "lock-tool: $part: cannot fetch $BASE/$tag/SHA256SUMS" >&2; return 1; }
  printf '%s\n' "$sums" | awk -v a="$asset" '{n=$2; sub(/^\*/, "", n)} n==a {print $1; exit}'
}

cmd_check() {
  local lock=$1 part rc=0 min max sch want have id kind prev key ids
  ids=$(lock_packs "$lock")
  if ! printf '%s\n' "$ids" | grep -q '^charts-'; then
    echo "lock-tool: no charts pack in the lock" >&2
    rc=1
  fi
  for key in plotter.pack_schema_min plotter.pack_schema_max; do
    if ! [[ $(get "$lock" "$key") =~ ^[0-9]+$ ]]; then
      echo "lock-tool: $key is missing or not a whole number" >&2
      rc=1
    fi
  done
  for id in $ids; do
    if ! [[ $(get "$lock" "pack.$id.schema") =~ ^[0-9]+$ ]]; then
      echo "lock-tool: pack.$id.schema is missing or not a whole number" >&2
      rc=1
    fi
  done
  [ "$rc" -eq 0 ] || return 1
  min=$(get "$lock" plotter.pack_schema_min); max=$(get "$lock" plotter.pack_schema_max)
  for id in $ids; do
    sch=$(get "$lock" "pack.$id.schema")
    if [ "$sch" -lt "$min" ] || [ "$sch" -gt "$max" ]; then
      echo "lock-tool: $id: schema $sch outside plotter range $min..$max" >&2
      rc=1
    fi
  done
  # spec 5.4: all packs of one kind share one schema
  for kind in $(printf '%s\n' "$ids" | sed 's/-.*//' | sort -u); do
    prev=
    for id in $ids; do
      [ "${id%%-*}" = "$kind" ] || continue
      sch=$(get "$lock" "pack.$id.schema")
      if [ -n "$prev" ] && [ "$sch" != "$prev" ]; then
        echo "lock-tool: $kind packs have mixed schemas ($prev and $sch)" >&2
        rc=1
        break
      fi
      prev=$sch
    done
  done
  [ "$rc" -eq 0 ] || return 1
  for part in $(lock_parts "$lock"); do
    want=$(get "$lock" "$part.sha256")
    have=$(sums_line "${part#pack.}" "$(get "$lock" "$part.tag")" "$(get "$lock" "$part.asset")") || return 1
    if [ -z "$have" ]; then
      echo "lock-tool: ${part#pack.}: asset $(get "$lock" "$part.asset") not in SHA256SUMS" >&2
      rc=1
    elif [ "$have" != "$want" ]; then
      echo "lock-tool: ${part#pack.}: sha256 mismatch (lock $want, release $have)" >&2
      rc=1
    fi
  done
  return "$rc"
}

cmd_fill() {
  local lock=$1 part have tmp
  tmp=$(mktemp)
  cp "$lock" "$tmp"
  for part in $(lock_parts "$lock"); do
    have=$(sums_line "${part#pack.}" "$(get "$lock" "$part.tag")" "$(get "$lock" "$part.asset")") || { rm -f "$tmp"; return 1; }
    if [ -z "$have" ]; then
      echo "lock-tool: ${part#pack.}: asset not in SHA256SUMS" >&2; rm -f "$tmp"; return 1
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
