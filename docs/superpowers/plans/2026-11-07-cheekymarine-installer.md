# CheekyMarine installer (plan 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One script from a `cheekymarine-vX.Y.Z` pre-release turns a fresh Ubuntu 26.04 x86_64 into a working helm from a pinned set (n2kd, charts, bathy, plotter), with an offline one-command rollback; plus the plotter's first release.

**Architecture:** One bash file, `installer/cheekymarine.sh`, is both the published `install-cheekymarine.sh` (the set workflow embeds the lock in it) and the installed `/opt/cheekymarine/bin/cheekymarine` command (`install`, `rollback`, `version`). Every part runs through the `/opt/cheekymarine/current` symlink, so one atomic rename switches the whole set. The plotter gets a relocatable bundle and its own release workflow, and its About page shows the set version read from the lock beside its own binary.

**Tech Stack:** bash 5, curl, coreutils, iproute2, systemd (units, udev, logind, sysusers), GNOME gsettings, GDM; Python 3 stdlib `unittest` for installer tests; C++23 / Qt 6.8.3 (Qt Test, QuickTest) for the plotter change; GitHub Actions, `softprops/action-gh-release@v2`.

**Spec:** `docs/superpowers/specs/2026-11-06-cheekymarine-installer-design.md` (revised 79ea934 after an adversarial review; owner approval pending; one open owner question: lid switch). Executors read both documents.

**Process:** branch `plan5-installer`, worktree `.claude/worktrees/plan5-installer`. No implementation starts before the owner approves the design and this plan. Ledger: `.superpowers/sdd/2026-11-07-installer/progress.md` (ignored), one line per task. Draft PR after Task 1 so CI runs early. One adversarial review of the whole branch before merge; threads resolved one by one after verified fixes; the owner merges. Tags are outward-facing: the controller asks the owner before pushing any tag (Task 12). ThinkPad work goes to the `laptop-chart` Remote Control session by SendMessage (controller's job, not an implementer's).

## Global Constraints

- No GPL code in anything shipped (owner). GPL build tools that ship nothing, like GCC, are allowed; the bundle and the installer contain no GPL file. No new runtime dependency beyond Ubuntu's base desktop and the apt run-time set.
- No em-dash character (U+2014) anywhere. US English in new text.
- Names: tag `cheekymarine-vX.Y.Z`, published script `install-cheekymarine.sh`, lock `cheekymarine.lock`, plotter tag `plotter-vX.Y.Z`, plotter asset `cheekyplotter-X.Y.Z-x86_64.tar.gz` with one top directory `cheekyplotter-X.Y.Z-x86_64/`.
- Every CheekyMarine release in this project: `make_latest: false`; set releases are `prerelease: true`. Nobody edits or deletes n2kd `v0.1.0`.
- Downloads only from `https://github.com/jjveleber/CheekyMarine/releases/download/<tag>/<asset>`; no GitHub API call in the installer.
- `can0`: 250000 bit/s, listen-only on, up on add and at boot.
- Prompts read `/dev/tty`, no timeout, default "leave it"; no `/dev/tty` means leave the setting and print the command.
- Paths (production values; tests prefix them with `CM_ROOT`): `/opt/cheekymarine/{sets,current,previous,bin}`, `/var/lib/cheekymarine/db-copies`, `/var/lib/cheekymarine/db-label`, `/etc/systemd/system/n2kd.service`, `/etc/sysusers.d/cheekymarine.conf`, `/etc/udev/rules.d/80-cheekymarine-can0.rules`, `/etc/systemd/system/cheekymarine-can0.service`, `/etc/systemd/logind.conf.d/cheekymarine.conf`, `/etc/gdm3/custom.conf`, `~user/.config/autostart/cheekyplotter.desktop`, `~user/.local/share/cheekyplotter/plotter.db`.
- Test hooks (environment, documented in the script header, never in user docs): `CM_ROOT` (path prefix), `CM_BASE_URL` (replaces the GitHub download base; `file://` works), `CM_LOCK_FILE` (replaces the embedded lock), `CM_TTY` (replaces `/dev/tty`; a path that does not exist means "no terminal").
- Installer tests: `python3 -m unittest discover -s installer/tests -v` from the repo root. Plotter tests: the plan 4 build lines (`env -u LD_LIBRARY_PATH PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"`, `cmake --build build-plotter`, `ctest --test-dir build-plotter --output-on-failure`).
- ASSUMED pending owner answer (lid switch): closing the keyboard cover keeps the helm running (`HandleLidSwitch=ignore`, `HandleLidSwitchExternalPower=ignore`, `HandleLidSwitchDocked=ignore`). If the owner says "sleep", Task 6 drops the logind file and its test.

## Review Focus

1. **The script killed (Ctrl-C, power loss) between unpack and the `current` rename, or right after it.** Expected: before, the old set is `current`, complete and running after a reboot; after, the new set is. Never n2kd of one set with the plotter of another. Tests `test_kill_before_flip_keeps_old_set` and `test_kill_after_flip_rerun_finishes` (Task 4).
2. **A rerun of the set that is already `current`.** Expected: `previous` still names the older set, so rollback still works. Test `test_rerun_same_set_keeps_previous` (Task 4).
3. **A rollback where the newer plotter migrated `plotter.db` forward.** Expected: the older plotter gets the copy saved when the newer set went in, never the migrated file; the migrated file survives in `db-copies`. Test `test_rollback_restores_pre_upgrade_db_and_keeps_newer_copy` (Task 7).
4. **A fresh 26.04 where unattended-upgrades holds the apt lock.** Expected: the script waits (up to 600 s) and proceeds; an apt failure leaves the active set untouched. Test `test_apt_failure_leaves_current_untouched` and the `DPkg::Lock::Timeout=600` assertion (Task 5).
5. **The script piped into `sudo bash` with the prompts answered "no", then run again.** Expected: nothing changed either time, both prompts asked both times, the printed commands shown. Test `test_no_answer_leaves_settings_and_asks_again` (Task 6).

---

## File Structure

```
installer/cheekymarine.sh            the installer and the installed command (Tasks 2 to 7)
installer/cheekymarine.lock          the set's lock, source of truth for the next set tag (Task 1)
installer/lock-tool.sh               check / fill the lock against part releases' SHA256SUMS (Task 1)
installer/README.md                  user doc + the lock format contract (Tasks 1, 7)
installer/tests/harness.py           temp root, PATH shims, fake releases, runner (Task 2)
installer/tests/shims/*              fake systemctl, apt-get, usermod, ... that log calls (Task 2)
installer/tests/test_*.py            unit tests per task
installer/tests/e2e.sh               real-systemd scenarios on a CI runner (Task 8)
.github/workflows/installer-ci.yml   unit tests + e2e (Task 8)
plotter/src/core/AppInfo.{h,cpp}     setVersion property, readSetVersion() (Task 9)
plotter/src/app/main.cpp             passes the lock path (Task 9)
plotter/qml/AboutPage.qml            set version line (Task 9)
plotter/CMakeLists.txt               CM_PLOTTER_BUNDLE option: $ORIGIN RPATH (Task 10)
scripts/build-maplibre-qt.sh         CMAKE_INSTALL_RPATH=$ORIGIN (Task 10)
scripts/bundle-plotter.sh            allowlist bundle, qt.conf, manifest, GPL check (Task 10)
THIRD_PARTY_NOTICES                  shipped Qt modules' third-party code, Qt source URL (Task 10)
scripts/check-plotter-tag.sh         tag vs PLOTTER_VERSION (Task 11)
.github/workflows/plotter-ci.yml     + workflow_call (Task 11)
.github/workflows/plotter-release.yml (Task 11)
.github/workflows/release.yml        make_latest: false (Task 12)
.github/workflows/set-release.yml    (Task 12)
README.md                            "Installing a release" points at the set release (Task 12)
```

---

### Task 1: The lock file and its tool

**Files:**
- Create: `installer/cheekymarine.lock`, `installer/lock-tool.sh`, `installer/README.md`, `installer/tests/test_lock.py`

**Interfaces:**
- Produces: lock format (flat `key=value`, `#` comments, no sections, keys below); `lock-tool.sh check LOCK` exits 0 when every part's `sha256` equals the line for its `asset` in `<base>/<tag>/SHA256SUMS`, else 1 naming the part; `lock-tool.sh fill LOCK` rewrites each `sha256` from those files. Base is `${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}`.

Lock keys, in this order: `schema=1`, `set=X.Y.Z`, then for each part in `n2kd charts bathy plotter`: `<part>.version`, `<part>.tag`, `<part>.asset`, `<part>.sha256`. First lock: `set=0.1.0`; n2kd `0.1.0` / `v0.1.0` / `n2kd-0.1.0-x86_64.tar.gz`; charts `1.1.0` / `charts-puget-north-v1.1.0` / `charts-puget-north-1.1.0.tar`; bathy likewise; plotter `0.1.0` / `plotter-v0.1.0` / `cheekyplotter-0.1.0-x86_64.tar.gz`. Hashes of parts not yet released are `0` x 64 until Task 12 fills them.

- [ ] **Step 1: Write failing tests** `test_check_passes_on_matching_sums`, `test_check_fails_naming_part_on_mismatch`, `test_check_fails_on_missing_release`, `test_fill_writes_hashes_and_keeps_order`, `test_lock_keys_are_complete` (committed lock has all 18 keys, `schema=1`). Fake releases are `file://` directories built by the test.
- [ ] **Step 2: Run** `python3 -m unittest installer.tests.test_lock -v`. Expected: FAIL (no tool).
- [ ] **Step 3: Implement** `lock-tool.sh` (bash, `set -euo pipefail`, curl `-fsSL`) and the committed lock. README section "Lock format (contract)": every key, its meaning, that readers ignore unknown keys, that `schema` bumps on an incompatible change, and that the plotter and the later self-updater read it.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): lock format and lock-tool`. Open the draft PR.

### Task 2: Script skeleton, preflight and test harness

**Files:**
- Create: `installer/cheekymarine.sh`, `installer/tests/harness.py`, `installer/tests/shims/` (`systemctl apt-get usermod systemd-sysusers udevadm loginctl pkill pgrep systemd-run sudo gsettings dbus-run-session uname`), `installer/tests/test_preflight.py`

**Interfaces:**
- Produces in `cheekymarine.sh`: `main "$@"` dispatching `install` (default when run as `install-cheekymarine.sh`, or when `$0` is not `cheekymarine`), `rollback`, `version`; `lock_get KEY` (from the embedded block between `# BEGIN LOCK` / `# END LOCK`, or `CM_LOCK_FILE`); `die MSG` (prints `cheekymarine: MSG` to stderr, exit 1); `p PATH` (prints `$CM_ROOT$PATH`); a `flock` on `$(p /run/cheekymarine-install.lock)` for `install` and `rollback`.
- Produces in `harness.py`: `class Rig` with `run(*args, tty_answers=None, env=None) -> CompletedProcess`, `root: Path`, `calls() -> list[str]` (one line per shim call), `make_release(tag, asset, content) -> None`, `make_set(set_ver, plotter_ver, n2kd_ver=...) -> Path` (lock file plus fake parts: a plotter tarball whose `bin/cheekyplotter` is a shell stub, a pack tar with the right top directory, an n2kd tarball with the real layout). Shims log `name args` to `$CM_ROOT/calls` and keep tiny state files (for example `usermod` records groups, `gsettings` a key store).

- [ ] **Step 1: Write failing tests** `test_refuses_non_ubuntu` (os-release `ID=debian`), `test_refuses_ubuntu_2204`, `test_refuses_aarch64` (uname shim), `test_refuses_root_without_sudo_user`, `test_refuses_second_concurrent_run`, `test_version_prints_set_and_parts` (from the lock of `current`; "no set installed" when none), each asserting exit status and the exact first line of stderr.
- [ ] **Step 2: Run** `python3 -m unittest installer.tests.test_preflight -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the skeleton. Ubuntu check reads `$(p /etc/os-release)` (`ID=ubuntu`, `VERSION_ID` >= 24.04 by `sort -V`); arch from `uname -m` must be `x86_64`; desktop user is `SUDO_USER`, home from `getent passwd`. Header comment lists the four test hooks.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): skeleton, preflight, test harness`.

### Task 3: Download and verify

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_download.py`

**Interfaces:**
- Produces: `fetch_parts STAGE_DIR` downloads each part's asset from `${CM_BASE_URL}/<tag>/<asset>` with `curl -fL --retry 3` and checks `sha256sum` against the lock; returns 1 with `die` text `download failed: <part> <url>` or `checksum mismatch: <part> <asset>`. Staging is `$(p /opt/cheekymarine/.stage-<set>)`, removed on any exit.

- [ ] **Step 1: Write failing tests** `test_download_failure_leaves_current_untouched` (an installed set A, then set B with a missing asset: exit 1, `current` still A, `sets/` unchanged, no staging dir left, no `systemctl` call in `calls()`), `test_checksum_mismatch_names_part`, `test_downloads_use_fixed_urls_only` (every curl URL starts with the base and has the `<tag>/<asset>` shape).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `fetch_parts`; `install` calls it before anything that changes the system.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): download and verify parts against the lock`.

### Task 4: Unpack, switch and the data rule

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_switch.py`

**Interfaces:**
- Consumes: `fetch_parts`, `lock_get`.
- Produces: `unpack_set STAGE_DIR SET` (into `sets/<set>.new`, then rename over `sets/<set>`; n2kd tarball and plotter tarball with `--strip-components=1` into `n2kd/` and `plotter/`; pack tars into `packs/` as is; the lock copied to `sets/<set>/cheekymarine.lock`); `switch_to SET` (the five steps of the design's "The switch"); `data_rule FROM_PLOTTER_VER TO_PLOTTER_VER TO_SET` (design "Data rule"); `prune_sets` (keeps `current` and `previous`). `db-label` holds two lines: `set=<ver>` and `plotter=<ver>` of the set that last used the live db.

The `current` replacement is exactly: `ln -sfn "sets/$set" current.tmp && mv -T current.tmp current` inside `/opt/cheekymarine`. `previous` moves only when the target differs from the current target. The db copy is `plotter-<set>-<UTC yyyymmddThhmmssZ>.db` (plus `-wal`, `-shm` when present), taken with the plotter stopped; `chown` restored files to the desktop user.

`CM_TEST_DIE_AT` (test hook, add to the header list): `before_flip` or `after_flip` makes the script `kill -9 $$` at that point.

- [ ] **Step 1: Write failing tests**:
  - `test_fresh_install_layout`: `current -> sets/0.1.0`, no `previous`, `sets/0.1.0/{n2kd/usr/bin/n2kd,plotter/bin/cheekyplotter,packs/charts-puget-north-1.1.0,packs/bathy-puget-north-1.1.0,cheekymarine.lock}` exist, `db-label` says set 0.1.0.
  - `test_upgrade_sets_previous`: install A then B: `current` B, `previous` A, both dirs present.
  - `test_third_set_prunes_oldest`: A, B, C: only B and C remain.
  - `test_rerun_same_set_keeps_previous`: A, B, B: `previous` still A; `sets/B` re-unpacked (a marker file planted inside it is gone).
  - `test_kill_before_flip_keeps_old_set` and `test_kill_after_flip_rerun_finishes`: with `CM_TEST_DIE_AT`; after the kill `current` is A (resp. B) and the target dir is complete; a rerun without the hook ends with `current` B and the starts in `calls()`.
  - `test_plotter_stopped_before_db_copy`: in `calls()`, `pkill -TERM` precedes the copy's existence; the copy holds the planted `plotter.db`, `-wal` and `-shm`.
  - `test_forward_switch_keeps_live_db`: A (plotter 0.1.0) to B (plotter 0.2.0): live db unchanged, copy labeled A in `db-copies`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Plotter stop: `pkill -TERM -u <user> -x cheekyplotter`, wait up to 10 s with `pgrep`, then `pkill -KILL`. n2kd stop/start and plotter start are calls to Task 5's functions; stub them here as no-ops if Task 5 is not in yet.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): atomic set switch and data rule`.

### Task 5: n2kd service, launcher, autostart, can0, apt

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_system.py`

**Interfaces:**
- Produces: `install_apt` (`apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends <list>`; list is `CM_APT_PACKAGES` in the script, filled by Task 10's dependency check, start with `iproute2 libxkbcommon0 libxcb-cursor0 libegl1 libgl1 libwayland-client0 libwayland-egl1 fontconfig libcurl4t64 libuv1t64`); `install_n2kd_unit SET` (writes `/etc/systemd/system/n2kd.service` from `sets/<set>/n2kd/usr/lib/systemd/system/n2kd.service` with `ExecStart` replaced as in the design, copies sysusers to `/etc/sysusers.d/cheekymarine.conf`, runs `systemd-sysusers`, `systemctl daemon-reload`, `systemctl enable n2kd`); `ensure_group` (returns 0 and sets `NEED_RELOGIN=1` when it added the user to `cheekymarine`); `install_launcher` (`/opt/cheekymarine/bin/cheekyplotter`: `exec /opt/cheekymarine/current/plotter/bin/cheekyplotter --fullscreen --packs /opt/cheekymarine/current/packs "$@"`; `/opt/cheekymarine/bin/cheekymarine` is a copy of this script with the lock block of the installed set); `install_autostart` (desktop entry `Exec=/opt/cheekymarine/bin/cheekyplotter`, owned by the user); `install_can0` (udev rule `ACTION=="add", SUBSYSTEM=="net", KERNEL=="can0", TAG+="systemd", ENV{SYSTEMD_WANTS}+="cheekymarine-can0.service"`; unit `BindsTo=` and `After=sys-subsystem-net-devices-can0.device`, `Type=oneshot`, `RemainAfterExit=yes`, `ExecStart=/usr/sbin/ip link set can0 down`, `ExecStart=/usr/sbin/ip link set can0 type can bitrate 250000 listen-only on`, `ExecStart=/usr/sbin/ip link set can0 up`, `WantedBy=sys-subsystem-net-devices-can0.device`; then `udevadm control --reload`); `start_plotter` (only when `loginctl` shows a graphical session for the user and `NEED_RELOGIN` is unset: `systemd-run --user --machine=<user>@ --collect /opt/cheekymarine/bin/cheekyplotter`; otherwise print `Log out and back in (or reboot) to start the plotter.`).

Install order (design "Install or upgrade"): preflight, fetch, apt, unpack, launcher/autostart/can0/group, desktop (Task 6), switch (which calls `install_n2kd_unit` after the flip, then starts), prune, print versions.

- [ ] **Step 1: Write failing tests** `test_n2kd_unit_execstart_through_current` (exact ExecStart string, `User=cheekymarine` kept), `test_n2kd_unit_written_after_flip` (in `calls()` order), `test_apt_uses_lock_timeout`, `test_apt_failure_leaves_current_untouched`, `test_can0_rule_and_unit_contents` (bitrate 250000, `listen-only on`), `test_group_add_skips_plotter_start_and_says_relogin`, `test_launcher_and_autostart` (exec line, desktop entry owner), `test_installed_command_carries_set_lock` (`/opt/cheekymarine/bin/cheekymarine version` prints the installed set).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** all installer tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): n2kd unit, launcher, autostart, can0, apt`.

### Task 6: Desktop settings and the two prompts

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_desktop.py`

**Interfaces:**
- Produces: `as_user CMD...` (runs as the desktop user; uses `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus` when that socket exists, else `dbus-run-session --`); `gset SCHEMA KEY VALUE` (sets, reads back, `die` on a mismatch); `ask QUESTION` (reads one line from `${CM_TTY:-/dev/tty}`; returns 0 only for `y` or `yes`, case-insensitive; returns 2 when there is no terminal); `ini_set FILE SECTION KEY VALUE` (adds or replaces a key, keeps other lines).

Settings: always `org.gnome.desktop.session idle-delay uint32 0`, `org.gnome.settings-daemon.plugins.power idle-dim false`, `sleep-inactive-ac-type 'nothing'`, `sleep-inactive-battery-type 'nothing'`; logind drop-in `[Login]` with the three `HandleLidSwitch*=ignore` lines (ASSUMED, see Global Constraints). Auto-login prompt: skipped when `/etc/gdm3/custom.conf` already has `AutomaticLoginEnable=true` and `AutomaticLogin=<user>` under `[daemon]`; a yes sets both. Lock prompt: skipped when `org.gnome.desktop.screensaver lock-enabled` is `false`; a yes sets it `false` and `ubuntu-lock-on-suspend` `false`. Prompt copy (exact):

```
Turn on automatic login for <user>? Anyone who opens this tablet gets your desktop with no password. [y/N]
Turn off the lock screen? The screen will not ask for your password after it wakes. [y/N]
```

On "no" or no terminal, print `Left as it is. To change it later: <command>` with the `sudo` command for that setting.

- [ ] **Step 1: Write failing tests** `test_power_settings_written_and_read_back`, `test_yes_sets_autologin_and_lock`, `test_no_answer_leaves_settings_and_asks_again` (two runs, both answered "n": files and keys unchanged, both prompts in output both times, the commands printed), `test_no_tty_leaves_settings_without_asking`, `test_already_set_asks_nothing`, `test_ini_set_keeps_other_lines` (a custom.conf with comments and a `[security]` section), `test_logind_dropin_contents`, `test_session_bus_used_when_present` (shim sees the bus address).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): desktop settings and security prompts`.

### Task 7: Rollback, downgrade and the user doc

**Files:**
- Modify: `installer/cheekymarine.sh`, `installer/README.md`
- Create: `installer/tests/test_rollback.py`

**Interfaces:**
- Consumes: `switch_to`, `data_rule`, `ask`.
- Produces: `cheekymarine rollback`; downgrade confirmation in `install`.

- [ ] **Step 1: Write failing tests** `test_rollback_restores_pre_upgrade_db_and_keeps_newer_copy` (A, write "a" to db, B, write "b", rollback: live db is "a", a copy labeled B holding "b" exists, owner is the desktop user), `test_downgrade_without_copy_starts_fresh` (install B first, then A with a "yes": no live db, it sits in `db-copies`, `db-label` set A), `test_rollback_offline` (`CM_BASE_URL` unreachable; switch to `previous`; n2kd unit rewritten from the older set; newer set dir deleted; `previous` gone), `test_second_rollback_refused` (exit 1, `cheekymarine: nothing to roll back to`), `test_downgrade_asks_and_no_stops` (exit 1, nothing changed), `test_downgrade_without_tty_stops`, `test_upgrade_after_rollback_is_ordinary`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** README: install one-liner, what the script changes, the two prompts, `cheekymarine version`, `cheekymarine rollback`, where data copies live, "log out and back in after the first install".
- [ ] **Step 4: Run** all installer tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): rollback and downgrade`.

### Task 8: Installer CI with real systemd

**Files:**
- Create: `installer/tests/e2e.sh`, `.github/workflows/installer-ci.yml`

**Interfaces:**
- Consumes: the script; Task 2's fake-set builder via `python3 installer/tests/harness.py make-sets DIR` (add this CLI entry) but with the real n2kd `v0.1.0` tarball downloaded from its release.

`installer-ci.yml` (on push and pull_request touching `installer/**` or the workflow; `ubuntu-24.04`): job `unit` runs the unittest discover line and `bash -n installer/*.sh`; job `e2e` creates user `helm`, installs `dbus libglib2.0-bin gsettings-desktop-schemas dconf-gsettings-backend`, and runs `sudo SUDO_USER=helm CM_BASE_URL=file://$PWD/rel CM_LOCK_FILE=... installer/cheekymarine.sh` (no `CM_ROOT`) through these scenarios, asserting after each: fresh install (`systemctl is-active n2kd` is `active`, `readlink /opt/cheekymarine/current`, `id -nG helm` has `cheekymarine`, gsettings read back as `helm`); rerun; upgrade to a second fake set; `cheekymarine rollback` with the network blocked (`CM_BASE_URL=http://127.0.0.1:9/`); a set with a corrupted asset (exit 1, `current` unchanged, n2kd still active). No tty in CI, so the prompts take the no-terminal path; one extra run under `script -qec` answers "y" to both and checks `/etc/gdm3/custom.conf`.

- [ ] **Step 1: Write** `e2e.sh` with `set -euo pipefail` and one function per scenario.
- [ ] **Step 2: Run it** in a privileged `ubuntu:24.04` systemd container locally if available, else push and watch the job. Expected: the job is green and each scenario prints `PASS <name>`.
- [ ] **Step 3: Commit** `ci(installer): unit tests and real-systemd scenarios`.

### Task 9: About page shows the set version

**Files:**
- Modify: `plotter/src/core/AppInfo.h`, `plotter/src/core/AppInfo.cpp`, `plotter/src/app/main.cpp`, `plotter/qml/AboutPage.qml`
- Test: `plotter/tests/tst_appshell.cpp` (or the file that tests `AppInfo`), `plotter/tests/qml/tst_pages.qml`

**Interfaces:**
- Produces: `QString readSetVersion(const QString& lockPath)` (free function in `AppInfo.cpp`, declared in `AppInfo.h`: `QSettings(lockPath, QSettings::IniFormat)`; returns `set` when the file exists and `schema` is `1`, else empty); `AppInfo` gains `Q_PROPERTY(QString setVersion READ setVersion CONSTANT)` set by a constructor argument `const QString& setVersion = {}`. `main.cpp` passes `readSetVersion(QCoreApplication::applicationDirPath() + "/../../cheekymarine.lock")` (the lock of the set this binary belongs to: `sets/<v>/plotter/bin/` up two). (design goal 7).

- [ ] **Step 1: Write failing tests**: C++ `readSetVersionReadsSet`, `readSetVersionEmptyWhenMissing`, `readSetVersionEmptyOnOtherSchema`; QML in `tst_pages.qml` `test_aboutShowsSetVersion` (`setVersion: "0.1.0"` shows the line `Set: cheekymarine 0.1.0`) and `test_aboutShowsNoSet` (empty shows `Set: none (not installed from a set)`).
- [ ] **Step 2: Run** `ctest --test-dir build-plotter --output-on-failure`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** The line sits under the `Heading` in `AboutPage.qml`, same `Line` component as the n2kd line.
- [ ] **Step 4: Run.** Expected: all plotter tests PASS.
- [ ] **Step 5: Commit** `feat(plotter): About page shows the installed set version`.

### Task 10: Relocatable plotter bundle

**Files:**
- Modify: `plotter/CMakeLists.txt` (near the RPATH block at lines 94 to 125), `scripts/build-maplibre-qt.sh`, `THIRD_PARTY_NOTICES`
- Create: `scripts/bundle-plotter.sh`, `scripts/tests/test_bundle_plotter.sh`

**Interfaces:**
- Produces: CMake option `CM_PLOTTER_BUNDLE` (default `OFF`; `ON` sets the `cheekyplotter` RPATH to `$ORIGIN/../lib`, classic RPATH kept, and no absolute build path); `scripts/bundle-plotter.sh BUILD_DIR QT_PREFIX MAPLIBRE_PREFIX VERSION` writes `cheekyplotter-VERSION-x86_64.tar.gz` and prints its name, layout `bin/{cheekyplotter,qt.conf}`, `lib/`, `plugins/`, `qml/`, `licenses/`, `THIRD_PARTY_NOTICES`, `MANIFEST` (one line per file: path, SPDX license id), `DEPS` (sonames resolved outside the bundle).

Rules (design "The plotter release"): libs copied are the `ldd` closure of the binary and every bundled plugin, restricted to files under `QT_PREFIX` and `MAPLIBRE_PREFIX`. Plugin allowlist: `platforms/libqxcb.so`, `platforms/libqwayland-egl.so`, `platforms/libqwayland-generic.so`, `wayland-shell-integration/`, `wayland-graphics-integration-client/`, `wayland-decoration-client/`, `xcbglintegrations/`, `sqldrivers/libqsqlite.so`, `imageformats/libqsvg.so`, `iconengines/libqsvgicon.so`, `platforminputcontexts/libcomposeplatforminputcontextplugin.so`, `platforminputcontexts/libibusplatforminputcontextplugin.so`. QML modules: exactly what `qmlimportscanner` reports for `plotter/qml` and `plotter/src/qml`. Denylist (script fails, exit 1, naming the file): any path matching `VirtualKeyboard`, `virtualkeyboard`, `QtCharts`, `Charts`, `DataVisualization`, `Quick3DPhysics`. `qt.conf`: `[Paths]` `Prefix=..`, `Plugins=plugins`, `QmlImports=qml`. Never copy libstdc++, libgcc_s, libc, libm, libGL, libEGL, libxcb*, fontconfig, freetype from the system. `build-maplibre-qt.sh` adds `-DCMAKE_INSTALL_RPATH='$ORIGIN'` (changes its CI cache key: expected). `THIRD_PARTY_NOTICES` gains the third-party code of each shipped Qt module (check Qt 6.8.3's "Licenses used in Qt" for every module in `lib/`) and `Qt 6.8.3 source: https://download.qt.io/archive/qt/6.8/6.8.3/single/qt-everywhere-src-6.8.3.tar.xz`.

- [ ] **Step 1: Write the failing test** `scripts/tests/test_bundle_plotter.sh`: given a bundle tarball, (a) no denylisted path, (b) every MANIFEST line has a license, (c) `readelf -d bin/cheekyplotter` RPATH is `$ORIGIN/../lib`, (d) in a clean `ubuntu:24.04` container with only the Task 5 apt list installed, `ldd bin/cheekyplotter` and every plugin show no `not found`, and `QT_QPA_PLATFORM=offscreen bin/cheekyplotter --help` exits 0. Plant a fake `libQt6VirtualKeyboard.so` once to see (a) fail.
- [ ] **Step 2: Run** against a bundle from the current tree. Expected: FAIL (no script yet).
- [ ] **Step 3: Implement.** Feed `DEPS` back into `CM_APT_PACKAGES` in `installer/cheekymarine.sh` (map each soname to its 26.04 package; a soname with no package in the base desktop must be in the list).
- [ ] **Step 4: Run** the test. Expected: PASS, and the same check on a 26.04 container if the image exists.
- [ ] **Step 5: Commit** `feat(plotter): relocatable bundle with license manifest`.

### Task 11: Plotter release workflow

**Files:**
- Create: `scripts/check-plotter-tag.sh`, `.github/workflows/plotter-release.yml`
- Modify: `.github/workflows/plotter-ci.yml` (add `workflow_call:`)

**Interfaces:**
- Produces: `check-plotter-tag.sh TAG` (pattern `plotter-vX.Y.Z` vs `PLOTTER_VERSION` in `plotter/CMakeLists.txt`, same output style as `scripts/check-version-tag.sh`); workflow artifact `plotter-release` (tarball + `SHA256SUMS`).

Workflow: on `push: tags: ['plotter-v*']` and `workflow_dispatch`. Jobs: `version` (tag check, skipped on dispatch), `test` (`uses: ./.github/workflows/plotter-ci.yml`, tests ON), `bundle` (needs test; `ubuntu-24.04`; same Qt and maplibre cache keys as plotter-ci; configure with `-DCM_PLOTTER_TESTS=OFF -DCM_PLOTTER_BUNDLE=ON -DCMAKE_BUILD_TYPE=Release`; run `bundle-plotter.sh` and `test_bundle_plotter.sh`; `sha256sum` into `SHA256SUMS`; upload artifact), `publish` (only when the ref is a tag; `make_latest: false`, `generate_release_notes: true`).

- [ ] **Step 1: Write a failing test** for `check-plotter-tag.sh` in `scripts/tests/test_check_plotter_tag.sh`: `plotter-v0.1.0` passes, `plotter-v0.1.1` and `v0.1.0` fail.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the script and the workflow.
- [ ] **Step 4: Run** the test (PASS), then trigger `workflow_dispatch` on the branch: expected green with the `plotter-release` artifact present.
- [ ] **Step 5: Commit** `ci(plotter): release workflow`.

### Task 12: Set release workflow, n2kd Latest fix, and the first releases

**Files:**
- Create: `.github/workflows/set-release.yml`
- Modify: `.github/workflows/release.yml` (`make_latest: false` with the same comment as chartpack-release), `README.md` ("Installing a release": the set one-liner first, the n2kd tarball as a manual alternative), `installer/cheekymarine.lock` (real hashes)

**Interfaces:**
- Consumes: `lock-tool.sh check`, `installer/cheekymarine.sh` with its `# BEGIN LOCK` / `# END LOCK` block.

`set-release.yml`: on `push: tags: ['cheekymarine-v*']`. Steps: tag version equals `set=` in `installer/cheekymarine.lock` (fail otherwise); `installer/lock-tool.sh check installer/cheekymarine.lock`; build `install-cheekymarine.sh` by replacing the lock block with the lock file; `bash -n` it; `SHA256SUMS` over the script and the lock; publish with `prerelease: true`, `make_latest: false`, and a body that starts with:

```
Install or upgrade (Ubuntu 24.04 or newer, x86_64):

    curl -fsSL https://github.com/jjveleber/CheekyMarine/releases/download/cheekymarine-vX.Y.Z/install-cheekymarine.sh | sudo bash
```

then a table of the four parts and versions from the lock.

- [ ] **Step 1: Test** the embed step locally: build the script from the lock, run `CM_ROOT=... ./install-cheekymarine.sh version`-equivalent through the harness (`test_embedded_lock_matches_file` in `installer/tests/test_lock.py`). Expected: FAIL first, then PASS after the embed logic exists (put it in `lock-tool.sh embed LOCK SCRIPT OUT` so the test and the workflow share it).
- [ ] **Step 2: Commit** `ci: set release workflow; n2kd releases stop taking Latest`.
- [ ] **Step 3: Whole-branch adversarial review**, fixes, owner merges the PR.
- [ ] **Step 4 (controller, owner says yes to each tag):** tag `plotter-v0.1.0`, `charts-puget-north-v1.1.0`, `bathy-puget-north-v1.1.0` on main; wait for their releases; check `v0.1.0` is still Latest.
- [ ] **Step 5:** `installer/lock-tool.sh fill installer/cheekymarine.lock`, then `check`; small PR, owner merges.
- [ ] **Step 6 (owner says yes):** tag `cheekymarine-v0.1.0`; check it is a pre-release and `v0.1.0` is still Latest.

### Task 13: ThinkPad run, then CapnButts (controller and owner)

- [ ] **Step 1:** Before the merge in Task 12 Step 3, send `laptop-chart` the e2e scenarios against a `file://` set built from the `plotter-release` dispatch artifact, the real n2kd `v0.1.0` and the pack 1.0.0 releases (1.1.0 may not exist yet): fresh install answering "y" to both prompts, reboot, plotter full screen with no manual step, `cheekymarine version`, About page set line, upgrade to a second set, `cheekymarine rollback` with Wi-Fi off, `systemctl status cheekymarine-can0` with the adapter plugged if it is at hand. Post results on the plan 5 GitHub issue.
- [ ] **Step 2:** After Task 12 Step 6, the same fresh install on the ThinkPad from the real one-liner.
- [ ] **Step 3:** The owner runs the one-liner on CapnButts and reboots. Done when the plotter comes up full screen with no step besides the two prompts.
