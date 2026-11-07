# CheekyMarine installer (plan 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One script from a `cheekymarine-vX.Y.Z` pre-release turns a fresh Ubuntu 26.04 x86_64 into a working helm from a pinned set (n2kd, charts, bathy, plotter), with an offline one-command rollback; plus the plotter's first release.

**Architecture:** One bash file, `installer/cheekymarine.sh`, is both the published `install-cheekymarine.sh` (the set workflow embeds the lock in it) and the installed `/opt/cheekymarine/bin/cheekymarine` command (`install`, `rollback`, `version`). Every part runs through the `/opt/cheekymarine/current` symlink, so one atomic rename switches the whole set. Packs live once in a shared store, `/opt/cheekymarine/packs/`, and each set links to its packs there, so a set whose packs are already present downloads none. The plotter gets a relocatable bundle and its own release workflow, and its About page shows the set version read from the lock beside its own binary.

**Tech Stack:** bash 5, curl, coreutils, iproute2, systemd (units, udev, sysusers), GNOME gsettings, GDM; Python 3 stdlib `unittest` for installer tests; C++23 / Qt 6.8.3 (Qt Test, QuickTest) for the plotter change; GitHub Actions, `softprops/action-gh-release@v2`.

**Spec:** `docs/superpowers/specs/2026-11-06-cheekymarine-installer-design.md` (revised after an adversarial review and owner feedback 2026-11-07: shared pack store, pack schema range, no lid switch file; owner approval pending). Executors read both documents.

**Process:** branch `plan5-installer`, worktree `.claude/worktrees/plan5-installer`. No implementation starts before the owner approves the design and this plan. Ledger: `.superpowers/sdd/2026-11-07-installer/progress.md` (ignored), one line per task. Draft PR after Task 1 so CI runs early. One adversarial review of the whole branch before merge; threads resolved one by one after verified fixes; the owner merges. Tags are outward-facing: the controller asks the owner before pushing any tag (Task 12). ThinkPad work goes to the `laptop-chart` Remote Control session by SendMessage (controller's job, not an implementer's).

## Global Constraints

- No GPL code in anything shipped (owner). GPL build tools that ship nothing, like GCC, are allowed; the bundle and the installer contain no GPL file. No new runtime dependency beyond Ubuntu's base desktop and the apt run-time set.
- No em-dash character (U+2014) anywhere. US English in new text.
- Names: tag `cheekymarine-vX.Y.Z`, published script `install-cheekymarine.sh`, lock `cheekymarine.lock`, plotter tag `plotter-vX.Y.Z`, plotter asset `cheekyplotter-X.Y.Z-x86_64.tar.gz` with one top directory `cheekyplotter-X.Y.Z-x86_64/`.
- Every CheekyMarine release in this project: `make_latest: false`; set releases are `prerelease: true`. Nobody edits or deletes n2kd `v0.1.0`.
- Downloads only from `https://github.com/jjveleber/CheekyMarine/releases/download/<tag>/<asset>`; no GitHub API call in the installer.
- `can0`: 250000 bit/s, listen-only on, up on add and at boot.
- Prompts read `/dev/tty`, no timeout, default "leave it"; no `/dev/tty` means leave the setting and print the command.
- Paths (production values; tests prefix them with `CM_ROOT`): `/opt/cheekymarine/{sets,packs,current,previous,bin}`, `/var/lib/cheekymarine/db-copies`, `/var/lib/cheekymarine/db-label`, `/etc/systemd/system/n2kd.service`, `/etc/sysusers.d/cheekymarine.conf`, `/etc/udev/rules.d/80-cheekymarine-can0.rules`, `/etc/systemd/system/cheekymarine-can0.service`, `/etc/gdm3/custom.conf`, `~user/.config/autostart/cheekyplotter.desktop`, `~user/.local/share/cheekyplotter/plotter.db`.
- Test hooks (environment, documented in the script header, never in user docs): `CM_ROOT` (path prefix), `CM_BASE_URL` (replaces the GitHub download base; `file://` works), `CM_LOCK_FILE` (replaces the embedded lock), `CM_TTY` (replaces `/dev/tty`; a path that does not exist means "no terminal").
- Installer tests: `python3 -m unittest discover -s installer/tests -v` from the repo root, no `__init__.py` (namespace packages); tests import `from installer.tests.harness import Rig`. Tests run unprivileged: when `CM_ROOT` is set the EUID check is skipped and tests set `SUDO_USER=$(id -un)`, so the real `getent`, `id` and `chown` (to self) work; those three are never shimmed.
- Script basics: `set -euo pipefail`, `umask 022`. Commands that legitimately fail on a first install or an idle system (`systemctl stop` of an unloaded unit, `pkill` with no match) carry an explicit `|| true` or an `is-active` / `pgrep` guard; shims return what the real command returns in that state (`pkill` 1 with no match, `systemctl stop` 5 for an unknown unit).
- The script never reads its own file: under `curl ... | sudo bash`, `$0` is `bash`. The lock is embedded as a heredoc variable between the markers: `# BEGIN LOCK` / `CM_LOCK=$(cat <<'LOCK'` / lock lines / `LOCK` / `)` / `# END LOCK`. `lock_get` reads `$CM_LOCK` (or `CM_LOCK_FILE`). Plotter tests: the plan 4 build lines (`env -u LD_LIBRARY_PATH PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"`, `cmake --build build-plotter`, `ctest --test-dir build-plotter --output-on-failure`).
- Lid switch (owner): not touched. No logind file; Ubuntu's default applies. On the boat the cover is detached.
- Pack store (owner, option A): sets still pin pack versions in the lock, but a pack version is downloaded and unpacked once, into `/opt/cheekymarine/packs/<pack>-<region>-<version>/` with a sidecar `<pack>-<region>-<version>.sha256` holding the release tar's SHA-256. A set's `packs/` holds only relative symlinks into the store. Pruning keeps every store pack that `current` or `previous` links to.

## Review Focus

1. **The script killed (Ctrl-C, power loss) between unpack and the `current` rename, or right after it.** Expected: before, the old set is `current`, complete and running after a reboot; after, the new set is. Never n2kd of one set with the plotter of another. Tests `test_kill_before_flip_keeps_old_set`, `test_kill_after_flip_rerun_finishes` and `test_rerun_kill_before_flip_keeps_running_set` (Task 4).
2. **A rerun of the set that is already `current`.** Expected: `previous` still names the older set, so rollback still works. Test `test_rerun_same_set_keeps_previous` (Task 4).
3. **A rollback where the newer plotter migrated `plotter.db` forward.** Expected: the older plotter gets the copy saved when the newer set went in, never the migrated file; the migrated file survives in `db-copies`. Test `test_rollback_restores_pre_upgrade_db_and_keeps_newer_copy` (Task 7).
4. **A fresh 26.04 where unattended-upgrades holds the apt lock.** Expected: the script waits (up to 600 s) and proceeds; an apt failure leaves the active set untouched. Test `test_apt_failure_leaves_current_untouched` and the `DPkg::Lock::Timeout=600` assertion (Task 5).
5. **The script piped into `sudo bash` with the prompts answered "no", then run again.** Expected: nothing changed either time, both prompts asked both times, the printed commands shown. Tests `test_no_answer_leaves_settings_and_asks_again` (Task 6) and `test_piped_install` (Task 3).
6. **The shared pack store under a kill or a rollback.** Expected: a pack killed mid-unpack is never taken as present (no `.sha256` until after the rename); a rollback finds the older set's packs still in the store with no network; pruning never deletes a pack `current` or `previous` links to. Tests `test_kill_mid_pack_unpack_refetches`, `test_rollback_offline` and `test_prune_keeps_packs_of_current_and_previous` (Tasks 4, 7).

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
plotter/src/core/PackCatalog.cpp     pack schema range from PLOTTER_PACK_SCHEMA_MIN/MAX (Task 9)
plotter/CMakeLists.txt               PLOTTER_PACK_SCHEMA_MIN/MAX (Task 9); install() rule with $ORIGIN/../lib RPATH (Task 10)
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
- Create: `installer/cheekymarine.lock`, `installer/lock-tool.sh`, `installer/README.md`, `installer/tests/test_lock.py`, a minimal `installer/cheekymarine.sh` holding only the lock block and `lock_get` (Task 2 grows it)

**Interfaces:**
- Produces: lock format (flat `key=value`, `#` comments, no sections, keys below); `lock-tool.sh check LOCK` exits 0 when every part's `sha256` equals the line for its `asset` in `<base>/<tag>/SHA256SUMS` and each pack's `schema` is within `plotter.pack_schema_min`..`plotter.pack_schema_max`, else 1 naming the part; `lock-tool.sh fill LOCK` rewrites each `sha256` from those files; `lock-tool.sh embed LOCK SCRIPT OUT` writes OUT = SCRIPT with the lines between `CM_LOCK=$(cat <<'LOCK'` and `LOCK` replaced by LOCK's lines (used by the harness and the set workflow). Base is `${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}`.

Lock keys, in this order: `schema=1`, `set=X.Y.Z`, then for each part in `n2kd charts bathy plotter`: `<part>.version`, `<part>.tag`, `<part>.asset`, `<part>.sha256`, with `charts.schema` and `bathy.schema` after their pack's `sha256`, and `plotter.pack_schema_min` and `plotter.pack_schema_max` after the plotter's `sha256` (22 keys). First lock: `set=0.1.0`; n2kd `0.1.0` / `v0.1.0` / `n2kd-0.1.0-x86_64.tar.gz`; charts `1.1.0` / `charts-puget-north-v1.1.0` / `charts-puget-north-1.1.0.tar`; bathy likewise; both packs `schema=1`; plotter `0.1.0` / `plotter-v0.1.0` / `cheekyplotter-0.1.0-x86_64.tar.gz`, `pack_schema_min=1`, `pack_schema_max=1`. Hashes of parts not yet released are `0` x 64 until Task 12 fills them.

- [ ] **Step 1: Write failing tests** `test_check_passes_on_matching_sums`, `test_check_fails_naming_part_on_mismatch`, `test_check_fails_on_missing_release`, `test_fill_writes_hashes_and_keeps_order`, `test_lock_keys_are_complete` (committed lock has all 22 keys, `schema=1`), `test_check_fails_when_pack_schema_outside_plotter_range` (no download needed for this check), `test_embed_replaces_block_and_bash_parses` (`bash -n` on the output passes; the output's `lock_get set` equals the file's). Fake releases are `file://` directories built by the test.
- [ ] **Step 2: Run** `python3 -m unittest installer.tests.test_lock -v`. Expected: FAIL (no tool).
- [ ] **Step 3: Implement** `lock-tool.sh` (bash, `set -euo pipefail`, curl `-fsSL`) and the committed lock. README section "Lock format (contract)": every key, its meaning (the pack schema fields exist so a later project can update packs apart from sets), that readers ignore unknown keys, that `schema` bumps on an incompatible change, and that the plotter and the later self-updater read it.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): lock format and lock-tool`. Open the draft PR.

### Task 2: Script skeleton, preflight and test harness

**Files:**
- Create: `installer/cheekymarine.sh`, `installer/tests/harness.py`, `installer/tests/shims/` (`systemctl apt-get usermod systemd-sysusers udevadm loginctl pkill pgrep systemd-run sudo gsettings dbus-run-session uname curl`), `installer/tests/test_preflight.py`

**Interfaces:**
- Produces in `cheekymarine.sh`: `main "$@"` dispatching `install` (default when run as `install-cheekymarine.sh`, or when `$0` is not `cheekymarine`), `rollback`, `version`; `lock_get KEY` (from `$CM_LOCK`, or `CM_LOCK_FILE`); `die MSG` (prints `cheekymarine: MSG` to stderr, exit 1); `p PATH` (prints `$CM_ROOT$PATH`); a `flock` on `$(p /run/cheekymarine-install.lock)` for `install` and `rollback`. `version` prints `installed: <set>` and each part from `current`'s lock (or `installed: none`), plus `this script installs: <set>` when the embedded set differs.
- Produces in `harness.py`: `class Rig` with `run(*args, tty_answers=None, env=None) -> CompletedProcess`, `root: Path`, `calls() -> list[str]` (one line per shim call), `downloads() -> list[str]` (every URL curl fetched; curl is shimmed to log and then run the real curl), `make_release(tag, asset, content) -> None`, `make_set(set_ver, plotter_ver, n2kd_ver=..., charts_ver=..., bathy_ver=..., pack_schema=1, plotter_range=(1, 1)) -> Path` (lock file, the set release `cheekymarine-v<set>/{install-cheekymarine.sh,SHA256SUMS}` built with `lock-tool.sh embed`, plus fake parts: a plotter tarball whose `bin/cheekyplotter` is a shell stub and with a `PACK_SCHEMA` file, a pack tar with the right top directory and a `manifest.json` with `schema` (default 1, settable), an n2kd tarball with the real layout). Shims log `name args` to `$CM_ROOT/calls` and keep tiny state files (for example `usermod` records groups, `gsettings` a key store).

- [ ] **Step 1: Write failing tests** `test_refuses_non_ubuntu` (os-release `ID=debian`), `test_refuses_ubuntu_2204`, `test_refuses_aarch64` (uname shim), `test_refuses_root_without_sudo_user`, `test_refuses_second_concurrent_run` (Python holds `fcntl.flock` on `$CM_ROOT/run/cheekymarine-install.lock`), `test_version_prints_set_and_parts` (from the lock of `current`; "no set installed" when none), each asserting exit status and the exact first line of stderr.
- [ ] **Step 2: Run** `python3 -m unittest installer.tests.test_preflight -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the skeleton. Ubuntu check reads `$(p /etc/os-release)` (`ID=ubuntu`, `VERSION_ID` >= 24.04 by `sort -V`); arch from `uname -m` must be `x86_64`; EUID 0 required unless `CM_ROOT` is set; desktop user is `SUDO_USER`, home from `getent passwd`. Header comment lists the four test hooks.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): skeleton, preflight, test harness`.

### Task 3: Download and verify

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_download.py`

**Interfaces:**
- Produces: `fetch_parts STAGE_DIR` downloads each part's asset from `${CM_BASE_URL}/<tag>/<asset>` with `curl -fL --retry 3` and checks `sha256sum` against the lock; returns 1 with `die` text `download failed: <part> <url>` or `checksum mismatch: <part> <asset>`. A pack is not downloaded when `$(p /opt/cheekymarine/packs)/<name>/` exists and `<name>.sha256` equals the lock's `sha256`, where `<name>` is the asset name without `.tar`. It also downloads the set's own `install-cheekymarine.sh` from `<base>/cheekymarine-v<set>/` and checks it against that release's `SHA256SUMS` (so the installed command never depends on how the script was started). Staging is `$(p /opt/cheekymarine/.stage-<set>)`: `rm -rf` of a stale stage first (a `kill -9` skips traps), removed by an EXIT trap.

- [ ] **Step 1: Write failing tests** `test_download_failure_leaves_current_untouched` (an installed set A, then set B with a missing asset: exit 1, `current` still A, `sets/` unchanged, no staging dir left, no `systemctl` call in `calls()`), `test_checksum_mismatch_names_part`, `test_downloads_use_fixed_urls_only` (every curl URL starts with the base and has the `<tag>/<asset>` shape), `test_pack_in_store_not_downloaded` (plant `packs/<name>/` and `<name>.sha256` equal to the lock's `sha256` by hand, since `unpack_set` is Task 4: `downloads()` has no pack asset), `test_pack_with_wrong_sidecar_is_downloaded` (a store dir whose `.sha256` differs from the lock is fetched again), `test_piped_install` (`cat install-cheekymarine.sh | bash` with `CM_ROOT`, no `CM_LOCK_FILE`: installs the embedded set; `bin/cheekymarine` equals the downloaded set script).
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
- Produces: `unpack_set STAGE_DIR SET` (into a fresh `sets/<set>.<UTC yyyymmddThhmmssZ>` every time, never over an existing dir; n2kd tarball and plotter tarball with `--strip-components=1` into `n2kd/` and `plotter/`; each downloaded pack tar into `$(p /opt/cheekymarine/packs)/.tmp-<name>`, then `mv -T` to `packs/<name>`, then `<name>.sha256` written (a store dir already present with a matching sidecar is left alone; leftover `.tmp-*` dirs are deleted first; a store dir present without a matching sidecar is removed with `rm -rf packs/<name> packs/<name>.sha256` before the `mv -T`, which would otherwise fail with ENOTEMPTY. If that stale dir is one `current` links to (its sidecar lost), the running plotter keeps its open files and is restarted at the switch, so this is acceptable); in the set dir, `packs/<name>` as a relative symlink `../../../packs/<name>`; `check_pack_schema DIR` (after unpack, before the switch: each linked pack's `manifest.json` `schema` equals the lock's `<pack>.schema`, and the plotter bundle's `PACK_SCHEMA` `min`/`max` equal the lock's `plotter.pack_schema_min`/`max`; else `die pack schema mismatch: <detail>` with `current` untouched; the new set dir and newly stored packs stay until the next successful run's `prune_sets`, as for any failed run: do not add an earlier prune, it could delete what `previous` needs for rollback; reads JSON with `python3 -c` from the stdlib, present on every Ubuntu desktop, or a `grep -o` on the `"schema":` line, implementer's pick, tested); the lock copied to `<dir>/cheekymarine.lock`, the set script to `<dir>/cheekymarine.sh`); `switch_to DIR` (the five steps of the design's "The switch"; after the flip it copies `current/cheekymarine.sh` to `bin/cheekymarine`, so the command always matches the running set, rollback included); `data_rule FROM_PLOTTER_VER TO_PLOTTER_VER TO_SET` (design "Data rule"); `prune_sets` (runs after the starts; deletes every dir in `sets/` that is not the target of `current` or `previous`, then every store pack, with its `.sha256`, that neither of those two set dirs links to). `db-label` holds two lines, `set=<ver>` and `plotter=<ver>`, and is written for T on every switch, a first install included. A live `plotter.db` with no `db-label` (a hand install, the ThinkPad) counts as unknown and newer: copy it labeled `unknown`, move it aside, T starts fresh.

The `current` replacement is exactly: `ln -sfn "sets/$dir" current.tmp && mv -T current.tmp current` inside `/opt/cheekymarine`. `previous` moves only when the target's set version differs from the running set's; a rerun of the same set flips `current` to the new dir and leaves `previous` alone. The db copy is `plotter-<set>-<UTC yyyymmddThhmmssZ>.db` (plus `-wal`, `-shm` when present), taken with the plotter stopped; restored or moved `plotter.db`, `-wal` and `-shm` are owned by the desktop user.

`CM_TEST_DIE_AT` (test hook, add to the header list): `before_flip` or `after_flip` makes the script `kill -9 $$` at that point.

- [ ] **Step 1: Write failing tests**:
  - `test_fresh_install_layout`: `current -> sets/0.1.0.<stamp>`, no `previous`, `current/{n2kd/usr/bin/n2kd,plotter/bin/cheekyplotter,cheekymarine.lock,cheekymarine.sh}` exist, `current/packs/charts-puget-north-1.1.0` and `current/packs/bathy-puget-north-1.1.0` are relative symlinks resolving to store dirs with matching `.sha256` files, `db-label` says set 0.1.0.
  - `test_upgrade_sets_previous`: install A then B: `current` B, `previous` A, both dirs present.
  - `test_third_set_prunes_oldest`: A, B, C: only B and C remain.
  - `test_prune_keeps_packs_of_current_and_previous`: A (charts 1.0.0), B (charts 1.1.0), C (charts 1.1.0, new plotter): store holds only charts 1.1.0; with A, B only, both charts versions remain.
  - `test_kill_mid_pack_unpack_refetches`: a planted `packs/.tmp-<name>` and a store dir with no `.sha256`: the run deletes the `.tmp-` dir, downloads the pack again and ends with a sidecar.
  - `test_pack_schema_mismatch_leaves_current_untouched`: set B whose pack manifest says `schema` 2 while the lock says 1 (and a second case: bundle `PACK_SCHEMA` range differs from the lock): exit 1, `pack schema mismatch` in stderr, `current` still A.
  - `test_rerun_same_set_keeps_previous`: A, B, B: `previous` still A; `current` is a new B dir and the old B dir is pruned.
  - `test_rerun_kill_before_flip_keeps_running_set`: A, B, then B again with `CM_TEST_DIE_AT=before_flip`: `current` still the first B dir, intact.
  - `test_unlabeled_db_is_moved_aside`: a planted `plotter.db` and no `db-label`, fresh install: a copy labeled `unknown`, no live db, `db-label` set to the new set.
  - `test_kill_before_flip_keeps_old_set` and `test_kill_after_flip_rerun_finishes`: with `CM_TEST_DIE_AT`; after the kill `current` is A (resp. B) and the target dir is complete; a rerun without the hook ends with `current` B and the starts in `calls()`.
  - `test_plotter_stopped_before_db_copy`: in `calls()`, `pkill -TERM` precedes the copy's existence; the copy holds the planted `plotter.db`, `-wal` and `-shm`.
  - `test_forward_switch_keeps_live_db`: A (plotter 0.1.0) to B (plotter 0.2.0): live db unchanged, copy labeled A in `db-copies`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Plotter stop: `pkill -TERM -u <user> -x cheekyplotter || true`, wait up to 10 s with `pgrep`, then `pkill -KILL ... || true`. n2kd stop: only when `systemctl is-active --quiet n2kd`. Install n2kd sysusers before the switch (Task 5); the unit after the flip. n2kd stop/start and plotter start are calls to Task 5's functions; stub them here as no-ops if Task 5 is not in yet.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): atomic set switch and data rule`.

### Task 5: n2kd service, launcher, autostart, can0, apt

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_system.py`

**Interfaces:**
- Produces: `install_apt` (with `DEBIAN_FRONTEND=noninteractive`: `apt-get -o DPkg::Lock::Timeout=600 update`, then `apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends <list>`; either failing stops with the set untouched; list is `CM_APT_PACKAGES` in the script, filled by Task 10's dependency check, start with `iproute2 libxkbcommon0 libxcb-cursor0 libegl1 libgl1 libwayland-client0 libwayland-egl1 fontconfig libcurl4t64 libuv1t64 libopengl0 libglx0`); `install_sysusers DIR` (before the switch: copies `<dir>/n2kd/usr/lib/sysusers.d/cheekymarine.conf` to `/etc/sysusers.d/cheekymarine.conf`, runs `systemd-sysusers`; this creates the group `ensure_group` needs); `install_n2kd_unit DIR` (after the flip: writes `/etc/systemd/system/n2kd.service` from `<dir>/n2kd/usr/lib/systemd/system/n2kd.service` with `ExecStart` replaced as in the design, `systemctl daemon-reload`, `systemctl enable n2kd`); `ensure_group` (returns 0 and sets `NEED_RELOGIN=1` when it added the user to `cheekymarine`); `install_launcher` (`/opt/cheekymarine/bin/cheekyplotter`: `exec /opt/cheekymarine/current/plotter/bin/cheekyplotter --fullscreen --packs /opt/cheekymarine/current/packs "$@"`; `bin/cheekymarine` is written by `switch_to`, Task 4); `install_autostart` (`~/.config/autostart/` created owned by the user if missing; entry `[Desktop Entry]`, `Type=Application`, `Name=CheekyMarine plotter`, `Exec=/opt/cheekymarine/bin/cheekyplotter`, owned by the user); `install_can0` (udev rule `ACTION=="add", SUBSYSTEM=="net", KERNEL=="can0", TAG+="systemd", ENV{SYSTEMD_WANTS}+="cheekymarine-can0.service"`; unit `BindsTo=` and `After=sys-subsystem-net-devices-can0.device`, `Type=oneshot`, `RemainAfterExit=yes`, `ExecStart=/usr/sbin/ip link set can0 down`, `ExecStart=/usr/sbin/ip link set can0 type can bitrate 250000 listen-only on`, `ExecStart=/usr/sbin/ip link set can0 up`, no `[Install]` section (the udev `SYSTEMD_WANTS` pulls it in); then `udevadm control --reload`, and when `/sys/class/net/can0` exists, `udevadm trigger --action=add /sys/class/net/can0`); `start_plotter` (only when `NEED_RELOGIN` is unset and `loginctl` lists a session of the user with `Type` `wayland` or `x11` and `State` `active`: `systemd-run --user --machine=<user>@ --collect /opt/cheekymarine/bin/cheekyplotter`; otherwise print `Log out and back in (or reboot) to start the plotter.`).

Install order (design "Install or upgrade"): preflight, downgrade confirmation (Task 7), fetch, apt, unpack, sysusers, group, launcher/autostart/can0, desktop (Task 6), switch (which calls `install_n2kd_unit` after the flip, then starts), prune, print versions.

- [ ] **Step 1: Write failing tests** `test_n2kd_unit_execstart_through_current` (exact ExecStart string, `User=cheekymarine` kept), `test_n2kd_unit_written_after_flip` (in `calls()` order), `test_apt_uses_lock_timeout` (update precedes install, both with the timeout), `test_apt_failure_leaves_current_untouched`, `test_sysusers_before_group_add`, `test_can0_rule_and_unit_contents` (bitrate 250000, `listen-only on`, no `[Install]`), `test_can0_trigger_when_present`, `test_first_install_survives_no_n2kd_and_no_plotter` (shims return 5 and 1 as real ones do), `test_group_add_skips_plotter_start_and_says_relogin`, `test_launcher_and_autostart` (exec line, desktop entry owner), `test_installed_command_carries_set_lock` (after installing B with the A script around, `bin/cheekymarine version` prints `installed: B` and no `this script installs` line).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** all installer tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): n2kd unit, launcher, autostart, can0, apt`.

### Task 6: Desktop settings and the two prompts

**Files:**
- Modify: `installer/cheekymarine.sh`
- Create: `installer/tests/test_desktop.py`

**Interfaces:**
- Produces: `as_user CMD...` (runs `sudo -u "$user" -H` as the desktop user; uses `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus` when that socket exists, else `dbus-run-session --`); `gset SCHEMA KEY VALUE` (sets, reads back, `die` on a mismatch); `ask QUESTION` (no terminal means `exec 3<"${CM_TTY:-/dev/tty}"` fails, which covers a missing `CM_TTY` path and a `/dev/tty` node with no controlling terminal (ENXIO); returns 2 then; otherwise reads one line from fd 3 and returns 0 only for `y` or `yes`, case-insensitive); `gset` compares against the literal `gsettings get` output (`uint32 0`, `false`, `'nothing'`) and the shim prints the same form; `ini_set FILE SECTION KEY VALUE` (adds or replaces a key, keeps other lines, accepts `Key = value` spacing, ignores commented lines like `#  AutomaticLoginEnable = true`, creates the section when absent; the "already set" check reads the same way).

Settings: always `org.gnome.desktop.session idle-delay uint32 0`, `org.gnome.settings-daemon.plugins.power idle-dim false`, `sleep-inactive-ac-type 'nothing'`, `sleep-inactive-battery-type 'nothing'`. No logind file (lid switch left to Ubuntu, Global Constraints). Auto-login prompt: skipped when `/etc/gdm3/custom.conf` already has `AutomaticLoginEnable=true` and `AutomaticLogin=<user>` under `[daemon]`; a yes sets both. Lock prompt: skipped when `org.gnome.desktop.screensaver lock-enabled` is `false`; a yes sets it `false` and `ubuntu-lock-on-suspend` `false`. Prompt copy (exact):

```
Turn on automatic login for <user>? Anyone who opens this tablet gets your desktop with no password. [y/N]
Turn off the lock screen? The screen will not ask for your password after it wakes. [y/N]
```

On "no" or no terminal, print `Left as it is. To change it later: <command>` with the `sudo` command for that setting.

- [ ] **Step 1: Write failing tests** `test_power_settings_written_and_read_back`, `test_yes_sets_autologin_and_lock`, `test_no_answer_leaves_settings_and_asks_again` (two runs, both answered "n": files and keys unchanged, both prompts in output both times, the commands printed), `test_no_tty_leaves_settings_without_asking`, `test_already_set_asks_nothing`, `test_ini_set_keeps_other_lines` (fixture: Ubuntu's stock custom.conf with its commented `AutomaticLogin` lines, plus a `[security]` section, plus a variant with no `[daemon]`), `test_dev_tty_without_terminal_is_no_terminal`, `test_no_logind_file_written` (no file under `etc/systemd/logind.conf.d/`, no `systemd-logind` call), `test_session_bus_used_when_present` (shim sees the bus address).
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
- Produces: `cheekymarine rollback`; downgrade confirmation in `install`, asked right after preflight, before fetch, apt or unpack (compare `set` versions with `sort -V`).

- [ ] **Step 1: Write failing tests** `test_rollback_restores_pre_upgrade_db_and_keeps_newer_copy` (A, write "a" to db, B, write "b", rollback: live db is "a", a copy labeled B holding "b" exists, owner is the desktop user), `test_downgrade_without_copy_starts_fresh` (install B first, then A with a "yes": no live db, it sits in `db-copies`, `db-label` set A), `test_rollback_offline` (A with charts 1.0.0, B with charts 1.1.0, `CM_BASE_URL` unreachable; switch to `previous`; n2kd unit rewritten from the older set; newer set dir deleted; `previous` gone; `current/packs` resolves to charts 1.0.0 in the store; charts 1.1.0 pruned), `test_second_rollback_refused` (exit 1, `cheekymarine: nothing to roll back to`), `test_downgrade_asks_and_no_stops` (exit 1, nothing changed), `test_downgrade_without_tty_stops`, `test_upgrade_after_rollback_is_ordinary`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** README: install one-liner, what the script changes (including the pack store and that a set reuses packs already downloaded), the two prompts, `cheekymarine version`, `cheekymarine rollback`, where data copies live, "log out and back in after the first install".
- [ ] **Step 4: Run** all installer tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(installer): rollback and downgrade`.

### Task 8: Installer CI with real systemd

**Files:**
- Create: `installer/tests/e2e.sh`, `.github/workflows/installer-ci.yml`

**Interfaces:**
- Consumes: the script; Task 2's fake-set builder via `python3 installer/tests/harness.py make-sets DIR` (add this CLI entry) but with the real n2kd `v0.1.0` tarball downloaded from its release.

`installer-ci.yml` (on push and pull_request touching `installer/**` or the workflow; `ubuntu-24.04`): job `unit` runs the unittest discover line and `bash -n installer/*.sh`; job `e2e` creates user `helm`, installs `dbus libglib2.0-bin gsettings-desktop-schemas gnome-settings-daemon-common dconf-gsettings-backend`, and runs `sudo SUDO_USER=helm CM_BASE_URL=file://$PWD/rel CM_LOCK_FILE=... installer/cheekymarine.sh` (no `CM_ROOT`) through these scenarios, asserting after each: fresh install (`systemctl is-active n2kd` is `active`, `readlink /opt/cheekymarine/current`, `id -nG helm` has `cheekymarine`, gsettings read back as `helm`); rerun; upgrade to a second fake set with the same packs (before it, move the pack release dirs out of `rel/` so any pack download fails the run; assert exit 0 and the store dirs' mtimes unchanged); `cheekymarine rollback` with the network blocked (`CM_BASE_URL=http://127.0.0.1:9/`); a downgrade (install the second set, then the first answering "y" under `script -qec`); a set with a corrupted asset (exit 1, `current` unchanged, n2kd still active). No tty in CI, so the prompts take the no-terminal path; one extra run under `script -qec` answers "y" to both and checks `/etc/gdm3/custom.conf`.

- [ ] **Step 1: Write** `e2e.sh` with `set -euo pipefail` and one function per scenario.
- [ ] **Step 2: Run it** in a privileged `ubuntu:24.04` systemd container locally if available, else push and watch the job. Expected: the job is green and each scenario prints `PASS <name>`.
- [ ] **Step 3: Commit** `ci(installer): unit tests and real-systemd scenarios`.

### Task 9: About page set version and the pack schema range

**Files:**
- Modify: `plotter/src/core/AppInfo.h`, `plotter/src/core/AppInfo.cpp`, `plotter/src/app/main.cpp`, `plotter/qml/AboutPage.qml`, `plotter/CMakeLists.txt`, `plotter/src/core/PackCatalog.cpp`
- Test: `plotter/tests/tst_appshell.cpp` (or the file that tests `AppInfo`), `plotter/tests/qml/tst_pages.qml`, `plotter/tests/tst_packcatalog.cpp`

**Interfaces:**
- Produces: `QString readSetVersion(const QString& lockPath)` (free function in `AppInfo.cpp`, declared in `AppInfo.h`: `QSettings(lockPath, QSettings::IniFormat)`; returns `set` when the file exists and `schema` is `1`, else empty); `AppInfo` gains `Q_PROPERTY(QString setVersion READ setVersion CONSTANT)` set by a constructor argument `const QString& setVersion = {}`. `main.cpp` passes `readSetVersion(QCoreApplication::applicationDirPath() + "/../../cheekymarine.lock")` (the lock of the set this binary belongs to: `sets/<v>/plotter/bin/` up two). (design goal 7). `plotter/CMakeLists.txt` gains `set(PLOTTER_PACK_SCHEMA_MIN 1)` and `set(PLOTTER_PACK_SCHEMA_MAX 1)` beside `PLOTTER_VERSION`, passed as compile definitions on `plottercore` (it has none today) and to the tests through `plotter_add_test` (beside `PLOTTER_EXPECTED_VERSION`); `PackCatalog` refuses a schema outside `[MIN, MAX]` with the existing text `schema %1 not supported` (design "Pack schema range").

- [ ] **Step 1: Write failing tests**: C++ `readSetVersionReadsSet`, `readSetVersionEmptyWhenMissing`, `readSetVersionEmptyOnOtherSchema`; `tst_packcatalog.cpp` `schemaBelowMinRefused` (schema `PLOTTER_PACK_SCHEMA_MIN - 1`) and `schemaAtMaxAccepted` (schema `PLOTTER_PACK_SCHEMA_MAX`), values taken from the definitions, not hard-coded; `schemaTwoRefusedAndSkipped` stays green; QML in `tst_pages.qml` `test_aboutShowsSetVersion` (`setVersion: "0.1.0"` shows the line `Set: cheekymarine 0.1.0`) and `test_aboutShowsNoSet` (empty shows `Set: none (not installed from a set)`).
- [ ] **Step 2: Run** `ctest --test-dir build-plotter --output-on-failure`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** The line sits under the `Heading` in `AboutPage.qml`, same `Line` component as the n2kd line. Add `setVersion` to both QML stand-ins: the fixture's `appInfo` used at `tst_pages.qml:140` and `appInfoStub` at `tst_pages.qml:715`.
- [ ] **Step 4: Run.** Expected: all plotter tests PASS.
- [ ] **Step 5: Commit** `feat(plotter): About page set version; pack schema range in one place`.

### Task 10: Relocatable plotter bundle

**Files:**
- Modify: `plotter/CMakeLists.txt` (near the RPATH block at lines 94 to 125), `THIRD_PARTY_NOTICES`
- Create: `scripts/bundle-plotter.sh`, `scripts/tests/test_bundle_plotter.sh` (Docker: available on the GitHub runner and on the dev box)

**Interfaces:**
- Produces: `install(TARGETS cheekyplotter RUNTIME DESTINATION bin)` with `INSTALL_RPATH "\$ORIGIN/../lib"` and `INSTALL_RPATH_USE_LINK_PATH OFF` (the build-tree binary keeps its build RPATH for tests; `cmake --install` rewrites the existing DT_RPATH, so `--disable-new-dtags` still yields classic RPATH); no new option; `scripts/bundle-plotter.sh BUILD_DIR QT_PREFIX MAPLIBRE_PREFIX VERSION` writes `cheekyplotter-VERSION-x86_64.tar.gz` and prints its name, layout `bin/{cheekyplotter,qt.conf}`, `lib/`, `plugins/`, `qml/`, `licenses/`, `THIRD_PARTY_NOTICES`, `MANIFEST` (one line per file: path, SPDX license id), `DEPS` (sonames resolved outside the bundle), `PACK_SCHEMA` (`min=<PLOTTER_PACK_SCHEMA_MIN>`, `max=<PLOTTER_PACK_SCHEMA_MAX>`, read from `plotter/CMakeLists.txt`).

Rules (design "The plotter release"): the binary comes from `cmake --install BUILD_DIR --prefix <bundle>`. Libs copied (`cp -L`, keeping soname file names) are the `ldd` closure of `bin/cheekyplotter`, `plugins/**/*.so` and `qml/**/*.so`, computed with `LD_LIBRARY_PATH=$QT_PREFIX/lib:$MAPLIBRE_PREFIX/lib` and restricted to files under those two prefixes. Lib allowlist (committed in the script; any other file in `lib/` fails the build): Qt6 Core Gui Network Sql Qml QmlMeta QmlModels QmlWorkerScript Quick QuickControls2 QuickControls2Basic QuickControls2BasicStyleImpl QuickControls2Impl QuickTemplates2 QuickLayouts QuickShapes Svg OpenGL DBus WaylandClient WaylandEglClientHwIntegration XcbQpa, `libicu*`, `libQMapLibre*`. Extend it only after checking the module is LGPL. Plugin allowlist: `platforms/libqxcb.so`, `platforms/libqwayland-egl.so`, `platforms/libqwayland-generic.so`, `wayland-shell-integration/`, `wayland-graphics-integration-client/`, `wayland-decoration-client/`, `xcbglintegrations/`, `sqldrivers/libqsqlite.so`, `imageformats/libqsvg.so`, `imageformats/libqjpeg.so` (the splash logo is a JPEG, `plotter/qml/Splash.qml:41`), `iconengines/libqsvgicon.so`, `platforminputcontexts/libcomposeplatforminputcontextplugin.so`, `platforminputcontexts/libibusplatforminputcontextplugin.so`. QML modules: exactly what `$QT_PREFIX/libexec/qmlimportscanner -rootPath plotter/qml -rootPath plotter/src/qml -importPath $QT_PREFIX/qml` reports, skipping `CheekyMarine` (static, linked in); today that is QML, QtQml, QtQml.Models, QtQml.WorkerScript, QtQuick, QtQuick.Controls.Basic, QtQuick.Controls.Basic.impl, QtQuick.Controls.impl, QtQuick.Layouts, QtQuick.Shapes, QtQuick.Templates. Denylist, a second check (script fails, exit 1, naming the file): any path matching `VirtualKeyboard`, `virtualkeyboard`, `QtCharts`, `Charts`, `DataVisualization`, `Quick3DPhysics`. `qt.conf`: `[Paths]` `Prefix=..`, `Plugins=plugins`, `QmlImports=qml`. Never copy libstdc++, libgcc_s, libc, libm, libGL, libEGL, libxcb*, fontconfig, freetype from the system. `build-maplibre-qt.sh` is not changed: libQMapLibre has no RUNPATH, so the binary's classic RPATH resolves its dependencies (revisit only if the launch test fails). `THIRD_PARTY_NOTICES` gains the third-party code of each shipped Qt module (check Qt 6.8.3's "Licenses used in Qt" for every module in `lib/`) and `Qt 6.8.3 source: https://download.qt.io/archive/qt/6.8/6.8.3/single/qt-everywhere-src-6.8.3.tar.xz`.

- [ ] **Step 1: Write the failing test** `scripts/tests/test_bundle_plotter.sh`: given a bundle tarball, (a) no denylisted path, (b) every MANIFEST line has a license, and `PACK_SCHEMA` matches `plotter/CMakeLists.txt`, (c) `readelf -d bin/cheekyplotter` RPATH is `$ORIGIN/../lib`, (d) in a clean `ubuntu:24.04` container with only the Task 5 apt list installed (plus `xvfb libgl1-mesa-dri` for the test only), `ldd` on the binary, every plugin and every QML plugin shows no `not found`, and `xvfb-run -a bin/cheekyplotter --window 800x480 --data $tmp --exit-after-ms 3000` exits 0 and logs `ready in` (offscreen is refused by `platformProblem()`, `plotter/src/app/main.cpp:92`, and is not bundled). This launch is what proves plugins and QML load. Plant a fake `libQt6VirtualKeyboard.so` once to see (a) fail.
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

Workflow: on `push: tags: ['plotter-v*']` and `workflow_dispatch`. Jobs: `version` (tag check, skipped on dispatch), `test` (`uses: ./.github/workflows/plotter-ci.yml`, tests ON), `bundle` (needs test; `ubuntu-24.04`; same Qt and maplibre cache keys as plotter-ci; configure with `-DCM_PLOTTER_TESTS=OFF -DCMAKE_BUILD_TYPE=Release`; run `bundle-plotter.sh` and `test_bundle_plotter.sh`; `sha256sum` into `SHA256SUMS`; upload artifact), `publish` (only when the ref is a tag; `make_latest: false`, `generate_release_notes: true`).

- [ ] **Step 1: Write a failing test** for `check-plotter-tag.sh` in `scripts/tests/test_check_plotter_tag.sh`: `plotter-v0.1.0` passes, `plotter-v0.1.1` and `v0.1.0` fail.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the script and the workflow.
- [ ] **Step 4: Run** the test (PASS), then trigger `workflow_dispatch` on the branch: expected green with the `plotter-release` artifact present.
- [ ] **Step 5: Commit** `ci(plotter): release workflow`.

### Task 12: Set release workflow, n2kd Latest fix, and the first releases

**Files:**
- Create: `.github/workflows/set-release.yml`
- Modify: `.github/workflows/release.yml` (`make_latest: false`, comment: `# Latest stays on v0.1.0 until the first prod set (prod gates project).`), `README.md` ("Installing a release": the set one-liner first, the n2kd tarball as a manual alternative), `installer/cheekymarine.lock` (real hashes)

**Interfaces:**
- Consumes: `lock-tool.sh check`, `installer/cheekymarine.sh` with its `# BEGIN LOCK` / `# END LOCK` block.

`set-release.yml`: on `push: tags: ['cheekymarine-v*']`. Steps: tag version equals `set=` in `installer/cheekymarine.lock` (fail otherwise); `installer/lock-tool.sh check installer/cheekymarine.lock`; build `install-cheekymarine.sh` with `installer/lock-tool.sh embed`; `bash -n` it; `SHA256SUMS` over the script and the lock; publish with `prerelease: true`, `make_latest: false`, and a body that starts with:

```
Install or upgrade (Ubuntu 24.04 or newer, x86_64):

    curl -fsSL https://github.com/jjveleber/CheekyMarine/releases/download/cheekymarine-vX.Y.Z/install-cheekymarine.sh | sudo bash
```

then a table of the four parts and versions from the lock, and the pack schema range.

- [ ] **Step 1: Check** the workflow's build step locally: run the same `embed` line and `bash -n` on the output. Expected: exit 0 (the embed itself is tested in Task 1).
- [ ] **Step 2: Commit** `ci: set release workflow; n2kd releases stop taking Latest`.
- [ ] **Step 3: Whole-branch adversarial review**, fixes, owner merges the PR.
- [ ] **Step 4 (controller, owner says yes to the tag):** tag `plotter-v0.1.0` on main; wait for its release; check `v0.1.0` is still Latest. (Charts and bathy 1.1.0 are already released.)
- [ ] **Step 5:** `installer/lock-tool.sh fill installer/cheekymarine.lock`, then `check`, then embed the filled lock into the committed script (`installer/lock-tool.sh embed installer/cheekymarine.lock installer/cheekymarine.sh <tmp> && cat <tmp> > installer/cheekymarine.sh`, which keeps the file mode; `fill` does not embed, and `test_committed_script_embeds_committed_lock` fails without it); small PR, owner merges.
- [ ] **Step 6 (owner says yes):** tag `cheekymarine-v0.1.0`; check it is a pre-release and `v0.1.0` is still Latest.

### Task 13: ThinkPad run, then CapnButts (controller and owner)

- [ ] **Step 1:** Before the merge in Task 12 Step 3, send `laptop-chart` the e2e scenarios against a `file://` set built from the `plotter-release` dispatch artifact, the real n2kd `v0.1.0` and the pack 1.0.0 and 1.1.0 releases (first set with 1.0.0 packs, the second with 1.1.0, so the store and pruning are exercised): fresh install answering "y" to both prompts, reboot, plotter full screen with no manual step, `cheekymarine version`, About page set line, upgrade to a second set, a third set with the same packs and a new plotter (no pack download), `cheekymarine rollback` with Wi-Fi off, `systemctl status cheekymarine-can0` with the adapter plugged if it is at hand. Post results on the plan 5 GitHub issue.
- [ ] **Step 2:** After Task 12 Step 6, the same fresh install on the ThinkPad from the real one-liner.
- [ ] **Step 3:** The owner runs the one-liner on CapnButts and reboots. Done when the plotter comes up full screen with no step besides the two prompts.
