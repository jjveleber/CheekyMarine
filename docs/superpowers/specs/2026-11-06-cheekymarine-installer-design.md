# CheekyMarine installer: design

Date: 2026-11-06, revised 2026-11-07 after an adversarial review. Status: draft for owner approval.
Plan 5, first project.

## Intent

The owner wants every install on CapnButts (the Dell Latitude 7320 Detachable helm tablet, Ubuntu
26.04 LTS, x86_64) to come from a GitHub release, never from a source build. Today only n2kd has a
release; the chart packs have releases that predate the amber night style; the plotter has none.

This project delivers one install script, published in a release, that turns a freshly installed
Ubuntu into a working helm in one run, from a pinned, matched set of component versions. It also
gives an offline rollback to the previous set.

The worst outcome (owner): the wrong version in use on the water, either because a set reached prod
too early, or because a prod set never got picked up. Every choice below leans away from that. In
particular, the machine is never left running parts of two different sets.

## Goals

1. **A set release.** A tag `cheekymarine-vX.Y.Z` publishes a GitHub release holding
   `install-cheekymarine.sh`, `cheekymarine.lock` and `SHA256SUMS` (owner names: the app name is
   already the joke). The bare `v*` tags stay n2kd's.
2. **A pinned set.** `cheekymarine.lock` names the exact version of each part: n2kd, the charts
   pack, the bathy pack and the plotter. One set version always installs the same parts. Running the
   script of a set again upgrades or repairs in place to exactly that set (owner).
3. **Whole helm, nothing manual.** One run of the script, on a fresh Ubuntu 26.04 x86_64, installs
   (owner: "enough so that it will work ... nothing manual needs to happen"):
   - the apt packages that n2kd and the bundled plotter need at run time;
   - n2kd as a systemd service, with the `cheekymarine` user and group, and the desktop user added
     to the group;
   - both chart packs where the plotter of that set reads them;
   - the plotter, started full screen at login through a launcher that runs the active set's
     plotter with the active set's packs;
   - `can0` up whenever the adapter is plugged in, at boot or on replug: 250 kbit/s, listen-only;
   - screen blanking, idle dimming and suspend turned off, since each would hide or stop the
     plotter (exact scope under "Desktop settings").
4. **Ask before security changes** (owner). Auto-login and turning off the lock screen change only
   after the user confirms at a prompt that says plainly what the change means. The script never
   changes either setting without a yes: "no" means "leave it as it is", so a setting a
   previous install (or the user) already made stays as it is. If the setting is already in the
   helm state (auto-login on, lock off), there is no prompt. The prompt reads from the controlling
   terminal (`/dev/tty`), so it still works when the script is piped into bash, and it waits with no
   timeout; the default answer is "leave it". Only when there is no terminal at all (no `/dev/tty`:
   a systemd unit, cron, ssh without a tty, the later self-updater) does it leave the setting
   without asking. When it leaves a setting off, the script prints the command that changes it.
   Lock screen is my call: same kind of change as auto-login. Answers are not remembered (my call):
   a run asks again whenever a setting is not in the helm state and a terminal exists, which is
   rare (one run per set) and needs no stored state.
5. **A plotter release.** The plotter ships as an x86_64 tarball that carries Qt 6.8.3 and
   maplibre-native-qt (pinned commit) inside it, so it does not depend on Ubuntu's Qt. Its own tag
   and workflow, like n2kd and the packs.
6. **Offline rollback** (owner). One command returns to the previous set with no network. Data
   recorded since the upgrade may be lost on rollback; the owner accepts that.
7. **Visible versions.** The script ends by printing the set version and each part's version, and a
   `cheekymarine version` command prints the same at any time. The plotter's About page shows the
   set version read from `/opt/cheekymarine/current/cheekymarine.lock` (my call), so a set that did
   not land is obvious at the helm.
8. **Every set is a pre-release** until the prod gates exist (see Non-goals). No workflow marks a
   set as prod, and no CheekyMarine release becomes GitHub "Latest" in this project.

## Non-goals

- **Prod gates.** How a set earns prod (quality gates, what must be seen on CapnButts and on the
  water, when a workflow may mark it) is the next brainstorm, a separate design. The owner said a
  workflow may mark prod, but only behind solid gates, and that the process is loose today.
- **Self-update.** Later the plotter will find the prod set and update itself. Not built here.
- **Machine health.** No apt full-upgrade, Ubuntu updates, firmware, backups or general setup
  (owner).
- **aarch64 / the Pi.** x86_64 only. The Pi build is parked.
- **The packs themselves.** PR #57 (merged 2026-11-07) bumped them to 1.1.0; their tags and
  workflow are unchanged.
- **Tamper-proofing.** The concern is the right version, not an attacker. HTTPS plus the SHA-256
  pinned in the lock is the integrity check; no signing.

## Anti-goals

- Nothing here may block the later self-update. The lock file is a stable, documented format the
  plotter can read too.
- Nothing may count as prod by accident. In particular "Latest" on the repo must not land on a
  random release (see Constraints).
- A security-relevant change made without the user knowing.
- A failed or partial download that leaves the helm broken: the old set stays active until the new
  one is fully in place.
- A mixed state: n2kd from one set and the plotter or packs from another.

## Owner decisions (as stated)

- Install script from a release; it sets up all of the helm.
- Pinned matched set per release, not the newest of each part.
- Names: `cheekymarine-vX.Y.Z`, `install-cheekymarine.sh`, `cheekymarine.lock`.
- Prod releases are marked, the app will update to the prod one; other releases are installable on
  purpose but never offered as updates. The rest of the marker scheme (below) the owner called right.
- A workflow may mark prod, but only behind gates designed later. Order: installer first, gates next.
- Rollback to a known-good set, working offline. A phone hotspot exists, but updates mostly happen at
  home or off the boat.
- Rollback may lose data.
- Ensure deps and leave nothing manual, but do not manage the machine's general health.
- Ask before turning on auto-login.

## Constraints and facts

- **Release marker scheme** (agreed): prod = a normal release marked GitHub "Latest"; every other
  set is a pre-release. Consequence: CheekyMarine sets must own "Latest" for the whole repo. Today
  n2kd `v0.1.0` holds it. `chartpack-release.yml` already sets `make_latest: false`; `release.yml`
  (n2kd) does not, and the new plotter release workflow must not either. This project sets
  `make_latest: false` on n2kd and plotter releases; the `release.yml` change must land before any
  n2kd `v0.2.0` tag, or that tag takes Latest. Moving "Latest" off `v0.1.0` waits for the first
  prod set (prod gates project); until then nothing points the app at "Latest". Nobody edits
  `v0.1.0` to a pre-release or deletes it before then: GitHub would hand Latest to the newest other
  normal release, a pack release.
- **n2kd release** (`v0.1.0`): tarball `n2kd-X.Y.Z-x86_64.tar.gz` holding one top-level directory
  `n2kd-X.Y.Z-x86_64/` with a `usr/` tree (`usr/bin/n2kd`, `usr/share/cheekymarine/canboat.json`,
  `usr/lib/systemd/system/n2kd.service`, `usr/lib/sysusers.d/cheekymarine.conf`), the licenses and
  an inner `SHA256SUMS` (`scripts/package-n2kd.sh`). The release-level `SHA256SUMS` lists both
  arch tarballs. Built on Ubuntu 24.04; needs glibc 2.38 and GLIBCXX_3.4.32. The unit runs
  `/usr/bin/n2kd --can can0 --rawlog /var/lib/cheekymarine/rawlog` (absolute path), reads `can0`
  and retries every 5 s while it is missing. `--pgns PATH` overrides the canboat.json location.
  Socket `/run/cheekymarine/n2k.sock`, group `cheekymarine`, mode 0660.
- **Pack releases**: `charts-puget-north-vX.Y.Z` and `bathy-puget-north-vX.Y.Z`, each a
  `<pack>-<region>-<version>.tar` plus `SHA256SUMS`. 1.1.0 (PR #57, merged) is the first with amber
  night; its two tags are not cut yet.
- **Plotter**: `cheekyplotter [--socket PATH] [--packs DIR] [--data DIR] [--window WxH]
  [--fullscreen]`. All user data is one SQLite file, `plotter.db`, in `--data`, default
  `~/.local/share/cheekyplotter/`, opened in WAL mode (so `plotter.db-wal` and `plotter.db-shm` sit
  beside it while it runs). Packs default to `<data dir>/packs`. The plotter scans the packs
  directory and uses the highest version of each kind it finds there (`PackCatalog::best`), so the
  only way to pin packs per set is to point `--packs` at a directory holding only that set's packs.
  Pack styles load at start. SIGTERM quits cleanly. Today the binary finds Qt and maplibre by an
  absolute build RPATH with `--disable-new-dtags` (classic RPATH, because RUNPATH is not searched
  for `libQMapLibre.so`'s own dependencies); a relocatable bundle needs `$ORIGIN`-relative paths
  instead. The plotter version is `PLOTTER_VERSION` in `plotter/CMakeLists.txt`, separate from the
  root CMake version (n2kd's). Build deps and the Ubuntu 26.04 GCC 15 flag are in
  `plotter/README.md`; CI already caches Qt and the maplibre prefix.
- **Licenses**: Qt is LGPL-3.0, linked dynamically. A bundle that ships Qt libraries must carry the
  license texts and the notices in `THIRD_PARTY_NOTICES`, keep the libraries replaceable (separate
  `.so` files), and point to the exact Qt 6.8.3 source archive. Qt's own lib directory also ships
  third-party code (ICU, and inside Qt modules freetype, harfbuzz, pcre2, libpng, libjpeg, sqlite,
  zlib); `THIRD_PARTY_NOTICES` lists only Qt today, so the bundle adds their notices. Some Qt
  modules and plugins are GPL-only (for example Qt Virtual Keyboard, Qt Charts, Qt Data
  Visualization); none may enter the bundle. No GPL components (owner rule).
- **Data schema moves forward**: a newer plotter migrates `plotter.db` forward (as schema 1.2.0
  renamed `favourite` to `favorite`). An older plotter refuses a file only when its schema major is
  newer (`Store.cpp`, recovery screen). A newer minor it opens silently, skips every migration,
  misreads renamed data and writes old-style data back; the newer migration then never reruns,
  because the file already says the newer version. So the plotter does not protect itself: the
  installer must never hand an older plotter a database from a newer set (see "Data rule").
- **Hardware**: 256 GB disk, so keeping two sets and old database copies is cheap.
- **Desktop**: Ubuntu 26.04 with GNOME on Wayland and GDM, NetworkManager (not systemd-networkd).
  Auto-login is `/etc/gdm3/custom.conf`, `[daemon]` `AutomaticLoginEnable=true` and
  `AutomaticLogin=<user>`. Screen blank, lock, dim and idle sleep are per-user GNOME settings (the
  gist's `post-install.sh` has the gsettings keys used on CapnButts so far). The lid switch is
  logind, a system setting. A fresh install runs unattended-upgrades soon after first boot, so apt
  may be locked for minutes.
- **Downloads**: the repo is public. Release assets download from fixed URLs
  `https://github.com/jjveleber/CheekyMarine/releases/download/<tag>/<asset>` with no GitHub API
  call, so no token and no API rate limit apply. The installer depends on the repo staying public.

## How it behaves

### Layout (my call; the builder may refine names)

```
/opt/cheekymarine/
  sets/<set-version>/        one installed set, all parts unpacked:
    cheekymarine.lock          the set's lock
    n2kd/                      n2kd tarball contents (usr/bin/n2kd, canboat.json, ...)
    plotter/                   plotter bundle
    packs/                     this set's charts and bathy packs only
  current -> sets/<ver>      the active set
  previous -> sets/<ver>     the set rollback returns to
  bin/cheekymarine           the command: version, rollback
  bin/cheekyplotter          launcher: runs current/plotter with --fullscreen --packs current/packs
/var/lib/cheekymarine/db-copies/
  plotter-<set-version>-<timestamp>.db   saved databases (see "Data rule")
```

Only the active set and the one before it are kept (my call). Every part runs through `current`:

- **n2kd**: the script installs `/etc/systemd/system/n2kd.service` (taken from the set's unit, so
  it shadows any `/usr/lib/systemd/system/n2kd.service` from an earlier tarball install) with
  `ExecStart=/opt/cheekymarine/current/n2kd/usr/bin/n2kd --can can0 --rawlog
  /var/lib/cheekymarine/rawlog --pgns /opt/cheekymarine/current/n2kd/usr/share/cheekymarine/canboat.json`,
  and installs the set's sysusers file to `/etc/sysusers.d/cheekymarine.conf` and runs
  `systemd-sysusers`. A `/usr/bin/n2kd` from an earlier hand install is left in place, unused.
- **plotter and packs**: the GNOME autostart entry and any desktop entry run the launcher, which
  execs `/opt/cheekymarine/current/plotter/bin/cheekyplotter --fullscreen --packs
  /opt/cheekymarine/current/packs`.

So flipping `current` is the whole switch for all three parts, and it is one atomic rename.

### The switch (used by install, upgrade, downgrade and rollback)

1. Stop the plotter (SIGTERM to the desktop user's `cheekyplotter`, wait for it to exit) and stop
   n2kd.
2. Apply the data rule (below) with the plotter stopped.
3. Point `previous` at the old set (only when the target differs from `current`), then replace
   `current` atomically (`ln -sfn` to a temporary name, then `mv -T` over `current`).
4. `systemctl daemon-reload` if the unit changed, start n2kd, start the plotter for the desktop
   user (or, on a run that changed group membership, skip the start and say a log-out or reboot is
   needed, since the new group only applies to a new login).
5. Print the set and part versions.

If the script dies before step 3, the old set is still `current` and complete; a rerun starts
over. If it dies after step 3, the new set is `current` and complete; a rerun finishes the starts.
Either way no mix of sets runs.

### Install or upgrade (online)

1. The user runs the one-liner from the set release notes (`curl -fsSL <url>/install-cheekymarine.sh
   | sudo bash`) or downloads the script and runs it. The set workflow embeds the set version and
   the lock contents in the published script, so it needs no file beside it. `SHA256SUMS` on the set
   release is for a person who downloads by hand.
2. It checks: Ubuntu 24.04 or newer, x86_64, run with sudo (`SUDO_USER` set; plain root without
   `SUDO_USER` stops with a message). Anything else stops with a plain message. The desktop user
   (autostart, auto-login, group membership, `plotter.db`) is `SUDO_USER` (my call).
3. It downloads every part named in the lock from its fixed release URL into a staging directory
   and checks each against the SHA-256 in the lock (the lock is the single source of truth). Any
   mismatch or failed download stops the script with the active set untouched.
4. It installs the run-time apt packages (waiting up to 10 minutes for the apt lock, so a running
   unattended-upgrade does not fail the run). Failure stops the script with the active set
   untouched.
5. It unpacks every part into a fresh `sets/<version>.new`, then renames it to `sets/<version>`
   (replacing a previous copy of the same set when repairing). It installs or refreshes the n2kd
   unit, sysusers file, group membership, the launcher, autostart, `can0`, and the desktop
   settings, and asks the two security questions (goal 4).
6. It runs the switch.
7. It deletes sets other than `current` and `previous`.

A rerun of the set that is already `current` re-unpacks it fresh and runs the switch; `previous`
does not move, so the rollback target is kept.

CapnButts today has Ubuntu installed and no plotter, no packs and no `plotter.db`; it may already
have n2kd `v0.1.0` in `/usr` from its tarball, which the `/etc` unit shadows. So no adoption of an
earlier layout is needed.

### Rollback (offline)

`cheekymarine rollback` runs the switch to `previous` with no network. Afterwards `current` is the
older set, `previous` is cleared and the newer set is deleted (its database copy is kept, see the
data rule). A second rollback is refused with a plain message. Running the newer set's script again
later is an ordinary upgrade (fresh download).

### Installing an older set over a newer one (my call)

Allowed, because non-prod sets are installable on purpose, but the script says it is a downgrade
and asks to confirm (no terminal: it stops). The newer set becomes `previous` as in any switch. The
data rule decides the database.

### Data rule (one rule for every switch, my call)

The installer records which set's plotter last used the live `plotter.db` (a label file beside the
copies). On a switch to set T, with the plotter stopped:

1. Copy the live `plotter.db` with its `-wal` and `-shm` files (or one `sqlite3 .backup`) to
   `db-copies`, labeled with the set it belonged to. Copies are kept (disk is cheap); the owner
   can delete them.
2. If T's plotter is the same as or newer than the db's plotter, keep the live database: the newer
   plotter migrates it forward. Data recorded on the older set is kept.
3. If T's plotter is older: restore the newest copy labeled T if one exists, otherwise move the
   live database aside and let T's plotter start with a fresh one. An older plotter never meets a
   database from a newer set. Data recorded since the upgrade is lost (owner accepts; it remains in
   `db-copies`).

Restored and moved files keep the desktop user as owner. A first install with no `plotter.db` skips
the rule.

### Desktop settings

Written for the desktop user, as that user, and read back to confirm (builder picks the mechanism,
for example `sudo -u "$SUDO_USER"` with the user's session bus when it exists, else
`dbus-run-session`):

- idle blank off, idle dim off, automatic sleep off on AC and on battery;
- lock screen: only after a yes (goal 4).

System files:

- auto-login: `/etc/gdm3/custom.conf`, only after a yes (goal 4);
- lid switch: logind drop-in `/etc/systemd/logind.conf.d/cheekymarine.conf`
  (OPEN: owner decides whether closing the keyboard cover keeps the helm running or sleeps; see
  "Open questions").

### `can0`

A udev rule matches the CAN adapter's `can0` and pulls in a oneshot unit (`SYSTEMD_WANTS`), bound to
the device, that runs `ip link set can0 type can bitrate 250000 listen-only on` then `ip link set
can0 up` (iproute2, no can-utils needed). It survives replug and reboot and does not need
systemd-networkd. Listen-only means the tablet never acknowledges frames: a bench with one talker
and this tablet goes error-passive, so bench loopback tests need a second acknowledging node.

### The lock file

`cheekymarine.lock` is a flat `key=value` text file (my call: bash reads it with no extra tool, the
plotter reads it as an INI file through `QSettings`) with a schema number, the set version, and for
each part its release tag, asset name and SHA-256. The later self-update reads the same file, so
the format is a contract: document it in the repo the way the n2kd JSON contract is documented.

### The plotter release

A tag (name left to the builder, for example `plotter-vX.Y.Z`) runs a workflow that:

- checks the tag against `PLOTTER_VERSION`;
- builds and runs the plotter tests in one job (`CM_PLOTTER_TESTS=ON`), so an untested commit does
  not ship;
- builds `cheekyplotter` for the tarball on an Ubuntu 24.04 runner (so it runs on 24.04 and 26.04),
  with `CM_PLOTTER_TESTS=OFF`;
- bundles Qt and maplibre libraries, Qt plugins and QML modules from an explicit allowlist (what
  the plotter uses: QtQuick and QtQuick.Controls.Basic, QSQLITE, SVG, the wayland and xcb platform
  plugins, and their dependencies), with `$ORIGIN`-relative paths, and a `qt.conf` next to the
  binary (`Plugins=../plugins`, `QmlImports=../qml`), since plugins and QML are not found through
  RPATH;
- never bundles system libraries: libstdc++, libgcc_s, glibc, libGL/libEGL, Mesa, libxcb*,
  fontconfig, the system freetype (an older libstdc++ reached through the classic RPATH would load
  before the system one and break the 26.04 Mesa driver);
- adds the license texts, the third-party notices of the shipped Qt modules, the Qt 6.8.3 source
  archive URL, and a manifest of every bundled file with its license;
- fails if any GPL-only Qt file is in the tarball;
- publishes the tarball and `SHA256SUMS`, `make_latest: false`.

### The set release

A tag `cheekymarine-vX.Y.Z` runs a workflow that checks the tag against the version in
`cheekymarine.lock`, checks that every release the lock names exists and that each SHA-256 in the
lock matches that part release's `SHA256SUMS` (no large downloads), embeds the lock in the
script, and publishes the script, the lock and `SHA256SUMS` as a pre-release with release notes
that print the one-liner.

## Done means real releases (my call)

The project ends with CapnButts running a real set, not only with workflows. The first set pins
n2kd `v0.1.0` (no n2kd code changed since; `release.yml` still gets `make_latest: false` for later
releases), charts and bathy 1.1.0 (PR #57 merged; waits on its two tags), and the first plotter
release (which carries the About page set version). Then the first `cheekymarine-v0.1.0` tag is cut
as a pre-release and the owner installs it on CapnButts.

## Verification

- A throwaway Ubuntu environment (container with systemd, VM, or CI runner; builder picks) tests the
  logic: fresh install, a rerun with nothing to do, an upgrade between two sets, a rollback with the
  network off, a downgrade, the data rule, and a failed download that leaves the old set active.
- The ThinkPad test laptop (Ubuntu 26.04.1, GNOME on Wayland, the `laptop-chart` session) runs the
  full script from a real release before CapnButts: both prompts, the desktop settings, auto-login,
  reboot to the full-screen plotter, and rollback. A container cannot exercise GDM, GNOME, Wayland
  or group re-login.
- On CapnButts, the owner runs the first set from its release and sees the plotter come up full
  screen after a reboot with no manual step besides answering the two prompts.

## Left to the builder

- Exact names under `/opt/cheekymarine` and the plotter tag name.
- How the plotter bundle is made (tooling), within the allowlist and license rules above.
- Which apt packages are the run-time set.
- The test environment for the logic tests.
- How desktop settings are written as the user, within "Desktop settings".

## Open questions (owner)

- Lid switch: when the keyboard cover is closed on CapnButts, should the helm keep running (screen
  on, plotter live) or go to sleep?
