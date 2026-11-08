# Plotter plan 6: display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 9 mm own-boat icon modeled on the owner's Hewescraft, AIS icons scaled to match, switchable heading and COG lines with a settable COG time and a T end, a user-styled track, amber night overlays, and a categorized, collapsible legend that matches the current view.

**Architecture:** Settings gain six keys. `Overlays` (pure functions) gains own-ship options, the COG tip feature and the new colour sets; `Icons.cpp` draws the new boat, AIS sizes and the tip bar. `ChartController` feeds settings into the own-ship GeoJSON and the runtime track layers and builds the legend model from the loaded style. A new `SpriteSheet` (core) plus `LegendImageProvider` (app) give QML the pack's real symbols; `LegendSheet.qml` is rewritten around collapsible categories.

**Tech Stack:** C++23, Qt 6.8 (Quick, Test, QuickTest), MapLibre Native Qt, QML.

**Spec:** `docs/superpowers/specs/2026-11-07-plotter-plan6-design.md` (approved 2026-11-07). Mockups: `docs/superpowers/specs/2026-11-07-plotter-plan6-mockups/`.

## Global Constraints

- Never use an em-dash character anywhere: code, comments, QML strings, commit messages, docs.
- US English in new text (color, center, meter, favorite). Existing British identifiers (`OverlayColours`, `colours`) keep their names; do not rename them.
- Build and test: `cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"`, `cmake --build build-plotter`, `ctest --test-dir build-plotter --output-on-failure` (from the repo root; if linuxbrew is on PATH, prefix with `env -u LD_LIBRARY_PATH PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin`). Report a pass only from ctest's own exit status of a fresh run, never from piped output.
- Touch only, no keyboard on the boat: every new control is tap or drag, touch targets at least `Units.mm(12)`.
- Settings write immediately and validate on set (the existing `Settings` pattern); unknown or invalid values are ignored and logged.
- Night overlay rule (spec 4.1): every night overlay colour has blue <= 0x20 and green <= 0.75 x red, except the starboard light, which is exactly `#20A040`.
- Dusk overlays: the day colour scaled toward black by 0.45 (each channel x 0.55, rounded), the same as `_toward_black(colour, 0.45)` in `chartpack/src/chartpack/style/palette.py`.
- Sizes on screen in mm through `pxPerMm`: boat 9, AIS A 6, AIS B 4.5, AIS lost 6, COG tip bar 4.
- No new third-party dependency.
- Branch: `plan6-display` from `main` (the spec commit on `plan6-display-design` is merged into it or cherry-picked first). One PR.

## Review Focus

1. Changing a display setting while the chart has no style yet (no pack, or before `styleLoaded`) must not crash or lose the value; it applies on the next load. Test in Task 4 (`displaySettingsBeforeReadyApplyOnLoad`).
2. A `trackColor` value that is not `#RRGGBB` (hand-edited DB, old build) must be refused by the setter and read as the default. Test in Task 1 (`trackColorRejectsBadText`).
3. A charts pack whose sprite files are missing or unreadable must still show the legend, with rows but no symbol images, and no crash. Test in Task 6 (`missingSheetIsError`) and Task 8 (`test_legendRowWithoutImage`).
4. Switching between nav and fish views, or changing palette or depth settings, while the legend is open must update its rows in place. Test in Task 7 (`legendFollowsModeAndDepths`).
5. Very long COG lines (60 min at 26 kn is about 48 km) and very short ones (just above 0.5 kn at 1 min, about 16 m) must both get the tip at the line's end. Test in Task 2 (`cogTipAtLineEnd`).

---

### Task 0: Branch and GitHub issues (controller, not a subagent)

- [ ] **Step 1:** `git switch -c plan6-display plan6-display-design` (that branch is `main` plus the spec commit `2e2335a`).
- [ ] **Step 2:** Create one issue per item, each with plain-language context and a link to the spec section: own-boat icon (4), night overlays amber (4.1), AIS sizes (5), heading and COG line settings with T end (6), track style (7), legend categories (8), and the three bugs from section 9 (corner slot resize stops early; slot edit dialog buttons overlap; long press on a corner slot shows no resize handle). Label `plan 6`. Record the numbers in this plan's tasks before dispatching.

### Task 1: Settings keys

**Files:**
- Modify: `plotter/src/core/Settings.h`, `plotter/src/core/Settings.cpp`
- Test: `plotter/tests/tst_settings.cpp`

**Interfaces:**
- Produces (Q_PROPERTYs with READ/WRITE/NOTIFY, setters named `setX`, signals `xChanged`):
  - `bool showHeadingLine`, default `true`
  - `bool showCogLine`, default `true`
  - `int cogLineMin`, default `1`, valid 1..60 whole numbers
  - `QString trackLineType`, default `"dashed"`, one of `"solid"`, `"dashed"`, `"dotted"`, `"dashdot"`
  - `QString trackColor`, default `"#444444"`, valid `^#[0-9A-Fa-f]{6}$`, stored as given
  - `QStringList legendOpen`, default empty, stored as a JSON array of strings (the open legend category ids)

- [ ] **Step 1: Write the failing tests** in `tst_settings.cpp`:
  - `displayDefaults`: fresh store gives `showHeadingLine()==true`, `showCogLine()==true`, `cogLineMin()==1`, `trackLineType()=="dashed"`, `trackColor()=="#444444"`, `legendOpen().isEmpty()`.
  - `cogLineMinRange`: `setCogLineMin(60)` stores 60; `setCogLineMin(0)` and `setCogLineMin(61)` leave 60 and emit nothing.
  - `trackLineTypeDomain`: each of the four values stores; `"wavy"` is ignored.
  - `trackColorRejectsBadText`: `"#1a2B3c"` stores; `"red"`, `"#12345"`, `"#1234567"` are ignored; a row written directly to the store as `"\"blue\""` reads back as `"#444444"` after reopening.
  - `legendOpenRoundTrip`: set `{"ais","hazards"}`, reopen the store, read the same list; setting the same list again emits nothing.
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_settings --output-on-failure`. Expected: build failure (no such members).
- [ ] **Step 3:** Add the keys to `defs()` in `Settings.cpp`. Add `Check isInt(int min, int max)` (keep the one-argument form for `trackIntervalS`), a regex check for the color, and an all-strings array check. Add the members to `Settings.h` in the existing one-line style.
- [ ] **Step 4:** Run the same ctest command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): display settings for lines, track style and legend state`.

### Task 2: Own-ship options and the COG tip feature

**Files:**
- Modify: `plotter/src/core/Overlays.h`, `plotter/src/core/Overlays.cpp`
- Test: `plotter/tests/tst_overlays.cpp`

**Interfaces:**
- Produces:
  - `struct OwnShipOptions { bool heading = true; bool cog = true; double cogSecs = 60.0; };`
  - `QJsonObject ownShipGeoJson(const VesselState& v, const OwnShipOptions& opts = {});` Features: kind `"boat"` as today; `"heading"` only when `opts.heading` and a true heading is known; `"cog"` LineString of length `sogMs * opts.cogSecs` only when `opts.cog` and `cogDeg(v)`; with it a kind `"cogtip"` Point at the cog line's end with `rot` = the COG in degrees.
  - Remove `kCogSecs`.

- [ ] **Step 1: Write the failing tests:**
  - `headingOffLeavesHeadingOut`: with heading and COG known, `{.heading=false}` gives no `"heading"` feature and still a `"cog"`.
  - `cogOffLeavesCogAndTipOut`: `{.cog=false}` gives no `"cog"` and no `"cogtip"`.
  - `cogLengthFollowsTime`: SOG 10 m/s, `cogSecs` 600: the cog line's end is 6000 m from the start within 1 m (`distanceM`).
  - `cogTipAtLineEnd` (data-driven: SOG 0.26 m/s with 60 s; SOG 13.4 m/s with 3600 s): the `"cogtip"` point equals the cog line's last coordinate and its `rot` equals the COG degrees within 1e-9.
  - Existing tests keep passing with the default options (update any that assumed 120 s).
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_overlays --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement in `Overlays.cpp`; update the header comment to describe the options and the `"cogtip"` kind.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): heading and COG line options and COG tip point`.

### Task 3: Overlay colours, boat and AIS icons

**Files:**
- Modify: `plotter/src/core/Overlays.h`, `plotter/src/core/Overlays.cpp`, `plotter/src/app/Icons.cpp`, `plotter/src/app/Icons.h` (comment only, if it lists sizes)
- Test: `plotter/tests/tst_palette.cpp`

**Interfaces:**
- Produces:
  - `struct OverlayColours { QColor hullFill, hullOutline, cabin, windshield, motor, motorOutline, portLight, stbdLight, aisFill, aisOutline, heading, cog, aisVector, track; };` (`boatFill` and `boatOutline` are replaced by the hull fields; `track` is the night track colour and the fallback; day and dusk track colours come from `trackColour`.)
  - `OverlayColours overlayColours(const QString& palette);`
  - `QColor towardBlack(const QColor& c, double t);` each channel x (1 - t), rounded.
  - `QColor trackColour(const QColor& chosen, const QString& palette);` day: `chosen`; dusk: `towardBlack(chosen, 0.45)`; night: `overlayColours("night").track`.
  - `OverlayIds::kCogTipImage = "cm-cog-tip"` (new image id).
  - `chartIcons(pxPerMm, palette)` returns 5 images: `cm-boat`, `cm-ais-a`, `cm-ais-b`, `cm-ais-hollow`, `cm-cog-tip`.
- Values (spec 4, 4.1, 5):
  - Day: hullFill `#6E99BE`, hullOutline `#1e3448`, cabin `#d4d8dc`, windshield `#22303f`, motor `#3a3f45`, motorOutline `#111111`, portLight `#b85450`, stbdLight `#4f9a64`. AIS, heading, cog, aisVector keep today's day values.
  - Dusk: every day value through `towardBlack(_, 0.45)` (replaces today's hand-picked dusk set).
  - Night: hullFill `#7a5000`, hullOutline `#E0A000`, cabin `#2a1a08`, windshield `#0a0500`, motor `#1a0e04`, motorOutline `#C08000`, portLight `#a02018`, stbdLight `#20A040`. AIS fill, AIS outline, heading, cog, aisVector, track: the builder's ambers within the night rule (Global Constraints); the COG line and AIS vector must stay distinguishable from the chart's amber text (`#E0A000`, `#C08000`), so use a darker or redder amber for them.
  - Boat shape: the 40 x 100 box of `boat-icon-v3.html`, style C (hull path, cabin rect 10..30 x 36..64 r3, windshield band, D lights of radius 3.5 from y 37.5 to 44.5 on the cabin walls at x 10 and 30, main motor 9 x 9 at x 15.5, kicker 4.5 x 6 at x 27, both from y 88), scaled so the box height is 9 mm, on a square transparent canvas of side = that height so `icon-rotate` turns it about its center.
  - AIS: Class A 6 mm, Class B 4.5 mm, hollow 6 mm; shapes unchanged.
  - COG tip: a bar 4 mm long, as thick as the `cm-own-cog` line (3 px), in the palette's `cog` colour, horizontal and centered on a square canvas, so rotated by the COG it lies across the line.

- [ ] **Step 1: Write the failing tests** in `tst_palette.cpp`:
  - Replace `nightOverlayColoursAreRedOnly` with `nightOverlayColoursAreAmber`: every field of `overlayColours("night")` passes `amberSafe(c)` (blue <= 0x20, green <= 0.75 x red) except `stbdLight == QColor("#20A040")`.
  - Replace `nightIconsAreRedOnly` with `nightIconsAreAmber`: every opaque pixel of every night icon passes `amberSafe`, or is within 8 per channel of `#20A040` (the starboard light, with antialiasing); `icons.size() == 5`.
  - `duskIsDayTowardBlack`: for each field, dusk == `towardBlack(day, 0.45)`.
  - `trackColourPerPalette`: `trackColour(#444444,"day") == #444444`; dusk == `towardBlack(#444444,0.45)`; night == `overlayColours("night").track` for any chosen colour.
  - `iconSizes` (pxPerMm 4): `cm-boat` is 36 x 36; `cm-ais-a` 24; `cm-ais-b` 18; `cm-ais-hollow` 24; `cm-cog-tip` 16 wide.
  - `dayBoatHasHullAndLights`: the day boat image contains pixels of `#6E99BE`, `#b85450` and `#4f9a64` (within 8 per channel); the port colour appears only left of center, the starboard only right.
  - Keep `overlayColoursDifferPerPalette` (update field names).
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_palette --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement the colours in `Overlays.cpp` (update the header comment: night is amber, not red-only) and the drawing in `Icons.cpp`.
- [ ] **Step 4:** Run `ctest --test-dir build-plotter --output-on-failure` (full run: `ChartController` uses the renamed fields). Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): Hewescraft own-boat icon, AIS sizes and amber night overlays`.

### Task 4: Chart controller applies the display settings

**Files:**
- Modify: `plotter/src/core/ChartController.h`, `plotter/src/core/ChartController.cpp`
- Test: `plotter/tests/tst_chartcontroller.cpp`

**Interfaces:**
- Consumes: Task 1 settings; Task 2 `OwnShipOptions`, `ownShipGeoJson(v, opts)`; Task 3 `trackColour`, `kCogTipImage`.
- Produces:
  - `OwnShipOptions ChartController::ownShipOptions() const` from `showHeadingLine`, `showCogLine`, `cogLineMin * 60`.
  - Runtime layer `cm-own-cog-tip` (symbol, source `cm-own`, filter kind `"cogtip"`, `icon-image` `cm-cog-tip`, `icon-rotate` `["get","rot"]`, `icon-rotation-alignment` `"map"`, overlap and ignore-placement true), directly above `cm-own-cog` and below `cm-own-boat`.
  - Track layers (`cm-tracks-line`, `cm-track-active-line`): `line-color` = `trackColour(QColor(trackColor), palette)`; `line-dasharray` by type: solid none, dashed `[4,2]`, dotted `[0.1,2]` with `line-cap` `"round"`, dashdot `[4,2,0.1,2]` with `line-cap` `"round"`.

- [ ] **Step 1: Write the failing tests:**
  - `headingAndCogSettingsRepushOwnShip`: with a moving vessel and a loaded style, `setShowHeadingLine(false)` makes the next `cm-own` GeoJSON lack `"heading"`; `setShowCogLine(false)` lacks `"cog"` and `"cogtip"`; `setCogLineMin(5)` lengthens the cog line to SOG x 300 s. No style reload happens (`calls` has no new `"style"`).
  - `cogTipLayerAboveCog`: after load, `layerIds` has `cm-own-cog`, then `cm-own-cog-tip`, then `cm-own-boat`.
  - `trackStyleFromSettings` (data rows for the four types): the two track layers carry the expected `line-color` and `line-dasharray` (absent for solid); changing `trackColor` or `trackLineType` triggers a style reload and the new layers carry the new values.
  - `trackNightIsAmberWhateverChosen`: palette night, `trackColor` `#00ff00`: track `line-color` == `overlayColours("night").track`.
  - `displaySettingsBeforeReadyApplyOnLoad`: with `syncStyleLoaded=false`, change all five display settings before `styleLoaded`; no crash; after emitting `styleLoaded`, the layers and the own-ship GeoJSON reflect them.
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_chartcontroller --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement: connect the three line settings to a re-push of `cm-own` (only when `m_ready`); connect `trackColorChanged` and `trackLineTypeChanged` to `loadStyle()`; make `runtimeLayers` take the track colour and dash.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): chart applies line, COG time and track style settings`.

### Task 5: Settings page rows and the color picker

**Files:**
- Modify: `plotter/qml/SettingsPage.qml`
- Create: `plotter/qml/TrackColorSheet.qml`, `plotter/qml/StepperRow.qml` only if `SettingsPage` has no reusable stepper (reuse the depth stepper pattern if it fits)
- Modify: `plotter/CMakeLists.txt` (QML module file list)
- Test: `plotter/tests/qml/tst_pages.qml`

**Interfaces:**
- Consumes: Task 1 settings.
- Produces (objectNames for tests): rows `row-showHeadingLine`, `row-showCogLine`, `row-cogLineMin`, `row-trackLineType`, `row-trackColor`; COG stepper buttons `cogLineMinMinus`, `cogLineMinPlus`; sheet `trackColorSheet` with `trackColorDefault`, `trackColorDone`, preview `trackColorPreview`.
- Row text: `"Heading line: On"`/`"Off"`, `"COG line: On"`/`"Off"`, `"COG line time: 1 min"`, `"Track line: Dashed"` (Solid, Dashed, Dotted, Dash-dot), `"Track color"` with a swatch of the current color.
- Behavior: on/off rows toggle on tap. The COG stepper changes by 1 per tap and repeats while held (400 ms delay, then 5 per second), clamped to 1..60, like `SlotSheet.qml`. Line type opens the existing `openList`. The color sheet: a saturation/value square and a hue strip, both draggable by touch with thumbs of at least `Units.mm(12)`; a preview line (`trackColorPreview`) drawn in the chosen color and the current line type; `Default` sets `#444444`; every change writes `settings.trackColor` as `#RRGGBB`.

- [ ] **Step 1: Write the failing tests** in `tst_pages.qml`:
  - `test_lineToggles`: tapping `row-showHeadingLine` flips `settings.showHeadingLine` and the row text; same for `row-showCogLine`.
  - `test_cogLineMinStepper`: from 1, minus stays 1; plus 3 times gives 4; set 60, plus stays 60; row reads `"COG line time: 60 min"`.
  - `test_trackLineTypeList`: choosing Dotted from the list sets `"dotted"` and the row reads `"Track line: Dotted"`.
  - `test_trackColorSheet`: opening the sheet; a drag on the hue strip changes `settings.trackColor` to a valid `#RRGGBB`; `trackColorDefault` sets `#444444`; `trackColorDone` closes it.
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_qml --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement the rows and the sheet (the settings stub in `tst_pages.qml` gains the six properties).
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): settings rows for lines, COG time and track style, touch color picker`.

### Task 6: Sprite sheet reader

**Files:**
- Create: `plotter/src/core/SpriteSheet.h`, `plotter/src/core/SpriteSheet.cpp`
- Modify: `plotter/CMakeLists.txt` (plottercore sources, `plotter_add_test(tst_spritesheet ...)`)
- Test: `plotter/tests/tst_spritesheet.cpp` (fixtures generated in the test into a `QTemporaryDir`)

**Interfaces:**
- Produces:
  - `class SpriteSheet { public: static std::expected<SpriteSheet, QString> load(const QString& base); QImage image(const QString& name, const std::optional<QColor>& tint) const; bool contains(const QString& name) const; };` `base` is the path without extension (for example `<pack>/sprites/nav`); it reads `base + "@2x.json"` and `@2x.png`, falling back to the 1x pair.
  - An `sdf: true` entry becomes `tint` with alpha from the SDF value: fully opaque at 0.75 x 255 and above, falling linearly to 0 at 0.75 x 255 - 16 (MapLibre's SDF edge is 0.75); with no tint, black. A non-SDF entry is the cropped RGBA as is (tint ignored). An unknown name gives a null `QImage`.

- [ ] **Step 1: Write the failing tests:**
  - `loadsTwoXFirst`: with both pairs present, the image of a 2x entry has the 2x size.
  - `sdfTinted`: a 4 x 4 SDF cell with alpha 255 in the middle and 0 at the edges gives the tint colour at full alpha in the middle and alpha 0 at the edges.
  - `bakedCroppedAsIs`: a non-SDF entry returns its exact RGBA pixels.
  - `unknownNameIsNull`.
  - `missingSheetIsError`: no files gives an unexpected with a message naming the path.
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_spritesheet --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): sprite sheet reader for legend symbols`.

### Task 7: Legend model

**Files:**
- Create: `plotter/src/core/Legend.h`, `plotter/src/core/Legend.cpp`
- Modify: `plotter/src/core/ChartController.h`, `plotter/src/core/ChartController.cpp`, `plotter/CMakeLists.txt`
- Test: `plotter/tests/tst_legend.cpp` (new), `plotter/tests/tst_chartcontroller.cpp`

**Interfaces:**
- Consumes: Task 3 `overlayColours`; the loaded style (`m_style`), mode and palette; `m_legend` (seabed entries).
- Produces:
  - `std::optional<QColor> styleColour(const QJsonObject& style, const QString& layer, const QString& paintProp, int output = -1);` A literal colour string is returned as is. For a `step` or `match` expression, `output` k >= 0 is the k-th output value (step: the base, then each stop's value; match: each case's value, then the fallback), and -1 is the last output (the fallback). Anything else, or a missing layer, gives none.
  - `QVariantList legendCategories(const QString& mode, const QJsonObject& style, const QString& palette, const QVariantList& seabed);` (empty `style` means no pack). Each category: `{id, title, rows, needsPack}`; each row: `{label, note, kind, color, sprite, tint, dash, width, text, depthFrom, depthTo, layers}`. `kind` is one of `"sprite"`, `"swatch"`, `"line"`, `"text"`, `"overlay"`, `"seabed"`. `sprite` names a sheet entry (hazard rows use the baked name `hazard-<shape>[-danger]-<palette>` and no tint); `"overlay"` rows name a `chartIcons` id. `depthFrom`/`depthTo` are strings: empty when the row is not a depth band or the band is open-ended; `"0"`, `"shallow"`, `"safety"` or `"deep"` for nav bands (QML resolves the names from the current settings); a number of metres for fish bands (fixed 0, 30, 90, 180 ft, converted).
  - Category ids and order: `ais`, `navaids` (nav only), `lights`, `hazards`, `depths`, `seabed`. Titles: "AIS targets", "Buoys and beacons", "Lights", "Hazards", "Depths, areas and lines", "Seabed".
  - Rows: the spec's section 8 lists, plus one row per style layer otherwise unexplained, so that every layer id of the six fixture styles (`plotter/tests/fixtures/styles/*.json`), `background` included ("No chart data"), appears in some row's `layers`. Contour and sounding label layers get `"text"` rows; `hillshade` gets a "Relief shading" row (kind `"swatch"`, the hillshade shadow colour); `water-base` gets "Water outside the fine survey".
  - Without a style: only `ais` has rows; every other category has `needsPack: true` and no rows.
  - `ChartController`: `Q_PROPERTY(QVariantList legendCategories READ legendCategories NOTIFY legendCategoriesChanged)`, rebuilt on every style load (mode and palette changes reload the style); `Q_PROPERTY(QString spriteBase READ spriteBase NOTIFY legendCategoriesChanged)` = the loaded style's `sprite` value without `file://`. The existing `legend` property stays (seabed entries).

- [ ] **Step 1: Write the failing tests** in `tst_legend.cpp`:
  - `styleColourLiteralAndExpressions`: on `nav-day.json`, `depare-deep` `fill-color` is `#F4EEE2`; on `fish-day.json`, `band-fill` `fill-color` outputs 0..3 are `#8EC3E6`, `#B8DCF2`, `#DCEEF9`, `#F4EEE2`; `navaid` `icon-color` with -1 is the CHGRD default; an unknown layer gives none.
  - `everyStyleLayerHasALegendRow` (data rows: the six fixture styles): every `layers[].id` is in some row's `layers` for that style's mode.
  - `fishHasNoNavaidsOrSoundings`: fish categories have no `navaids` and no row whose `layers` contains `soundg-deep`.
  - `categoryOrder`: nav ids are `ais, navaids, lights, hazards, depths, seabed`; fish ids drop `navaids`.
  - `hazardSpritesFollowPalette`: on `nav-night.json` the rock row's `sprite` is `hazard-rock-night`.
  - `noStyleOnlyAis`: empty style gives `ais` with 4 rows, the rest `needsPack` with no rows.
  And in `tst_chartcontroller.cpp`:
  - `legendFollowsModeAndDepths`: `legendCategoriesChanged` fires on `setMode("fish")` and on a palette change; the fish set has no `navaids`.
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R "tst_legend|tst_chartcontroller" --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement `Legend.cpp` (the row table is data in one function per category) and the controller properties.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): legend model covering every chart layer, per view`.

### Task 8: Legend images and the collapsible legend sheet

**Files:**
- Create: `plotter/src/app/LegendImageProvider.h`, `plotter/src/app/LegendImageProvider.cpp`
- Modify: `plotter/src/app/main.cpp`, `plotter/qml/LegendSheet.qml`, `plotter/qml/ChartPage.qml`, `plotter/CMakeLists.txt`
- Test: `plotter/tests/qml/tst_pages.qml`

**Interfaces:**
- Consumes: Task 6 `SpriteSheet`; Task 7 `legendCategories`, `spriteBase`; Task 3 `chartIcons`; Task 1 `legendOpen`.
- Produces:
  - `class LegendImageProvider : public QQuickImageProvider` registered as `"legend"`. Ids: `sprite/<name>/<tint hex without # or "none">` from the `SpriteSheet` at `spriteBase` (reloaded when `spriteBase` changes), and `overlay/<chartIcons id>` from the current palette's `chartIcons`. An unknown id or unreadable sheet returns an empty image, not an error.
  - `LegendSheet.qml`: title `"Legend"`; properties `categories` (bound to `chart.legendCategories`), `openIds` (bound to `settings.legendOpen`), `depthUnit`, `shallowM`, `safetyM`, `deepM`. One header per category (objectName `legendHeader-<id>`) showing title, row count in parentheses and a chevron; tapping toggles the id in `settings.legendOpen`. Rows (objectName `legendRow`) show the sample (sprite or overlay `Image`, swatch `Rectangle`, line with dash, sample text, or the seabed abbreviation) and label plus note. Depth band notes read like `"6 to 10 ft"`, `"deeper than 30 ft"`, in the user's depth unit, with the depth formatting of `SettingsPage.depthText`. A `needsPack` category shows one line `"Needs a charts pack"` when open.

- [ ] **Step 1: Write the failing tests** in `tst_pages.qml` (the chart stub gains `legendCategories` and `spriteBase`):
  - Update `test_legendSheet` to the new title and headers.
  - `test_legendCollapsed`: with nothing in `legendOpen`, no `legendRow` is visible; tapping `legendHeader-hazards` shows its rows and stores `["hazards"]`; tapping again hides them and stores `[]`.
  - `test_legendDepthNotes`: with shallow 1.8288, safety 3.048, deep 9.144 m and unit ft, the nav depth rows read `"0 to 6 ft"`, `"6 to 10 ft"`, `"10 to 30 ft"`, `"deeper than 30 ft"`; switching to m re-labels them.
  - `test_legendNeedsPack`: a category with `needsPack: true`, opened, shows `"Needs a charts pack"`.
  - `test_legendRowWithoutImage`: a sprite row whose image is empty still shows its label.
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_qml --output-on-failure`. Expected: FAIL.
- [ ] **Step 3:** Implement the provider, register it in `main.cpp` (refresh on palette change alongside `chart.setImages`), and rewrite `LegendSheet.qml`.
- [ ] **Step 4:** Run `ctest --test-dir build-plotter --output-on-failure`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): collapsible legend with real chart symbols`.

### Task 9: Docs, renders and owner check

**Files:**
- Modify: `plotter/README.md` (settings list: the six new keys with defaults and ranges), `docs/plotter/renders/` (new day and night renders of the chart with the boat, AIS, COG T and track, and of the legend open on nav and on fish)

- [ ] **Step 1:** Update the README settings section.
- [ ] **Step 2:** Produce the renders with the existing render tooling (see how `docs/plotter/renders/views/` was made in plan 4) using the `navigating` scenario; check each image by eye against the mockups: boat about 9 mm, the T at the COG end, dashed dark gray track, amber night overlays, legend categories collapsed and one open.
- [ ] **Step 3:** Run the full `ctest --test-dir build-plotter --output-on-failure`. Expected: PASS, exit status 0.
- [ ] **Step 4:** Commit `docs(plotter): plan 6 settings and renders`.
- [ ] **Step 5 (controller):** Open the PR referencing the issues from Task 0; independent adversarial review before merge; then ask the owner to look on the test laptop (`laptop-chart` session) or CapnButts, and post the result on the issues.

Section 9's three bugs are not in this plan: each is reproduced, tested and fixed on its own branch (superpowers:systematic-debugging), tracked by its Task 0 issue.
