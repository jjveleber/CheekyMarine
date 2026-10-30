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
- `--lock`: starts with the touch lock on (hold the padlock for 1.5 s to unlock).
- `--screenshot PATH --screenshot-after-ms N`: saves a grab of the window N ms after start;
  repeatable, paired in order.

For example `plotter/tools/run-dev.sh "" --palette dusk --mode fish` (an empty first argument
means the default fixture).

## CI

The `plotter` job in `.github/workflows/plotter-ci.yml` runs the steps above on ubuntu-24.04. It
caches `~/Qt` and the installed maplibre prefix (keyed on the hash of `scripts/build-maplibre-qt.sh`,
which holds the pinned commit); the 8.5 GB source checkout is never cached. A cache miss prints
`df -h` and frees disk space first. Observed on the first (cache miss) run: 84 GB free before and
101 GB free after removing dotnet, android and ghc, so the 8.5 GB checkout fits either way. A cache
miss takes about 17 minutes in total (the maplibre build step alone about 15).
