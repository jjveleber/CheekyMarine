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

A touch UI for a 10 inch panel (the diagonal is a setting), built from saved views, with a tab bar
on the right edge:

- Views: each view is a chart view (Nav: the charts pack for navigation; Fish: the bathy pack for
  fishing) or a cell view (no chart: big readouts in a grid layout). A chart view has own ship with
  follow and orientation, eight overlay slots (four corners, top and bottom banners, left and right
  bars), each on or off with its own field and digit height in mm, AIS targets (tap one for its
  sheet) and a seabed legend sheet from the "Legend" button. Three views ship: Navigation, Fishing
  and Big numbers. The last view shown comes back at start.
- Home: a tile per view (a drawing of its layout, its name, a star on favourites) in the owner's
  order, then "+ New view", Tracks, Settings and About. Tap a tile to show the view; hold it for
  its menu: Edit, Favourite, Move left, Move right, Duplicate, Delete (the last view cannot go).
- Tab bar: the favourite views (icon over short name, as many as fit the bar's height: 5 on the
  10.1 in panel at both sizes; the rest say "Not on tab bar (full)"), the house tab (Home), Lock and
  the palette button. On a view it slides off the right edge after the delay set in Settings (8 s
  by default, or never); a plain tap on the map or the cells brings it back. The view's own buttons
  (Legend, zoom, Recenter, an AIS target) leave it hidden, and nothing on the view moves when it
  hides or shows. It never hides on Home, Tracks, Settings, About or in the editor.
- Editor: from a tile's Edit, "+ New view" (with Setup open) or a hold on a favourite tab. The view
  stays live underneath with the tab bar dimmed; Setup, Done and Cancel float over it. Tap a slot
  for its sheet (show, field, size with + and -, or drag its round handle) or a cell for its field.
  Setup: Name and Short name (on our own keyboard), icon, chart (Nav, Fish or None), layout (None
  only: a gallery of every layout), favourite, delete. Done saves; Cancel drops every change. A hold
  on a slot or cell of a live view opens just its sheet, and its Done saves.
- Tracks: records the boat's track (off by default), lists saved tracks, shows or hides them on the chart.
- Settings: units, depth thresholds, orientation, palette (auto follows the sun, or day, dusk,
  night), tab bar hide delay, panel size, track interval and distance. About shows versions and
  installed packs.
- Touch lock: the padlock in the tab bar locks the screen; hold the padlock for 1.5 s to unlock.
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
needs about 1.1 GB of free disk for the shallow clone plus the build tree (the clone takes longer than the build):

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

Everything the app stores is one SQLite file, `plotter.db` (settings, views and recorded tracks), in the
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
| `lastPalette` | `day` | `day`, `dusk`, `night`: the palette last applied, where auto mode starts before the first fix |
| `lastViewId` | empty | the id of the view last shown, shown again at start (empty or unknown: the first view) |
| `tabBarHideS` | 8 | `0`, `5`, `8`, `15`, `30`: seconds before the tab bar slides off a view, 0 = never hides |
| `showChartNotice` | on | the notice line on the chart and the boot splash |
| `panelDiagonalIn` | 10.1 | inches, sizes the touch targets |
| `trackRecording` | off | |
| `trackIntervalS` | 5 | seconds between track points |
| `trackMinDistanceM` | 10 | metres moved before a new point |

Track points are written every 30 s or every 20 points. If the database refuses writes, the recorder holds at most one batch and retries; those points stay on the chart and in the Tracks row, and are lost if the app exits while writes still fail.

The plan 3 keys `chartMode`, `touchLockTimeoutS`, `slots` and `bigNumbers` are gone: the chart and
the slots and cells live in each view, and the idle auto-lock was removed.

### Views

The views are the `views` table of `plotter.db`: `id` (text, the primary key), `ord` (integer, the
Home order; favourite tabs follow it) and `json`, one JSON object per view:

```json
{"id": "shipped-nav", "name": "Navigation", "short": "Nav", "icon": "compass", "chart": "nav",
 "favourite": true,
 "slots": [{"id": "TL", "on": true, "field": "depth", "sizeMm": 25}, "...the other seven..."],
 "cells": {"layout": "2x2:0,0,1,2;1,0,1,2", "fields": ["depth", "sog"]},
 "created": 1793404800, "modified": 1793404800}
```

- `name` 1 to 24 characters, `short` 1 to 6 (the tab label), `icon` one of the 16 bundled Tabler
  icons, `chart` `nav`, `fish` or `none`. Slot ids `TL`, `TR`, `BL`, `BR`, `Top`, `Bottom`, `Left`,
  `Right`; `sizeMm` is the digit height, one decimal, at least 6. Fields `depth`, `sog`, `stw`,
  `cog`, `hdg`, `wtemp`, `pos`, `time`, `rpm`. `created` and `modified` are Unix seconds. Every view
  stores both `slots` and `cells`, so a switch to None and back keeps both. Unknown keys are kept on
  save, at the top level and inside a slot entry.
- Shipped on a fresh file, all favourites, in this order: Navigation (`Nav`, nav chart), Fishing
  (`Fish`, fish chart), both with TL Depth and TR SOG on at 25 mm and the other six slots off, and
  Big numbers (`Big #`, no chart) with two cells side by side, Depth and SOG.
- The slot size clamp: a slot's digit height is held between 6 mm and the largest size whose box
  (sized for the field's widest value) still fits beside its neighbours, so slots never overlap or
  leave the page; the editor clamps on every change and shows what was applied, and a stored size
  too big for a smaller panel is clamped when drawn, not rewritten.
- Cell layouts: every rectangular tiling of a 2x2, 2x3 and 3x2 grid, 72 distinct shapes of 1 to 6
  cells, stored by a stable key (`<cols>x<rows>:<col>,<row>,<colSpan>,<rowSpan>;...`), shown in the
  gallery by cell count, then grid, then key.
- Schema 1.1.0 adds the `views` table. Opening a plan 3 database (schema 1.0.0) migrates it once: the
  stored `slots` become the Navigation view's slots (small, medium and large map to 8, 14 and 25 mm),
  the stored `bigNumbers` become the Big numbers view's cells (2 fields side by side, 3 in a row of
  three, 4 in the equal 2x2 quad; 0 or 1 fields are padded to two with the defaults, Depth then SOG,
  and more than 4 are cut to the first 4), a Fishing view is added, and `slots`, `bigNumbers`, `chartMode`
  and `touchLockTimeoutS` are deleted from `settings`.

## Dev run

`plotter/tools/run-dev.sh [FIXTURE] [extra cheekyplotter args...]` replays an N2K log through n2kd
and starts the app on it (see the script header for `CM_PACKS_DIR`). Hidden dev and checkpoint
options of `cheekyplotter` (not in `--help`):

- `--palette auto|day|dusk|night`: writes the palette mode setting at start (it persists in the
  data dir). The default `auto` follows the sun at the boat; the fixture log starts at night.
- `--view SHORT`: the view shown first, by its short name (for example `Fish` or `"Big #"`); it
  persists as `lastViewId`, as a tab tap does. An unknown short name exits 2 and lists the known ones.
- `--page home|view|tracks|settings|about`: the page shown first (not stored); `view` is the shown
  view and the default.
- `--editor`: opens the view editor on the shown view.
- `--sheet legend|ais|setup|slot|cell|gallery|keyboard`: `legend` opens the seabed legend sheet;
  `ais` selects the first AIS target that arrives and so opens its sheet; the rest open the editor
  too and then a sheet: `setup` the Setup sheet, `slot` the TL slot's sheet, `cell` the first cell's
  sheet, `gallery` Setup then the layout gallery, `keyboard` Setup then the keyboard on Name (not
  stored). `cell` and `gallery` need the shown view to have no chart (for example `--view "Big #"`);
  on a chart view they exit 2.
- `--lock`: starts with the touch lock on (hold the padlock for 1.5 s to unlock).
- `--record`: turns track recording on at start (it persists in the data dir).
- `--screenshot PATH --screenshot-after-ms N`: saves a grab of the window N ms after start;
  repeatable, paired in order.
- `--exit-after-ms N`: quits N ms after start (for scripted renders).

For example `plotter/tools/run-dev.sh "" --palette dusk --view Fish` (an empty first argument
means the default fixture).

The saved views renders (every page and editor sheet, day and night, at 1024x600 and 1280x800) are
in `docs/plotter/renders/views/`, named `<name>-<day|night>-<WxH>.png`. They come from
`CM_PACKS_DIR=DIR plotter/tools/run-dev.sh "" --palette P --window WxH --screenshot FILE
--screenshot-after-ms 7000 --exit-after-ms 8000` (the splash stays up 5 s) plus `--view`, `--page`,
`--editor`, `--sheet`, `--lock` or `--record` as needed (`splash` is taken at 800 ms,
`nav-barhidden` at 10000 ms, after the 8 s hide). The earlier walkthrough renders in `docs/plotter/renders/final/` predate views; they
keep the no-data banner (the app run without n2kd, `nodata-*.png`) and the recovery screen
(`--data` pointing at a directory whose `plotter.db` is junk, `recovery-*.png`).

## Bring-up checks

On the real panel, once the app runs there (the tests cover these offscreen only):

- Tap on target: with AIS targets on the chart, tap one with a finger; its sheet must open for that
  target. The tap point is in map area coordinates (`tst_pages` proves it reaches `selectAt` that
  way); this checks that on the panel's touch driver it matches where the map draws the target
  (`pixelForCoordinate`), including with the Top and Left bars on.

## Licences

See `THIRD_PARTY_NOTICES` at the repository root: Qt 6 (LGPL-3.0, dynamic), maplibre-native-qt core
(BSD-2-Clause), Noto Sans (OFL-1.1) and what `libQMapLibre.so` compiles in.

## CI

The `plotter` job in `.github/workflows/plotter-ci.yml` runs the steps above on ubuntu-24.04. It
caches `~/Qt` and the installed maplibre prefix (keyed on the hash of `scripts/build-maplibre-qt.sh`,
which holds the pinned commit, and on the Qt version); the about 1.1 GB source checkout is never cached. A cache miss prints
`df -h` and frees disk space first. Observed on the first (cache miss) run: 84 GB free before and
101 GB free after removing dotnet, android and ghc, so the about 1.1 GB checkout (shallow since 8db3647) fits either way. A cache
miss takes about 17 minutes in total (the maplibre build step alone about 15).
