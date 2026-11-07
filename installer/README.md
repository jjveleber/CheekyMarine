# CheekyMarine installer

The installer puts one CheekyMarine set (n2kd, the plotter and the chart and depth packs, at
versions that are known to work together) on an Ubuntu 24.04 or newer x86_64 tablet.

## Install or upgrade

Run the one-liner from the set's release notes in a terminal, from the desktop user's account:

```
curl -fsSL https://github.com/jjveleber/CheekyMarine/releases/download/cheekymarine-vX.Y.Z/install-cheekymarine.sh | sudo bash
```

Replace `X.Y.Z` with the set version. You can also download `install-cheekymarine.sh` from the set
release, check it against the release's `SHA256SUMS`, and run `sudo bash install-cheekymarine.sh`.
Running the same set again repairs it; running a newer set upgrades.

The script downloads every part and checks each against the SHA-256 in its lock. If a download,
a check or the apt step fails, it stops with the running set untouched.

Log out and back in after the first install. The first install adds you to the `cheekymarine`
group, and a new group only applies to a new login, so the plotter starts after that.

## What the script changes

- `/opt/cheekymarine/sets/`: one directory per installed set. Only the active set and the one
  before it are kept.
- `/opt/cheekymarine/packs/`: the pack store. Each pack version is downloaded and unpacked once, so
  a set reuses packs already downloaded by an earlier set. Packs that neither kept set uses are
  deleted.
- `/opt/cheekymarine/current` and `/opt/cheekymarine/previous`: links to the active set and to the
  one `cheekymarine rollback` returns to.
- `/opt/cheekymarine/bin/cheekymarine` (the command below) and `/opt/cheekymarine/bin/cheekyplotter`
  (starts the active set's plotter, full screen).
- `/etc/systemd/system/n2kd.service` (enabled), `/etc/sysusers.d/cheekymarine.conf` (the
  `cheekymarine` user and group), and your account added to the `cheekymarine` group.
- `can0` at 250 kbit/s, listen-only, brought up whenever the CAN adapter is plugged in and at boot:
  `/etc/udev/rules.d/80-cheekymarine-can0.rules` and `/etc/systemd/system/cheekymarine-can0.service`.
- `~/.config/autostart/cheekyplotter.desktop`: the plotter starts when you log in.
- Your desktop settings: screen blanking, dimming and automatic sleep are turned off.
- The apt packages the plotter needs to run.
- `/var/lib/cheekymarine/db-copies/` and `/var/lib/cheekymarine/db-label`: see "Your data" below.

The lid switch is not changed: closing the cover still suspends.

## The two questions

The script asks two questions on the terminal. Each answer defaults to no, which leaves the
setting as it is and prints the command to change it later:

- Turn on automatic login (in `/etc/gdm3/custom.conf`). Anyone who opens the tablet gets your
  desktop with no password.
- Turn off the lock screen. The screen does not ask for your password after it wakes.

With no terminal (for example from a script), both settings are left as they are and the commands
are printed.

## Installing an older set

Installing a set older than the installed one is a downgrade. The script asks to confirm it before
it changes anything; anything but yes, or no terminal, stops it with nothing changed. The newer
set is kept as `previous`.

## Commands

- `cheekymarine version`: the installed set and the version of each part.
- `sudo cheekymarine rollback`: go back to the previous set (the one active before the last
  upgrade or downgrade), with no network. The newer set is deleted, with the packs only it used. A second rollback is refused
  (`cheekymarine: nothing to roll back to`). To go forward again, run the newer set's install
  one-liner; it downloads only what is missing.
- `sudo cheekymarine install`: reinstall the active set (downloads what is missing).

The command lives in `/opt/cheekymarine/bin`; run it by that path, or add the directory to your
`PATH`.

## Your data

All the plotter's user data is one file, `~/.local/share/cheekyplotter/plotter.db`.
On every switch the script copies it to `/var/lib/cheekymarine/db-copies/`, named
`plotter-<set>-<time>.db` after the set that used it. The copies are kept; delete old ones by hand
if you like.

Moving to a set whose plotter is the same or newer keeps your data. Moving to an older plotter (a
rollback or a downgrade) never hands it data from a newer one: the script puts back the newest copy
made from that older set, or, if there is none, the older plotter starts with an empty database.
Data recorded on the newer set stays in `db-copies`.

## Lock format (contract)

`cheekymarine.lock` pins one matched set of parts. It is a flat `key=value` text file: no sections,
`#` comments, one key per line. Bash reads it with no extra tool, and the plotter reads it as an
INI file through `QSettings`. The installer embeds it in `cheekymarine.sh`, and the plotter and
the later self-updater read the same file, so this format is a contract.

Keys, in this order:

| Key | Meaning |
| --- | --- |
| `schema` | Lock format number. Bumps on an incompatible change. Currently `1`. |
| `set` | Set version `X.Y.Z`. |
| `<part>.version` | Version of the part (`n2kd`, `charts`, `bathy`, `plotter`). |
| `<part>.tag` | GitHub release tag that holds the part's asset. |
| `<part>.asset` | Asset file name in that release. |
| `<part>.sha256` | SHA-256 of the asset, as listed in the release's `SHA256SUMS`. |
| `charts.schema`, `bathy.schema` | The pack's manifest `schema`. Placed after the pack's `sha256`. They exist so a later project can update packs apart from sets. |
| `plotter.pack_schema_min`, `plotter.pack_schema_max` | Inclusive range of pack manifest `schema` values the set's plotter accepts. Placed after the plotter's `sha256`. |

Rules for readers:

- Ignore keys you do not know. New keys may appear without a `schema` bump.
- `schema` bumps only on an incompatible change (a key removed or its meaning changed).
- A `sha256` of 64 zeros means the part is not released yet.

## lock-tool.sh

- `lock-tool.sh check LOCK`: exit 0 when every part's `sha256` equals the line for its `asset` in
  `<base>/<tag>/SHA256SUMS` and each pack's `schema` is inside the plotter range. Otherwise exit 1,
  naming the part.
- `lock-tool.sh fill LOCK`: rewrite each `sha256` from those files.
- `lock-tool.sh embed LOCK SCRIPT OUT`: write OUT as SCRIPT with the lines between
  `CM_LOCK=$(cat <<'LOCK'` and `LOCK` replaced by the lines of LOCK.

`<base>` is `${CM_BASE_URL:-https://github.com/jjveleber/CheekyMarine/releases/download}`.

## Tests

From the repo root: `python3 -m unittest discover -s installer/tests -v`
