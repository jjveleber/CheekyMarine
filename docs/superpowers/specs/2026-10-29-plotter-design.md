# plotter: the Qt chart plotter app, design

Date: 2026-10-29
Status: approved by the owner 2026-10-29 ("let's move forward")
Parent: `docs/superpowers/specs/2026-10-28-cheekymarine-design.md` (sections 2, 4, 6.2, 6.5, 6.9, 8, 9). Inputs: the n2kd JSON contract in the root `README.md` and the pack contract in `chartpack/README.md`.

The owner asked to skip the discovery questions ("Let's just get down to what to build"). Everything below that is not quoted from the parent spec or the two contracts is my call and is marked so.

## 1. Intent

The app the owner looks at from the stern: a full-screen nautical chart with the own boat on it, big depth and speed numbers, and a Fishing chart mode, running on the Pi 5 helm display. It reads live data from n2kd and charts from the installed chart and bathy packs. This plan delivers the parent spec's phase 1 app scope (the "install candidate" items 3, 4 and 7 of section 9) so the unit can go on the boat in April 2027. Phase 2 features follow over hotspot updates after install.

## 2. Goals (plan 3)

1. Chart page: the installed charts pack drawn by MapLibre Native in Navigation mode, the bathy pack in Fishing mode, one big toggle between them. Own boat with heading line and COG vector, follow mode, pan and pinch zoom, recenter.
2. Data overlay slots on the chart page as in parent 6.5: TL, TR, BL, BR, top banner, bottom banner, left bar, right bar; each on or off, one field each, small, medium or large. Defaults: depth large TL, SOG large TR.
3. Big numbers page: depth and speed filling the screen, fields pickable.
4. Day, dusk and night palettes: chart styles switch to the pack's matching style, the app UI follows (night is dim red on black). Manual choice or automatic by sunrise and sunset at the boat's position.
5. Safety depth (shallow, safety, deep) set by the owner and applied to the chart live, through the pack contract's named depth layers.
6. Tracks: record on or off, interval, saved tracks list, show or hide, delete.
7. Touch lock: on demand and after an idle timeout; unlock by a deliberate 1.5 s long press.
8. Pack notices shown while the chart is shown (pack contract); versions of app, charts pack and bathy pack on the About page and the boot splash (parent 6.9).
9. Seabed letters quick lookup: a legend sheet from the pack's `legend.json` (owner requirement from chartpack 6.10).
10. AIS targets on the chart (triangles with heading vectors), since the data is already published and parent 9 allows it in phase 1. My call; it is the last task and can be dropped if time runs short.
11. Runs on the dev machine (WSL2, Qt desktop platform, 1024x600 and 1280x800 windows) against n2kd in replay mode, and on the Pi 5 under EGLFS.

## 3. Non-goals (plan 3)

- Phase 2 features: waypoints, routes, go-to, XTE and arrival, AIS list page, MOB, alarms, depth history page and banner. They come in a later plan. The data model (section 6.7) leaves room for them.
- Anchor scope calculator (owner's parked idea, 2026-10-29). Phase 2 candidate, raised again when that plan is brainstormed.
- Downloading or installing packs and software, WiFi join, A/B slots: plan 4. Plan 3 reads packs already present in a directory.
- Backlight brightness control and the brightness global button: depend on the panel chosen in plan 5. My call to defer; the button slot is reserved in the global control bar.
- Pi image, systemd unit for the app, read-only root: plan 4. Plan 3 runs the app by hand on a Pi.
- Any change to the n2kd JSON contract or the pack contract.
- Sonar, radar, autopilot (parent non-goals).

## 4. Anti-goals

From the parent spec, restated because this plan is where they are won or lost:

- A chart that looks like a road map. The app draws the pack styles unchanged except for the contract rewrites and the depth filters.
- Small or fiddly targets. Every tappable thing is at least 12 mm on the real panel.
- Ghost touches changing the page or the chart while locked.
- Numbers not readable from 12 to 15 ft. Large slot digits are at least 25 mm tall on the panel (my call: about 1 inch digit height reads at 15 ft).
- A stale value shown as live. A null or stale value shows as `--`, never as the last good number.
- Settings or tracks lost or corrupted by a power cut.

## 5. Constraints

- Stack (parent 6.2, owner decided): C++ (the repo builds with C++23), Qt 6 Quick/QML, MapLibre Native through maplibre-native-qt, EGLFS on the Pi, no desktop and no browser.
- maplibre-native-qt needs Qt 6.5 or newer. Ubuntu 24.04 (the WSL2 dev machine) packages Qt 6.4, too old. Debian 13 (trixie), and so Raspberry Pi OS trixie, packages Qt 6.8.2.
- maplibre-native-qt licences: core BSD-2; its QML bindings are GPL-2, GPL-3 or LGPL-3, used under LGPL-3 and linked dynamically. Qt under LGPL-3, linked dynamically. No GPL (owner rule). `THIRD_PARTY_NOTICES` gains both.
- Data comes only from n2kd's Unix socket (`/run/cheekymarine/n2k.sock`, JSON lines, `hello` schema 1). The app never touches CAN.
- Packs follow `chartpack/README.md` "Pack contract": the app rewrites exactly the source URLs, `sprite` and `glyphs`, and changes depth thresholds only through the filters of the named depth layers listed in `metadata.cheekymarine.depths.layers`. Fish styles use the `enc` source too, so Fishing mode needs both packs.
- Screen: 9" to 10.1", 1024x600 or 1280x800, not chosen yet (plan 5). Layout must work at both.
- The parent spec's development rules apply: TDD where tests pay, adversarial subagent review on the PR, semver from the first release, owner reviews and validates.

## 6. Decisions

### 6.1 Repo shape and build (my call)

- New top-level `plotter/` directory (CMake subproject added from the root `CMakeLists.txt`), same layout as `n2kd/`: `src/`, `qml/`, `tests/`, plus `include/` only if needed.
- Built only when `CM_BUILD_PLOTTER=ON` and Qt 6.5 or newer is found, so the existing n2kd CI and release jobs are unaffected.
- Tests use Qt Test (it reaches QObject view models and QML), run under ctest with `QT_QPA_PLATFORM=offscreen`. Catch2 stays for n2kd.
- App version: the plotter has its own semver in `plotter/CMakeLists.txt` and its own tag pattern `plotter-vX.Y.Z`, like the pack tags, so it does not collide with n2kd's `v*`. Release packaging of the app is plan 4; plan 3 only needs the version compiled in and shown.

### 6.2 Qt and MapLibre on the dev machine and the Pi (my call)

- Dev machine: Qt 6.8 LTS installed with aqtinstall into `~/Qt` (desktop gcc_64, no extra modules: no Qt Location or Positioning, owner decided 2026-10-29 after the spike; aqtinstall installed with `pipx install aqtinstall`), documented in `plotter/README.md`. CI does the same, cached.
- maplibre-native-qt: built from source by a script (`scripts/build-maplibre-qt.sh`) into a prefix, pinned to a commit hash recorded in the script (v3.0.0 is from 2024; main is active and heading to 4.0; the spike picks the pin). Shared libraries. CI caches the prefix by the pinned hash.
- Pi: Raspberry Pi OS trixie, Qt 6.8 from apt, maplibre-native-qt built on the Pi (or in an arm64 trixie container) with the same script. Qt Location is not needed, so no private headers and no `qt6-location-dev`; the Pi needs `libqt6sql6-sqlite` at run time and `libqt6opengl6-dev` to build.
- How the app is cross-built and shipped to the Pi for good is plan 4.

### 6.3 First task: the MapLibre spike (parent 8, risk 1)

Answers (Task 1): all six questions are answered in `docs/plotter/spike-findings.md` (done 2026-10-29, owner checkpoint 1 approved). In short: `mbtiles://` URLs, `file://` sprites and glyphs, runtime filters and runtime GeoJSON work; the API is `QMapLibre::Map` in a custom `QQuickItem` (answer 5), with no rendered-feature query.

Before any feature work, a throwaway spike answers, in writing, in the plan's ledger:

1. maplibre-native-qt loads a charts pack style with the source URL rewritten to `mbtiles:///abs/path/enc.mbtiles` (MapLibre Native core has an MBTiles file source; the Qt path is unverified, chartpack 7 flagged it). If it does not, the fallback is a small local tile reader inside the app serving the MBTiles over a custom URL scheme or localhost; the pack format does not change.
2. Sprites and glyphs load from `file://` paths in the pack.
3. The depth layers' filters can be replaced at runtime from C++ or QML.
4. A GeoJSON source can be added and updated at runtime at 2 Hz (own boat, track, AIS) with images added at runtime.
5. Which API the app uses: the Qt Location `Map` with the `maplibre` plugin and its style parameters, or the C++ `QMapLibre::Map` behind a custom `QQuickItem`. The spike picks the one that does 1 to 4 with less code.
6. Frame rate at 1024x600 panning and zooming the puget-north packs on the dev machine. The owner has no Pi 5 yet (2026-10-29) and will buy one soon; the Pi 5 EGLFS measurement runs as soon as it arrives, as its own task, and may land during or after plan 3. If EGLFS under-performs, try `cage` (parent 8) before anything else.

The spike's code is thrown away; the plan's later tasks are written knowing its answers. If question 1 or 5 changes the shape of the chart layer, the plan is revised before feature tasks start.

### 6.4 Process and data flow (my call)

```
n2kd --(Unix socket, JSON lines)--> N2kClient --> VesselModel, AisModel (C++ QObjects)
packs dir --> PackCatalog --> StyleLoader (contract rewrites, depth filters) --> ChartView (MapLibre)
SQLite (data partition) <--> Store --> Settings, Tracks
QML pages bind to the models; no logic in QML beyond layout and bindings.
```

- `N2kClient`: `QLocalSocket`, reconnects every 2 s, expects `hello` with `schema` 1 (any other schema: show "daemon too new or too old", ignore its data), splits lines, discards a final line without a newline after a disconnect, ignores unknown keys (n2kd contract). Converts units once, here: m/s to knots, radians to degrees, kelvin to the display unit is left to the formatter (models keep SI; formatters convert, so unit changes do not touch models).
- Staleness: n2kd already nulls stale values. The client additionally marks everything stale if no `vessel` line arrives for 3 s or the socket is down, and the UI shows a "No data from N2K" banner.
- Command line: `--socket PATH` (default the n2kd default), `--packs DIR` (default `/var/lib/cheekymarine/packs` my call, plan 4 installs there), `--data DIR` (SQLite location, default `/var/lib/cheekymarine/plotter`), `--window WxH` for the dev desktop size.

### 6.5 Packs and styles

- `PackCatalog` scans `--packs DIR` for `charts-<region>-<version>/` and `bathy-<region>-<version>/` directories, reads each `manifest.json`, refuses (and lists on the About page as refused, with the reason) a pack whose `schema` is not 1 or whose manifest is unreadable. File hashes are not re-checked at every start (plan 4 verifies at install). With several valid packs of one kind, the highest semver wins. One region at a time in plan 3 (only puget-north exists); multi-region selection is a later plan.
- Fishing mode needs a charts pack and a bathy pack of the same region. If the bathy pack is missing, the mode button is disabled with "No fishing chart installed".
- `StyleLoader` takes a style JSON, applies the three contract rewrites to absolute `mbtiles://` (or the spike's fallback scheme) and `file://` locations, and returns it. Pure function, unit tested against the real shipped styles.
- Safety depth: settings hold shallow, safety and deep in metres (defaults from the style metadata: 6, 10, 30 ft). On change, the app replaces the threshold literals in the `filter` of each layer named in `metadata.cheekymarine.depths.layers` of the current style, through MapLibre's set-filter API, without reloading the style. The filter rewrite is a pure function on the style's filter JSON, tested against every named layer in the shipped nav and fish styles: it replaces each threshold whose value equals the style's recorded `shallow_m`, `safety_m` or `deep_m` with the new value, and in `depcnt-safety` replaces the value equal to `safety_contour_m`; it fails loudly if a layer has a threshold it cannot map. Validation: shallow < safety < deep, each in 0.5 to 60 m.
- Safety contour (found by the builder check, my call): contours exist only at charted values, so `depcnt-safety` matches `VALDCO == safety_contour_m` (3.6 m in the shipped pack while `safety_m` is 3.048). The app repeats chartpack's rule (`assemble.py` `_safety_contour_m`, the ECDIS convention): the safety contour is the smallest charted contour value at or deeper than the safety depth, chosen from the charts pack's MBTiles metadata `cheekymarine:valdco`. `PackCatalog` therefore reads MBTiles metadata (SQLite, read-only) as well as the manifest; Fishing mode takes it from the charts pack too. A test checks the app's rule gives 3.6 for the shipped 10 ft default.
- Chart depth units (my call): the pack styles draw soundings and contour labels in feet (`metadata.cheekymarine.units`), and the pack contract does not let the app rewrite label expressions. The depth unit setting changes the overlay slots and big numbers only; the settings screen says "Chart depths are in feet". Metres on the chart would need a pack contract change and new packs, a later decision.
- Palette: day, dusk, night select `nav-<palette>` or `fish-<palette>`. A palette or mode change reloads the style, keeps camera and runtime layers (own boat, track, AIS are re-added after load), and re-applies the depth filters.
- Notice: the current style's `metadata.cheekymarine.notice` is shown as a small, always-visible line at the bottom edge of the chart, under any bottom banner slot. It is not dismissable (the notices say "not certified for navigation"; my call that it stays visible).
- Legend: a button on the chart page opens a sheet listing `legend.json` entries (abbreviation, meaning, kind), large rows, searchable by scrolling only (no keyboard on the boat). There is no tap-to-lookup on the chart: the spike found the MapLibre Qt API has no rendered-feature query (owner decided 2026-10-29, checkpoint 1 approved; it could return by exposing `queryRenderedFeatures` upstream).

### 6.6 Chart page behaviour (my calls unless marked)

- Orientation: head-up default (owner decided 2026-10-29: "I generally run in head up mode, not North up."); three settings values: north-up, head-up, course-up. Head-up uses true heading (magnetic + variation), else COG when SOG > 0.5 kn, else bearing 0. Course-up uses COG when SOG > 0.5 kn, else heading if present, else stays north-up.
- Follow mode on by default: boat kept at the screen centre (or lower third in head-up and course-up). Any pan turns follow off and shows a large "Recenter" button.
- Zoom: pinch, plus large + and - buttons (wet fingers pinch badly). Zoom range limited to the packs' range plus 2 overzoom.
- Own boat: a boat icon at the GNSS position rotated to heading if present, else COG; a heading line to the screen edge; a COG vector of length equal to 2 minutes at SOG (my call, setting later if wanted). No boat icon without a position; a "No position" chip instead.
- Mode toggle Navigation / Fishing: one large button, always visible on the chart page, labelled with the mode it is in.
- Overlays and AIS are runtime GeoJSON sources and layers inside MapLibre (so they move with the chart exactly), with icons added as runtime images drawn by us. If the spike shows that is not workable, QML items positioned by the map's coordinate conversion are the fallback.
- AIS (goal 10): triangle per target rotated to heading, else COG; a COG vector of 6 minutes at SOG; class B drawn smaller; targets with `posAge` over 60 s drawn hollow; tap a target for a sheet with name, MMSI, SOG, COG, range and bearing from own ship. No CPA alarms (phase 2).

### 6.7 Overlay slots and fields

- Slots exactly as parent 6.5. Sizes small, medium, large map to digit heights of about 8, 14 and 25 mm on the configured panel (section 6.10). Bars and banners shrink the chart viewport rather than covering it (my call: the boat stays visible).
- Fields in plan 3: depth, SOG, STW, COG, heading, water temperature, position, time, engine RPM. Bearing, distance, XTE and ETA arrive with waypoints in phase 2; the field list is an enum the phase 2 plan extends.
- Depth shown is `depth + depthOffset` when an offset is present (n2kd contract: positive to the waterline, negative to the keel), so it reads like the Garmin, which applies the same configured offset. My call; a setting "Apply transducer offset" defaults on.
- Units (settings): depth ft (default), m, fathoms; speed kn (default), mph, km/h; temperature F (default), C; position degrees and decimal minutes. Formatting is pure C++ and unit tested, including rounding (depth under 10 ft one decimal, otherwise whole feet; my call matching the Garmin's look).
- Editing: on the chart page, a settings entry "Edit overlays" shows each slot outlined; tap a slot to pick on or off, field and size from big lists. No drag and drop.

### 6.8 Big numbers page

Two to four cells filling the screen, default depth and SOG, each cell's field pickable the same way as slots. Large digits fill the cell; labels and units small.

### 6.9 Navigation, global controls, touch lock (my calls inside parent 6.5)

- Page switch: a persistent tab bar on the right edge (no swipe: swipe fights chart panning). Tabs: Chart, Numbers, Tracks, Settings. Each tab at least 15 mm square.
- Global control bar (part of the tab bar, always reachable): touch lock and palette (day, dusk, night, auto cycling). Reserved spaces: brightness (plan 5) and MOB (phase 2).
- Touch lock: on from the lock button or after the idle timeout (setting, default 2 min, can be off). While locked every touch is swallowed except a 1.5 s long press on the lock icon, which shows a progress ring while held. Locked state shows a small padlock on the tab bar and dims the tab bar. The lock is a C++ state machine with an injectable clock, unit tested.
- Boot splash: app, charts pack and bathy pack versions and the pack notice, shown for at least 2 s.

### 6.10 Panel sizing (my call)

Physical size comes from a setting `panel_diagonal_in` (default 10.1) with the resolution read at run time, giving pixels per millimetre. All sizes in QML are in millimetres through one `Units` singleton. Screenshots at 1024x600 and 1280x800 are part of every UI checkpoint for the owner.

### 6.11 Palette automation

Auto mode picks day between sunrise and sunset, dusk from sunset to civil dusk and from civil dawn to sunrise, night otherwise, from the boat's position and GNSS or system time, re-evaluated every minute. Without a position it keeps the last palette. The solar calculation is a small pure C++ implementation of the NOAA solar position equations (public domain), tested against NOAA's published sunrise and sunset times for Seattle on several dates. UI night palette: red on black, no white anywhere.

### 6.12 Storage and schema (parent 6.9)

- SQLite file `plotter.db` in `--data DIR`, through Qt SQL's SQLite driver. `journal_mode=WAL`, `synchronous=FULL`, so a power cut loses at most the last write and never corrupts the file.
- A `schema_version` table and numbered migrations in C++, each tested from an empty database and from the previous version's fixture. Plan 3 ships schema 1.0.0: `settings` (key, JSON value), `tracks` (id, name, started, ended, visible), `track_points` (track id, t, lat, lon, sog, cog, depth). Waypoints and routes are added by phase 2 as a minor bump.
- Settings are read at start and written on change. Unknown keys are kept; unknown schema major refuses to open the database and shows a recovery screen offering "Start fresh (keeps a copy)", the only way out without a keyboard.

### 6.13 Tracks (deviation from parent 6.2, owner decided 2026-10-29: "App")

Parent 6.2 says the daemon writes the track log. n2kd's socket is one-way, so start, stop and interval set from the UI would need a command channel and n2kd changes. Owner decided: the app records tracks into SQLite. A UI crash stops recording until systemd restarts the app (seconds); n2kd's `--rawlog` still holds every position frame, so nothing is unrecoverable.

- Recording: on or off, interval by time (default 5 s) with a minimum distance (default 10 m) so a stopped boat adds no points. Recording state survives restarts. A new track starts on each app start while recording is on, and after a position gap over 10 min.
- Tracks page: list (name defaulting to start date and time, duration, distance), show or hide each, delete with a confirm, rename is out (no keyboard).
- Shown tracks draw as lines on the chart; the active track always shows.
- Track writing is batched (every 30 s or 20 points) so the database is not written every fix; at most 30 s of track is lost on a power cut.

### 6.14 Dev and test data (my call)

- n2kd's fixtures have no position in Puget Sound and no real depth. A Python script `plotter/tools/synth-n2k.py` (stdlib only) writes candump `-L` logs of 129025, 129026, 127250, 128267, 130316 and a few AIS class A and B targets along a scripted path near Everett and Port Townsend, with depth taken from a list. The output replays through `n2kd --replay`, so the app is tested through the real daemon. Generated logs are committed as fixtures (small) with their generating command.
- `plotter/tools/run-dev.sh` starts n2kd in replay with a fixture and the app against it with the local packs (`chartpack/work/...` or a downloaded release).
- C++ tests cover: n2k client parsing, staleness and reconnect (against a fake socket server), unit formatting, slot configuration, pack catalog, style rewrites, depth filter rewrite, sun times, touch lock, track recorder thinning and gap splitting, migrations, settings round trip.
- QML is tested where it pays: a QML test that loads each page with mocked models under the offscreen platform and checks it constructs, and minimum target sizes. Look and feel is checked by the owner from screenshots at checkpoints.

### 6.15 Owner checkpoints (my call)

1. After the spike: written answers to 6.3 and a short screen recording or screenshots of the chart in the spike.
2. Chart page with own boat, both modes, three palettes: screenshots at both resolutions. Taken at the end of plan Task 11, once the palettes exist (owner decided 2026-10-29).
3. Overlay slots and big numbers: screenshots, especially digit sizes against the 15 ft target.
4. Whole app before the PR is marked ready.

## 7. Risks

- maplibre-native-qt MBTiles through the Qt platform, runtime filters, runtime GeoJSON (spike 6.3). Highest risk; first task.
- Qt Location dependency: resolved by the spike (owner decided 2026-10-29). The adapter is a custom `QQuickItem` over `QMapLibre::Map`; no Qt Location or Positioning is needed on the dev machine or the Pi.
- Pi 5 performance with EGLFS and the full packs, especially Fishing mode's hillshade from `dem.mbtiles`. No Pi yet (owner, 2026-10-29); feature work proceeds on the dev machine and the Pi measurement is done the day the hardware arrives. Until then this risk is open.
- Building maplibre-native-qt is slow (tens of minutes); CI caching is required or every push pays it.
- Large-digit sizing depends on the panel's real size; the setting covers both candidates, the bench test in plan 5 confirms.

## 8. Left to the builder

- Class names, file layout inside `plotter/`, QML component structure.
- Choice between the two MapLibre APIs, after the spike.
- The pinned maplibre-native-qt commit.
- Exact visual design of the boat icon, AIS triangles, slots and tab bar, within the size rules and palettes, shown to the owner at checkpoints.
- Task order after the spike, within: models and client first, chart page, slots and numbers, palettes and safety depth, tracks, touch lock, AIS last.
