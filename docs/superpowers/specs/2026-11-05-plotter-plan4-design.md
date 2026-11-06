# plotter: plan 4, design

Date: 2026-11-05
Status: draft after the builder check of 2026-11-05 (five questions: #41 sheet fit and the tablet size answered by the owner, time sync, #32 path and the #46 bar settled as my calls); waiting for the owner's approval
Parents: `docs/superpowers/specs/2026-10-29-plotter-design.md` (plan 3) and `docs/superpowers/specs/2026-10-31-plotter-views-design.md` (saved views). Everything there stands; this document only adds and changes what it names.
Issues: #46, #41, #40, #39, #34, #33, #32, #31, #30, #28 (label `triage: plan 4`, owner decision comments of 2026-11-01), plus two new items from 2026-11-05: fullscreen and the GCC 15 build fix.

Owner decisions are quoted or marked "owner". Everything else is my call, marked "my call".

## 1. Intent

The Pi build is parked. The next real test is a touchscreen laptop (Ubuntu 26.04, the proxy) today and the Dell Latitude 7320 tablet on the boat after that. The boat is not available, so there are no live NMEA 2000 packets. The owner's rule for this plan (2026-11-05): "We need to address all of these and we don't want to waste time on things that can't actually be tested."

So plan 4 does three things:

1. Closes the ten triaged issues, each with evidence that runs off the boat (a test, a measurement on the laptop, or a render the owner can judge).
2. Makes off-boat testing realistic: scripted scenarios for the two ways the boat is actually used, "navigating at that ~26kts and fishing at ~3mph. Those are the 2 main use cases" (owner), real Puget Sound AIS traffic for density, and a tool that moves any recorded log onto our charts.
3. Adds a fullscreen mode so the owner can test the laptop the way the tablet will run ("I want to test using the fullscreen mode", owner).

The owner's own laptop feedback arrives after they test the next build; it is not in this document and becomes its own batch.

## 2. Goals

1. Every issue in the list is fixed, or closed with a measured reason, in one plotter PR (plus one chartpack PR for #33). The per-issue decisions are in section 6.
2. Two synth scenarios, `navigating` and `fishing`, on the owner's waypoints (section 5.1), replayable through real n2kd with `plotter/tools/run-dev.sh` on the dev box and on the laptop, and used by the tests that need motion.
3. One real-traffic AIS fixture for Puget Sound from MarineCadastre (CC0), played as N2K AIS PGNs (section 5.2), so #41 is tested for density, not only placement.
4. A log relocation tool: any candump or canboat RAW log, positions shifted and optionally rotated so the track lies on our charts (section 5.3).
5. `--fullscreen` (section 7), off by default.
6. `scripts/build-maplibre-qt.sh` builds on GCC 15 (section 8).
7. The "measure on the Pi first" items (#30, #46) are measured on the laptop with the `navigating` scenario, against the bars in section 6, and the numbers go in the ledger.

## 3. Non-goals

- The tablet's auto-start, auto-login and desktop integration. That is the laptop design doc (hardware workstream, `docs/hardware/`), which will pass `--fullscreen`. Plan 4 only provides the flag.
- AIS sheet content beyond today's rows (no CPA or TCPA, no target list page). #41 is placement and a density check.
- New chart regions. The packs cover 47.5 to 48.3 N (Everett, Possession bar, Jeff Head). The San Juans and Tacoma Narrows the owner also named are outside and wait for a region.
- Committing any OpenSkipper log (CC BY-SA 3.0 with a mandatory public redistribution clause). The relocate tool documents how to fetch and relocate one locally.
- A stress job in CI for #31 (owner: "No stress job now").
- The owner's laptop feedback batch (not yet given).

## 4. Anti-goals

- A fix that ships on "trust me". If the evidence needs the boat, the item is split out into its own issue that says so, per the owner's split rule, not quietly closed.
- Faking speed. A relocated log keeps its recorded SOG; the 26 kn runs come from the synth tool only.
- Fullscreen that gets in the way of dev. Off unless asked for on the command line; nothing stored in `plotter.db`.
- Losing a track point to a clean shutdown. After this plan `systemctl stop`, a desktop logout or Ctrl-C loses nothing that was already kept.
- Performance "fixes" without a number. #30 and #46 change code only if the measurement crosses the bar.

## 5. The off-boat data kit

All of it lives under `plotter/tools/` and `plotter/tests/fixtures/n2k/`, Python 3 stdlib only at test time, deterministic output (same bytes every run), and runs through the real n2kd decode path as the existing `everett-pt-townsend` scenario does. The existing scenario and its tests stay untouched (the fix-next tests pin it).

### 5.1 Two scenarios (owner's use cases and waypoints, 2026-11-05)

`navigating`: 26 kn, Everett out past Possession bar toward Jeff Head, waypoints 47.9482896,-122.3136073 then 47.9021326,-122.3743223 then 47.9080896,-122.4492273. About 12.5 km, about 16 minutes at 26 kn. The owner says the full Everett to Jeff Head run is about an hour; this is its first stretch. My call: a few degrees of heading wander at about 1 Hz and SOG within 1 kn of 26, the way a Hewescraft runs in light chop, so the display looks right rather than mathematically smooth. Depth follows a plausible profile for Possession Sound (deepening from the marina to over 100 m, then shoaling over the bar). Three AIS targets as today.

`fishing`: 3 mph (2.6 kn), trolling at Jeff Head between 47.7441216,-122.4728663 and 47.7444076,-122.4562403, back and forth, two passes (about 31 minutes). Depth along a bank profile (my call: 15 to 40 m with a small swell), water temperature steady, one AIS target passing. This scenario also feeds the dock-track rule (section 6, #34): a variant with the boat stopped (SOG 0, position jitter under 3 m) for the whole run.

Both are selected with `--scenario`, and the committed logs are `plotter/tests/fixtures/n2k/navigating.log` and `fishing.log` with a README line each (origin: generated, command to regenerate, the owner's waypoints). Duration and PGN cadence per scenario are the builder's; cadence stays what the existing scenario uses (position 1 Hz, heading 1 Hz, depth 1 Hz, AIS every 10 s).

Speed ceiling for judgment: wide open throttle, flat calm, is about 47 mph (41 kn). No scenario runs at it, but any pan or tile budget must not fall over at 41 kn; the builder notes the implied pan rate (about 21 m/s) where it sets a budget.

### 5.2 Real Puget Sound AIS traffic (#41 density)

Source: NOAA Office for Coastal Management, MarineCadastre nationwide AIS, 2024 daily broadcast points, GeoParquet, CC0 1.0 (citation: Martin, Brass, Dornback, Fontenault, 2025, Nationwide Automatic Identification System 2024, NOAA Office for Coastal Management; files under `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-MM-DD.parquet`, about 325 MB per day).

Extract: one script, `plotter/tools/extract_ais.py` (needs pyarrow; run once by the builder, not at test time), takes one day's file, a bounding box and a time window, and writes a CSV fixture with MMSI, time, lat, lon, SOG, COG, heading, name, type, length. My calls: a summer Saturday afternoon in 2024 (ferries, tugs, pleasure traffic), the box 47.70 to 48.00 N, 122.55 to 122.25 W (Possession Sound and Jeff Head, both scenarios), a two hour window, and the fixture kept under about 300 KB (thin to the busiest 30 minutes if needed). The exact date goes in the fixture README with the citation and the CC0 line, and in `THIRD_PARTY_NOTICES`.

Play: a third scenario, `ais-density`, which plays the CSV as PGN 129038 (class A position), 129039 (class B position), 129794 (class A static) and 129809 (class B static), with the own ship running the `fishing` scenario in the middle of it. The synth encoder already packs these PGNs.

What it proves: the chart draws a real day's worth of targets without stutter on the laptop, a tap picks the intended target when several are close, the sheet (now placed per #41) never covers a slot, and the no-data and expiry rules behave with real cadence (AIS at 2 s to 3 min per vessel, not every 10 s).

### 5.3 Relocating a recorded log

`plotter/tools/relocate_n2k.py IN OUT --to LAT,LON [--rotate DEG]`: reads candump `-L` or canboat RAW (the two formats n2kd replays), reassembles fast packets, moves every position by a rigid transform (translate so the first fix lands on `--to`, optionally rotate about that point), re-fragments and writes candump `-L`. PGNs touched: 129025 (int32, 1e-7 deg), 129029 (int64, 1e-16 deg), 129038 and 129039 (int32, 1e-7 deg). Everything else, including SOG, COG, heading, depth, timestamps and fast packet sequence numbers, passes through unchanged. Not-available values pass through unchanged.

Tests: relocate the committed `navigating.log` to Jeff Head and decode both with n2kd; the relocated positions equal the originals plus the transform within 1e-6 deg, every other decoded field is identical, frame count identical.

README line for the one real log worth having: OpenSkipper `Kees NMEA2000 Sample.log` (one hour underway on the IJsselmeer in 2009, real GPS and depth cadence, 60 AIS frames; it is canboat RAW with `Z` in the timestamp, which the reader must accept) with its fetch URL and the license reason it is not committed. The owner's own boat logs, when they exist, need no relocation.

## 6. The issues, one by one

Each line is the decision; the plan turns it into tasks. "Evidence" is what closes the issue.

**#46 setActiveTrack re-sends the whole line per kept point.** Owner: measure first. Two numbers, both on the laptop, both in the ledger: (1) the main-thread cost of one active-track write at 7200 points, from a Qt Test on `ChartController` with a stub map that counts calls, bytes and the serialization time (no replay needed); (2) the frame time while the real map takes those writes, from the `navigating` scenario replayed at 20x with `trackIntervalS` 1 and `trackMinDistanceM` 1 for 6 real minutes (2 hours of log, 7200 kept points, since the interval rule now runs on the monotonic clock) with the frame interval logged behind a dev flag (`frameSwapped` deltas, max and 99th percentile). Bars (my call): (1) under 4 ms (a quarter of a 60 Hz frame) and (2) no frame over 50 ms attributable to a write (MapLibre re-tiles GeoJSON sources on worker threads, so the call time alone can hide a stutter; the builder check flagged this). Under both: close with the numbers. Over either: write the full line at most once per 2 s (coalesced on a timer; the first point of a track writes at once), which keeps the data path and the GeoJSON source; the test asserts the write count over a replayed hour. Evidence: the ledger numbers and the test.

**#41 AIS sheet covers the top corner slots at 1024x600.** The builder check found the single-column sheet (eight rows, about 82 mm) cannot fit between the corner rows at 1024x600, so the rule is: the sheet lives in the part of the chart free of slots (between the top and bottom corner rows, between the left and right bar slots when shown, width clamped to that free width, floor 60 mm), its rows are "field name: value" and a long value wraps (owner: "It should be field name and value. Lines should wrap if needed"), and when the rows do not fit the free height the sheet pages (owner: "paged or scrollable when there is too much data"). My call between the two: pages, turned by two 12 mm tap buttons in the sheet's footer with a "1 of 2" label, because live views are tap-only on the water (saved views design, anti-goals) and a flick is not. The sheet never covers a slot at any of the three render sizes (section 12) with all eight slots on at their default sizes; a QML test asserts no intersection at each size and that paging reaches every row. Density: the `ais-density` scenario on the laptop, screenshot at each size with a target selected, and a tap test that picks the nearest of two targets 8 mm apart. Evidence: the test, the renders, the laptop run in the ledger.

**#40 chart controller and core minors.** `fieldRoleText(Field, bool unit, ...)` becomes `fieldRoleText(Field, FieldText part, ...)` with `enum class FieldText { Value, Unit }` (owner: whenever `Slots.h` is touched; this plan touches it). Single style parse: `styleProblem` returns the parsed styles it already read (a small struct keyed by palette) and `loadStyle` takes them, so a pack is read once at start; the later `loadStyle` warning path stays for files that change after start. AppInfo wiring: the pack list, daemon version and schema mismatch assembly moves out of `main.cpp` into a core function (`buildAppInfo(...)`) with a Qt Test. Evidence: tests.

**#39 Store::moveAside partial move.** One stamp chosen once for all three files (`plotter.db`, `-wal`, `-shm`), the result set when any file moved, the error naming what moved and what did not. Two unit tests: only `-wal` exists (result names the stamp); main moves and `-wal` rename fails (error names both). Evidence: tests.

**#34 backlog from plan 3.** Five parts:
- Time sync: both recorder rules that compare times, the new-track gap (`kNewTrackGapS`) and the keep interval (`trackIntervalS`), run on the recorder's monotonic clock (`m_nowS`, already injected), not on the vessel wall clock `s.t`, so a backward clock step no longer stops storage for its length and a forward step no longer splits the track (the builder check caught that moving only the gap rule would leave the interval rule silently dropping points for an hour). Point times stay the vessel time, so a stepped clock can store points whose `t` goes backward; the store therefore orders points by insertion (rowid), not by `t`, and `tracks.ended` is the last stored point's `t` (may be earlier than a previous one; nothing reads it for ordering). Tests: a clock step backward and forward of 1 hour mid-track keeps one track and keeps storing points every interval; the drawn order equals the recorded order. The 1970 stamps are a Pi problem (no RTC); the tablet has one. My call: no code for it; the laptop design doc gets a line that the tablet keeps time and its timezone is set at setup. Timezone display (`toLocalTime()`) stands.
- SIGTERM flush: a `SignalBridge` (socketpair plus `QSocketNotifier`, the Qt-documented pattern) turns SIGTERM and SIGINT into `QCoreApplication::quit()`, so the normal teardown runs and `~TrackRecorder` flushes. Qt Test: raise SIGTERM in-process with a recorder holding buffered points; the store has them after the event loop exits.
- License texts: `THIRD_PARTY_NOTICES` gets the full text of every license the plotter section lists without one (BSD-2-Clause for maplibre-native-qt and MapLibre Native, the ICU license, MIT for nunicode, csscolorparser, RapidJSON, unordered_dense and mlt-cpp, the curl license, Apache-2.0 for FastPFOR, BSD-3-Clause, ISC, BSL-1.0, Zlib), each once, with a pointer from each component to its text. Check: every "License:" line in the plotter section names a text present in the file.
- Qt Test optional: a CMake option `CM_PLOTTER_TESTS` (default ON) gates `Test` and `QuickTest` in `find_package` and the `tests/` subdirectory, so the app builds on a machine without the Qt Test packages. Evidence: the laptop configures and builds with it OFF (the laptop session runs it); CI stays ON.
- Dock tracks: a track that is closed with fewer than two kept points is deleted (closed = a new track starts after the gap, recording turns off, or the app quits). Test: the `fishing` stopped variant leaves no track; two starts at the dock leave none; a track with two points is kept. My call, since the issue describes the symptom and not the rule; the owner can veto.

**#33 chartpack night style keeps blue water and colored buoys.** Owner: "Let's judge the laptop in a dark room for the red-only night mode." The `night` palette in `chartpack/src/chartpack/style/palette.py` (and whatever `fish.py` adds for the bathy style) goes red-only: black water, near-black land, dim red depth contours and area fills graded by brightness instead of hue, red buoys and marks (the sprites get a night variant if the SDF path cannot recolor them), red text. Depth-area shading keeps its order (shallow brighter than deep) so the fishing chart still reads. Deliverable: the owner judges on the laptop in a dark room, `nav-night` and `fish-night` renders at 1024x600 in the PR for the record. Separate PR on the chartpack workstream (owner: "chartpack workstream, not plotter code"); the builder states how the owner gets the new styles onto the laptop's installed packs without a full pack rebuild (my call: the style files are inside the pack directory, so a style-only pack bump is the cheap path; the mechanics are the builder's). Evidence: the owner's dark-room verdict, recorded in the ledger.

**#32 migration drops slot-level unknown keys.** Owner: fix when the next schema change touches the migration. This plan makes that change: views schema 1.2.0 renames the stored key `favourite` to `favorite` (the US English item the review checklist defers to this issue). The builder check found that the 1.1.0 to 1.2.0 step goes through `viewFromJson` and `viewToJson`, which already keep per-slot extras, so the actual hole is the plan 3 path (`viewsFromPlan3` through `slotsFromJson`, which builds `SlotConfig`s and drops every extra key). My call: fix that path too, since it is the one the issue names and the fix is small (carry each slot's unknown keys from the plan 3 slot JSON into `s.extra`). Identifiers follow the rename (`favouriteCapacity`, `setFavourite`, `FavouriteRole` become the US spellings). Tests: a plan 3 fixture with an unknown slot key migrates to 1.2.0 with the key kept; a 1.1.0 fixture with `favourite: true` migrates to `favorite: true`; a 1.2.0 file is left alone. My call on doing the rename now; the owner can veto and keep the key.

**#31 tst_qml failures under load, unreproduced.** Owner: watch CI, no stress job. One run on the laptop (a slower, different machine), `ctest --test-dir build-plotter -R tst_qml --repeat until-fail:10 --output-on-failure` with the full log kept, run by the laptop session. Clean: close the issue with the log attached and the note that a CI flake reopens it. A failure: it becomes a fix task in this plan. Evidence: the log on the issue.

**#30 gallery and keyboard built at start.** Measurement on the laptop: a `qInfo("ready in N ms")` line at the window's first `frameSwapped` (kept; it is cheap and useful on the tablet), five cold starts each with the current code and with the gallery and keyboard behind a `Loader` that loads on first Setup open. Bar (my call): the Loader stays if it saves 200 ms or 10 percent of the start, whichever is less; otherwise close with the numbers and keep the simpler code. Either way a QML test keeps the Setup sheet's gallery and keyboard working on first open.

**#28 review minors carried past PR #27.** Every bullet gets a line in the ledger: fixed with a test, or closed with the reason. My calls where the bullet leaves room: whitespace-only names are floored to the default name on load and the keyboard's Done disables for whitespace-only text; the duplicated default layout literal becomes one constant; `seen[int(s.id)]` gets the range check; `replaceAll` logs the failing insert's error; the no-op signals are dropped; the fill-only icon case gets a one-line comment, not code (none is bundled); the R66 test gets its comment; the gallery Flow gap at 1024x600 is fixed in the layout; `--editor` waits for the view to be ready instead of 300 ms; the offscreen-platform crash gets a clear message at start ("renders need a GL display") instead of a crash; the drag-from-a-button test gets a touch twin; the Settings and Legend renders use a tall `--window` (for example 1024x1400) so every row is in the picture, and the no-data render takes a fixed `--position LAT,LON` dev option so the map is not black. The last two are dev aids, hidden from `--help` like the others.

## 7. Fullscreen

`--fullscreen`: the window is shown with `showFullScreen()`; `--window` is ignored with it and says so in the help text. Off by default, nothing persisted, no in-app toggle (owner: "It would be pretty irritating during dev to have it enabled, but needs to be for production"; my call: the production auto-start entry passes the flag, so dev never sees it unless asked). Leaving fullscreen is the desktop's business (the tablet never leaves it; on the laptop the owner uses the desktop's own means or quits the app). Tests: the CLI parse and the window visibility in a Qt Test on a platform that supports it, plus the laptop session confirms a screenshot with no window chrome at the panel's native size.

## 8. Build on GCC 15

`scripts/build-maplibre-qt.sh` adds `-DCMAKE_CXX_FLAGS=-Wno-error=free-nonheap-object` (the vendored MapLibre Native builds with `-Werror`; GCC 15.2 raises a false positive in `symbol_bucket.cpp`). The CI cache key hashes the script, so CI rebuilds maplibre once. Evidence: the laptop rebuilds from an empty build tree with the script unchanged otherwise; `plotter-ci` green. `plotter/README.md` gains an "Ubuntu 26.04" line (GCC 15, CMake 4.2 work; the apt list needs `pipx` and `python3-venv`; `build-essential`, `cmake` and `git` are assumed).

## 9. How the laptop is used

The laptop runs its own Claude Code session (`laptop-chart`, Remote Control). Measurements and checks that need a real screen or a slower machine are sent to it with the exact commands and the result format, and its report goes in the ledger. Items that go there: #30 and #46 numbers, #31 stress run, #34 `CM_PLOTTER_TESTS=OFF` build, fullscreen screenshot, the `ais-density` run, and the owner's dark-room check for #33. The laptop needs a screenshot tool (`grim` on Wayland) and the puget-north packs copied over; the first laptop task sets those up.

Laptop facts (its session, 2026-11-05): Lenovo ThinkPad 20W1S2E400, panel 1920x1080 at 60 Hz, 309 x 174 mm, 13.96 in diagonal; GNOME on Wayland with a 1.25 logical scale, so a fullscreen Qt window is 1536x864 logical pixels at device pixel ratio 1.25; touch screen present (Raydium I2C, multitouch); Ubuntu 26.04.1, GCC 15.2, CMake 4.2.3, Intel Iris Xe (Mesa). The laptop session sets `panelDiagonalIn` to 14 before screenshots. Its numbers for #30 and #46 are a proxy: the tablet's i7-1180G7 is faster, so laptop numbers under the bar are conservative.

## 10. Constraints

- No GPL, no license with a redistribution obligation on committed data (owner's rule; the OpenSkipper log stays out).
- US English in new text (`docs/superpowers/review-checklist.md`); existing British identifiers change only where this plan renames them (#32).
- No em-dash anywhere.
- One adversarial review of the whole branch before merge; PR threads resolved one by one after verified fixes; no merge with open threads or red CI (owner's rules, 2026-10-31).
- Every deferred part of a split issue gets its own issue with context and a reference back (owner, 2026-11-01).
- `plotter-ci` must stay green on ubuntu-24.04; the laptop is Ubuntu 26.04; both build.

## 11. Left to the builder

- Task order and the per-task test lists (superpowers:writing-plans).
- The AIS sheet's page size and footer layout (#41), within the rule in section 6.
- Scenario internals: depth profiles, wander model, AIS target placement, fixture durations, CSV column order.
- The exact MarineCadastre day and window within the stated box and size.
- How `styleProblem` hands the parsed styles to `loadStyle`.
- The `SignalBridge` shape and where it lives.
- The night palette's exact red values and the sprite recoloring path.
- The render tooling details for the two #28 render bullets.
- The ledger: `.superpowers/sdd/2026-11-05-plotter-plan4/progress.md`.

## 12. Verification bar for the PR

- `ctest --test-dir build-plotter` green on the dev box and on the laptop; `plotter-ci` green; `chartpack-ci` green for the #33 PR.
- Three render sizes from this plan on: 1024x600 and 1280x800 at 10.1 in (the Pi panel) and 1920x1280 at 13 in (the Dell Latitude 7320 Detachable, 3:2; owner, 2026-11-05: add it). Renders at all three for every visual change (#41, #28 gallery gap, #28 render tooling, fullscreen on the laptop); the layout tests that run at both old sizes run at the third too. The laptop (1920x1080 at 14 in, 1536x864 logical under its 1.25 Wayland scale; section 9) is a fourth, manual-only size for the fullscreen screenshot, not a render-set size.
- Ledger lines with numbers for #30 and #46, the #31 log, the laptop build with tests off, and the owner's dark-room verdict for #33.
- Every one of the ten issues closed by the PR or re-filed per the split rule, none left dangling.
