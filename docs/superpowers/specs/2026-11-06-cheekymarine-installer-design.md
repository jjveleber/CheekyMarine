# CheekyMarine installer: design

Date: 2026-11-06. Status: draft for owner approval. Plan 5, first project.

## Intent

The owner wants every install on CapnButts (the Dell Latitude 7320 Detachable helm tablet, Ubuntu
26.04 LTS, x86_64) to come from a GitHub release, never from a source build. Today only n2kd has a
release; the chart packs have releases that predate the amber night style; the plotter has none.

This project delivers one install script, published in a release, that turns a freshly installed
Ubuntu into a working helm in one run, from a pinned, matched set of component versions. It also
gives an offline rollback to the previous set.

The worst outcome (owner): the wrong version in use on the water, either because a set reached prod
too early, or because a prod set never got picked up. Every choice below leans away from that.

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
   - both chart packs where the plotter reads them;
   - the plotter, started full screen at login (`cheekyplotter --fullscreen`);
   - `can0` up at boot whenever the adapter is plugged in: 250 kbit/s, listen-only;
   - screen blanking and suspend turned off, since each would hide or stop the plotter.
4. **Ask before security changes** (owner). Auto-login and turning off the lock screen change only
   after the user confirms at a prompt that says plainly what the change means. The script never
   changes either setting without a yes: "no" means "leave it as it is", so a setting a
   previous install (or the user) already made stays as it is. If the setting is already in the
   helm state (auto-login on, lock off), there is no prompt. The prompt reads from the controlling
   terminal (`/dev/tty`), so it still works when the script is piped into bash, and it waits with no
   timeout; the default answer is "leave it". Only when there is no terminal at all (no `/dev/tty`:
   a systemd unit, cron, ssh without a tty, the later self-updater) does it leave the setting
   without asking. When it leaves a setting off, the script prints the command that changes it. Lock screen is my call: same kind of change as auto-login.
5. **A plotter release.** The plotter ships as an x86_64 tarball that carries Qt 6.8.3 and
   maplibre-native-qt (pinned commit) inside it, so it does not depend on Ubuntu's Qt. Its own tag
   and workflow, like n2kd and the packs.
6. **Offline rollback** (owner). One command returns to the previous set with no network. Data
   recorded since the upgrade may be lost on rollback; the owner accepts that.
7. **Visible versions.** The script ends by printing the set version and each part's version. The
   plotter's About page shows the set version (my call), so a set that did not land is obvious.
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
- **The packs themselves.** PR #57 bumps them to 1.1.0; their tags and workflow are unchanged.

## Anti-goals

- Nothing here may block the later self-update. The lock file is a stable, documented format the
  plotter can read too.
- Nothing may count as prod by accident. In particular "Latest" on the repo must not land on a
  random release (see Constraints).
- A security-relevant change made without the user knowing.
- A failed or partial download that leaves the helm broken: the old set stays active until the new
  one is fully in place.

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
  `make_latest: false` on n2kd and plotter releases. Moving "Latest" off `v0.1.0` waits for the first
  prod set (prod gates project); until then nothing points the app at "Latest".
- **n2kd release** (`v0.1.0`): tarball `n2kd-X.Y.Z-x86_64.tar.gz` with a `/usr` install tree
  (`usr/bin/n2kd`, `usr/share/cheekymarine/canboat.json`, `usr/lib/systemd/system/n2kd.service`,
  `usr/lib/sysusers.d/cheekymarine.conf`) plus licenses; outer `SHA256SUMS`. Built on Ubuntu 24.04;
  needs glibc 2.38 and GLIBCXX_3.4.32. The unit reads `can0` and retries every 5 s while it is
  missing. Socket `/run/cheekymarine/n2k.sock`, group `cheekymarine`, mode 0660.
- **Pack releases**: `charts-puget-north-vX.Y.Z` and `bathy-puget-north-vX.Y.Z`, each a
  `<pack>-<region>-<version>.tar` plus `SHA256SUMS`. 1.1.0 (PR #57) is the first with amber night.
- **Plotter**: `cheekyplotter [--socket PATH] [--packs DIR] [--data DIR] [--window WxH]
  [--fullscreen]`. All user data is one SQLite file, `plotter.db`, in `--data`, default
  `~/.local/share/cheekyplotter/`. Packs default to `<data dir>/packs`. Pack styles load at start.
  Today the binary finds Qt and maplibre by an absolute build RPATH with `--disable-new-dtags`
  (classic RPATH, because RUNPATH is not searched for `libQMapLibre.so`'s own dependencies); a
  relocatable bundle needs `$ORIGIN`-relative paths instead. Build deps and the Ubuntu 26.04 GCC 15
  flag are in `plotter/README.md`; CI already caches Qt and the maplibre prefix.
- **Licenses**: Qt is LGPL-3.0, linked dynamically. A bundle that ships Qt libraries must carry the
  license texts and the notices in `THIRD_PARTY_NOTICES`, and keep the libraries replaceable
  (separate `.so` files). No GPL components (owner rule).
- **Data schema moves forward**: a newer plotter can migrate `plotter.db` (as schema 1.2.0 renamed
  `favourite` to `favorite`), and an older plotter may then refuse it (recovery screen). Hence the
  data copy below.
- **Hardware**: 256 GB disk, so keeping two sets is cheap.
- **Desktop**: Ubuntu 26.04 with GNOME and GDM. Auto-login is a GDM setting; screen blank, lock and
  suspend are per-user GNOME settings (the gist's `post-install.sh` has the gsettings keys used on
  CapnButts so far).

## How it behaves

### Layout (my call; the builder may refine names)

```
/opt/cheekymarine/
  sets/<set-version>/        one installed set: plotter bundle, packs (or links to them), the lock
  current -> sets/<ver>      the active set
  previous -> sets/<ver>     the set rollback returns to
```

Only the active set and the one before it are kept (my call). n2kd installs to `/usr` from its
tarball, as its release documents; the cached n2kd tarball sits in the set directory so rollback can
reinstall the previous n2kd offline. Whether the plotter and packs are referenced through `current`
by a launcher or by paths the script writes is left to the builder, as long as flipping `current`
plus a restart is the whole switch for the plotter and packs.

### Install or upgrade (online)

1. The user downloads `install-cheekymarine.sh` and `SHA256SUMS` from a set release, or runs a
   one-liner the release notes print. The script reads its own set's `cheekymarine.lock`.
2. It checks it runs on Ubuntu x86_64 and stops with a plain message otherwise.
3. It downloads every part named in the lock from its GitHub release and checks each against that
   release's `SHA256SUMS`. Any mismatch or failed download stops the script with the active set
   untouched.
4. It installs run-time apt packages, unpacks the set under `sets/<version>` (n2kd staged there,
   not yet in `/usr`), sets up `can0`, autostart, blank and suspend, and asks the two security
   questions (goal 4).
5. Before it switches, it copies `plotter.db` aside, labeled with the set it belonged to.
6. At switch time it installs the staged n2kd into `/usr`, points `previous` at the old set,
   `current` at the new one, restarts n2kd and the plotter, and prints the set and part versions.

The desktop user (autostart, auto-login, group membership, `plotter.db`) is the user who ran the
script with sudo (`SUDO_USER`) (my call). Running as plain root with no `SUDO_USER` stops with a
message.

CapnButts today has Ubuntu installed and no plotter, no packs and no `plotter.db`; it may already
have n2kd `v0.1.0` in `/usr` from its tarball, which the installer simply installs over. So no
adoption of an earlier layout is needed.

A second run of the same set changes nothing that is already right and asks no question it already
has an answer for (my call: it re-asks only if the setting is still off and the user said nothing
last time; the builder picks how to remember the answer).

### Rollback (offline)

One command (name left to the builder; my guess `cheekymarine rollback`, installed by the script)
swaps `current` back to `previous`, reinstalls the previous n2kd from its cached tarball, restores
the `plotter.db` copy taken when the newer set went in, restarts both, and prints the versions.
Anything recorded since the upgrade is lost (owner accepts). No network is used.

After a rollback (my call): `current` is the older set, `previous` is cleared and the newer set and
its data copy are deleted. A second rollback is refused with a plain message. Running the newer
set's script again later is an ordinary upgrade (fresh download, fresh data copy).

### Installing an older set over a newer one (my call)

Allowed, because non-prod sets are installable on purpose, but the script says it is a downgrade
and asks to confirm (no terminal: it stops). The newer set becomes `previous` as in any switch. For
data: if a `plotter.db` copy labeled with the target set exists, it is restored; otherwise the
current `plotter.db` is moved aside (renamed, kept) and the older plotter starts with a fresh one,
so it never meets a database from a newer schema. The owner accepted data loss on rollback; this
is the same trade.

### The lock file

`cheekymarine.lock` is a small, documented text or JSON file (format left to the builder) with a
schema number, the set version, and for each part its release tag, asset name and SHA-256. The
later self-update reads the same file, so the format is a contract: document it in the repo the way
the n2kd JSON contract is documented.

### The plotter release

A tag (name left to the builder, for example `plotter-vX.Y.Z`) runs a workflow that builds
`cheekyplotter` on a runner whose glibc is no newer than Ubuntu 24.04's (so it runs on 24.04 and
26.04), with `CM_PLOTTER_TESTS=OFF`, bundles the Qt and maplibre libraries and Qt plugins and QML it
needs into one tarball with `$ORIGIN`-relative paths, adds the license texts, and publishes it with
`SHA256SUMS`, `make_latest: false`. The plotter's own version comes from its build; the set version
reaches the About page from the installed lock (builder picks the mechanism).

### The set release

A tag `cheekymarine-vX.Y.Z` runs a workflow that checks the tag against the version in
`cheekymarine.lock`, checks that every release the lock names exists and that its SHA-256 matches
the published asset, then publishes the script, the lock and `SHA256SUMS` as a pre-release.

## Done means real releases (my call)

The project ends with CapnButts running a real set, not only with workflows. The first set pins
n2kd `v0.1.0` (no n2kd code changed since; `release.yml` still gets `make_latest: false` for later
releases), charts and bathy 1.1.0 (waits on PR #57 merging and its two tags), and the first plotter
release (which carries the About page set version). Then the first `cheekymarine-v0.1.0` tag is cut
as a pre-release and the owner installs it on CapnButts.

## Verification

- The installer and rollback are tested on a throwaway Ubuntu 26.04 x86_64 environment before
  CapnButts (builder picks: VM, container with systemd, or CI runner), including a fresh install,
  a rerun with nothing to do, an upgrade between two sets, a rollback with the network off, and a
  failed download that leaves the old set active.
- On CapnButts, the owner runs the first set from its release and sees the plotter come up full
  screen after a reboot with no manual step besides answering the two prompts.

## Left to the builder

- Exact file layout under `/opt/cheekymarine`, the launcher, the rollback command name.
- The lock file format (inside the contract above) and the plotter tag name.
- How the plotter bundle is made (tooling, which Qt plugins and QML modules), within the license
  constraints.
- How `can0` comes up (udev rule, systemd-networkd, or a unit), as long as it is 250 kbit/s,
  listen-only, and survives replug and reboot.
- Which apt packages are the run-time set.
- The test environment.
- How the script remembers prompt answers.
