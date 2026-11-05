# plotter: plan 4 (ten triaged issues, off-boat data kit, fullscreen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the ten `triage: plan 4` issues (#46, #41, #40, #39, #34, #33, #32, #31, #30, #28) with off-boat evidence, add the two synth scenarios, the AIS density fixture and the log relocation tool, add `--fullscreen`, and make the maplibre build pass on GCC 15; one plotter PR plus one chartpack PR for #33.

**Architecture:** No new subsystem. The data kit is Python 3 stdlib under `plotter/tools/` (the synth generator grows scenarios and a `--duration-s` override; two new scripts). The plotter changes are local to the recorder (`Tracks`), the store (`moveAside`, schema 1.2.0), the chart controller (style cache, active track write, start position), a new `SignalBridge`, `main.cpp` options, and four QML files (`AisSheet`, `ChartPage`, `LayoutGallery`, `SetupSheet`, `Keyboard`, `Main`). The chartpack change is the night palette plus a `restyle` subcommand, on its own branch.

**Tech Stack:** C++23, Qt 6.8 (Qt Test, QuickTest offscreen), QML, Python 3 unittest and pytest, canboat.json, MarineCadastre GeoParquet (pyarrow, builder only), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-05-plotter-plan4-design.md` (approved 2026-11-05). Its section 6 holds the per-issue decisions; section 9 the laptop facts; section 12 the verification bar. The issues' owner comments (2026-11-01) are quoted in the design.

**Process:** branch `worktree-plotter-plan4` from origin/main 777ceef, worktree `.claude/worktrees/plotter-plan4` (the worktree guard refuses compound shell commands that name git: run git alone, one command per call). Ledger: `.superpowers/sdd/2026-11-05-plotter-plan4/progress.md` (ignored), created by Task 1, one line per task and every laptop number. Draft PR opened after Task 1 so CI runs early. Laptop work goes to the `laptop-chart` Remote Control session by SendMessage with exact commands and the result format (design section 9); the controller does this between tasks, it is not an implementer's job. One adversarial review of the whole branch before merge; threads resolved one by one after verified fixes; no merge with open threads or red CI; the owner merges. Baseline on 27dd987: `ctest --test-dir build-plotter` 114 tests pass, `vcan round trip` skipped.

## Global Constraints

- Everything in the parent plans' Global Constraints still holds (no GPL, Qt dynamic, `-DCM_BUILD_PLOTTER=ON` only, Qt 6.5 minimum, 12 mm controls, 15 mm tabs, `--` for a missing value, WAL + FULL, TDD).
- No em-dash character (U+2014) anywhere: code, comments, UI strings, docs, commit messages.
- US English in every new or changed string, comment and doc line (`docs/superpowers/review-checklist.md`). This plan renames the `favourite` identifiers and the stored key (Task 9); after it the word does not appear in `plotter/` except the migration's legacy read.
- No committed data with a redistribution obligation: MarineCadastre AIS is CC0 and is committed; the OpenSkipper log is CC BY-SA and is only documented.
- Python tools: stdlib only at test time; `extract_ais.py` alone may import pyarrow (run once by the builder). Deterministic output: the same bytes every run.
- Three render sizes: 1024x600 and 1280x800 at 10.1 in, 1920x1280 at 13 in (`Units.diagonalIn` 13, 6.988 px/mm). `H.sizes()` in `plotter/tests/qml/Helpers.js` gains the third entry with a `diagIn` field (Task 10), and every `_data` test that uses it sets `Units.diagonalIn = data.diagIn`.
- Build and test from this worktree, without linuxbrew in the way: `env -u LD_LIBRARY_PATH PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"`, `cmake --build build-plotter`, `cmake -S . -B build -G Ninja && cmake --build build` (n2kd for the replay tests), `ctest --test-dir build-plotter --output-on-failure`. A scratch script with these lines is fine; the guard refuses `env -u` inline.
- Hidden dev options (not in `--help`) follow the existing pattern in `main.cpp` (`setFlags(QCommandLineOption::HiddenFromHelp)`) and get a line in `plotter/README.md` "Dev run".

## Review Focus

1. **A wall clock that steps backward by an hour while recording (Task 5).** Expected: one track, points keep landing every interval, the drawn line keeps the recorded order. Test `clockStepBackwardKeepsOneTrackAndKeepsStoring` and `drawnOrderIsRecordedOrder`.
2. **Ctrl-C or `systemctl stop` with buffered track points (Task 6).** Expected: nothing lost. Test `sigtermFlushesBufferedPoints` runs SIGTERM through the bridge and a nested event loop, then checks the store.
3. **An AIS target tapped at 1024x600 with all eight slots on (Task 10).** Expected: the sheet lies between the corner rows, covers no slot, and its footer pages through every row. Tests `test_aisSheetNeverCoversASlot` (three sizes) and `test_aisSheetPagesReachEveryRow`.
4. **A plan 3 database whose slot entries carry an unknown key, and a 1.1.0 database with `favourite: true` (Task 9).** Expected: both keys survive migration to 1.2.0 and the view is a favorite. Tests `plan3SlotExtrasSurviveMigration` and `favouriteKeyBecomesFavoriteAt120`.
5. **A relocated log with a not-available position field (Task 3).** Expected: the field passes through unchanged, every other field is byte-identical. Test `test_not_available_positions_pass_through` and the n2kd field-by-field comparison.

---

## File Structure

```
.superpowers/sdd/2026-11-05-plotter-plan4/progress.md   Task 1: ledger (ignored)
scripts/build-maplibre-qt.sh                             Task 1: GCC 15 flag
plotter/src/app/main.cpp                                 Task 1 --fullscreen; Task 6 SignalBridge; Task 8 connectAppInfo; Task 11 platform check, --position; Task 12 ready line; Task 13 --frame-stats
plotter/src/core/WindowOptions.h                         Task 1: applyWindowOptions()
plotter/tests/tst_appshell.cpp                           Task 1, 8, 11 tests
plotter/README.md                                        Task 1 fullscreen + Ubuntu 26.04; Task 2 scenarios; Task 9 schema 1.2.0; Task 11 dev options; Task 16 tests option
plotter/tools/synth_n2k.py                               Task 2: navigating, fishing, fishing-stopped, --duration-s, bounce; Task 4: ais-density
plotter/tools/test_synth_n2k.py                          Task 2, Task 4
plotter/tests/fixtures/n2k/{navigating,fishing,fishing-stopped}.log, README.md   Task 2
plotter/tools/relocate_n2k.py, test_relocate_n2k.py      Task 3
plotter/tools/extract_ais.py                             Task 4 (builder-run)
plotter/tests/fixtures/ais/puget-2024-07-13.csv, README.md   Task 4
THIRD_PARTY_NOTICES                                      Task 4 AIS data line; Task 16 license texts
plotter/src/core/Tracks.{h,cpp}, tests/tst_tracks.cpp    Task 5
plotter/src/core/SignalBridge.{h,cpp}, tests/tst_signalbridge.cpp   Task 6
plotter/src/core/Store.{h,cpp}, tests/tst_store.cpp      Task 7 moveAside; Task 9 schema 1.2.0
plotter/src/core/Slots.{h,cpp}, ViewDraft.cpp, tests/tst_slots.cpp   Task 8 FieldText
plotter/src/core/ChartController.{h,cpp}, tests/tst_chartcontroller.cpp   Task 8 style cache; Task 10 two-target test; Task 11 start position; Task 13 write cost (and coalescing if needed)
plotter/src/core/AppInfo.{h,cpp}                         Task 8 connectAppInfo; Task 11 platformProblem
plotter/src/core/Views.{h,cpp}, ViewsModel.{h,cpp}, ViewDraft.{h,cpp}, src/qml/PanelMath.h, qml/*.qml, tests   Task 9 rename; Task 11 #28 items
plotter/qml/AisSheet.qml, ChartPage.qml, tests/qml/tst_pages.qml, Helpers.js   Task 10
plotter/qml/LayoutGallery.qml, Keyboard.qml, Main.qml, SetupSheet.qml   Task 11, Task 12
plotter/CMakeLists.txt                                   Task 6 sources; Task 16 CM_PLOTTER_TESTS
plotter/tools/check_notices.py                           Task 16
chartpack/src/chartpack/style/palette.py, cli.py, pack/restyle.py, tests   Task 15 (own branch)
docs/plotter/renders/views/                              Task 17
```

---

### Task 1: `--fullscreen`, GCC 15 build fix, ledger, draft PR

Design sections 7 and 8.

**Files:**
- Create: `plotter/src/core/WindowOptions.h`
- Modify: `plotter/src/app/main.cpp` (options, window show)
- Modify: `scripts/build-maplibre-qt.sh` (cmake flags)
- Modify: `plotter/README.md` ("Command line", "Prerequisites")
- Test: `plotter/tests/tst_appshell.cpp`
- Create: `.superpowers/sdd/2026-11-05-plotter-plan4/progress.md`

**Interfaces:**
- Produces: `void applyWindowOptions(QWindow& w, bool fullscreen, QSize size)` in `WindowOptions.h` (inline): fullscreen calls `w.showFullScreen()` and ignores `size`; otherwise resizes when `size.isValid()` and does nothing else. `main.cpp` calls it in place of `window->resize(windowSize)`. Main.qml keeps `visible: true` (the QML tests create Main directly), so the window is already shown when the call happens; `showFullScreen` on a shown window switches it.

- [ ] **Step 1: Failing test** in `tst_appshell.cpp`:

```cpp
void fullscreenIgnoresWindowSize() {
    QWindow w;
    w.show();
    applyWindowOptions(w, true, QSize(300, 200));
    QVERIFY(w.windowState() & Qt::WindowFullScreen);
    QVERIFY(w.isVisible());
    QVERIFY(w.size() != QSize(300, 200) || QGuiApplication::primaryScreen()->size() == QSize(300, 200));
}
void windowSizeAppliesWithoutFullscreen() {
    QWindow w;
    w.show();
    applyWindowOptions(w, false, QSize(300, 200));
    QCOMPARE(w.size(), QSize(300, 200));
    QVERIFY(!(w.windowState() & Qt::WindowFullScreen));
}
```

(`tst_appshell` runs offscreen; the offscreen platform honors `showFullScreen` on the window state. If the first assertion cannot hold there, `QSKIP` with the platform name, as the design allows.)

- [ ] **Step 2: Run** `ctest --test-dir build-plotter -R tst_appshell` → FAIL (header missing).
- [ ] **Step 3: Implement** `WindowOptions.h`; in `main.cpp` add `QCommandLineOption fullscreenOpt("fullscreen", "Show the window full screen (--window is ignored).")` (visible in help), and the "Command line" README bullet. Main.qml: `visible: false`; `applyWindowOptions(*window, cli.isSet(fullscreenOpt), windowSize)` after the window is found. Check `recover()` still shows its own view.
- [ ] **Step 4: GCC 15**: in `build-maplibre-qt.sh` add `-DCMAKE_CXX_FLAGS=-Wno-error=free-nonheap-object` to the cmake line with a comment naming GCC 15.2 and `symbol_bucket.cpp`. README "Prerequisites": an "Ubuntu 26.04" paragraph (GCC 15 and CMake 4.2 work; apt also needs `pipx` and `python3-venv`; `build-essential`, `cmake`, `git` assumed).
- [ ] **Step 5: Run** the two tests and the whole suite → PASS; `plotter/tools/run-dev.sh "" --fullscreen --exit-after-ms 3000` on the dev box starts and exits 0 (WSLg).
- [ ] **Step 6: Ledger**: create `progress.md` with the plan path, branch and base, the ten issues, baseline numbers, and a STATE/NEXT line; append one pointer line to `.superpowers/sdd/2026-10-29-plotter/progress.md` in the `plotter` worktree if that path exists.
- [ ] **Step 7: Commit, push, draft PR**: `feat(plotter): --fullscreen; maplibre builds on GCC 15`. `git push -u origin worktree-plotter-plan4`; `gh pr create --draft` titled "plotter: plan 4 (ten triaged issues, off-boat data kit, fullscreen)", body: one line per issue, `Fixes #46 #41 #40 #39 #34 #32 #31 #30 #28` (#33 by the chartpack PR), a task checklist, the attribution lines from the session instructions.

---

### Task 2: scenarios `navigating`, `fishing`, `fishing-stopped`; `--duration-s`; bounce

Design 5.1. The `everett-pt-townsend` scenario and its tests stay byte-identical.

**Files:**
- Modify: `plotter/tools/synth_n2k.py`, `plotter/tools/test_synth_n2k.py`
- Create: `plotter/tests/fixtures/n2k/navigating.log`, `fishing.log`, `fishing-stopped.log`
- Modify: `plotter/tests/fixtures/n2k/README.md`, `plotter/README.md` ("Dev run": the fixture names)

**Interfaces:**
- Produces: `SCENARIOS` keys `navigating`, `fishing`, `fishing-stopped`; CLI `--duration-s N` (default per scenario); `Track(waypoints, speed, bounce=False)`; module constants below (tests import them).

Constants (exact):
- `T0_DAY = 1798056000.0` (2026-12-23 20:00 UTC, noon PST: the auto palette picks day) for the three new scenarios; `T0` stays for everett.
- `NAV_WAYPOINTS = [(47.9482896, -122.3136073), (47.9021326, -122.3743223), (47.9080896, -122.4492273)]`, `NAV_SPEED = 26 * KN` (13.3756 m/s), default duration 960 s (the route is about 12,460 m, 932 s).
- `FISH_WAYPOINTS = [(47.7441216, -122.4728663), (47.7444076, -122.4562403)]`, `FISH_SPEED = 3 * 0.44704` (1.34112 m/s), default duration 1860 s (two passes of the 1,244 m leg).
- `fishing-stopped`: default 600 s at `FISH_WAYPOINTS[0]`, SOG 0, COG 0, position jitter east `1.2*sin(0.7*s)` m and north `1.2*cos(0.9*s)` m (radius under 1.7 m).
- Bounce: past the route end the boat turns back along the waypoints (fold the distance on `2 * total`), course reversed. `navigating` and `fishing` use `bounce=True`; everett keeps `False`.
- Wander (navigating): heading magnetic `= cog - 0.2731 + 0.03*sin(2*pi*s/7)`, variation 0.2731 east, SOG `= NAV_SPEED + 0.5*KN*sin(2*pi*s/11)`. Fishing: heading `= cog - 0.2731`, SOG constant.
- Depth: navigating by route fraction f (distance along the route over its length, folded by bounce), linear through `[(0, 8), (0.3, 90), (0.55, 120), (0.8, 20), (1.0, 60)]` m plus `0.3*sin(2*pi*s/5)`; fishing `27.5 + 12.5*cos(2*pi*f) + 0.2*sin(2*pi*s/8)` (15 to 40 m); stopped 12 m flat. Offset -0.3 m everywhere.
- Water temp: navigating 283.15 K, fishing and stopped 284.15 K, every 2 s.
- AIS: navigating reuses the everett three (factor the target loop into `ais_targets(emit, own, duration, names)`), laid along the own track's first leg. Fishing: one class A, MMSI 367000011, "TEST FERRY", starts at `offset_position(FISH_WAYPOINTS[0], 800, 2000)`, course 200 deg true, 12 kn, every 10 s, static 129794 every 60 s. Stopped: none.
- Cadence as everett: 129025, 129026, 127250, 128267 at 1 Hz; no dropouts in the new scenarios.

- [ ] **Step 1: Failing tests** in `test_synth_n2k.py` (a second replay class per scenario, same `generate()` with `--scenario`):
  - `test_everett_unchanged`: `generate("everett-pt-townsend")` equals the committed fixture bytes.
  - `NavigatingTest.test_speed_and_waypoints`: SOG near 60 s within 0.3 m/s of `NAV_SPEED`; first position within 1e-6 of `NAV_WAYPOINTS[0]`; some position after 500 s is within 50 m of `NAV_WAYPOINTS[1]` (passes the turn).
  - `NavigatingTest.test_heading_wanders`: headings over 60 s span at least 2 deg and under 5 deg.
  - `NavigatingTest.test_depth_profile`: depth at s=0 within 1 m of 8; max depth over the run above 110.
  - `NavigatingTest.test_bounce_keeps_the_boat_on_route`: with `--duration-s 2400`, every position stays within 200 m of the route's segments (point-to-segment distance in flat-earth meters).
  - `FishingTest.test_trolls_back_and_forth`: SOG within 0.05 of 1.34112; longitude is monotonic increasing until about 927 s then decreasing; depth within [14.5, 40.5].
  - `FishingTest.test_one_ais_target`: exactly one MMSI, 367000011, class A, name "TEST FERRY".
  - `StoppedTest.test_stays_within_3_m_with_sog_zero`: every position within 3 m of `FISH_WAYPOINTS[0]`, every SOG 0.
  - `test_duration_override`: `--duration-s 30` gives a log whose last timestamp is under T0_DAY + 31.
- [ ] **Step 2: Run** `N2KD=build/n2kd/n2kd python3 -I plotter/tools/test_synth_n2k.py` → FAIL (unknown scenario).
- [ ] **Step 3: Implement** as specified; `--duration-s` overrides `DURATION_S` per scenario; `main()` picks `T0_DAY` for the new scenarios.
- [ ] **Step 4: Run** the tests → PASS. Generate the three fixtures with the README's command (`--scenario X --out plotter/tests/fixtures/n2k/X.log`); run `generate` twice and `cmp` → identical. Sizes under 500 KB each.
- [ ] **Step 5: README** (fixtures): one section per scenario with origin "generated", the regenerate command, the owner's waypoints (2026-11-05) and the speed; `plotter/README.md` "Dev run": `run-dev.sh plotter/tests/fixtures/n2k/navigating.log` example.
- [ ] **Step 6: Commit**: `feat(plotter): navigating and fishing synth scenarios (26 kn, 3 mph), --duration-s`.

(Controller: after Tasks 1 and 2 are pushed, hand the laptop its pull, build and fullscreen run of both scenarios.)

---

### Task 3: `relocate_n2k.py`

Design 5.3.

**Files:**
- Create: `plotter/tools/relocate_n2k.py`, `plotter/tools/test_relocate_n2k.py`
- Modify: `plotter/CMakeLists.txt` (add the test beside `synth_n2k`), `plotter/tests/fixtures/n2k/README.md` (OpenSkipper paragraph), `plotter/README.md` ("Dev run": one line)

**Interfaces:**
- CLI: `relocate_n2k.py IN OUT --to LAT,LON [--rotate DEG] --canboat PATH`. Reads candump `-L` (`(ts) iface ID#HEX`) and canboat RAW (`ts,prio,pgn,src,dst,len,b0,...`, timestamp `YYYY-MM-DD-HH:MM:SS.mmm` or `...THH:MM:SS.mmmZ`); writes candump `-L` with the input timestamps (RAW timestamps become epoch seconds, UTC).
- Functions (importable): `read_frames(path) -> list[(ts, can_id, bytes)]`, `reassemble(frames) -> list[Message(ts, can_id, src, pgn, payload, frame_indexes)]` (fast packets by (src, pgn) and sequence; single frames as is), `transform(lat, lon, origin, to, rotate_deg) -> (lat, lon)` (translate so `origin` lands on `to`, then rotate about `to` by `rotate_deg` clockwise in flat-earth meters), `relocate(messages, to, rotate_deg, canboat) -> list[frame]`.
- Position fields by canboat `BitOffset`/`BitLength`/`Resolution` of `latitude` and `longitude`: 129025 and 129038, 129039 (int32, 1e-7), 129029 (int64, 1e-16). A field whose raw value is the not-available pattern (all ones unsigned, or the signed maximum) passes through unchanged. The origin is the first 129025 or 129029 position in the file.

- [ ] **Step 1: Failing tests** (`test_relocate_n2k.py`, unittest, imports the module):
  - `test_raw_line_with_z_timestamp_parses`: one hand-written RAW line `2020-08-22T13:52:52.882Z,2,129025,1,255,8,...` reads as one frame with the epoch of that instant.
  - `test_transform_translate_and_rotate`: `transform(47.0, -122.0, (47.0, -122.0), (48.0, -123.0), 0)` is `(48.0, -123.0)`; a point 1000 m north of the origin rotated 90 deg lands 1000 m east of `to` within 1 m.
  - `test_not_available_positions_pass_through`: a 129025 payload of all ones relocates to the same bytes.
  - `test_relocated_navigating_matches_n2kd` (skipped without `N2KD`): relocate `navigating.log` to `47.7441216,-122.4728663`, no rotation; frame count equal; n2kd `--speed 0 --stdout` on both: the same number of vessel lines; for each pair `pos` differs by the translation within 1e-6 deg, and `t`, `sog`, `cog`, `hdg`, `depth`, `waterTemp` are equal; AIS targets' positions shift by the same vector.
- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement**; CMake `add_test(NAME relocate_n2k ...)` with `N2KD` like `synth_n2k`.
- [ ] **Step 4: Run** `ctest -R relocate_n2k` → PASS.
- [ ] **Step 5: README** paragraph: OpenSkipper `Kees NMEA2000 Sample.log` (IJsselmeer 2009, canboat RAW with `Z`), its URL, the CC BY-SA 3.0 reason it is not committed, and the relocate command to put it on Possession Sound.
- [ ] **Step 6: Commit**: `feat(plotter): relocate_n2k.py moves a recorded log onto the charts`.

---

### Task 4: MarineCadastre AIS fixture and the `ais-density` scenario

Design 5.2.

**Files:**
- Create: `plotter/tools/extract_ais.py` (needs pyarrow; run once), `plotter/tests/fixtures/ais/puget-2024-07-13.csv`, `plotter/tests/fixtures/ais/README.md`
- Modify: `plotter/tools/synth_n2k.py` (`ais-density`), `test_synth_n2k.py`, `THIRD_PARTY_NOTICES` (a data section), `plotter/README.md`

**Interfaces:**
- `extract_ais.py --parquet FILE --bbox W,S,E,N --start ISO --end ISO --out CSV [--thin-s 20]`: columns `mmsi,t,lat,lon,sog_kn,cog,heading,name,type,length,cls` (`cls` from `TransceiverClass`); one row per vessel per `--thin-s` seconds; `t` as seconds from `--start`.
- Builder picks: file `ais-2024-07-13.parquet` (a Saturday), bbox `-122.55,47.70,-122.25,48.00`, the busiest 30 minutes of 20:00 to 22:00 UTC, thinned until the CSV is under 300 KB. The README records the exact window, the citation (Martin, Brass, Dornback, Fontenault, 2025, Nationwide Automatic Identification System 2024, NOAA Office for Coastal Management), the URL, CC0 1.0, and the extract command.
- `ais-density` scenario: own ship is `fishing`; each CSV row at `T0_DAY + t` as 129038 (cls A) or 129039 (cls B) from source 2 with `userId`, position, `sog`, `cog`, `heading` (omit a field whose CSV value is empty or 511 for heading); the first row of each vessel also sends 129794 (A, `name`, `typeOfShip`) or 129809 (B, `name`). CSV path `--ais-csv`, default the fixture.

- [ ] **Step 1: Failing test** `AisDensityTest.test_real_traffic_plays`: n2kd sees at least 20 distinct MMSIs, at least one class B, and the own ship SOG is the fishing speed; `test_density_deterministic` (two generations identical).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Extract** (pyarrow in a scratch venv under the scratchpad, never committed), **implement** the scenario, write the README and the NOTICES section ("MarineCadastre AIS 2024 extract, CC0 1.0, plotter/tests/fixtures/ais/").
- [ ] **Step 4: Run** → PASS; `du -h` of the CSV under 300 KB.
- [ ] **Step 5: Commit**: `feat(plotter): ais-density scenario from a MarineCadastre CC0 extract`.

---

### Task 5: recorder time rules on the monotonic clock; store order by rowid; dock tracks (#34)

Design 6 (#34 time sync, dock tracks).

**Files:**
- Modify: `plotter/src/core/Tracks.h`, `Tracks.cpp`
- Test: `plotter/tests/tst_tracks.cpp`
- Modify: `plotter/README.md` (Settings: "Track points are kept ... measured on a steady clock, so a GPS or NTP step neither splits nor stalls a track"; a track closed with fewer than two points is deleted)

**Interfaces:**
- `TrackRecorder`: `m_lastPosS` and `m_lastKeptS` (monotonic seconds) replace `m_lastPosT` and the `p.t - m_last->t` interval test; point times stay `s.t`. New private `void closeTrack()`: `flush()`, then if `m_active != 0 && m_activePoints.size() < 2` call `m_store.remove(m_active)`; called from `startTrack` (before `create`), `recordingChanged` (off) and `~TrackRecorder`.
- `TrackStore::points` orders `BY rowid`; `TrackStore::list` keeps `ORDER BY started DESC, id DESC`.

- [ ] **Step 1: Failing tests** (the `Rig` keeps `now`; these set `now` and the vessel time apart):
  - `clockStepBackwardKeepsOneTrackAndKeepsStoring`: feed 60 s moving; then vessel time jumps back 3600 s while `now` advances 1 s per update for 60 more updates; one track, points stored ≈ 24 (12 per minute).
  - `clockStepForwardKeepsOneTrack`: vessel time jumps forward 3600 s mid-run; one track.
  - `drawnOrderIsRecordedOrder`: with the backward step, `points(id)` equals the fed order (the second half has earlier `t` than the first).
  - `monotonicGapStartsASecondTrack`: `now` advances 601 s between two updates with vessel time advancing 1 s: two tracks (the existing `gapOf601SecondsStartsASecondTrack` stays and still passes since its clock follows).
  - `trackClosedWithOnePointIsDeleted`: (a) recording on, one fix, recording off: zero tracks; (b) two starts at the dock (one fix, 601 s monotonic gap, one fix): zero tracks after the second start; (c) two kept points then off: one track kept; (d) destroy the recorder after one fix: zero tracks.
  - `stoppedBoatLeavesNoTrack`: jittering position under 3 m (as `fishing-stopped`) for 600 s then recording off: zero tracks.
- [ ] **Step 2: Run** `ctest -R tst_tracks` → FAIL.
- [ ] **Step 3: Implement**; update the header comments (the `nowS` comment: "for the write interval, the point interval and the new-track gap").
- [ ] **Step 4: Run** `tst_tracks` and `tst_qml` → PASS (the tracks page tests use the fixture recorder).
- [ ] **Step 5: Commit**: `fix(plotter): recorder time rules on the monotonic clock; dock tracks deleted (#34)`.

---

### Task 6: SIGTERM and SIGINT flush (#34)

**Files:**
- Create: `plotter/src/core/SignalBridge.h`, `SignalBridge.cpp`, `plotter/tests/tst_signalbridge.cpp`
- Modify: `plotter/CMakeLists.txt` (source, test), `plotter/src/app/main.cpp`

**Interfaces:**
- `class SignalBridge : public QObject { public: explicit SignalBridge(std::initializer_list<int> signals, QObject* parent = nullptr); ~SignalBridge(); signals: void signalled(int signo); }`: a `socketpair(AF_UNIX, SOCK_STREAM)`, a C handler that writes the signal number as one byte, a `QSocketNotifier` that reads it and emits. The destructor restores the previous handlers. `main.cpp`: `SignalBridge signals{SIGINT, SIGTERM}; connect(&signals, &SignalBridge::signalled, &app, [] { QCoreApplication::quit(); });` declared after the recorder so `~TrackRecorder` runs after the loop exits (it already does).

- [ ] **Step 1: Failing test** `sigtermFlushesBufferedPoints`: a store, settings, recorder (interval 1, min distance 0) with 3 fixes fed (buffered, not written); `SignalBridge b{SIGTERM}; QEventLoop loop; connect(&b, &SignalBridge::signalled, &loop, &QEventLoop::quit); raise(SIGTERM); loop.exec();` then destroy the recorder and `QCOMPARE(points stored, 3)`. Second test `sigintIsReported`: the signal argument is `SIGINT`.
- [ ] **Step 2: Run** → FAIL (missing class).
- [ ] **Step 3: Implement**; wire `main.cpp`.
- [ ] **Step 4: Run** `tst_signalbridge` → PASS; manual: `run-dev.sh plotter/tests/fixtures/n2k/navigating.log --record`, Ctrl-C after 20 s, reopen the data dir with `sqlite3` and count `track_points` (at least 15).
- [ ] **Step 5: Commit**: `feat(plotter): SIGTERM and SIGINT quit cleanly so buffered track points are written (#34)`.

---

### Task 7: `Store::moveAside` one stamp, result from any move (#39)

**Files:**
- Modify: `plotter/src/core/Store.cpp` (`moveAside`), `Store.h` comment
- Test: `plotter/tests/tst_store.cpp`

- [ ] **Step 1: Failing tests**: `moveAsideOnlyWalSetsResult` (only `plotter.db-wal` exists: result is the stamp path `plotter.db.bad-...` and `-wal` was renamed to `<stamp>-wal`); `moveAsidePartialErrorNamesBoth` (main and `-wal` exist, the rename seam fails for `-wal`: error text contains `plotter.db was moved to <stamp>` and `plotter.db-wal could not be moved aside`; the main file is at `<stamp>`). Keep the existing moveAside tests passing.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**: `result = moved` once any file is renamed; the partial error names the files moved so far by suffix.
- [ ] **Step 4: Run** `tst_store` → PASS. **Step 5: Commit**: `fix(plotter): moveAside reports any moved file; partial move names both (#39)`.

---

### Task 8: `FieldText` enum, one style parse, `connectAppInfo` (#40)

**Files:**
- Modify: `plotter/src/core/Slots.h`, `Slots.cpp`, `ViewDraft.cpp` (callers), `tests/tst_slots.cpp`
- Modify: `plotter/src/core/ChartController.h`, `ChartController.cpp`, `tests/tst_chartcontroller.cpp`
- Modify: `plotter/src/core/AppInfo.h`, `AppInfo.cpp`, `src/app/main.cpp`, `tests/tst_appshell.cpp`

**Interfaces:**
- `enum class FieldText { Value, Unit }; QString fieldRoleText(Field, FieldText, const VesselModel&, const Settings&);`
- `ChartController`: `QHash<QString, QJsonObject> m_styles;` keyed `styleName(mode, palette)`; the constructor's `styleProblem` becomes `std::expected<QHash<QString, QJsonObject>, QString> readStyles(mode, charts, bathy, depths)` and the accepted packs' styles go into `m_styles`; `loadStyle` takes `m_styles.value(name)` and keeps its warning when the name is missing.
- `void connectAppInfo(N2kClient& client, AppInfo& info)` in `AppInfo.h`: the two `QObject::connect` lines now in `main.cpp`.

- [ ] **Step 1: Failing tests**: tst_slots `fieldRoleTextValueAndUnit` (Depth with a 3 m fix: Value `"9.8"`, Unit `"ft"`); tst_chartcontroller `stylesAreReadOnceAtStart` (build the controller on a temp pack, delete `styles/nav-night.json`, `setPalette("night")`: `styleLoaded` arrives and the fake map's style JSON names `nav night`); tst_appshell `connectAppInfoForwardsDaemonSignals` (`N2kClient c("/nonexistent"); AppInfo i({}); connectAppInfo(c, i); emit c.daemonVersion("1.2.3"); QCOMPARE(i.daemonVersion(), "1.2.3"); emit c.schemaMismatch(2); QVERIFY(i.schemaMismatch()); emit c.daemonVersion("1.2.3"); QVERIFY(!i.schemaMismatch());`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** all three. **Step 4: Run** `tst_slots tst_chartcontroller tst_appshell tst_qml` → PASS.
- [ ] **Step 5: Commit**: `refactor(plotter): FieldText enum, styles parsed once, connectAppInfo (#40)`.

---

### Task 9: schema 1.2.0, `favorite` key and identifiers, plan 3 slot extras (#32)

**Files:**
- Modify: `plotter/src/core/Store.h` (`kSchemaVersion{1, 2, 0}`), `Store.cpp` (migration), `Views.h`, `Views.cpp`, `ViewsModel.h`, `ViewsModel.cpp`, `ViewDraft.h`, `ViewDraft.cpp`, `src/qml/PanelMath.h`, every `plotter/qml/*.qml` and `plotter/tests/**` that names `favourite`, `plotter/README.md` (Views section and schema paragraph), `docs/superpowers/review-checklist.md` (drop the identifier and stored key exceptions)
- Test: `plotter/tests/tst_store.cpp`, `tst_views.cpp`

**Interfaces:**
- `View::favorite`; `viewToJson` writes `"favorite"`; `viewFromJson` reads `"favorite"`, else the legacy `"favourite"`; `kKnownKeys` lists both. Migration `{1,2,0}`: `SELECT id, json FROM views`, each row `UPDATE views SET json = viewJsonText(viewFromJson(parsed))` (unparseable json is left alone with a warning). `viewsFromPlan3` carries each plan 3 slot object's unknown keys into that `ViewSlot::extra` (first entry per id wins).
- Renames: `favouriteCapacity` → `favoriteCapacity` (free function, `PanelMath`, `ViewsModel` property and methods), `setFavourite` → `setFavorite`, `FavouriteRole` → `FavoriteRole` with role name `"favorite"`, `ViewDraft::favourite` → `favorite` (property, setter, signal), QML properties and signals (`ViewTile.favorite`, `TileMenu.favorite`, `favoriteChosen`), test names.

- [ ] **Step 1: Failing tests**: tst_store `favouriteKeyBecomesFavoriteAt120` (open a fresh store, then with a plain `QSqlDatabase` set `schema_version` to 1,1,0 and one view's json to contain `"favourite":true` and no `"favorite"`; reopen: `schemaVersion()` is 1.2.0, the json has `"favorite":true` and no `"favourite"`); `plan3SlotExtrasSurviveMigration` (the 1.0.0 fixture of `plan3DatabaseIsMigrated` with a slot entry `{"id":"TL","on":true,"field":"depth","size":"large","note":"x"}`: after open the Navigation view's TL slot json has `"note":"x"`); `a120FileIsLeftAlone` (reopen a 1.2.0 store: json text unchanged). tst_views `favoriteKeyRoundTrip` (`viewToJson` has `favorite`, not `favourite`; `viewFromJson({"favourite": true})` gives `favorite == true`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**, then the rename sweep: `grep -rn avourite plotter/ docs/superpowers/review-checklist.md` must list only the legacy read in `Views.cpp` and its comment.
- [ ] **Step 4: Run** the whole suite → PASS. README: the JSON example key and "Schema 1.2.0 renames the stored key `favourite` to `favorite` and rewrites every view row once".
- [ ] **Step 5: Commit**: `feat(plotter): views schema 1.2.0 (favorite key); plan 3 slot extras kept (#32)`.

---

### Task 10: AIS sheet in the free area, wrapped rows, paging; third size (#41)

Design 6 (#41) and 12.

**Files:**
- Modify: `plotter/qml/AisSheet.qml`, `plotter/qml/ChartPage.qml`, `plotter/tests/qml/Helpers.js`, `plotter/tests/qml/tst_pages.qml` (and every `_data` test using `H.sizes()` in `tst_pages.qml`, `tst_editor.qml`, `tst_views.qml`: set `Units.diagonalIn = data.diagIn`), `plotter/tests/tst_chartcontroller.cpp`

**Interfaces:**
- `H.sizes()` returns three entries: `{tag, w, h, ppm, diagIn}` with `1920x1280, ppm 6.988, diagIn 13` added; the old two carry `diagIn: 10.1`.
- `ChartPage` exposes `readonly property rect aisFreeRect`: x from `cornerArea.x` to `cornerArea.x + cornerArea.width` (bars and strip already excluded), y from `max(TL.bottom, TR.bottom of the on corners, cornerArea.y) + margin` to `min(BL.top, BR.top of the on corners, cornerArea bottom) - margin`.
- `AisSheet`: `property rect freeRect`; `width = max(min(freeRect.width, Units.mm(90)), Units.mm(60))`, centered horizontally in `freeRect`, `y = freeRect.y`; `height = min(content, freeRect.height)`. Rows are one `Label` each, text `"<label>: <value>"`, `wrapMode: Text.WordWrap`, `font.pixelSize: Units.mm(4)`. Rows are laid in pages: a page holds the consecutive rows whose heights fit above the footer. Footer: `Close` (right), and when `pageCount > 1` a `Label` `"<page> of <pageCount>"` (objectName `aisPageLabel`) between two 12 mm `BigButton`s `"<"` and `">"` (objectNames `aisPrev`, `aisNext`, disabled at the ends). `property int page: 0`, `readonly property int pageCount`.

- [ ] **Step 1: Failing tests** (tst_pages): `test_aisSheetNeverCoversASlot_data() { return H.sizes() }`: a chart page with the draft's eight slots on at their default sizes (`fixture.draft.setSlot(id, true, field, 25 for TL and TR, 14 for the others, 8 for Top and Bottom)`), `chartStub.aisSelection` set to an eight-field map with a 24-character name; for each on slot `verify(!H.overlaps(sheet, slot, page))`; sheet inside the page. `test_aisSheetPagesReachEveryRow`: at 1024x600 with the same setup `pageCount >= 2`; collect the visible row texts, tap `aisNext` until disabled; every one of the eight labels was seen once; `aisPrev` returns to page 0. `test_aisSheetWrapsALongValue`: a 40-character name produces a row taller than one line. tst_chartcontroller `targetAtPicksTheNearerOfTwoCloseTargets`: two targets whose screen points are 30 px apart (fake map `toScreen` by a fixed scale); `targetAt` 5 px from the first within radius 37 px (8 mm at 4.626 px/mm) returns the first.
- [ ] **Step 2: Run** `tst_qml tst_chartcontroller` → FAIL.
- [ ] **Step 3: Implement**. Extending `H.sizes()` may change answers of existing size-parameterized tests at 1920x1280 (tab capacity, bar fits): fix the expectation only where the third size legitimately differs, and say so in the ledger.
- [ ] **Step 4: Run** `tst_qml` → PASS at all three sizes.
- [ ] **Step 5: Commit**: `feat(plotter): AIS sheet lives between the corner rows, wraps and pages (#41); 1920x1280 test size`.

---

### Task 11: review minors carried past PR #27 (#28)

Twelve bullets; each gets a test or a ledger reason.

**Files:**
- Modify: `plotter/src/core/Views.cpp` (1, 2), `ViewsModel.cpp` (1, 4, 5), `ViewDraft.cpp` (3), `plotter/qml/Keyboard.qml` (1), `LayoutGallery.qml` (8), `Main.qml` (9), `src/app/main.cpp` (10, 12), `src/core/AppInfo.h/.cpp` (10), `src/core/ChartController.h/.cpp` (12), the Tabler icon tint site (6; `grep -rn currentColor plotter/src plotter/qml`), `plotter/README.md` (10, 12), tests named below

- [ ] **Step 1: Failing tests**:
  1. tst_views `whitespaceOnlyNameIsFloored` (`viewFromJson({"name": "   "}).name == "View"`); tst_viewsmodel `saveFloorsWhitespaceName`; tst_editor `test_keyboardDoneDisabledForWhitespace` (type three spaces: `key-done` disabled).
  2. none (one constant; compile).
  3. tst_viewsmodel `loadIgnoresASlotWithAnOutOfRangeId` (construct a `View` whose `slotList` has an id cast from 9: no crash, eight slots).
  4. none; ledger line (log text only).
  5. tst_viewsmodel `saveUnchangedEmitsNoDataChanged`, `addNonFavoriteEmitsNoTabViewsChanged` (`QSignalSpy`).
  6. none: a one-line comment at the tint site.
  7. none: a comment on `test_sideBarsClearTheBannersOnASmallPanel` naming R66 and the C++ tests that isolate it.
  8. tst_editor `test_galleryRowsFillTheWidth_data() { return H.sizes() }`: the first row's last thumbnail right edge is within 1 px of the Flow's width; columns = `floor((width + spacing) / (minThumbW + spacing))`, thumb width `(width - (columns - 1) * spacing) / columns`, height = width / 1.6.
  9. `test_mainInitialEditorAndSheet` already waits; add `test_initialEditorOpensAfterFirstFrame`: `main.editorOpen = true` then `tryVerify(main.editing)` with no `wait(300)`. Implementation: replace the 300 ms `Timer` with a one-shot `Connections` on `root.frameSwapped` that calls `Qt.callLater(root.openInitialEditor)`.
  10. tst_appshell `platformProblemNamesOffscreen`: `platformProblem("offscreen")` and `("minimal")` return `"renders need a GL display: QT_QPA_PLATFORM <name> cannot draw the chart"`; `platformProblem("xcb")` and `("wayland")` return empty. `main.cpp` prints it with `qCritical` and returns 1 before creating the map.
  11. tst_views `test_touchDragFromTabDoesNotPanTheMap`: the touch twin of `test_dragFromTabDoesNotPanTheMap` using `touchEvent(main).press(0, tab, x0, y0).commit()`, moves, release; same assertions.
  12. tst_chartcontroller `startPositionCentersTheMapWithoutAFix`: `chart.setStartPosition(47.98, -122.23)`; after `styleLoaded` the fake map's camera center is that point; a later vessel fix wins. `main.cpp`: hidden `--position LAT,LON` (regex `^(-?\d+(\.\d+)?),(-?\d+(\.\d+)?)$`, else exit 2). README "Dev run": `--position`, and the tall-window recipe for the Settings and Legend renders (`--window 1024x1400`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** each. **Step 4: Run** the whole suite → PASS.
- [ ] **Step 5: Ledger**: one line per bullet (fixed with test X, or closed with reason). **Commit**: `fix(plotter): review minors carried past PR #27 (#28)`.

---

### Task 12: start time line; gallery and keyboard behind a Loader, measured (#30)

**Files:**
- Modify: `plotter/src/app/main.cpp` (ready line), `plotter/qml/SetupSheet.qml` (Loaders), `plotter/tests/qml/tst_editor.qml`

**Interfaces:**
- `main.cpp`: a `QElapsedTimer` started first in `main`; on the window's first `frameSwapped` `qInfo().noquote() << QStringLiteral("ready in %1 ms").arg(ms)`. Always on.
- `SetupSheet.qml`: `Keyboard` and `LayoutGallery` inside `Loader { active: sheet.everOpened }` with `property bool everOpened: false` set true in `onVisibleChanged` when visible; `editText` and `openGallery` go through `loader.item`.

- [ ] **Step 1: Failing test** `test_setupKeyboardAndGalleryWorkOnFirstOpen`: open the editor's Setup on a fresh Main, `editText("name")` shows the keyboard and typing works; `openGallery()` shows 72 thumbnails. (Existing gallery and keyboard tests keep passing through `H.byName`.)
- [ ] **Step 2: Run** → FAIL only if the Loader breaks lookups; otherwise it passes before and after (the test still guards the Loader).
- [ ] **Step 3: Implement** the ready line first and commit it (`feat(plotter): "ready in N ms" at the first frame`). Then the Loader as a second commit (`perf(plotter): gallery and keyboard load on first Setup open (#30)`).
- [ ] **Step 4: Measurement (controller, laptop)**: five starts each of the two commits (`cheekyplotter ... --exit-after-ms 9000 2>&1 | grep "ready in"`), median of each. Bar (design): keep the Loader if it saves 200 ms or 10 percent of the start, whichever is less; otherwise `git revert` the Loader commit and keep the test. Ledger gets the ten numbers and the decision.

---

### Task 13: active track write cost and frame time (#46)

**Files:**
- Modify: `plotter/tests/tst_chartcontroller.cpp`, `plotter/src/app/main.cpp` (`--frame-stats`), `plotter/README.md`; conditionally `plotter/src/core/ChartController.h/.cpp`

**Interfaces:**
- Hidden `--frame-stats`: records `frameSwapped` intervals from the first frame; at quit prints `frame-stats: frames N max M ms p99 P ms over50 K`.
- Test `activeTrackWriteCostAt7200Points`: a track of 7200 points along the navigating route (1 s at 26 kn is 13.4 m apart); `QElapsedTimer` around one `setActiveTrack`; the fake map records the GeoJSON byte size; `qInfo` prints `active-track write: X ms, Y bytes`; assert under 50 ms (a CI safety net, not the bar).
- If over the bar (design: call time 4 ms or any frame over 50 ms attributable to a write): `ChartController::setActiveTrack` coalesces: writes at once when the last write was 2 s or more ago (and always for a track of one point after an empty one), otherwise arms a single-shot `QTimer` for the remainder; `flushActiveTrack()` on style load. Test `activeTrackWritesAtMostEveryTwoSeconds`: 3600 points fed 1 s apart on a fake clock produce at most 1801 writes and the last write holds every point.

- [ ] **Step 1**: the measurement test and `--frame-stats` (TDD on the option: tst_appshell `frameStatsSummary` on a pure function `frameStatsLine(const QList<qint64>& intervalsMs)` in `WindowOptions.h` returning the line above).
- [ ] **Step 2 (controller, laptop)**: `python3 -I plotter/tools/synth_n2k.py --canboat third_party/canboat/canboat.json --scenario navigating --duration-s 7200 --out /tmp/nav2h.log`; `n2kd --replay /tmp/nav2h.log --speed 20`; the plotter with `--record --frame-stats --exit-after-ms 380000` and settings `trackIntervalS 1`, `trackMinDistanceM 1` written in its data dir; record the test's `active-track write` line from the laptop's ctest run and the `frame-stats` line.
- [ ] **Step 3**: both under the bars: close with the numbers (ledger and PR). Either over: implement the coalescing with its test; commit `perf(plotter): active track written at most every 2 s (#46)`.

---

### Task 14: `tst_qml` stress run on the laptop (#31)

Controller task, no code. The laptop runs `ctest --test-dir build-plotter -R tst_qml --repeat until-fail:10 --output-on-failure 2>&1 | tee /tmp/tst_qml-stress.log; echo EXIT=${PIPESTATUS[0]}` and reports the exit status and the log. Clean: attach the log to #31 (`gh issue comment 31 --body-file`), note "a CI flake reopens it", the PR closes it. A failure: a fix task is added to this plan.

---

### Task 15: chartpack night palette red-only, `restyle`, renders (#33, own PR)

Own branch `chartpack-night` from origin/main, own worktree (an agent with `isolation: worktree`), own PR on the chartpack workstream; `chartpack-ci` must pass.

**Files:**
- Modify: `chartpack/src/chartpack/style/palette.py` (`_NIGHT`), `chartpack/tests/test_style_palette.py`
- Create: `chartpack/src/chartpack/pack/restyle.py`, `chartpack/tests/test_pack_restyle.py`
- Modify: `chartpack/src/chartpack/cli.py` (`restyle` subcommand), `chartpack/README.md`

**Interfaces:**
- `_NIGHT` (every channel but red at most 0x20): `DEPDW #000000, DEPMD #140000, DEPMS #260000, DEPVS #3A0000, DEPIT #301010, LANDA #180404, LANDF #200808, CSTLN #700000, CHBLK #C00000, CHGRD #700000, CHMGD #900000, CHWHT #E00000, SNDG1 #E00000, SNDG2 #900000, LITRD #FF0000, LITGN #A00000, LITYW #C00000, NINFO #B00000, OUTLW #C00000, DNGHL #FF0000, ADINF #400000, RESBL #500000, TRFCD #600000, NODTA #080000`. Hazard sprites follow (baked from CHBLK and DNGHL); SDF icons take `icon-color` from the palette.
- `chartpack restyle PACKDIR`: rewrites `styles/*.json` and `sprites/` from the current code (nav styles for a charts pack with the manifest's safety contour, fish styles for a bathy pack), then rewrites `manifest.json` hashes; version unchanged. `chartpack check` passes afterwards.

- [ ] **Step 1: Failing tests**: `test_night_is_red_only` (every night token: G and B at most 0x20), `test_night_depth_fills_brighten_toward_shallow` (luminance strictly increasing DEPDW to DEPVS); update `test_owner_water_and_land_colours` and `test_night_water_is_dark` to the new values (night leans red). `test_restyle_rewrites_styles_and_manifest`: on the test pack fixture, change a palette color in a monkeypatch, run `restyle`, the style file has the new color and `check` passes.
- [ ] **Step 2: Run** `.venv/bin/pytest -q` → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `chartpack-ci` has a style validation step (gl-style-validate): keep it green.
- [ ] **Step 5: Renders**: on the dev box packs (`chartpack/work`), `restyle` both, then `chartpack render work/charts/charts-puget-north-1.0.0 work/bathy/bathy-puget-north-1.0.0 --views regions/puget-north.toml --styles nav-night,fish-night --out renders`; attach `everett` and `jeff-head` z13 PNGs to the PR. README: a "Night" paragraph (red-only, judged in a dark room) and `restyle` in the command list.
- [ ] **Step 6: Commit and PR**: `feat(chartpack): red-only night palette; restyle subcommand (#33)`; PR body with the renders, `Fixes #33`, and the laptop recipe: `git pull`, `.venv/bin/chartpack restyle ~/cm-packs/charts-puget-north-1.0.0` and the bathy pack, then `run-dev.sh ... --palette night` in a dark room. The owner's verdict goes in the ledger before merge.

---

### Task 16: `CM_PLOTTER_TESTS` option; full license texts (#34)

**Files:**
- Modify: `plotter/CMakeLists.txt`, `plotter/README.md` ("Configure, build, test": the option), `THIRD_PARTY_NOTICES`
- Create: `plotter/tools/check_notices.py`

**Interfaces:**
- `option(CM_PLOTTER_TESTS "Build the plotter tests (needs Qt Test and QuickTest)" ON)`; `find_package(Qt6 ... COMPONENTS Core Gui Network Sql Quick QuickControls2 Svg)` plus `if(CM_PLOTTER_TESTS) find_package(Qt6 REQUIRED COMPONENTS Test QuickTest) endif()`; every `plotter_add_test`, `tst_qml` and the Python tests inside `if(CM_PLOTTER_TESTS)`.
- `check_notices.py`: exits 1 unless every `License:` line in the plotter section names a license whose full text heading exists in the file; the set of names is the heading list it prints. Added as `add_test(NAME notices ...)`.
- Texts to append once each, with a pointer from each component: BSD-2-Clause (maplibre-native-qt, MapLibre Native, protozero), ICU, MIT (nunicode, csscolorparser, RapidJSON, unordered_dense, mlt-cpp), curl, Apache-2.0 (FastPFOR), BSD-3-Clause (PMTiles, variant, mapbox-base), ISC, BSL-1.0, Zlib. Sources: `$HOME/.cache/cheekymarine/maplibre-native-qt/src` and its `vendor/` trees (the dev box has the checkout); the OFL and Tabler MIT are already pointed at files.

- [ ] **Step 1**: `check_notices.py` fails on the current file (names without texts). **Step 2**: append the texts; it passes. **Step 3**: configure a second tree `build-plotter-notests` with `-DCM_PLOTTER_TESTS=OFF`, build `cheekyplotter`, `ctest` lists no plotter tests; the normal tree still runs them all. (Controller: the laptop repeats the OFF build.)
- [ ] **Step 4: Commit**: `build(plotter): CM_PLOTTER_TESTS option; full third-party license texts (#34)`.

---

### Task 17: renders at three sizes, docs, merge gate

- [ ] **Step 1: Renders** (`plotter/README.md` recipe, `CM_PACKS_DIR` set to the dev box packs, `--screenshot-after-ms 7000 --exit-after-ms 8000`): at 1024x600, 1280x800 (panel 10.1) and 1920x1280 (panel 13: write `panelDiagonalIn` 13 into the run's data dir first, or add `--panel-in` as a hidden dev option if that is simpler, documented): `ais-<pal>-<size>` (`--sheet ais`, `navigating.log`), `gallery-<pal>-<size>`, `settings-<pal>-1024x1400` and `legend-<pal>-1024x1400` (tall), `nodata-<pal>-<size>` with `--position 47.98,-122.23` and no n2kd, day and night. Replace the old files of the same names under `docs/plotter/renders/views/`; README render list updated.
- [ ] **Step 2: Laptop results in the ledger**: fullscreen screenshot (grim), #30 and #46 numbers, #31 log, tests-off build, `ais-density` run at the three window sizes with a target selected, and the #33 dark-room verdict.
- [ ] **Step 3: Review**: one adversarial reviewer on the whole branch posts its own PR review (COMMENT, inline); adjudicate; fix wave; re-review ADDRESSED; resolve threads one by one; `plotter-ci` green.
- [ ] **Step 4: Issues**: the PR body's `Fixes` list is complete; any part that needed the boat is split into its own issue with a reference back (none expected). Mark the PR ready for the owner.
