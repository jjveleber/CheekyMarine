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

cmd_install() {
  preflight
  take_lock
  CM_STAGE=$(p "/opt/cheekymarine/.stage-$(lock_get set)")
  rm -rf "$CM_STAGE"
  mkdir -p "$CM_STAGE"
  trap 'rm -rf "$CM_STAGE"' EXIT
  fetch_parts "$CM_STAGE"
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
