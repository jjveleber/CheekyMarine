#!/usr/bin/env bash
# Real-systemd end-to-end scenarios for installer/cheekymarine.sh. Run on a disposable
# ubuntu-24.04 machine with systemd as PID 1 (the CI runner), as a sudo-capable user, with user
# `helm` already created. It changes the machine: do not run it on a real one.
set -eEuo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=${E2E_WORK:-$REPO/e2e-work}
REL=$WORK/rel
INSTALLER=$REPO/installer/cheekymarine.sh
N2KD_URL=https://github.com/jjveleber/CheekyMarine/releases/download/v0.1.0
ROOT=/opt/cheekymarine
SCENARIO=setup
trap 'echo "FAIL $SCENARIO" >&2' ERR

declare -A LOCK
OUT=
RC=0

fail() { echo "assert: $*" >&2; return 1; }

# prepare: the real n2kd v0.1.0 tarball (checked against that release's SHA256SUMS) and the fake
# sets built around it.
prepare() {
  rm -rf "$WORK"
  mkdir -p "$WORK/dl"
  curl -fL --retry 3 -sS -o "$WORK/dl/n2kd-0.1.0-x86_64.tar.gz" "$N2KD_URL/n2kd-0.1.0-x86_64.tar.gz"
  curl -fL --retry 3 -sS -o "$WORK/dl/SHA256SUMS" "$N2KD_URL/SHA256SUMS"
  (cd "$WORK/dl" && grep ' n2kd-0.1.0-x86_64.tar.gz$' SHA256SUMS | sha256sum -c -)
  local name path
  while read -r name path; do LOCK[$name]=$path; done < <(
    python3 -I "$REPO/installer/tests/harness.py" make-sets "$REL" --n2kd "$WORK/dl/n2kd-0.1.0-x86_64.tar.gz")
  # A stock-shaped gdm3 config, for the runner that has none (the prompts edit it).
  if [ ! -f /etc/gdm3/custom.conf ]; then
    sudo mkdir -p /etc/gdm3
    printf '[daemon]\n# Uncomment the line below to force the login screen to use Xorg\n#WaylandEnable=false\n\n[security]\n\n[xdmcp]\n\n[chooser]\n\n[debug]\n' | sudo tee /etc/gdm3/custom.conf > /dev/null
  fi
}

# cm LOCKNAME ARGS...: the committed script with that set's lock; no terminal (setsid), so the
# prompts take the no-terminal path. Sets OUT and RC.
cm() {
  local lock=${LOCK[$1]}; shift
  RC=0
  OUT=$(setsid -w sudo env SUDO_USER=helm "CM_BASE_URL=${BASE_URL:-file://$REL}" "CM_LOCK_FILE=$lock" "$INSTALLER" "$@" 2>&1 < /dev/null) || RC=$?
  printf '%s\n' "$OUT"
}

# cm_tty LOCKNAME ANSWERS: the same under a pty, with the answers typed in. Sets OUT and RC.
cm_tty() {
  local lock=${LOCK[$1]}
  RC=0
  OUT=$(printf '%b' "$2" | script -qec "sudo env SUDO_USER=helm CM_BASE_URL=${BASE_URL:-file://$REL} CM_LOCK_FILE=$lock $INSTALLER" /dev/null 2>&1) || RC=$?
  printf '%s\n' "$OUT"
}

want_rc() { [ "$RC" = "$1" ] || fail "exit status $RC, wanted $1"; }
cur() { basename "$(readlink "$ROOT/current")"; }
prev() { basename "$(readlink "$ROOT/previous")"; }
gs() { sudo -u helm -H env -u XDG_RUNTIME_DIR -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_CACHE_HOME dbus-run-session -- gsettings get "$1" "$2"; }

n2kd_active() {
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    [ "$(systemctl is-active n2kd || true)" = active ] && return 0
    sleep 1
  done
  systemctl status n2kd --no-pager || true
  fail "n2kd is not active"
}

store_state() { (cd "$ROOT/packs" && stat -c '%n %Y' ./* | sort); }

fresh_install() {
  cm first install
  want_rc 0
  n2kd_active
  case "$(cur)" in 0.2.0*) ;; *) fail "current is $(readlink "$ROOT/current")" ;; esac
  id -nG helm | tr ' ' '\n' | grep -qx cheekymarine || fail "helm is not in group cheekymarine"
  [ "$(gs org.gnome.desktop.session idle-delay)" = "uint32 0" ] || fail "idle-delay"
  [ "$(gs org.gnome.settings-daemon.plugins.power idle-dim)" = false ] || fail "idle-dim"
  [ "$(gs org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type)" = "'nothing'" ] || fail "sleep-inactive-ac-type"
  printf '%s\n' "$OUT" | grep -q "Log out and back in" || fail "no relogin line"
  printf '%s\n' "$OUT" | grep -q "Left as it is" || fail "no left-as-it-is line for the prompts"
  [ -x "$ROOT/bin/cheekymarine" ] || fail "no bin/cheekymarine"
}

rerun() {
  local before
  before=$(readlink "$ROOT/current")
  cm first install
  want_rc 0
  [ "$(readlink "$ROOT/current")" = "$before" ] || fail "current moved"
  n2kd_active
}

prompts_yes() {
  cm_tty first 'y\ny\n'
  want_rc 0
  grep -Eq '^AutomaticLoginEnable *= *true' /etc/gdm3/custom.conf || fail "AutomaticLoginEnable not set"
  grep -Eq '^AutomaticLogin *= *helm' /etc/gdm3/custom.conf || fail "AutomaticLogin not set"
  [ "$(gs org.gnome.desktop.screensaver lock-enabled)" = false ] || fail "lock-enabled"
  [ "$(gs org.gnome.desktop.screensaver ubuntu-lock-on-suspend)" = false ] || fail "ubuntu-lock-on-suspend"
}

upgrade_same_packs() {
  local before after
  # A pack download would now fail the run: the set must reuse the store.
  mkdir -p "$WORK/hidden"
  mv "$REL"/charts-puget-north-v1.1.0 "$REL"/bathy-puget-north-v1.1.0 "$WORK/hidden/"
  before=$(store_state)
  cm second install
  want_rc 0
  case "$(cur)" in 0.3.0*) ;; *) fail "current is $(readlink "$ROOT/current")" ;; esac
  case "$(prev)" in 0.2.0*) ;; *) fail "previous is $(readlink "$ROOT/previous")" ;; esac
  after=$(store_state)
  [ "$before" = "$after" ] || fail "store changed: $before / $after"
  n2kd_active
}

rollback_offline() {
  BASE_URL=http://127.0.0.1:9/ cm_rollback
  want_rc 0
  case "$(cur)" in 0.2.0*) ;; *) fail "current is $(readlink "$ROOT/current")" ;; esac
  [ ! -e "$ROOT/previous" ] || fail "previous still there"
  n2kd_active
}
cm_rollback() {
  RC=0
  OUT=$(setsid -w sudo env SUDO_USER=helm "CM_BASE_URL=$BASE_URL" "$ROOT/bin/cheekymarine" rollback 2>&1 < /dev/null) || RC=$?
  printf '%s\n' "$OUT"
}

downgrade() {
  cm second install
  want_rc 0
  cm_tty first 'y\n'
  want_rc 0
  printf '%s\n' "$OUT" | grep -q "downgrade" || fail "no downgrade prompt"
  case "$(cur)" in 0.2.0*) ;; *) fail "current is $(readlink "$ROOT/current")" ;; esac
  case "$(prev)" in 0.3.0*) ;; *) fail "previous is $(readlink "$ROOT/previous")" ;; esac
  n2kd_active
}

corrupted_asset() {
  local before
  before=$(readlink "$ROOT/current")
  cm bad install
  want_rc 1
  printf '%s\n' "$OUT" | grep -q "checksum mismatch" || fail "no checksum mismatch message"
  [ "$(readlink "$ROOT/current")" = "$before" ] || fail "current changed"
  n2kd_active
}

prepare
for SCENARIO in fresh_install rerun prompts_yes upgrade_same_packs rollback_offline downgrade corrupted_asset; do
  "$SCENARIO"
  echo "PASS $SCENARIO"
done
