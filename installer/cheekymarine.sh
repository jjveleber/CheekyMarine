#!/usr/bin/env bash
# CheekyMarine installer: install-cheekymarine.sh (install) and /opt/cheekymarine/bin/cheekymarine
# (install, rollback, version). Run with sudo on Ubuntu 24.04 or newer, x86_64.
#
# Test hooks (environment, for installer/tests only):
#   CM_ROOT         path prefix for every system path (also skips the root check)
#   CM_BASE_URL     replaces the GitHub release download base (file:// works)
#   CM_LOCK_FILE    replaces the embedded lock
#   CM_TTY          replaces /dev/tty; a path that does not exist means "no terminal"
#   CM_SOURCE_ONLY  when set, sourcing defines the functions without running main
#   CM_TEST_DIE_AT  before_flip or after_flip: the script kills itself (kill -9) at that point
set -euo pipefail
umask 022

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

# die MSG: print `cheekymarine: MSG` to stderr and exit 1.
die() {
  printf 'cheekymarine: %s\n' "$*" >&2
  exit 1
}

# p PATH: the real path for a production PATH ($CM_ROOT prefix in tests).
p() {
  printf '%s%s\n' "${CM_ROOT:-}" "$1"
}

# lock_file_get FILE KEY: value of KEY in the lock file FILE.
lock_file_get() {
  awk -F= -v k="$2" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$1"
}

# os_release_get KEY: value of KEY in os-release, quotes removed.
os_release_get() {
  awk -F= -v k="$1" '$1==k {v=$0; sub(/^[^=]*=/, "", v); gsub(/^["'"'"']|["'"'"']$/, "", v); print v; exit}' \
    "$(p /etc/os-release)"
}

# preflight: Ubuntu 24.04 or newer, x86_64, root through sudo. Sets CM_USER and CM_HOME.
preflight() {
  local id ver arch
  [ -r "$(p /etc/os-release)" ] || die "cannot read /etc/os-release; this installer needs Ubuntu 24.04 or newer"
  id=$(os_release_get ID)
  ver=$(os_release_get VERSION_ID)
  if [ "$id" != ubuntu ] || [ "$(printf '%s\n' 24.04 "$ver" | sort -V | head -n 1)" != 24.04 ]; then
    die "this installer needs Ubuntu 24.04 or newer; this system is ${id:-unknown} ${ver:-unknown}"
  fi
  arch=$(uname -m)
  [ "$arch" = x86_64 ] || die "this installer needs an x86_64 machine; this one is $arch"
  if [ -z "${CM_ROOT:-}" ] && [ "$EUID" -ne 0 ]; then
    die "run this installer with sudo, for example: curl -fsSL <url> | sudo bash"
  fi
  if [ -z "${SUDO_USER:-}" ] || [ "$SUDO_USER" = root ]; then
    die "run this installer with sudo from the desktop user's account, not as root"
  fi
  CM_USER=$SUDO_USER
  CM_HOME=$(getent passwd "$CM_USER" | cut -d: -f6)
  [ -n "$CM_HOME" ] || die "cannot find the home directory of user $CM_USER"
}

# take_lock: hold the install lock (fd 9) until exit; refuse when another run holds it.
take_lock() {
  local f
  f=$(p /run/cheekymarine-install.lock)
  mkdir -p "$(dirname "$f")"
  exec 9> "$f"
  flock -n 9 || die "another CheekyMarine install or rollback is running; wait for it to finish, then try again"
}

# base_url: the release download base.
base_url() {
  printf '%s\n' "${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}"
}

# fetch_file URL DEST WHAT: download URL to DEST, or die `download failed: WHAT URL`.
fetch_file() {
  curl -fL --retry 3 -sS -o "$2" "$1" || die "download failed: $3 $1"
}

# check_sum FILE WANT WHAT NAME: die `checksum mismatch: WHAT NAME` unless FILE hashes to WANT.
check_sum() {
  local got
  got=$(sha256sum "$1" | cut -d' ' -f1)
  [ "$got" = "$2" ] || die "checksum mismatch: $3 $4"
}

# fetch_parts STAGE_DIR: download and verify every part of the set, and the set's own script.
# A pack already in the store (dir plus a sidecar equal to the lock's sha256) is skipped.
fetch_parts() {
  local stage=$1 base part asset want name set
  base=$(base_url)
  set=$(lock_get set)
  for part in n2kd charts bathy plotter; do
    asset=$(lock_get "$part.asset")
    want=$(lock_get "$part.sha256")
    case "$asset" in
      *.tar)
        name=${asset%.tar}
        if [ -d "$(p /opt/cheekymarine/packs)/$name" ] \
          && [ "$(cat "$(p /opt/cheekymarine/packs)/$name.sha256" 2>/dev/null || true)" = "$want" ]; then
          continue
        fi
        ;;
    esac
    fetch_file "$base/$(lock_get "$part.tag")/$asset" "$stage/$asset" "$part"
    check_sum "$stage/$asset" "$want" "$part" "$asset"
  done
  fetch_file "$base/cheekymarine-v$set/SHA256SUMS" "$stage/SHA256SUMS" set
  fetch_file "$base/cheekymarine-v$set/install-cheekymarine.sh" "$stage/install-cheekymarine.sh" set
  want=$(awk '$2=="install-cheekymarine.sh" {print $1; exit}' "$stage/SHA256SUMS")
  check_sum "$stage/install-cheekymarine.sh" "$want" set install-cheekymarine.sh
}

# lock_text: the lock this script installs ($CM_LOCK_FILE or the embedded one).
lock_text() {
  if [ -n "${CM_LOCK_FILE:-}" ]; then cat "$CM_LOCK_FILE"; else printf '%s\n' "$CM_LOCK"; fi
}

# utc_stamp: the current time as yyyymmddThhmmssZ (UTC).
utc_stamp() {
  date -u +%Y%m%dT%H%M%SZ
}

# unique_name DIR PREFIX SUFFIX: print PREFIX<stamp>SUFFIX for a name not yet in DIR. When the
# name of this second is taken (a rerun within one second), wait for the next second, so names
# stay plain and sort by time.
unique_name() {
  local n
  n="$2$(utc_stamp)$3"
  while [ -e "$1/$n" ] || [ -L "$1/$n" ]; do
    sleep 1
    n="$2$(utc_stamp)$3"
  done
  printf '%s\n' "$n"
}

# pack_name PART: the store name of a pack part (its asset without .tar).
pack_name() {
  local asset
  asset=$(lock_get "$1.asset")
  printf '%s\n' "${asset%.tar}"
}

# pack_in_store NAME WANT: true when the store holds pack NAME with a sidecar equal to WANT.
pack_in_store() {
  local store
  store=$(p /opt/cheekymarine/packs)
  [ -d "$store/$1" ] && [ "$(cat "$store/$1.sha256" 2>/dev/null || true)" = "$2" ]
}

# unpack_set STAGE_DIR SET: unpack the set into a fresh sets/<SET>.<stamp> and set CM_SET_DIR to
# it. n2kd and the plotter go into the set dir; a downloaded pack goes into the store through a
# .tmp- dir and one rename, then gets its sidecar. The set dir links each pack from the store.
unpack_set() {
  local stage=$1 setver=$2 sets store d part name want
  sets=$(p /opt/cheekymarine/sets)
  store=$(p /opt/cheekymarine/packs)
  mkdir -p "$sets" "$store"
  d="$sets/$(unique_name "$sets" "$setver." "")"
  mkdir "$d" "$d/n2kd" "$d/plotter" "$d/packs"
  tar -xzf "$stage/$(lock_get n2kd.asset)" -C "$d/n2kd" --strip-components=1
  tar -xzf "$stage/$(lock_get plotter.asset)" -C "$d/plotter" --strip-components=1
  rm -rf "$store"/.tmp-*
  for part in charts bathy; do
    name=$(pack_name "$part")
    want=$(lock_get "$part.sha256")
    if ! pack_in_store "$name" "$want"; then
      rm -rf "${store:?}/$name" "$store/$name.sha256"
      mkdir "$store/.tmp-$name"
      tar -xf "$stage/$(lock_get "$part.asset")" -C "$store/.tmp-$name" --strip-components=1
      mv -T "$store/.tmp-$name" "$store/$name"
      printf '%s\n' "$want" > "$store/$name.sha256"
    fi
    ln -s "../../../packs/$name" "$d/packs/$name"
  done
  lock_text > "$d/cheekymarine.lock"
  cp "$stage/install-cheekymarine.sh" "$d/cheekymarine.sh"
  chmod 755 "$d/cheekymarine.sh"
  CM_SET_DIR=$d
}

# check_pack_schema DIR: each pack's manifest schema and the plotter's PACK_SCHEMA range in set
# DIR must equal the lock, else die `pack schema mismatch: <detail>`.
check_pack_schema() {
  local d=$1 part name want got key
  for part in charts bathy; do
    name=$(pack_name "$part")
    want=$(lock_get "$part.schema")
    got=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["schema"])' \
      "$d/packs/$name/manifest.json" 2>/dev/null) || got=
    [ "$got" = "$want" ] \
      || die "pack schema mismatch: $name manifest.json schema is ${got:-unreadable}, the lock says $want"
  done
  for key in min max; do
    want=$(lock_get "plotter.pack_schema_$key")
    got=$(lock_file_get "$d/plotter/PACK_SCHEMA" "$key" 2>/dev/null) || got=
    [ "$got" = "$want" ] \
      || die "pack schema mismatch: plotter PACK_SCHEMA $key is ${got:-unreadable}, the lock says $want"
  done
}

# install_sysusers DIR: install set DIR's sysusers file (Task 5).
install_sysusers() {
  :
}

# install_n2kd_unit DIR: install set DIR's n2kd unit to /etc/systemd/system, daemon-reload when
# it changed. Minimal for now: Task 5 rewrites ExecStart to run through `current`.
install_n2kd_unit() {
  local src=$1/n2kd/usr/lib/systemd/system/n2kd.service dst
  dst=$(p /etc/systemd/system/n2kd.service)
  if ! cmp -s "$src" "$dst"; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst.tmp"
    mv -T "$dst.tmp" "$dst"
    systemctl daemon-reload
  fi
}

stop_n2kd() {
  if systemctl is-active --quiet n2kd; then systemctl stop n2kd; fi
}

start_n2kd() {
  systemctl start n2kd
}

# stop_plotter: SIGTERM the desktop user's plotter, wait up to 10 s for it to exit, then SIGKILL.
stop_plotter() {
  local i=0
  pkill -TERM -u "$CM_USER" -x cheekyplotter || true
  while [ "$i" -lt 20 ] && pgrep -u "$CM_USER" -x cheekyplotter > /dev/null; do
    sleep 0.5
    i=$((i + 1))
  done
  pkill -KILL -u "$CM_USER" -x cheekyplotter || true
}

# start_plotter: start the plotter in the desktop user's session (Task 5 completes this).
start_plotter() {
  systemd-run --user --machine="$CM_USER@" --collect /opt/cheekymarine/bin/cheekyplotter
}

# label_get KEY: KEY (set or plotter) from db-label, empty when there is no label.
label_get() {
  local f
  f=$(p /var/lib/cheekymarine/db-label)
  [ -f "$f" ] || return 0
  lock_file_get "$f" "$1"
}

# data_rule FROM_PLOTTER_VER TO_PLOTTER_VER TO_SET: with the plotter stopped, copy the live
# plotter.db (labeled with its set from db-label), keep it when TO's plotter is the same or newer,
# else restore the newest copy labeled TO_SET or move it aside; then label it for TO_SET. A db
# with no label counts as unknown and newer.
data_rule() {
  local from=$1 to=$2 toset=$3 db label copies fromset base sfx newest f n
  db=$(p "$CM_HOME/.local/share/cheekyplotter/plotter.db")
  label=$(p /var/lib/cheekymarine/db-label)
  copies=$(p /var/lib/cheekymarine/db-copies)
  mkdir -p "$copies"
  if [ -f "$db" ]; then
    if [ -f "$label" ]; then fromset=$(label_get set); else fromset=unknown from=; fi
    base="$copies/$(unique_name "$copies" "plotter-$fromset-" .db)"
    for sfx in "" -wal -shm; do
      [ ! -f "$db$sfx" ] || cp -p "$db$sfx" "$base$sfx"
    done
    if [ -z "$from" ] || [ "$(printf '%s\n' "$from" "$to" | sort -V | tail -n 1)" != "$to" ]; then
      rm -f "$db" "$db-wal" "$db-shm"
      if [ "$fromset" != unknown ]; then
        newest=
        for f in "$copies/plotter-$toset-"*.db; do
          n=${f##*/}
          n=${n#"plotter-$toset-"}
          # the glob sorts, and stamps sort by time; skip names of other sets like <toset>-rc1
          if [[ $n =~ ^[0-9]{8}T[0-9]{6}Z\.db$ ]]; then newest=${f##*/}; fi
        done
        if [ -n "$newest" ]; then
          for sfx in "" -wal -shm; do
            if [ -f "$copies/$newest$sfx" ]; then
              cp -p "$copies/$newest$sfx" "$db$sfx"
              chown "$CM_USER:" "$db$sfx"
            fi
          done
        fi
      fi
    fi
  fi
  printf 'set=%s\nplotter=%s\n' "$toset" "$to" > "$label.tmp"
  mv -T "$label.tmp" "$label"
}

# switch_to DIR: the switch to set DIR (design "The switch"). Stop, data rule, `previous` (only
# when the set version changes), the atomic `current` flip, bin/cheekymarine, then the starts.
switch_to() {
  local dir=$1 root name toset
  root=$(p /opt/cheekymarine)
  name=$(basename "$dir")
  toset=$(lock_file_get "$dir/cheekymarine.lock" set)
  stop_plotter
  stop_n2kd
  data_rule "$(label_get plotter)" "$(lock_file_get "$dir/cheekymarine.lock" plotter.version)" "$toset"
  if [ -f "$root/current/cheekymarine.lock" ] \
    && [ "$(lock_file_get "$root/current/cheekymarine.lock" set)" != "$toset" ]; then
    ln -sfn "$(readlink "$root/current")" "$root/previous.tmp"
    mv -T "$root/previous.tmp" "$root/previous"
  fi
  [ "${CM_TEST_DIE_AT:-}" != before_flip ] || kill -9 $$
  (cd "$root" && ln -sfn "sets/$name" current.tmp && mv -T current.tmp current)
  [ "${CM_TEST_DIE_AT:-}" != after_flip ] || kill -9 $$
  mkdir -p "$root/bin"
  cp "$root/current/cheekymarine.sh" "$root/bin/cheekymarine.tmp"
  chmod 755 "$root/bin/cheekymarine.tmp"
  mv -T "$root/bin/cheekymarine.tmp" "$root/bin/cheekymarine"
  install_n2kd_unit "$root/current"
  start_n2kd
  start_plotter
}

# in_list WORD LIST: true when WORD is a line of LIST.
in_list() {
  printf '%s\n' "$2" | grep -qxF -- "$1"
}

# prune_sets: delete set dirs other than the targets of `current` and `previous`, then store
# packs (with their sidecars) that neither of those two sets links to.
prune_sets() {
  local root keep= links= l f n
  root=$(p /opt/cheekymarine)
  for l in current previous; do
    [ -L "$root/$l" ] || continue
    n=$(basename "$(readlink "$root/$l")")
    keep="$keep$n"$'\n'
    for f in "$root/sets/$n/packs"/*; do
      [ -L "$f" ] || continue
      links="$links$(basename "$(readlink "$f")")"$'\n'
    done
  done
  for f in "$root/sets"/*; do
    [ -e "$f" ] || [ -L "$f" ] || continue
    in_list "$(basename "$f")" "$keep" || rm -rf "$f"
  done
  for f in "$root/packs"/*; do
    [ -e "$f" ] || [ -L "$f" ] || continue
    n=$(basename "$f")
    in_list "${n%.sha256}" "$links" || rm -rf "$f"
  done
}

cmd_install() {
  preflight
  take_lock
  CM_STAGE=$(p "/opt/cheekymarine/.stage-$(lock_get set)")
  rm -rf "$CM_STAGE"
  mkdir -p "$CM_STAGE"
  trap 'rm -rf "$CM_STAGE"' EXIT
  fetch_parts "$CM_STAGE"
  unpack_set "$CM_STAGE" "$(lock_get set)"
  rm -rf "$CM_STAGE"
  check_pack_schema "$CM_SET_DIR"
  install_sysusers "$CM_SET_DIR"
  switch_to "$CM_SET_DIR"
  prune_sets
  cmd_version
}

cmd_rollback() {
  preflight
  take_lock
  echo "cheekymarine: rollback is not implemented yet"
}

# cmd_version: the installed set and its parts, and this script's set when it differs.
cmd_version() {
  local lock installed=none part
  lock="$(p /opt/cheekymarine/current)/cheekymarine.lock"
  if [ -f "$lock" ]; then
    installed=$(lock_file_get "$lock" set)
    echo "installed: $installed"
    for part in n2kd charts bathy plotter; do
      echo "  $part: $(lock_file_get "$lock" "$part.version")"
    done
  else
    echo "installed: none"
  fi
  if [ "$(lock_get set)" != "$installed" ]; then
    echo "this script installs: $(lock_get set)"
  fi
}

# main [COMMAND]: install, rollback or version. With no command: install, except when run as
# `cheekymarine` (the installed command), which needs one.
main() {
  local cmd=${1:-}
  if [ -z "$cmd" ]; then
    [ "$(basename -- "$0")" != cheekymarine ] || die "usage: cheekymarine install|rollback|version"
    cmd=install
  else
    shift
  fi
  case "$cmd" in
    install) cmd_install "$@" ;;
    rollback) cmd_rollback "$@" ;;
    version) cmd_version "$@" ;;
    *) die "unknown command: $cmd (use install, rollback or version)" ;;
  esac
}

if [ -z "${CM_SOURCE_ONLY:-}" ]; then
  main "$@"
fi
