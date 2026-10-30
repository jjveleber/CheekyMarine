# CheekyMarine plotter

Qt 6 / QML chart plotter app (`cheekyplotter`). It is an optional CMake subproject: the root build
only includes it with `-DCM_BUILD_PLOTTER=ON`, so the n2kd build and its tests are unaffected.

- `plottercore`: static library with all application logic (tests link it).
- `plotterqml`: the QML module `CheekyMarine` (static, so the QuickTest runner imports it too).
- `cheekyplotter`: the app.
- `tests/`: Qt Test executables, added with `plotter_add_test(NAME SOURCES...)`.
- `tests/qml/`: QML tests; the `tst_qml` QuickTest runner runs every `tst_*.qml` there, offscreen.
- `fonts/`: Noto Sans (OFL), copied from `chartpack/fonts`.

The plotter has its own version, `PLOTTER_VERSION` in `plotter/CMakeLists.txt`, independent of the
n2kd version.

## What it does

A touch UI for a 10 inch panel (the diagonal is a setting) with a tab bar on the right edge:

- Chart: charts pack for navigation, bathy pack for fishing, own ship with follow and orientation,
  up to eight configurable overlay slots, AIS targets (tap one for its sheet), and a seabed legend
  sheet from the "Legend" button.
- Numbers: big readouts (depth and speed by default).
- Tracks: records the boat's track (off by default), lists saved tracks, shows or hides them on the chart.
- Settings: units, depth thresholds, palette (auto follows the sun, or day, dusk, night), chart
  mode, touch lock timeout, panel size, overlay editing. About shows versions and installed packs.
- Touch lock: the padlock in the tab bar locks the screen (it also locks after the timeout); hold
  the padlock for 1.5 s to unlock.
- A no-data banner when n2kd is not running or sends nothing, and a recovery screen when
  `plotter.db` cannot be opened.

## Prerequisites

Ubuntu 24.04 packages:

```bash
sudo apt-get install -y ninja-build libgl1-mesa-dev libxkbcommon-dev libicu-dev \
    libcurl4-openssl-dev libuv1-dev libsqlite3-dev zlib1g-dev libpng-dev libjpeg-dev libwebp-dev \
    libxcb-cursor0
```

Qt 6.8.3 (plain `pip install --user` is blocked by PEP 668, so use pipx; no `-m` modules needed):

```bash
pipx install aqtinstall
aqt install-qt linux desktop 6.8.3 linux_gcc_64 -O ~/Qt
```

maplibre-native-qt at the pinned commit, installed into `~/.local/maplibre-qt` (the script is
`scripts/build-maplibre-qt.sh`; see `docs/plotter/spike-findings.md` for why this commit and these
options). The first run clones the source into `~/.cache/cheekymarine/maplibre-native-qt`, which
needs about 8.5 GB of free disk plus the build tree (the clone takes longer than the build):

```bash
CMAKE_PREFIX_PATH=$HOME/Qt/6.8.3/gcc_64 scripts/build-maplibre-qt.sh ~/.local/maplibre-qt
```

## Configure, build, test

```bash
cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON \
    -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"
cmake --build build-plotter
ctest --test-dir build-plotter --output-on-failure
```

`cheekyplotter` runs without `LD_LIBRARY_PATH`: its build RPATH contains Qt's lib dir and the
maplibre lib dir (derived from the linked targets), so `libQMapLibre.so` finds `libQt6Sql`.

Dev machine trap: if your shell has linuxbrew in `PATH`/`LD_LIBRARY_PATH`, CMake can pick up
linuxbrew libraries; configure and build with
`env -u LD_LIBRARY_PATH PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin`.

## Command line

`cheekyplotter [--socket PATH] [--packs DIR] [--data DIR] [--window WxH]`:

- `--socket`: the n2kd JSON socket, default `/run/cheekymarine/n2k.sock`.
- `--packs`: directory holding the installed charts and bathy packs, default `<data dir>/packs`.
- `--data`: directory for `plotter.db`.
- `--window`: window size, for example `1280x800`.

## Data location

Everything the app stores is one SQLite file, `plotter.db` (settings and recorded tracks), in the
data directory: `--data`, else Qt's app data location for `cheekyplotter`, which is
`~/.local/share/cheekyplotter/` on Linux. The default packs directory is `packs/` inside it. If the
file is corrupt, not ours, or from a newer major version, the recovery screen offers to move it
aside (it is renamed, not deleted) and start fresh.

## Settings

Stored in `plotter.db`, changed in the Settings page. Defaults:

| Key | Default | Values |
|-----|---------|--------|
| `depthUnit` | `ft` | `ft`, `m`, `fm` |
| `speedUnit` | `kn` | `kn`, `mph`, `kmh` |
| `tempUnit` | `F` | `F`, `C` |
| `applyDepthOffset` | on | transducer offset applied to depth |
| `shallowM`, `safetyM`, `deepM` | 1.8288, 3.048, 9.144 m (6, 10, 30 ft) | 0.5 to 60 m, shallow < safety < deep |
| `orientation` | `head` | `north`, `head`, `course` |
| `paletteMode` | `auto` | `auto`, `day`, `dusk`, `night` |
| `chartMode` | `nav` | `nav`, `fish` |
| `touchLockTimeoutS` | 120 | seconds, 0 for never |
| `panelDiagonalIn` | 10.1 | inches, sizes the touch targets |
| `trackRecording` | off | |
| `trackIntervalS` | 5 | seconds between track points |
| `trackMinDistanceM` | 10 | metres moved before a new point |
| `slots` | TL depth (large), TR speed over ground (large), the rest off | the eight overlay slots |
| `bigNumbers` | `depth`, `sog` | fields on the Numbers page |

## Dev run

`plotter/tools/run-dev.sh [FIXTURE] [extra cheekyplotter args...]` replays an N2K log through n2kd
and starts the app on it (see the script header for `CM_PACKS_DIR`). Hidden dev and checkpoint
options of `cheekyplotter` (not in `--help`):

- `--palette auto|day|dusk|night`: writes the palette mode setting at start (it persists in the
  data dir). The default `auto` follows the sun at the boat; the fixture log starts at night.
- `--mode nav|fish`: writes the chart mode setting at start (persists too).
- `--slots default|all`: writes the overlay slots at start: the defaults, or the defaults with all
  eight slots on (persists too).
- `--page chart|numbers|tracks|settings|about`: the page shown first (not stored).
- `--sheet legend|ais`: opens the seabed legend sheet, or selects the first AIS target that arrives
  and so opens its sheet (not stored).
- `--lock`: starts with the touch lock on (hold the padlock for 1.5 s to unlock).
- `--record`: turns track recording on at start (it persists in the data dir).
- `--screenshot PATH --screenshot-after-ms N`: saves a grab of the window N ms after start;
  repeatable, paired in order.

For example `plotter/tools/run-dev.sh "" --palette dusk --mode fish` (an empty first argument
means the default fixture).

The final walkthrough renders (every page, day and night, 1280x800) are in
`docs/plotter/renders/final/`, named `<page>-<day|night>-1280x800.png`. They come from
`plotter/tools/run-dev.sh "" --palette P --window 1280x800 --screenshot FILE --screenshot-after-ms N`
plus `--page`, `--sheet`, `--lock` or `--record` as needed. The no-data banner is the app run
without n2kd (`nodata-*.png`); the recovery screen is `--data` pointing at a directory whose
`plotter.db` is junk (`recovery-*.png`).

## Licences

See `THIRD_PARTY_NOTICES` at the repository root: Qt 6 (LGPL-3.0, dynamic), maplibre-native-qt core
(BSD-2-Clause), Noto Sans (OFL-1.1) and what `libQMapLibre.so` compiles in.

## CI

The `plotter` job in `.github/workflows/plotter-ci.yml` runs the steps above on ubuntu-24.04. It
caches `~/Qt` and the installed maplibre prefix (keyed on the hash of `scripts/build-maplibre-qt.sh`,
which holds the pinned commit); the 8.5 GB source checkout is never cached. A cache miss prints
`df -h` and frees disk space first. Observed on the first (cache miss) run: 84 GB free before and
101 GB free after removing dotnet, android and ghc, so the 8.5 GB checkout fits either way. A cache
miss takes about 17 minutes in total (the maplibre build step alone about 15).
