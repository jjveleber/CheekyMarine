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
schema=2
set=0.3.0
n2kd.version=0.1.0
n2kd.tag=v0.1.0
n2kd.asset=n2kd-0.1.0-x86_64.tar.gz
n2kd.sha256=1d47e0d861aff50a5c8e02009fd8da3f46fd18cc4cbd99eb86188487e9732670
pack.charts-sound-south.version=1.0.0
pack.charts-sound-south.tag=charts-sound-south-v1.0.0
pack.charts-sound-south.asset=charts-sound-south-1.0.0.tar
pack.charts-sound-south.sha256=53526c411954083aad34f7ff63e80003e3a4298dcfd276f707186b5c4b82503a
pack.charts-sound-south.schema=2
pack.charts-sound-central.version=1.0.0
pack.charts-sound-central.tag=charts-sound-central-v1.0.0
pack.charts-sound-central.asset=charts-sound-central-1.0.0.tar
pack.charts-sound-central.sha256=cc81b89b0286852374c18c17f54a9acd6eed1908dedb24bb544ec6fe5c3c3275
pack.charts-sound-central.schema=2
pack.charts-north-sound.version=1.0.0
pack.charts-north-sound.tag=charts-north-sound-v1.0.0
pack.charts-north-sound.asset=charts-north-sound-1.0.0.tar
pack.charts-north-sound.sha256=a4b26b2e9371be8a2ef4b872f431e14e43ce5d25797e88cebd347ae4df32694d
pack.charts-north-sound.schema=2
pack.charts-strait.version=1.0.0
pack.charts-strait.tag=charts-strait-v1.0.0
pack.charts-strait.asset=charts-strait-1.0.0.tar
pack.charts-strait.sha256=496d93b1cd6edaab7a36267e9fd06434c24f794d8a316f3577e21eb09fcb2797
pack.charts-strait.schema=2
pack.charts-wa-coast.version=1.0.0
pack.charts-wa-coast.tag=charts-wa-coast-v1.0.0
pack.charts-wa-coast.asset=charts-wa-coast-1.0.0.tar
pack.charts-wa-coast.sha256=1a3f97d02ff3e91ba684ffd61fea25b511366e2963de24b0544621b6f6ef408c
pack.charts-wa-coast.schema=2
pack.charts-overview.version=1.0.0
pack.charts-overview.tag=charts-overview-v1.0.0
pack.charts-overview.asset=charts-overview-1.0.0.tar
pack.charts-overview.sha256=ae702b9def9fd0b6eab20fa038aa3f154eaeb77942406d33933b845269652207
pack.charts-overview.schema=2
pack.bathy-sound-south.version=1.0.0
pack.bathy-sound-south.tag=bathy-sound-south-v1.0.0
pack.bathy-sound-south.asset=bathy-sound-south-1.0.0.tar
pack.bathy-sound-south.sha256=b668b75cf50001874d7f63e3a31fe4fc8ef70028a97575619ec1b10b351f14be
pack.bathy-sound-south.schema=2
pack.bathy-sound-central.version=1.0.0
pack.bathy-sound-central.tag=bathy-sound-central-v1.0.0
pack.bathy-sound-central.asset=bathy-sound-central-1.0.0.tar
pack.bathy-sound-central.sha256=5cd9cf650c9b222f857eb9d24f44f1b767352183f31bd88656d979cd39809e92
pack.bathy-sound-central.schema=2
pack.bathy-north-sound.version=1.0.0
pack.bathy-north-sound.tag=bathy-north-sound-v1.0.0
pack.bathy-north-sound.asset=bathy-north-sound-1.0.0.tar
pack.bathy-north-sound.sha256=b24ce5270ed0e214cb0c635b50e8f118787ccf12fb7c6ec7f9aa8d44e7ec2f0f
pack.bathy-north-sound.schema=2
pack.bathy-strait.version=1.0.0
pack.bathy-strait.tag=bathy-strait-v1.0.0
pack.bathy-strait.asset=bathy-strait-1.0.0.tar
pack.bathy-strait.sha256=5db5a2eecda4b26d2fe00d1dced525c2eac24bf502c5f4ff37186f6f0e46342a
pack.bathy-strait.schema=2
pack.bathy-wa-coast.version=1.0.0
pack.bathy-wa-coast.tag=bathy-wa-coast-v1.0.0
pack.bathy-wa-coast.asset=bathy-wa-coast-1.0.0.tar
pack.bathy-wa-coast.sha256=e9130991743d262bf88286d1960107b33cc3bf9f00afaebbb9c7ef2bf2faae0d
pack.bathy-wa-coast.schema=2
pack.bathy-overview.version=1.0.0
pack.bathy-overview.tag=bathy-overview-v1.0.0
pack.bathy-overview.asset=bathy-overview-1.0.0.tar
pack.bathy-overview.sha256=4700a2c048c79584e956eaae01188a5ad076015e3e3fc6d41d6a16f21e8f4a4b
pack.bathy-overview.schema=2
plotter.version=0.3.0
plotter.tag=plotter-v0.3.0
plotter.asset=cheekyplotter-0.3.0-x86_64.tar.gz
plotter.sha256=fd608a14b05937c3a39152b9dcda5d6afbed4c27e52ce8689daf118a1162b529
plotter.pack_schema_min=2
plotter.pack_schema_max=2
LOCK
)
# END LOCK

# Run-time packages: iproute2 for can0, fontconfig, and one package per soname in the plotter
# bundle's DEPS that a minimal Ubuntu 24.04 or 26.04 lacks (glibc, libstdc++, libgcc, zlib and
# zstd are always there). Names hold on both releases.
CM_APT_PACKAGES="iproute2 libxkbcommon0 libxkbcommon-x11-0 libegl1 libgl1 libglx0 libopengl0 libx11-6 libx11-xcb1 libdbus-1-3 fontconfig libfontconfig1 libfreetype6 libglib2.0-0t64 libgssapi-krb5-2 libwayland-client0 libwayland-cursor0 libwayland-egl1 libxcb1 libxcb-cursor0 libxcb-glx0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 libxcb-sync1 libxcb-xfixes0 libxcb-xkb1"

# NEED_RELOGIN is set to 1 by ensure_group when it added the desktop user to a group.
NEED_RELOGIN=

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

# lock_packs: the pack ids of the lock in use (charts-sound-central, ...), in lock order.
lock_packs() {
  lock_text | awk -F= '$1 ~ /^pack\..+\.version$/ {id=$1; sub(/^pack\./, "", id); sub(/\.version$/, "", id); print id}'
}

# lock_file_packs FILE: the same for the lock file FILE.
lock_file_packs() {
  awk -F= '$1 ~ /^pack\..+\.version$/ {id=$1; sub(/^pack\./, "", id); sub(/\.version$/, "", id); print id}' "$1"
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

# check_linked_packs: die when a store pack that `current` or `previous` links has a missing
# sidecar or one that differs from the lock's sha256 for that pack: replacing it in place would
# break the installed set (and rollback) if the run then stopped. Unlinked store packs are fine.
check_linked_packs() {
  local root part name want l
  root=$(p /opt/cheekymarine)
  for part in $(lock_packs); do
    name=$(pack_name "$part")
    want=$(lock_get "pack.$part.sha256")
    [ -d "$root/packs/$name" ] || continue
    pack_in_store "$name" "$want" && continue
    for l in current previous; do
      if [ -L "$root/$l/packs/$name" ]; then
        die "pack $name in the store does not match this set's lock, and the active or previous set uses it; pack releases must not change under the same version. To recover, remove /opt/cheekymarine/packs/$name and /opt/cheekymarine/packs/$name.sha256 by hand, then run this again."
      fi
    done
  done
}

# fetch_parts STAGE_DIR: download and verify every part of the set, and the set's own script and
# lock (which must equal the lock in use).
# A pack already in the store (dir plus a sidecar equal to the lock's sha256) is skipped.
fetch_parts() {
  local stage=$1 base part key asset want name set
  check_linked_packs
  base=$(base_url)
  set=$(lock_get set)
  for key in n2kd $(lock_packs | sed 's/^/pack./') plotter; do
    part=${key#pack.}
    asset=$(lock_get "$key.asset")
    want=$(lock_get "$key.sha256")
    case "$asset" in
      *.tar)
        name=${asset%.tar}
        if [ -d "$(p /opt/cheekymarine/packs)/$name" ] \
          && [ "$(cat "$(p /opt/cheekymarine/packs)/$name.sha256" 2>/dev/null || true)" = "$want" ]; then
          echo "$part already in the store"
          continue
        fi
        ;;
    esac
    echo "downloading $part $asset"
    fetch_file "$base/$(lock_get "$key.tag")/$asset" "$stage/$asset" "$part"
    check_sum "$stage/$asset" "$want" "$part" "$asset"
  done
  fetch_file "$base/cheekymarine-v$set/SHA256SUMS" "$stage/SHA256SUMS" set
  fetch_file "$base/cheekymarine-v$set/install-cheekymarine.sh" "$stage/install-cheekymarine.sh" set
  want=$(awk '$2=="install-cheekymarine.sh" {print $1; exit}' "$stage/SHA256SUMS")
  check_sum "$stage/install-cheekymarine.sh" "$want" set install-cheekymarine.sh
  fetch_file "$base/cheekymarine-v$set/cheekymarine.lock" "$stage/cheekymarine.lock" set
  want=$(awk '$2=="cheekymarine.lock" {print $1; exit}' "$stage/SHA256SUMS")
  check_sum "$stage/cheekymarine.lock" "$want" set cheekymarine.lock
  # The set script becomes bin/cheekymarine: its set's lock must be the one installed now.
  [ "$(cat "$stage/cheekymarine.lock")" = "$(lock_text)" ] \
    || die "the set release's cheekymarine.lock differs from the lock in this script; nothing was changed"
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

# pack_name ID: the store name of pack ID (its asset without .tar).
pack_name() {
  local asset
  asset=$(lock_get "pack.$1.asset")
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
  for part in $(lock_packs); do
    name=$(pack_name "$part")
    want=$(lock_get "pack.$part.sha256")
    if ! pack_in_store "$name" "$want"; then
      rm -rf "${store:?}/$name" "$store/$name.sha256"
      mkdir "$store/.tmp-$name"
      tar -xf "$stage/$(lock_get "pack.$part.asset")" -C "$store/.tmp-$name" --strip-components=1
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
  for part in $(lock_packs); do
    name=$(pack_name "$part")
    want=$(lock_get "pack.$part.schema")
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

# merge_packs DIR: when some kind (charts, bathy) has two or more packs in the lock, run the
# set's plotter with --merge-packs on DIR/packs; a non-zero exit dies `pack merge failed: <output>`.
# With one pack per kind there is nothing to merge (and a 0.2.1 plotter has no --merge-packs).
merge_packs() {
  local d=$1 out
  lock_packs | sed 's/-.*//' | sort | uniq -d | grep -q . || return 0
  out=$(QT_QPA_PLATFORM=offscreen "$d/plotter/bin/cheekyplotter" --merge-packs "$d/packs" 2>&1) \
    || die "pack merge failed: $out"
}

# install_apt: refresh the package lists and install the run-time packages; either failing stops
# the install (the set is still untouched at this point). Skipped when dpkg-query reports every
# package installed, so a dead apt source cannot block a repair or an upgrade.
install_apt() {
  local st
  # shellcheck disable=SC2016,SC2086
  if st=$(dpkg-query -W -f='${Status}\n' $CM_APT_PACKAGES 2>/dev/null) \
    && ! printf '%s\n' "$st" | grep -vqxF 'install ok installed'; then
    printf 'The run-time packages are already installed.\n'
    return 0
  fi
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 update
  # shellcheck disable=SC2086
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends \
    $CM_APT_PACKAGES
}

# install_sysusers DIR: install set DIR's sysusers file and run systemd-sysusers (creates the
# cheekymarine user and group, which ensure_group needs).
install_sysusers() {
  local dst
  dst=$(p /etc/sysusers.d/cheekymarine.conf)
  mkdir -p "$(dirname "$dst")"
  cp "$1/n2kd/usr/lib/sysusers.d/cheekymarine.conf" "$dst"
  systemd-sysusers
}

# ensure_group: add the desktop user to group cheekymarine (n2kd's socket) when not a member, and
# set NEED_RELOGIN, since a new group only applies to a new login.
ensure_group() {
  if ! id -nG "$CM_USER" | tr ' ' '\n' | grep -qxF cheekymarine; then
    usermod -aG cheekymarine "$CM_USER"
    NEED_RELOGIN=1
  fi
}

# install_launcher: /opt/cheekymarine/bin/cheekyplotter runs the active set's plotter. The
# content names production paths, whatever CM_ROOT is.
install_launcher() {
  local f
  f=$(p /opt/cheekymarine/bin/cheekyplotter)
  mkdir -p "$(dirname "$f")"
  cat > "$f.tmp" <<'LAUNCHER'
#!/bin/sh
exec /opt/cheekymarine/current/plotter/bin/cheekyplotter --fullscreen --packs /opt/cheekymarine/current/packs "$@"
LAUNCHER
  chmod 755 "$f.tmp"
  mv -T "$f.tmp" "$f"
}

# install_autostart: the GNOME autostart entry that runs the launcher at login, owned by the user.
install_autostart() {
  local d f
  d=$(p "$CM_HOME/.config/autostart")
  f=$d/cheekyplotter.desktop
  if [ ! -d "$(p "$CM_HOME/.config")" ]; then
    # 700, as GNOME creates it
    mkdir -p -m 700 "$(p "$CM_HOME/.config")"
    chown "$CM_USER:" "$(p "$CM_HOME/.config")"
  fi
  if [ ! -d "$d" ]; then
    mkdir "$d"
    chown "$CM_USER:" "$d"
  fi
  cat > "$f.tmp" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=CheekyMarine plotter
Exec=/opt/cheekymarine/bin/cheekyplotter
Icon=cheekyplotter
StartupWMClass=cheekyplotter
DESKTOP
  chown "$CM_USER:" "$f.tmp"
  mv -T "$f.tmp" "$f"
}

# install_icon DIR: copy set DIR's plotter icon into the system hicolor theme (644) and refresh the
# icon cache. A plotter bundle with no icon (an older release) is skipped and leaves any installed
# icon in place. A failed cache refresh only warns.
install_icon() {
  local src d f
  src=$1/plotter/share/icons/hicolor/scalable/apps/cheekyplotter.svg
  [ -f "$src" ] || return 0
  d=$(p /usr/share/icons/hicolor/scalable/apps)
  f=$d/cheekyplotter.svg
  mkdir -p "$d"
  install -m 644 "$src" "$f.tmp"
  mv -T "$f.tmp" "$f"
  if command -v gtk-update-icon-cache > /dev/null; then
    gtk-update-icon-cache -q -t -f "$(p /usr/share/icons/hicolor)" \
      || printf 'cheekymarine: warning: gtk-update-icon-cache failed, the icon may show after a relogin\n' >&2
  fi
}

# install_menu_entry: the system app-menu entry (app grid, Activities search) that runs the
# launcher, then refresh the desktop database. A failed refresh only warns. The content names
# production paths, whatever CM_ROOT is.
install_menu_entry() {
  local d f
  d=$(p /usr/share/applications)
  f=$d/cheekyplotter.desktop
  mkdir -p "$d"
  cat > "$f.tmp" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=CheekyMarine plotter
Comment=Chart plotter
Exec=/opt/cheekymarine/bin/cheekyplotter
Icon=cheekyplotter
StartupWMClass=cheekyplotter
Categories=Utility;
Terminal=false
DESKTOP
  chmod 644 "$f.tmp"
  mv -T "$f.tmp" "$f"
  if command -v update-desktop-database > /dev/null; then
    update-desktop-database -q "$d" \
      || printf 'cheekymarine: warning: update-desktop-database failed\n' >&2
  fi
}

# install_can0: bring can0 up at 250 kbit/s, listen-only, whenever the adapter appears (udev rule
# pulls in a oneshot unit), and now when it is already present.
install_can0() {
  local rule unit
  rule=$(p /etc/udev/rules.d/80-cheekymarine-can0.rules)
  unit=$(p /etc/systemd/system/cheekymarine-can0.service)
  mkdir -p "$(dirname "$rule")" "$(dirname "$unit")"
  cat > "$rule" <<'RULE'
ACTION=="add", SUBSYSTEM=="net", KERNEL=="can0", TAG+="systemd", ENV{SYSTEMD_WANTS}+="cheekymarine-can0.service"
RULE
  cat > "$unit" <<'UNIT'
[Unit]
Description=CheekyMarine can0 at 250 kbit/s, listen-only
BindsTo=sys-subsystem-net-devices-can0.device
After=sys-subsystem-net-devices-can0.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/ip link set can0 down
ExecStart=/usr/sbin/ip link set can0 type can bitrate 250000 listen-only on
ExecStart=/usr/sbin/ip link set can0 up
UNIT
  systemctl daemon-reload
  udevadm control --reload
  if [ -e "$(p /sys/class/net/can0)" ]; then
    udevadm trigger --action=add "$(p /sys/class/net/can0)"
  fi
}

# install_n2kd_unit DIR: write /etc/systemd/system/n2kd.service from set DIR's unit with ExecStart
# running through `current`, daemon-reload when it changed, and enable it. A regular file, never a
# symlink. The content names production paths, whatever CM_ROOT is.
install_n2kd_unit() {
  local src=$1/n2kd/usr/lib/systemd/system/n2kd.service dst
  dst=$(p /etc/systemd/system/n2kd.service)
  mkdir -p "$(dirname "$dst")"
  awk '/^ExecStart=/ {
    print "ExecStart=/opt/cheekymarine/current/n2kd/usr/bin/n2kd --can can0 --rawlog /var/lib/cheekymarine/rawlog --pgns /opt/cheekymarine/current/n2kd/usr/share/cheekymarine/canboat.json"
    next }
    { print }' "$src" > "$dst.tmp"
  if ! cmp -s "$dst.tmp" "$dst"; then
    mv -T "$dst.tmp" "$dst"
    systemctl daemon-reload
  else
    rm -f "$dst.tmp"
  fi
  systemctl enable n2kd
}

# stop_n2kd: stop n2kd in any state (active, activating in a restart loop, failed); an unknown
# unit on a first install makes systemctl exit 5.
stop_n2kd() {
  systemctl stop n2kd 2> /dev/null || true
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

# graphical_session: true when the desktop user has an active wayland or x11 session.
graphical_session() {
  local id out
  while read -r id; do
    [ -n "$id" ] || continue
    out=$(loginctl show-session "$id" -p Type -p State) || continue
    if printf '%s\n' "$out" | grep -Eqx 'Type=(wayland|x11)' && printf '%s\n' "$out" | grep -qx 'State=active'; then
      return 0
    fi
  done < <(loginctl list-sessions --no-legend | awk -v u="$CM_USER" '$3==u {print $1}')
  return 1
}

# manager_lacks_group: true when the desktop user is in group cheekymarine but the user's systemd
# --user manager (which systemd-run --user starts the plotter from) runs without it: the user
# joined after this login, for example a rerun before logging out after the first install. False
# when it cannot tell. The group's gid sits at the same place in `id -G` as its name in `id -nG`.
manager_lacks_group() {
  local names gids i gid= pid status
  read -ra names <<< "$(id -nG "$CM_USER")"
  read -ra gids <<< "$(id -G "$CM_USER")"
  for i in "${!names[@]}"; do
    [ "${names[$i]}" != cheekymarine ] || gid=${gids[$i]:-}
  done
  [ -n "$gid" ] || return 1
  pid=$(systemctl show --property=MainPID "user@$(id -u "$CM_USER").service" | sed -n 's/^MainPID=//p') || return 1
  status=$(p "/proc/$pid/status")
  [ -n "$pid" ] && [ "$pid" != 0 ] && [ -r "$status" ] || return 1
  ! awk -v g="$gid" '$1 == "Groups:" { for (i = 2; i <= NF; i++) if ($i == g) found = 1 } END { exit !found }' "$status"
}

# start_plotter: start the plotter in the desktop user's session, unless this run added a group
# or the user's manager predates the group (a new group needs a new login), or the user has no
# graphical session.
start_plotter() {
  if [ -z "${NEED_RELOGIN:-}" ] && graphical_session && ! manager_lacks_group; then
    systemd-run --user --machine="$CM_USER@" --collect /opt/cheekymarine/bin/cheekyplotter \
      || echo "Log out and back in (or reboot) to start the plotter."
  else
    echo "Log out and back in (or reboot) to start the plotter."
  fi
}

# as_user CMD...: run CMD as the desktop user, on that user's session bus when its socket exists,
# else inside a throwaway session bus (dbus-run-session).
as_user() {
  local bus
  bus=$(p "/run/user/$(id -u "$CM_USER")/bus")
  if [ -S "$bus" ]; then
    sudo -u "$CM_USER" -H env "DBUS_SESSION_BUS_ADDRESS=unix:path=$bus" "$@"
  else
    # The caller's XDG dirs (kept by some sudo setups) belong to another user: drop them.
    sudo -u "$CM_USER" -H env -u XDG_RUNTIME_DIR -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_CACHE_HOME \
      dbus-run-session -- "$@"
  fi
}

# gset SCHEMA KEY VALUE: set a desktop setting as the user and read it back; die on a mismatch.
# VALUE is the literal form `gsettings get` prints (uint32 0, false, 'nothing').
gset() {
  local got
  as_user gsettings set "$1" "$2" "$3"
  got=$(as_user gsettings get "$1" "$2")
  [ "$got" = "$3" ] || die "could not set $1 $2 to $3 (it reads $got)"
}

# ask QUESTION: ask on the terminal (QUESTION to stderr, so it shows when stdout is redirected;
# the answer from fd 3, opened once per run). Returns 0 for y or yes (any case),
# 1 for anything else, 2 when there is no terminal (the open failed; stays failed for the run).
CM_TTY_STATE=
ask() {
  local ans
  if [ -z "$CM_TTY_STATE" ]; then
    if { exec 3< "${CM_TTY:-/dev/tty}"; } 2> /dev/null; then CM_TTY_STATE=open; else CM_TTY_STATE=failed; fi
  fi
  [ "$CM_TTY_STATE" = open ] || return 2
  printf '%s ' "$1" >&2
  ans=
  read -r ans <&3 || true
  case "${ans,,}" in y | yes) return 0 ;; *) return 1 ;; esac
}

# ini_get FILE SECTION KEY: the value of KEY in [SECTION] (commented lines ignored, spaces around
# = ignored); prints nothing when absent.
ini_get() {
  awk -v sec="$2" -v key="$3" '
    /^[ \t]*[#;]/ { next }
    /^[ \t]*\[/ { s = $0; gsub(/^[ \t]*\[|\][ \t]*$/, "", s); in_s = (s == sec); next }
    in_s {
      i = index($0, "=")
      if (i == 0) next
      k = substr($0, 1, i - 1); v = substr($0, i + 1)
      gsub(/^[ \t]+|[ \t]+$/, "", k); gsub(/^[ \t]+|[ \t]+$/, "", v)
      if (k == key) { print v; exit }
    }' "$1"
}

# ini_set FILE SECTION KEY VALUE: set KEY=VALUE in [SECTION]: replace the key in place when present,
# else add it just after the section header, else add the section at the end. Other lines stay as
# they are. Two passes: the first finds out whether the key is already there.
ini_set() {
  local f=$1 tmp
  tmp=$f.tmp.$$
  awk -v sec="$2" -v key="$3" -v val="$4" '
    function parse(line) {
      if (line ~ /^[ \t]*[#;]/) return 0
      if (line ~ /^[ \t]*\[/) { s = line; gsub(/^[ \t]*\[|\][ \t]*$/, "", s); in_s = (s == sec); hdr = 1; return 1 }
      hdr = 0
      return 1
    }
    function is_key(line,   i, k) {
      i = index(line, "=")
      if (i == 0) return 0
      k = substr(line, 1, i - 1); gsub(/^[ \t]+|[ \t]+$/, "", k)
      return k == key
    }
    NR == FNR { if (parse($0)) { if (hdr) seen = seen || in_s; else if (in_s && is_key($0)) found = 1 } next }
    FNR == 1 { in_s = 0 }
    {
      if (!parse($0)) { print; next }
      if (hdr) { print; if (in_s && !found) print key "=" val; next }
      if (in_s && is_key($0)) { print key "=" val; next }
      print
    }
    END { if (!seen) { if (NR > 0) print ""; print "[" sec "]"; print key "=" val } }
  ' "$f" "$f" > "$tmp"
  chmod --reference="$f" "$tmp"
  mv -T "$tmp" "$f"
}

# desktop_settings: blanking, dimming and sleep off always; auto-login and the lock screen only
# after a yes at the terminal (no terminal or "no": leave it and print the command).
desktop_settings() {
  local conf cmd
  gset org.gnome.desktop.session idle-delay 'uint32 0'
  gset org.gnome.settings-daemon.plugins.power idle-dim false
  gset org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type "'nothing'"
  gset org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type "'nothing'"

  conf=$(p /etc/gdm3/custom.conf)
  if [ -f "$conf" ] && [ "$(ini_get "$conf" daemon AutomaticLoginEnable)" = true ] \
    && [ "$(ini_get "$conf" daemon AutomaticLogin)" = "$CM_USER" ]; then
    :
  elif ask "Turn on automatic login for $CM_USER? Anyone who opens this tablet gets your desktop with no password. [y/N]"; then
    [ -f "$conf" ] || { mkdir -p "$(dirname "$conf")"; : > "$conf"; }
    ini_set "$conf" daemon AutomaticLoginEnable true
    ini_set "$conf" daemon AutomaticLogin "$CM_USER"
  else
    cmd="sudo sh -c 'f=/etc/gdm3/custom.conf; grep -q \"^\\[daemon\\]\" \$f || echo \"[daemon]\" >> \$f; sed -i -E \"/^[[:space:]]*AutomaticLogin(Enable)?[[:space:]]*=/d; /^\\[daemon\\]/a AutomaticLoginEnable=true\\nAutomaticLogin=$CM_USER\" \$f'"
    printf 'Left as it is. To change it later: %s\n' "$cmd"
  fi

  if [ "$(as_user gsettings get org.gnome.desktop.screensaver lock-enabled)" = false ]; then
    :
  elif ask "Turn off the lock screen? The screen will not ask for your password after it wakes. [y/N]"; then
    gset org.gnome.desktop.screensaver lock-enabled false
    gset org.gnome.desktop.screensaver ubuntu-lock-on-suspend false
  else
    printf 'Left as it is. To change it later: gsettings set org.gnome.desktop.screensaver lock-enabled false && gsettings set org.gnome.desktop.screensaver ubuntu-lock-on-suspend false\n'
    printf '(Run that as %s in their desktop session, without sudo.)\n' "$CM_USER"
  fi
}

# label_get KEY: KEY (set or plotter) from db-label, empty when there is no label.
label_get() {
  local f
  f=$(p /var/lib/cheekymarine/db-label)
  [ -f "$f" ] || return 0
  lock_file_get "$f" "$1"
}

# write_label SET PLOTTER_VER: db-label says the live plotter.db belongs to SET's plotter.
write_label() {
  local label
  label=$(p /var/lib/cheekymarine/db-label)
  mkdir -p "$(dirname "$label")"
  printf 'set=%s\nplotter=%s\n' "$1" "$2" > "$label.tmp"
  mv -T "$label.tmp" "$label"
}

# newer_than A B: true when plotter version A is strictly newer than B (sort -V).
newer_than() {
  [ "$1" != "$2" ] && [ "$(printf '%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$1" ]
}

# data_rule FROM_PLOTTER_VER TO_PLOTTER_VER: with the plotter stopped, copy the live
# plotter.db (named with its set from db-label, with a sidecar <copy>.label holding that set and
# plotter version), keep it when TO's plotter is the same or newer, else restore the newest copy
# (by the stamp in its name) whose sidecar names TO's plotter version, or move it aside. A db with
# no label counts as unknown and newer; its copy's sidecar has an empty plotter= and is never
# restored. The label itself is written by switch_to, around the flip.
data_rule() {
  local from=$1 to=$2 db label copies fromset base sfx newest stamp best f n
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
    printf 'set=%s\nplotter=%s\n' "$fromset" "$from" > "$base.label"
    if [ -z "$from" ] || [ "$(printf '%s\n' "$from" "$to" | sort -V | tail -n 1)" != "$to" ]; then
      rm -f "$db" "$db-wal" "$db-shm"
      if [ "$fromset" != unknown ] && [ -n "$to" ]; then
        newest= best=
        for f in "$copies"/plotter-*.db; do
          n=${f##*/}
          [[ $n =~ -([0-9]{8}T[0-9]{6}Z)\.db$ ]] || continue
          stamp=${BASH_REMATCH[1]}
          if [ ! -f "$f.label" ] || [ "$(lock_file_get "$f.label" plotter)" != "$to" ]; then continue; fi
          # stamps compare by time as strings; the newest wins whatever set made it
          if [ -z "$best" ] || [[ $stamp > $best ]]; then best=$stamp newest=$n; fi
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
}

# switch_to DIR [rollback]: the switch to set DIR (design "The switch"). Stop, data rule,
# `previous` (only when the set version changes), the atomic `current` flip, bin/cheekymarine, then
# the starts. With `rollback`, DIR is the target of `previous`: `previous` is not moved to the set
# being left, and it is removed right after the flip (a rollback records no history).
# Until the flip, db-label names the newest plotter that could open the db after a kill (the
# label's, the running set's or the target's); right after the flip it names the target exactly.
# A kill in either window so errs toward "newer": a later run restores or moves the db aside,
# and an older plotter never keeps a db a newer one may have migrated.
switch_to() {
  local dir=$1 mode=${2:-} root name toset tover lset lver cset cver bset bver
  root=$(p /opt/cheekymarine)
  name=$(basename "$dir")
  toset=$(lock_file_get "$dir/cheekymarine.lock" set)
  tover=$(lock_file_get "$dir/cheekymarine.lock" plotter.version)
  lset=$(label_get set)
  lver=$(label_get plotter)
  stop_plotter
  stop_n2kd
  data_rule "$lver" "$tover"
  bset=$toset bver=$tover
  if [ -n "$lver" ] && newer_than "$lver" "$bver"; then bset=$lset bver=$lver; fi
  if [ -f "$root/current/cheekymarine.lock" ]; then
    cset=$(lock_file_get "$root/current/cheekymarine.lock" set)
    cver=$(lock_file_get "$root/current/cheekymarine.lock" plotter.version)
    if newer_than "$cver" "$bver"; then bset=$cset bver=$cver; fi
  fi
  write_label "$bset" "$bver"
  if [ "$mode" != rollback ] && [ -f "$root/current/cheekymarine.lock" ] \
    && [ "$(lock_file_get "$root/current/cheekymarine.lock" set)" != "$toset" ]; then
    ln -sfn "$(readlink "$root/current")" "$root/previous.tmp"
    mv -T "$root/previous.tmp" "$root/previous"
  fi
  [ "${CM_TEST_DIE_AT:-}" != before_flip ] || kill -9 $$
  (cd "$root" && ln -sfn "sets/$name" current.tmp && mv -T current.tmp current)
  write_label "$toset" "$tover"
  [ "$mode" != rollback ] || rm -f "$root/previous"
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

# confirm_downgrade: when this script's set is older than the installed one (sort -V), ask on
# the terminal; anything but yes stops the install before anything is changed. Equal is a rerun.
confirm_downgrade() {
  local lock cur new rc=0
  lock="$(p /opt/cheekymarine/current)/cheekymarine.lock"
  [ -f "$lock" ] || return 0
  cur=$(lock_file_get "$lock" set)
  new=$(lock_get set)
  newer_than "$cur" "$new" || return 0
  ask "Install $new over $cur? This is a downgrade. [y/N]" || rc=$?
  case "$rc" in
    0) ;;
    2) die "$new is older than the installed $cur (a downgrade), and there is no terminal to confirm it; nothing was changed" ;;
    *) die "downgrade from $cur to $new not confirmed; nothing was changed" ;;
  esac
}

cmd_install() {
  [ "$(lock_get schema)" = 2 ] \
    || die "lock schema $(lock_get schema) cannot be installed, only lock schema 2; nothing was changed"
  preflight
  take_lock
  confirm_downgrade
  CM_STAGE=$(p "/opt/cheekymarine/.stage-$(lock_get set)")
  rm -rf "$CM_STAGE"
  mkdir -p "$CM_STAGE"
  trap 'rm -rf "$CM_STAGE"' EXIT
  fetch_parts "$CM_STAGE"
  install_apt
  unpack_set "$CM_STAGE" "$(lock_get set)"
  rm -rf "$CM_STAGE"
  check_pack_schema "$CM_SET_DIR"
  merge_packs "$CM_SET_DIR"
  install_sysusers "$CM_SET_DIR"
  ensure_group
  install_launcher
  install_autostart
  install_icon "$CM_SET_DIR"
  install_menu_entry
  install_can0
  desktop_settings
  switch_to "$CM_SET_DIR"
  prune_sets
  cmd_version
}

# cmd_rollback: switch to `previous` with no network, then clear `previous` and prune the newer
# set and the store packs only it used. Refused when `previous` is missing, dangling, or the same
# dir as `current`.
cmd_rollback() {
  local root prev cur
  preflight
  take_lock
  root=$(p /opt/cheekymarine)
  prev=$(readlink -e "$root/previous") || prev=
  cur=$(readlink -e "$root/current") || cur=
  if [ -z "$prev" ] || [ ! -f "$prev/cheekymarine.lock" ] || [ "$prev" = "$cur" ]; then
    die "nothing to roll back to"
  fi
  switch_to "$prev" rollback
  prune_sets
  # Not cmd_version: this script is the set just left, so "this script installs" would mislead.
  print_installed
}

# print_installed: the installed set and its parts.
print_installed() {
  local lock part key
  lock="$(p /opt/cheekymarine/current)/cheekymarine.lock"
  if [ -f "$lock" ]; then
    echo "installed: $(lock_file_get "$lock" set)"
    if [ "$(lock_file_get "$lock" schema)" = 1 ]; then
      # a set installed by 0.2.1 or earlier (rollback target): charts.* and bathy.* keys
      set -- n2kd charts bathy plotter
    else
      set -- n2kd $(lock_file_packs "$lock" | sed 's/^/pack./') plotter
    fi
    for key in "$@"; do
      part=${key#pack.}
      echo "  $part: $(lock_file_get "$lock" "$key.version")"
    done
  else
    echo "installed: none"
  fi
}

# cmd_version: the installed set and its parts, and this script's set when it differs.
cmd_version() {
  local lock installed=none
  lock="$(p /opt/cheekymarine/current)/cheekymarine.lock"
  [ ! -f "$lock" ] || installed=$(lock_file_get "$lock" set)
  print_installed
  if [ "$(lock_get set)" != "$installed" ]; then
    echo "this script installs: $(lock_get set)"
  fi
}

# main [COMMAND]: install, rollback or version. With no command: install, except when run as
# `cheekymarine` (the installed command), which needs one.
main() {
  local cmd=${1:-}
  if [ -z "$cmd" ]; then
    [ "$(basename -- "$0")" != cheekymarine ] || die "usage: /opt/cheekymarine/bin/cheekymarine install|rollback|version"
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
