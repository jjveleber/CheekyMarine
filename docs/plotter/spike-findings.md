# MapLibre Qt spike findings (plan 3, Task 1)

Date: 2026-10-29. Machine: WSL2 Ubuntu 24.04, 16 cores, WSLg display. Packs: puget-north 1.0.0
(charts and bathy) read in place from `chartpack/work/`.

The spike app (a CMake app in `spike/`, a custom `QQuickItem` over `QMapLibre::Map`) is kept in git
history in commit "test(plotter): throwaway MapLibre Qt spike app" and deleted in the commit that adds
this file. Screenshots are in `docs/plotter/renders/spike/`, all 1024x600, grabbed from the app with
`QQuickWindow::grabWindow()`.

## Summary

| # | Question | Answer |
|---|----------|--------|
| 1 | `mbtiles:///abs/path/enc.mbtiles` loads tiles? | Yes, through the Qt platform, vector and raster-dem. Absolute path required. |
| 2 | `file://` sprites and glyphs load? | Yes, `file:///abs/sprites/nav` and `file:///abs/glyphs/{fontstack}/{range}.pbf`. |
| 3 | Replace the `depare-medium` filter at runtime? | Yes, `Map::setFilter()`; the tint changes on the next frame. |
| 4 | GeoJSON source at 2 Hz, runtime image, `icon-rotate` from a property? | Yes, 19 to 20 updates in 10 s, icon moves and rotates. |
| 5 | Which API? | `QMapLibre::Map` in our own `QQuickItem` (about 110 lines). No rendered-feature query in either API. |
| 6 | Frame rate 1024x600? | 50 to 62 fps (60 Hz vsync cap) in both modes on WSLg. A style reload drops runtime sources, layers and images. |

## Toolchain commands

Exactly what was run, in order:

```bash
# Qt 6.8.3. The brief's "python3 -m pip install --user aqtinstall" is refused on this
# machine (PEP 668, externally managed Python), so pipx was used instead:
pipx install aqtinstall                      # aqtinstall 3.3.0
aqt install-qt linux desktop 6.8.3 linux_gcc_64 -O ~/Qt -m qtlocation qtpositioning

# Build dependencies (as in the brief), plus libxcb-cursor0 so Qt's xcb plugin can load:
sudo apt-get install -y ninja-build libgl1-mesa-dev libxkbcommon-dev libicu-dev \
    libcurl4-openssl-dev libuv1-dev libsqlite3-dev zlib1g-dev libpng-dev libjpeg-dev libwebp-dev
sudo apt-get install -y libxcb-cursor0

# maplibre-native-qt into ~/.local/maplibre-qt:
CMAKE_PREFIX_PATH=$HOME/Qt/6.8.3/gcc_64 scripts/build-maplibre-qt.sh ~/.local/maplibre-qt
```

Result: `~/.local/maplibre-qt/lib/cmake/QMapLibre/QMapLibreConfig.cmake` exists, the only library
is `libQMapLibre.so.4.0.0` (16 MB installed). A clean configure and build (473 ninja steps) took
1 min 42 s wall time at about 14 cores busy, peak 1.4 GB RSS for one compiler process. The
recursive submodule checkout is large: 8.5 GB under `~/.cache/cheekymarine/maplibre-native-qt/src`
(it includes unused submodules such as Windows vcpkg and boost history); the first clone took
longer than the build.

Notes for this dev machine and for CI:

- The owner's shell has linuxbrew in `PATH` and `LD_LIBRARY_PATH=/home/linuxbrew/.linuxbrew/lib`.
  CMake derives search prefixes from `PATH`, so the build was run with a clean environment
  (`PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin`, `LD_LIBRARY_PATH` unset) to keep
  linuxbrew libraries out of the link. CI runners do not have this problem.
- At run time `libQMapLibre.so` needs `libQt6Sql.so.6` (and Qt's `QSQLITE` driver plugin, see
  question 1). An app that does not link `Qt6::Sql` itself does not get Qt's lib dir from its own
  RUNPATH for that library, so the spike ran with
  `LD_LIBRARY_PATH=$HOME/.local/maplibre-qt/lib:$HOME/Qt/6.8.3/gcc_64/lib`. The app should link
  `Qt6::Sql` or set an RPATH to both directories (Task 2).
- WSLg: `XDG_RUNTIME_DIR=/run/user/1001` has no Wayland socket (WSLg runs as uid 1000), so set
  `WAYLAND_DISPLAY=/mnt/wslg/runtime-dir/wayland-0`. Mesa picks `llvmpipe` (CPU) by default;
  `GALLIUM_DRIVER=d3d12` gives the GPU (`D3D12 (AMD Radeon(TM) Graphics)`). Both were measured.
- The app must select OpenGL before creating the application object:
  `QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);` (the library is built with the
  OpenGL renderer). Qt picked the threaded render loop, OpenGL 4.6 compatibility context.

## Pinned commit and why

`MLN_QT_COMMIT=c3485f3a9590081c7be8edbc542341e688f6663d` (maplibre-native-qt main, 2026-09-20,
"Update jurplel/install-qt-action action to v4.4.1 (#316)", `VERSION.txt` 4.0.0, unreleased). Its
`vendor/maplibre-native` submodule is `702ebc6114ad864d86f86dd23b469183014fd548` (2026-07-22).

Why main and not v3.0.0: the brief says start from main and fall back to v3.0.0 only if main does
not build against 6.8.3; main built and installed cleanly at the first attempt with zero compiler
warnings, so v3.0.0 was not tried. Main also has what the plotter uses: the zero-copy OpenGL
texture path for Qt Quick (`getFramebufferTextureId()`), Qt 6 only, the fix for a lost
`MapChangeDidFinishLoadingStyle` (#306). v3.0.0 dates from 2024 and was built for Qt 6.5 to 6.7.

Build options in the script and why:

| Option | Value | Why |
|--------|-------|-----|
| `BUILD_SHARED_LIBS` | ON | brief, and keeps the LGPL Qt link dynamic |
| `MLN_WITH_OPENGL` | ON | GLES on the Pi 5 (configure prints "Configuring OpenGL ES backend") |
| `MLN_QT_WITH_INTERNAL_ICU` | ON | as the upstream Linux preset; no dependency on the distro ICU version |
| `MLN_QT_WITH_LOCATION` | OFF | not used (question 5); LGPL-3.0/GPL code; avoids Qt Location private headers |
| `MLN_QT_WITH_QUICK_PLUGIN` | OFF | not used (question 5) |
| `MLN_QT_WITH_WIDGETS` | OFF | not used |

The first spike build had the three `WITH_*` options at their defaults (ON) so that the Qt Location
plugin could be compared for question 5; the script was then changed to OFF and rebuilt from an
empty build directory and an empty prefix, and the spike re-run against it (all results below are
from that build).

## The six answers

All snippets are from the spike and ran as shown. `map` is a `QMapLibre::Map*`.

### 1. MBTiles through the Qt platform: yes

The style's `"url": "mbtiles://enc"` rewritten to `mbtiles://` plus the absolute path loads tiles:

```cpp
src["url"] = "mbtiles://" + absPath;   // mbtiles:///home/.../charts-puget-north-1.0.0/enc.mbtiles
```

Navigation (`enc`) and Fishing (`enc`, `bathy` vector and `dem` raster-dem terrarium PNG) both
render with no tile errors. Why it works: the Qt platform (`platform/qt/qt.cmake` in
maplibre-native) compiles `platform/default/src/mbgl/storage/mbtiles_file_source.cpp` and the
default `main_resource_loader.cpp`, which routes any URL starting `mbtiles://` to
`MBTilesFileSource`. That source reads the file's `metadata` table into a TileJSON (tile URL
`<url>?file={x}/{y}/{z}.<format>`, min/max zoom from metadata) and reads tiles with
`SELECT tile_data FROM tiles ...` (TMS row flip). SQLite access goes through
`platform/qt/src/mbgl/sqlite3.cpp`, that is QtSql with the `QSQLITE` driver plugin, because
`MLN_QT_WITH_INTERNAL_SQLITE` is OFF. On the Pi that means Debian's `libqt6sql6-sqlite` package
must be installed.

Constraints found in the source and confirmed:

- The path must be absolute. `mbtiles://home/...` (no leading slash) fails with:
  `[ERROR] {unknown}[Style]: Failed to load source enc: MBTilesFileSource only supports absolute path urls`
- The path is percent-decoded and cut at the first `?`, so a pack path containing `%` or `?` would
  break. Pack paths do not contain them; `tileUrl()` should refuse such a path rather than encode it.

No custom file source or local server is needed.

### 2. Sprites and glyphs from `file://`: yes

```cpp
style["sprite"] = "file://" + packDir + "/sprites/" + spriteName;           // nav or fish
style["glyphs"] = "file://" + packDir + "/glyphs/{fontstack}/{range}.pbf";
```

`packDir` is the pack root (`sprites/` and `glyphs/` are not under `styles/`). Nav icons,
fish icons and Noto Sans labels all render (see `nav-day.png`, `fish-day.png`). The `@2x` sprite was
not exercised (device pixel ratio 1).

### 3. Runtime filter replacement: yes

```cpp
const QJsonArray filter =
    QJsonDocument::fromJson(R"([">=", ["to-number", ["get","DRVAL1"]], 20])").array();
map->setFilter("depare-medium", filter.toVariantList());
```

`map->getFilter("depare-medium")` returns the new expression and the next frame redraws: areas with
`DRVAL1 >= 20` take the medium tint and the 3.048 to 9.144 m areas lose it
(`q3-filter-before.png`, `q3-filter-after.png`). No style reload. `QJsonValue` arrays convert
directly with `toVariantList()`; integer and double literals both work.

### 4. Runtime GeoJSON, image and `icon-rotate`: yes

```cpp
map->addImage("cm-boat", boatImage);                            // QImage, drawn at runtime
map->addSource("cm-own", QVariantMap{{"type", "geojson"}, {"data", fcBytes}});
const QJsonObject layer = QJsonDocument::fromJson(R"({
    "type": "symbol", "source": "cm-own",
    "layout": {"icon-image": "cm-boat", "icon-rotate": ["get", "rot"],
               "icon-rotation-alignment": "map", "icon-allow-overlap": true,
               "icon-ignore-placement": true}})").object();
map->addLayer("cm-own-boat", layer.toVariantMap());              // id passed separately
// every 500 ms:
map->updateSource("cm-own", QVariantMap{{"data", fcBytes}});
```

`fcBytes` is `QJsonDocument(featureCollection).toJson(QJsonDocument::Compact)`: the `data` value
must be a `QByteArray` of GeoJSON text (or `QMapLibre::Feature` values); a `QVariantMap` is not
accepted for `data`. 19 to 20 updates landed in each 10 s window and the icon moved and turned
by its `rot` property each time (`q4-geojson-boat.png`).

One trap: `setStyleJson()` emits `MapChangeDidFinishLoadingStyle` synchronously, inside the call.
The first spike run connected its handler after `setStyleJson()` and never saw the event. Connect
everything first, then load.

### 5. API: `QMapLibre::Map` in a custom `QQuickItem`

Both candidates did 1 to 4 in the spike:

- Custom item (chosen): about 110 lines of C++ (`spike/mapitem.{h,cpp}` in history), modelled on
  maplibre-native-qt's own `TextureNodeOpenGL`: in `updatePaintNode()` on the scene graph thread,
  `createRenderer(nullptr)` once, `updateRenderer(size, dpr, fbo)`, `render()` between
  `beginExternalCommands()`/`endExternalCommands()`, then wrap `getFramebufferTextureId()` with
  `QNativeInterface::QSGOpenGLTexture::fromNative()` in a `QSGSimpleTextureNode`. Every call in 1
  to 4 is a direct `Map` method taking our own data (`setStyleJson`, `setFilter`, `addSource`,
  `updateSource`, `addImage(QImage)`, `addLayer`).
- Qt Location `Map` with the `maplibre` plugin and `MapLibre.style: Style { FilterParameter,
  SourceParameter, ImageParameter, LayerParameter }`: about 50 lines of QML, and it also did 1 to 4
  (filter by assigning `expression`, GeoJSON by binding `property var data`). Against it: the
  style must be a URL (`maplibre.map.styles`), so the rewritten style has to be written to a temp
  file; images come from a file path, not a `QImage`; the plugin code is
  `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; it needs Qt Location private headers that
  Debian does not package (spec 6.2); its `zoomLevel` is on Qt's 256 px scale (zoom 13 drew the
  area MapLibre draws at zoom 12), which would leak into `metresPerPixel` (Task 9 uses 512 px);
  and the C++ `ChartMap` seam would sit behind QML objects. Not tested: whether its style
  parameters survive a style reload by themselves.

The custom item is less code where it matters (no temp files, no QML to C++ bridging, no zoom
conversion, no Qt Location dependency) and keeps the plotter's MapLibre link to the BSD-2-Clause
core only.

Two things the item must do that the spike learned the hard way:

- Destroy the renderer on the scene graph thread: call `map->destroyRenderer()` in the texture
  node's destructor. Without it the app segfaults on exit in `mbgl::gl::Context::~Context()`
  (GL calls from `~Map()` on the GUI thread with no current context).
- The FBO texture is bottom-up: `setTextureCoordinatesTransform(QSGSimpleTextureNode::MirrorVertically)`,
  otherwise the chart is drawn upside down.

Rendered-feature queries at a screen point: not available. `QMapLibre::Map` at this commit has no
`queryRenderedFeatures` (or any query) in its public headers; only the private `MapPrivate` holds
the `mbgl::Map`. The Qt Location plugin has none either. Available instead:
`QPointF Map::pixelForCoordinate(const Coordinate&) const` and
`Coordinate Map::coordinateForPixel(const QPointF&) const`, which is what Task 17's fallback
needs.

### 6. Frame rate and style reload

Scripted at 1024x600, centred 47.98, -122.23, zoom 13: 10 s pan (8 px per 16 ms step, circular
path), then 10 s zoom (oscillating between zoom 13 and about 15 about the window centre). Frames
counted with `QQuickWindow::frameSwapped`; render time is `map->render()` plus `glFinish()` per
frame (the `glFinish` was added for the measurement only).

| Renderer | Mode | Pan fps | Pan render ms mean / p95 | Zoom fps | Zoom render ms mean / p95 |
|----------|------|---------|--------------------------|----------|---------------------------|
| llvmpipe (CPU) | Navigation | 61.9 | 9.2 / 11.7 | 62.0 | 5.9 / 9.4 |
| llvmpipe (CPU) | Fishing | 61.9 | 9.0 / 10.9 | 62.0 | 7.4 / 9.8 |
| D3D12 (GPU) | Navigation | 57.7 | 8.5 / 31.1 | 49.9 | 9.5 / 43.6 |
| D3D12 (GPU) | Fishing | 60.3 | 8.5 / 16.5 | 61.2 | 5.4 / 9.4 |

Swap interval is 1, so 60 Hz is the ceiling. WSLg is not representative of the Pi 5: llvmpipe uses
16 x86 cores, and the GPU path goes through Mesa's D3D12 translation to Windows (its spikes to 30
to 70 ms are likely that layer). The Pi 5 EGLFS measurement stays Task 18.

Style reload on palette change (nav-day to nav-night with `setStyleJson()`): drops everything added
at runtime. After the second `MapChangeDidFinishLoadingStyle`, `sourceExists("cm-own")` and
`layerExists("cm-own-boat")` are both false, and re-adding only the source and layer without
`addImage()` draws no icon, so runtime images are dropped too. Re-adding all three on each
style-loaded event works (`nav-night.png`, boat drawn after the reload).

Also seen in every run, both modes: `[WARNING] {unknown}[General]: Invalid geometry in line layer`
(one line feature in the `enc` tiles that MapLibre rejects). Harmless for the spike; worth a look on
the chartpack side.

## Licences of what the maplibre-native-qt build links or vendors

With the script's options the build produces one library, `libQMapLibre.so`, from these targets:
`MLNQtCore`, `mbgl-core`, `mbgl-vendor-icu`, `mbgl-vendor-nunicode`, `mbgl-vendor-parsedate`,
`mbgl-vendor-csscolorparser`, `mlt-cpp`, `fastpfor-lib` (from the ninja log), plus header-only
vendored code. Sources: maplibre-native-qt `LICENSES/` and SPDX tags, maplibre-native
`LICENSES.core.md` and each `vendor/*` licence file.

| Component | Licence | How it is used |
|-----------|---------|----------------|
| maplibre-native-qt core (`src/core`, 83 files) | BSD-2-Clause | compiled in |
| MapLibre Native | BSD-2-Clause | compiled in |
| ICU 61.1 (vendored subset) | Unicode / ICU licence | compiled in |
| nunicode | MIT | compiled in |
| parsedate (from curl) | curl licence (MIT-style) | compiled in |
| csscolorparser | MIT | compiled in |
| maplibre-tile-spec C++ (`mlt-cpp`) | MIT or Apache-2.0 (dual); its LICENSE-CC0 covers documentation and specification content only, not the compiled code (confirmed in Task 19, see its `THIRD_PARTY_NOTICES` entry) | compiled in |
| FastPFOR | Apache-2.0 | compiled in |
| PMTiles (`MLN_WITH_PMTILES` ON) | BSD-3-Clause | header-only |
| Boost (headers) | BSL-1.0 | header-only |
| expected-lite, unique_resource | BSL-1.0 | header-only |
| earcut.hpp, polylabel, eternal, shelf-pack-cpp, geojson-vt-cpp, cheap-ruler-cpp, kdbush.hpp, supercluster.hpp | ISC | header-only |
| protozero | BSD-2-Clause (parts Apache-2.0 from folly) | header-only |
| vector-tile, geojson.hpp, geometry.hpp | ISC | header-only |
| variant, mapbox-base | BSD-3-Clause | header-only |
| wagyu (incl. Clipper-derived code) | BSL-1.0 | header-only |
| RapidJSON | MIT (the JSON-licensed `bin/jsonchecker` is not used) | header-only |
| unordered_dense | MIT | header-only |
| Qt 6 (Core, Gui, Network, Sql, OpenGL) | LGPL-3.0 | dynamic link |
| zlib | Zlib | dynamic link (system) |

GPL check, loudly: nothing GPL-only is linked. The GPL items in the trees are:

- maplibre-native-qt `LICENSES/GPL-2.0-only.txt` and `GPL-3.0-only.txt`: they cover only the Qt
  Location plugin (`src/location/*`, `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`), which the
  script does not build.
- FreeType (`FTL OR GPL-2.0`) and HarfBuzz (Old MIT) are vendored but not built:
  `MLN_TEXT_SHAPING_HARFBUZZ` is OFF in the Qt build.
- `vendor/maplibre-tile-spec/cpp/vendor/json/LICENSES/GPL-3.0-only.txt` (nlohmann/json's REUSE
  folder for a test tool) and glfw's mingw headers: not compiled (configure prints
  "[MLT] No JSON support"; glfw is not part of the Qt build).
- Not linked: sqlite (vendored, public domain; the Qt build uses QtSql), FSST (MIT, only the MLT
  encoder uses it), SIMD Everywhere (MIT, listed in `LICENSES.core.md`, not referenced by the
  built code), Vulkan headers, glslang, googletest, benchmark, vcpkg.

## Changes this forces on Tasks 8, 10, 17 (and others)

Task 8 (style loader):

- `tileUrl(absPath)` stays `"mbtiles://" + absPath` (the plan's default is confirmed). Add: refuse
  (error) a path that is not absolute or that contains `?` or `%`, with a test.
- `rewriteStyle()`: the sprite and glyphs base is the pack root, not a `styles/` directory. The
  parameter named `styleDir` should be `packDir` (the charts pack for nav, the bathy pack for
  fish); the plan's expected values (`file:///p/charts/sprites/nav`, `/p/bathy/sprites/fish`)
  already assume this.

Task 10 (chart controller and MapLibre adapter):

- `MapLibreChartMap` is a C++ `QQuickItem` over `QMapLibre::Map` (no Qt Location). Mapping of the
  `ChartMap` methods: `setStyleJson` to `Map::setStyleJson`; `setLayerFilter(layer, filter)` to
  `Map::setFilter(layer, filter.toArray().toVariantList())`; `setGeoJson(source, fc)` to
  `addSource({"type":"geojson","data":bytes})` on first call, then `updateSource({"data":bytes})`
  with `bytes = QJsonDocument(fc).toJson(Compact)`; `addImage` to `Map::addImage(QImage)`;
  `addLayer(layer)` to `Map::addLayer(layer["id"], layer minus "id" as QVariantMap, before)`;
  `setCamera` to `Map::jumpTo(CameraOptions)`; `zoom()` to `Map::zoom()` (MapLibre 512 px scale,
  matching Task 9's `metresPerPixel`).
- `styleLoaded()` can be emitted synchronously from inside `setStyleJson()`. The adapter connects
  to `Map::mapChanged` before the first load, and `ChartController` must cope with `styleLoaded`
  arriving re-entrantly (it then calls `addImage`/`setGeoJson`/`addLayer` from inside its own
  `setStyleJson` call). Add a test where `FakeChartMap` emits `styleLoaded` synchronously in
  `setStyleJson`.
- Re-adding images, sources and layers after every `styleLoaded` (already in the plan) is
  required: a reload drops all three.
- The item needs `destroyRenderer()` in the texture node destructor, the vertical mirror, and
  `QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL)` in `main.cpp` before the
  `QGuiApplication`. Gestures are ours: `DragHandler`/`PinchHandler`/`WheelHandler` in
  `ChartPage.qml` calling `moveBy`/`scaleBy` on the item and emitting `userGesture()`.
- Link `Qt6::Sql` (or set an RPATH to Qt's lib dir) so `libQMapLibre.so` resolves `libQt6Sql`.

Task 17 (AIS taps):

- No rendered-feature query: use the fallback (nearest target within `Units.mm(8)`). `ChartMap`
  needs a projection method, for example `virtual QPointF toScreen(double lat, double lon) const = 0`,
  implemented with `Map::pixelForCoordinate()`, and `FakeChartMap` gets a simple linear projection
  for the test.

Others:

- Spec 6.2 and Task 18: Qt Location is no longer needed by MapLibre, so the Pi does not need the
  missing Qt Location private headers or `qt6-location-dev`. The Pi does need
  `libqt6sql6-sqlite` at run time and `libqt6opengl6-dev` to build. The dev machine's aqt
  `-m qtlocation qtpositioning` is now only needed if another task uses Qt Positioning.
- Task 19 `THIRD_PARTY_NOTICES`: drop "LGPL-3 QML bindings" (not built); use the table above;
  FreeType and HarfBuzz need no entry (not built).
- CI cache: cache the installed prefix by `MLN_QT_COMMIT`, as planned; the 8.5 GB source checkout
  should not be cached. Shallow submodules could cut the clone but were not tried.
