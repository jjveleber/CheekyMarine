# plotter: fix-next set (2026-11-01 triage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the eight issues the owner labeled `triage: fix next` on 2026-11-01 (#44, #37, #38, #43 items 1 to 3, #35, #45, #29, #36) in one plotter PR, each with its own test.

**Architecture:** Nothing structural changes. Eight independent fixes: one CI cache key, one Python test tool, two C++ cores (`N2kParse` docs, `Tracks` totals and visibility), three QML pages (`CellPage`, `LockOverlay`, `SlotView`) and a spelling sweep of strings and docs. Each task is a reviewer gate on its own: the ordering below puts the CI change first (so the PR's first run builds the new cache) and the renders last (three visual tasks change what the pictures show).

**Tech Stack:** As the parent plans (C++23, Qt 6.8, QML, Qt Test and QuickTest offscreen, Python 3 unittest for the synth tool, GitHub Actions).

**Spec:** There is no new design doc. The requirements are the eight issues and the owner's triage comment on each, dated 2026-11-01 (quoted in each task). The triage table that found them: `.superpowers/sdd/2026-10-29-plotter/plan3-deferred-triage.md` in the `plotter` worktree (untracked). Where a fix changes a spec sentence, the task names the section of `docs/superpowers/specs/2026-10-31-plotter-views-design.md`.

**Process:** branch `plotter-fix-next` from `origin/main` 6839d19 (worktree `.claude/worktrees/plotter-fix-next`; `.superpowers/` is ignored, so this worktree starts without a ledger). Ledger for this plan: `.superpowers/sdd/2026-11-01-plotter-fix-next/progress.md` in this worktree, created by Task 1; the previous ledger (`.superpowers/sdd/2026-10-29-plotter/progress.md` in the `plotter` worktree) gets one pointer line. One PR, opened as a draft after Task 1 so CI runs the new cache key early. TDD in every task. One independent adversarial review of the whole branch before merge (owner rule, 2026-10-31), not one per task; fix wave; review threads resolved one by one after each verified fix, never in bulk; no merge with open threads or red CI. The owner merges.

## Global Constraints

- Everything in the parent plans' Global Constraints still holds (no GPL, Qt dynamic, `-DCM_BUILD_PLOTTER=ON` only, Qt 6.5 minimum, 12 mm controls, 15 mm tabs, `--` for stale, WAL + FULL, TDD).
- No em-dash character (U+2014) anywhere: code, comments, UI strings, docs, commit messages.
- US English in every new or changed user-visible string, comment and doc line. The word list is in `docs/superpowers/review-checklist.md` (written by Task 8; until then: favorite, color, center, meter, gray, license, behavior, canceled, modeled, labeled, neighbor, -ize). Code identifiers and the stored JSON key `"favourite"` are not renamed.
- Every QML UI test runs at both 1024x600 and 1280x800 where the existing test beside it does (`H.sizes()`); renders are taken at both sizes, day and night, with the recipe in `plotter/README.md` ("The saved views renders").
- Build and test from this worktree: `cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"`, `cmake --build build-plotter`, `ctest --test-dir build-plotter --output-on-failure`. Baseline on 6839d19: 114 tests, all pass, `vcan round trip` skipped.

## Review Focus

1. **A touchpad pinch on the dev desktop while locked** (a `QNativeGestureEvent`, which QtTest cannot send). Expected: no zoom, and the padlock pulses. Task 6 adds a `PinchHandler` to the overlay and a manual check line to the README bring-up list; the reviewer checks it by hand on the desktop.
2. **Hide on the recording track, then recording stops or a 10 minute gap starts a new track.** Expected: the hidden flag belongs to the old track; the new track's row is visible and its line drawn. Task 4 tests it (`hiddenActiveTrackIsNotDrawn`, last block).
3. **The Top or Bottom bar's handle, half outside the bar.** Expected: the outer half is drawn over the chart, not clipped; the bar's text is still clipped to the bar. Task 7 moves the clip from the slot to its content item; Task 9's `slot-*` renders are taken with the Top bar on and selected so the owner sees it.
4. **A None view at 1024x600 whose digits are width-limited** (the shipped Big # view: two half-width cells with a 4-character value). Expected: the cells widen when the bar hides, the digits refit and grow a little (about 8 percent), never shrink, and come back exactly when the bar shows. Task 5's test asserts the never-shrink and the exact return at both sizes.
5. **Points the recorder dropped after a failed batch** (writes failing for 20 points). Expected: the "(recording)" row keeps counting them, as the drawn line already does; after exit they are lost, and the README says so. Task 4's totals come from the recorder, not the store, and the README line is written in the same task.

---

## File Structure

```
.github/workflows/plotter-ci.yml       Task 1: maplibre cache key carries the Qt version; size comment
plotter/README.md                      Task 1 CI paragraph; Task 4 tracks line; Task 6 bring-up line; Task 8 spelling; Task 9 render list
plotter/tools/synth_n2k.py             Task 2: signed not-available fill; WAYPOINTS and SPEED constants
plotter/tools/test_synth_n2k.py        Task 2: encoder test, cog and variation, depth dropout edges, near() contract
plotter/src/core/N2kParse.h            Task 3: vessel-strict / AIS-optional contract comment
README.md                              Task 3: JSON messages note (what the plotter requires)
plotter/tests/tst_n2kclient.cpp        Task 3: cleanup() frees the accepted socket
plotter/src/core/Tracks.{h,cpp}        Task 4: TrackRecorder::activeTotals(); TracksController honors the active track's visible flag
plotter/qml/TracksPage.qml             Task 4: delete confirm closes when the page hides
plotter/tests/tst_tracks.cpp           Task 4
plotter/tests/qml/tst_pages.qml        Task 4 (tracks), Task 8 (strings)
plotter/qml/CellPage.qml               Task 5: barInset, cells follow the bar; cellValue objectName
plotter/qml/Main.qml                   Task 5: CellPage.barInset wiring
plotter/tests/qml/tst_views.qml        Task 5 (cells follow), Task 6 (lock), Task 8 (strings)
docs/superpowers/specs/2026-10-31-plotter-views-design.md   Task 5 (6.5), Task 6 (6.8), Task 7 (6.7), Task 8 (spelling)
plotter/qml/LockOverlay.qml            Task 6: PinchHandler, key focus, swallowed counter, pulse
plotter/qml/SlotView.qml               Task 7: handle centered on the inner corner or edge, arrow, content clip
plotter/qml/ChartPage.qml              Task 7: clip moved off the slot
plotter/qml/Theme.qml                  Task 7: editHandleArrow per palette
plotter/tests/qml/tst_editor.qml       Task 7 (handle), Task 8 (strings)
plotter/tests/qml/tst_theme.qml        Task 7 (night rule covers the new token; no change expected)
plotter/qml/TileMenu.qml, SetupSheet.qml, SettingsPage.qml   Task 8: Favorite, Meters, object names
docs/superpowers/review-checklist.md   Task 8: US English word list, no em-dash
docs/plotter/renders/views/            Task 9: editor-*, slot-*, setup-*, settings-* retaken; big-barhidden-* added
```

---

### Task 1: CI cache key carries the Qt version (#44); PR and ledger opened

Owner (2026-11-01): "fix now. Add `QT_VERSION` to the maplibre-native-qt cache key and correct the 8.5 GB comment (about 1.1 GB since 8db3647). Verified by one CI run in the next plotter PR."

**Files:**
- Modify: `.github/workflows/plotter-ci.yml:50-56`
- Modify: `plotter/README.md` CI paragraph (the section `## CI`, two mentions of "8.5 GB" and the key description)
- Create: `.superpowers/sdd/2026-11-01-plotter-fix-next/progress.md` (ignored; the ledger)

**Interfaces:**
- Produces: the cache key `maplibre-qt-<hash of scripts/build-maplibre-qt.sh>-qt<QT_VERSION>-ubuntu-24.04`.

- [ ] **Step 1: Change the key and the comment**

In `plotter-ci.yml`, the `Cache maplibre-native-qt` step:

```yaml
      # Only the install prefix is cached. The source checkout (about 1.1 GB, shallow) is not. The key
      # carries the Qt version: a Qt bump must not reuse a libQMapLibre built against the old Qt.
      - name: Cache maplibre-native-qt
        id: maplibre-cache
        uses: actions/cache@v4
        with:
          path: ~/.local/maplibre-qt
          key: maplibre-qt-${{ hashFiles('scripts/build-maplibre-qt.sh') }}-qt${{ env.QT_VERSION }}-ubuntu-24.04
```

- [ ] **Step 2: Check the YAML parses**

Run: `python3 -I -c "import yaml,sys; yaml.safe_load(open('.github/workflows/plotter-ci.yml')); print('ok')"`
Expected: `ok` (if PyYAML is missing, `ruby -ryaml -e 'YAML.load_file(".github/workflows/plotter-ci.yml"); puts "ok"'` or a `grep -n "qt\${{ env.QT_VERSION }}" .github/workflows/plotter-ci.yml` that prints the key line).

- [ ] **Step 3: README CI paragraph**

In `plotter/README.md` `## CI`: the cache is "keyed on the hash of `scripts/build-maplibre-qt.sh`, which holds the pinned commit, and on the Qt version"; both "8.5 GB" become "about 1.1 GB" (shallow checkout since 8db3647); the observed free-space numbers stay.

- [ ] **Step 4: Ledger**

Create `.superpowers/sdd/2026-11-01-plotter-fix-next/progress.md` with: the plan path, the branch and base (`plotter-fix-next` from 6839d19), the eight issues, and a line per task as it completes (as the previous ledger did). Append one line to `.superpowers/sdd/2026-10-29-plotter/progress.md` in the `plotter` worktree: "Fix-next plan and ledger: `.claude/worktrees/plotter-fix-next`, `.superpowers/sdd/2026-11-01-plotter-fix-next/progress.md`."

- [ ] **Step 5: Commit, push, open the draft PR**

```bash
git add .github/workflows/plotter-ci.yml plotter/README.md docs/superpowers/plans/2026-11-01-plotter-fix-next.md
git commit -m "ci(plotter): maplibre cache key carries the Qt version; checkout size comment (#44)"
git push -u origin plotter-fix-next
gh pr create --draft --title "plotter: fix-next set from the 2026-11-01 triage" --body-file <body>
```

PR body: one line per issue with what the PR does for it. Closing words: `Fixes #44`, `Fixes #37`, `Fixes #38`, `Fixes #35`, `Fixes #45`, `Fixes #29`, `Fixes #36`, `Fixes #43` (items 1 to 3 fixed, item 5 documented; item 4 was split out to #46 for plan 4, owner rule 2026-11-01: a split part gets its own issue with a ref back). A task checklist (Tasks 1 to 9). End with the attribution line from the session's instructions.

- [ ] **Step 6: Verify by the CI run**

The first run misses the maplibre cache (new key) and builds it (about 17 minutes); the job must pass. The next push hits the cache: `Cache maplibre-native-qt` prints `Cache restored from key: maplibre-qt-...-qt6.8.3-ubuntu-24.04`. Record both run URLs in the ledger.

---

### Task 2: synth_n2k scenario tests and the signed not-available fill (#37)

Owner (2026-11-01): "fix now, all four items (test-only plus the signed not-available fill for 127250 deviation), as a filler task."

**Files:**
- Modify: `plotter/tools/synth_n2k.py:27-52` (`Encoder.payload`), `:104-124` (scenario constants)
- Test: `plotter/tools/test_synth_n2k.py`

**Interfaces:**
- Produces: module constants `WAYPOINTS` (the four `(lat, lon)` pairs now local to `everett_pt_townsend`) and `SPEED = 3.0866` in `synth_n2k.py`; `everett_pt_townsend` uses them.

Run every test here with `ctest --test-dir build-plotter -R synth_n2k --output-on-failure` (it sets `N2KD`), or directly `N2KD=build-plotter/n2kd/n2kd python3 -I plotter/tools/test_synth_n2k.py -v`.

- [ ] **Step 1: Failing encoder test**

In `EncoderRangeTest`:

```python
    def raw(self, pgn, payload, field_id):
        f = next(f for f in self.enc.pgns[pgn]["Fields"] if f["Id"] == field_id)
        return (int.from_bytes(payload, "little") >> f["BitOffset"]) & ((1 << f["BitLength"]) - 1)

    def test_unset_signed_field_is_the_signed_not_available_pattern(self):
        p = self.pack(127250, sid=0, heading=1.0, variation=0.2731, reference=1)  # no deviation
        self.assertEqual(self.raw(127250, p, "deviation"), 0x7FFF)
        self.assertEqual(self.raw(127250, p, "variation"), round(0.2731 / 0.0001))

    def test_unset_unsigned_field_is_all_ones(self):
        p = self.pack(128267, sid=0, depth=10.0, offset=-0.3)  # no range
        self.assertEqual(self.raw(128267, p, "range"), 0xFF)
```

- [ ] **Step 2: Run, expect the first to fail** with `AssertionError: 65535 != 32767`.

- [ ] **Step 3: Fill unset signed fields with `(1 << (bits - 1)) - 1`**

In `Encoder.payload`, after `word` starts as all ones: for every field with `BitLength > 0` and `Signed` true that is not in `values`, clear its bits and set the signed not-available pattern. Unsigned unset fields stay all ones. The scenario's 127250 frames then carry deviation 0x7FFF; nothing else changes.

- [ ] **Step 4: Run, expect both to pass**, and `test_deterministic` still passes.

- [ ] **Step 5: Failing scenario tests**

In `SynthN2kTest`:

```python
    def test_cog_and_variation(self):
        v = self.near(60, "cog")
        expected = synth_n2k.Track(synth_n2k.WAYPOINTS, synth_n2k.SPEED).at(60)[2]
        self.assertLess(abs(v["cog"] - expected), 1e-3)
        self.assertLess(abs(self.near(60, "variation")["variation"] - 0.2731), 1e-4)

    def test_depth_dropout(self):
        # Mirrors test_position_dropout: n2kd holds the last depth 5 s (kDepthMaxAge), so the nulls
        # sit inside the generator's [360, 372) gap and none appear once the frames resume at 372.
        gap = [v for v in self.vessel if v["depth"] is None and v["t"] >= T0 + 60]
        self.assertTrue(gap)
        self.assertGreaterEqual(min(v["t"] for v in gap), T0 + 365 - 1e-6)
        self.assertLess(max(v["t"] for v in gap), T0 + 372)
        before = [v for v in self.vessel if T0 + 350 <= v["t"] <= T0 + 360]
        self.assertTrue(before)
        self.assertTrue(all(v["depth"] is not None for v in before))
        after = [v for v in self.vessel if v["t"] >= T0 + 372]
        self.assertTrue(after)
        self.assertTrue(all(v["depth"] is not None for v in after))

    def test_near_reads_the_frames_stamped_one_second_earlier(self):
        # near()'s contract, pinned on a value that changes: at s = 150 and 200 the depth moves
        # 0.52 and 0.26 m per second, so the line at or after T0 + s + 1 matches depth_m(s) and
        # neither neighbor. A change in n2kd's tick order fails here, not silently in test_sog.
        for s in (150, 200):
            d = self.near(s, "depth")["depth"]
            self.assertLess(abs(d - synth_n2k.depth_m(s)), 0.006)
            self.assertGreater(abs(d - synth_n2k.depth_m(s - 1)), 0.1)
            self.assertGreater(abs(d - synth_n2k.depth_m(s + 1)), 0.1)
```

`test_cog_and_variation` fails first with `AttributeError: module 'synth_n2k' has no attribute 'WAYPOINTS'`. If an edge in `test_depth_dropout` is off by one tick against the real n2kd output, pin the observed edge and say in the test comment which n2kd rule sets it (`kDepthMaxAge = 5.0` in `n2kd/include/n2k/StateMappers.h`); do not widen the window.

- [ ] **Step 6: Hoist `WAYPOINTS` and `SPEED`** to module level in `synth_n2k.py`; `everett_pt_townsend` reads them. Run; expect all synth tests to pass.

- [ ] **Step 7: Commit**

```bash
git add plotter/tools/synth_n2k.py plotter/tools/test_synth_n2k.py
git commit -m "test(plotter): synth_n2k pins cog, variation, depth dropout edges and near(); signed fields unset read not available (#37)"
```

---

### Task 3: N2kParse contract documented; tst_n2kclient frees accepted sockets (#38)

Owner (2026-11-01): "fix now, both items. Document the existing contract in `N2kParse.h` and the n2kd contract doc: the vessel message requires every key (null when no data); an AIS target requires only `mmsi`, `class` and `age`, every other key is optional and absent reads as null. This is our daemon-to-plotter format, not an N2K rule; the code already behaves this way. `tst_n2kclient.cpp`: free the previous accepted socket in `cleanup()`."

**Files:**
- Modify: `plotter/src/core/N2kParse.h:9-11`
- Modify: `README.md` `## JSON messages`, the note at line 92 ("Every key shown above is always present...")
- Modify: `plotter/tests/tst_n2kclient.cpp:53-56`

- [ ] **Step 1: Failing test for the documented AIS behavior**

`tst_n2kparse.cpp` already has `aisOutOfRangeValues`; add beside it:

```cpp
    void aisTargetWithOnlyRequiredKeysParses() {
        const auto r = parseAis(obj(R"({"targets":[{"mmsi":7,"class":"B","age":1.5}]})"));
        QVERIFY(r.has_value());
        QCOMPARE(r->size(), 1);
        QVERIFY(!r->first().lat && !r->first().sogMs && !r->first().shipType && r->first().name.isEmpty());
    }
    void vesselMissingAKeyIsRefused() {
        QJsonObject o = obj(kVessel); // the file's full vessel line
        o.remove("stw");
        QVERIFY(!parseVessel(o).has_value());
    }
```

(`obj()` and `kVessel` already exist at the top of the file.) Run `build-plotter/plotter/tst_n2kparse` (path from `ctest -N`): both pass already if the code behaves as the owner says. If `vesselMissingAKeyIsRefused` fails, stop: the contract is not what the issue states; report before documenting.

- [ ] **Step 2: Document**

`N2kParse.h`, above the three declarations:

```cpp
// The daemon-to-plotter JSON (see README.md "JSON messages"). This is our contract, not an NMEA 2000
// rule. A vessel message must carry every key (null when there is no data); a missing key is an
// error. An AIS target must carry mmsi, class and age; every other target key is optional and an
// absent key reads as null, so a newer daemon can drop a key without breaking an older plotter.
```

`README.md` note at line 92, after "Every key shown above is always present.": "n2kd always writes them all. The plotter requires every vessel key and, per AIS target, only `mmsi`, `class` and `age`; any other target key may be absent and reads as null (`plotter/src/core/N2kParse.h`)."

- [ ] **Step 3: Socket cleanup**

`tst_n2kclient.cpp`:

```cpp
    void cleanup() {
        m_server.close();
        delete m_peer; // nextPendingConnection() parents it to the server, so it lived until the end
        m_peer = nullptr;
    }
```

Run `tst_n2kclient` and `tst_n2kparse`: pass, no new warnings on stderr.

- [ ] **Step 4: Commit**

```bash
git add plotter/src/core/N2kParse.h README.md plotter/tests/tst_n2kparse.cpp plotter/tests/tst_n2kclient.cpp
git commit -m "docs(plotter): vessel-strict, AIS-optional key contract in N2kParse and README; tst_n2kclient frees accepted sockets (#38)"
```

---

### Task 4: Tracks: Hide honored by the live line, confirm dismissed on page hide, recording row counts buffered points (#43 items 1 to 3; README line for item 5)

Owner (2026-11-01): "Fix now: 1. Hide on the recording track: the live line (`cm-track-active`) honors the visible flag. 2. The delete confirm is dismissed when the Tracks page hides. 3. The "(recording)" row counts the buffered points too, so it does not read "0 s, 0.0 nm" for the first 30 s. Close: 5. Buffered points lost on exit while writes keep failing: expected; one README line stating it, written with item 3." Item 4 (the whole line re-sent per kept point) is issue #46, plan 4.

**Files:**
- Modify: `plotter/src/core/Tracks.h:80-105` (TrackRecorder), `:117-141` (TracksController)
- Modify: `plotter/src/core/Tracks.cpp` (`startTrack`, `onVessel`, `recordingChanged`, `TracksController::refresh`, `onActive`)
- Modify: `plotter/qml/TracksPage.qml:26`
- Modify: `plotter/README.md` (after the settings table, near `trackMinDistanceM`)
- Test: `plotter/tests/tst_tracks.cpp`, `plotter/tests/qml/tst_pages.qml`

**Interfaces:**
- Produces, `TrackRecorder`:
  ```cpp
  struct ActiveTotals { int points = 0; double durationS = 0; double distanceM = 0; };
  // The active track, written and buffered points (and points dropped after a failed batch, which the
  // drawn line keeps too); zero when no track is active.
  ActiveTotals activeTotals() const;
  ```
  Members `double m_activeStartT = 0; double m_activeDistanceM = 0;` set in `startTrack` (start time, 0), added to in `onVessel` on a kept point (the `distanceM` already computed against `m_last`), cleared in `recordingChanged`. `points` is `m_activePoints.size()`, `durationS` is `m_last->t - m_activeStartT`.
- Produces, `TracksController`: `active()` returns an empty list while the active track's stored `visible` flag is false; `activeChanged` is emitted when that flag flips (through `refresh()`, which `setVisible()` calls). Member `bool m_activeVisible = true;`. The comment on `refresh()` changes to "(the active track's counts include the buffered points)".

- [ ] **Step 1: Failing C++ tests** in `tst_tracks.cpp`, beside `controllerRowsCarryTheDisplayFields`:

```cpp
    void activeRowCountsBufferedPoints() {
        Rig r(true, 1, 0);
        TracksController c(*r.tracks, *r.rec);
        r.feed(0, 47.0); r.feed(10, 47.001); r.feed(20, 47.002); // 3 points, under one batch and 30 s
        QCOMPARE(r.stored(r.rec->activeId()), 0);
        c.refresh();
        QVariantMap row = c.tracks().at(0).toMap();
        QCOMPARE(row["points"].toInt(), 3);
        QCOMPARE(row["durationS"].toDouble(), 20.0);
        QVERIFY(row["distanceM"].toDouble() > 200 && row["distanceM"].toDouble() < 240); // 2 x 111 m
        r.rec->flush();
        c.refresh();
        row = c.tracks().at(0).toMap();
        QCOMPARE(row["points"].toInt(), 3); // the same once written
        QCOMPARE(row["durationS"].toDouble(), 20.0);
    }
    void hiddenActiveTrackIsNotDrawn() {
        Rig r(true, 1, 0);
        TracksController c(*r.tracks, *r.rec);
        r.feed(0, 47.0); r.feed(1, 47.001);
        r.rec->flush();
        c.refresh();
        QSignalSpy active(&c, &TracksController::activeChanged);
        const qint64 id = r.rec->activeId();
        c.setVisible(id, false);
        QCOMPARE(c.active().size(), 0);
        QCOMPARE(active.count(), 1);
        QCOMPARE(c.tracks().at(0).toMap()["visible"].toBool(), false);
        r.feed(2, 47.002); // a kept point while hidden stays hidden
        QCOMPARE(c.active().size(), 0);
        c.setVisible(id, true);
        QCOMPARE(c.active().size(), 3);
        QCOMPARE(active.count(), 3); // hide, the kept point, show
        // Review Focus 2: the flag belongs to the old track; a new track starts visible.
        c.setVisible(id, false);
        r.feed(2000, 48.0); // 10 minute gap: a new track
        QCOMPARE(c.active().size(), 1);
        QCOMPARE(c.finished().size(), 0); // the old one is hidden
    }
```

And in `controllerShowsActiveAlwaysAndOthersWhenVisible` (rename to `controllerShowsActiveAndOthersWhenVisible`) the last block becomes:

```cpp
        // Hiding the active track hides its line too (issue #43); the finished one stays.
        c.setVisible(r.rec->activeId(), false);
        QCOMPARE(c.active().size(), 0);
        QCOMPARE(c.finished().size(), 1);
```

- [ ] **Step 2: Run `tst_tracks`**: `activeRowCountsBufferedPoints` fails at `points` (0 vs 3); `hiddenActiveTrackIsNotDrawn` fails at `active().size()` (2 vs 0).

- [ ] **Step 3: Implement** `activeTotals()` and the visible flag as in Interfaces. In `TracksController::refresh()`, for the row whose `id == active`: `points`, `durationS`, `distanceM` come from `m_recorder.activeTotals()`; `m_activeVisible = t.visible`. At the end of `refresh()`, if `m_activeVisible` changed, `emit activeChanged()`. `active()` returns `m_activeVisible ? m_activePoints : QList<LatLon>{}`. `onActive` keeps emitting on every kept point (the line only changes when visible, but `ChartController::setActiveTrack` with an empty list is cheap).

- [ ] **Step 4: Run `tst_tracks`**: all pass, including the renamed test and `powerCutKeepsAPrefixOfTheTrack`.

- [ ] **Step 5: Failing QML test** in `tst_pages.qml` beside `test_tracksDeleteAsksFirstInPage`:

```qml
    function test_tracksDeleteConfirmClosesWhenThePageHides() {
        const page = makeTracks(1200, 800)
        fixture.addTrack(1.7e9)
        const confirm = H.byName(page, "confirmDelete")
        mouseClick(H.byName(page, "trackDelete"))
        verify(confirm.visible)
        page.visible = false // a tab switch
        page.visible = true
        verify(!confirm.visible, "the confirm does not survive a page switch")
        compare(fixture.tracksController.tracks.length, 1)
    }
```

Run `build-plotter/plotter/tests/qml/tst_qml -input plotter/tests/qml/tst_pages.qml` (the path `ctest -N` prints for `tst_qml`; `-input` runs one file): fails at "the confirm does not survive".

- [ ] **Step 6: `TracksPage.qml:26`**: `onVisibleChanged: { if (visible) tracks.refresh(); else confirm.visible = false }`. Run: pass.

- [ ] **Step 7: README line** after the settings table: "Track points are written every 30 s or every 20 points. If the database refuses writes, the recorder holds at most one batch and retries; those points stay on the chart and in the Tracks row, and are lost if the app exits while writes still fail."

- [ ] **Step 8: Commit**

```bash
git add plotter/src/core/Tracks.h plotter/src/core/Tracks.cpp plotter/qml/TracksPage.qml plotter/tests/tst_tracks.cpp plotter/tests/qml/tst_pages.qml plotter/README.md
git commit -m "fix(plotter): hidden recording track is not drawn; delete confirm closes with the page; recording row counts buffered points (#43)"
```

---

### Task 5: None view cells follow the tab bar (#35)

Owner (2026-11-01): "fix now. `CellPage` gets a `barInset` like `ChartPage`'s, cells widen into the strip when the bar hides and give the room back when it shows; digit size keys on height so it does not change; spec 6.5 updated to the owner's call; test beside `test_slotsFollowTheBarAndTheButtonsHide`."

Note for the owner (planner, 2026-11-01): the digits in the shipped Big # view at 1024x600 are width-limited, not height-limited (a 4-character value in a half-width cell at about 540 px of digit box height wants about 1100 px of width), so widening the cell by half the 15 mm strip lets them refit about 8 percent larger. The cell heights, the label and the unit sizes do not change. This plan keeps the refit (the point of hiding the bar is more room) and pins "never smaller, exactly back when the bar shows". If the owner wants the digits pinned to the shown-bar size instead, the value label keeps `width: cell.width - strip share` and the test's `>=` becomes `==`.

**Files:**
- Modify: `plotter/qml/CellPage.qml:4-19` (comment, `barInset`, `areaW`), `:82-97` (value label `objectName: "cellValue"`)
- Modify: `plotter/qml/Main.qml:214-222` (CellPage block: `barInset: root.width - tabBar.x`)
- Modify: `docs/superpowers/specs/2026-10-31-plotter-views-design.md` section 6.5, the sentence "The cells of a None view stay put, the extra strip is background;"
- Test: `plotter/tests/qml/tst_views.qml`, after `test_slotsFollowTheBarAndTheButtonsHide`

**Interfaces:**
- Produces: `CellPage.barInset: real` (default `rightInset`; the part of the strip the bar covers now, 0 while hidden); `areaW` is `width - barInset`. The value `Label` in each cell has `objectName: "cellValue"`.

- [ ] **Step 1: Failing test**

```qml
    // A None view's cells widen into the strip when the bar slides off and come back exactly when it
    // shows; heights never change, digits never get smaller (they may refit larger, issue #35).
    function test_cellsFollowTheBar_data() { return H.sizes() }
    function test_cellsFollowTheBar(data) {
        const main = makeMain(data.w, data.h)
        main.hideDelayMs = 0
        mouseClick(item(main, "tab-view-shipped-big"))
        compare(main.page, "view")
        const page = item(main, "cellPage")
        waitForRendering(page)
        const cells = H.findAll(page, it => it.objectName.startsWith("cell-") && it.visible)
        compare(cells.length, 2)
        const boxOf = it => H.box(it, main.contentItem)
        const before = cells.map(boxOf)
        const digits = () => cells.map(c => H.byName(c, "cellValue").fontInfo.pixelSize)
        const digitsBefore = digits()
        const gap = page.gap

        main.hideDelayMs = 200
        tryVerify(() => item(main, "tabBar").x >= main.width - 0.01, 1500, "the bar slid all the way off")
        const after = cells.map(boxOf)
        for (let i = 0; i < cells.length; ++i) {
            compare(after[i].y, before[i].y, "cell-" + i + " y")
            compare(after[i].h, before[i].h, "cell-" + i + " height")
            fuzzyCompare(after[i].w, (main.width - 3 * gap) / 2, 1, "cell-" + i + " half of the full width")
        }
        compare(after[0].x, before[0].x, "cell-0 stays at the left edge")
        fuzzyCompare(after[1].x + after[1].w, main.width - gap, 1, "cell-1 reaches the right edge")
        const digitsAfter = digits()
        for (let i = 0; i < cells.length; ++i) verify(digitsAfter[i] >= digitsBefore[i] - 0.01, "digits never smaller: " + digitsBefore + " to " + digitsAfter)

        main.hideDelayMs = 2000
        mouseClick(cells[0], cells[0].width / 2, cells[0].height / 2) // a plain tap brings the bar back
        verify(item(main, "tabBar").shown)
        tryVerify(() => barShown(main) && JSON.stringify(cells.map(boxOf)) === JSON.stringify(before), 1500,
                  "every cell back: " + JSON.stringify(cells.map(boxOf)))
        compare(digits(), digitsBefore, "digits back to their size")
    }
```

Run `tst_qml -input plotter/tests/qml/tst_views.qml`: fails at "half of the full width" (the cells keep the shown-bar width).

- [ ] **Step 2: Implement** `barInset` in `CellPage.qml` and the `cellValue` object name; wire `barInset: root.width - tabBar.x` in `Main.qml`'s `CellPage` block. Update the file comment: "its cells tile the page left of the tab bar, and widen into the strip while the bar is hidden".

- [ ] **Step 3: Run `tst_views.qml` and `tst_pages.qml`**: pass at both sizes (`test_cellPageLaysOutTheLayout` still passes: with `barInset` defaulting to `rightInset` nothing changes for a page built alone).

- [ ] **Step 4: Spec 6.5**: replace "The cells of a None view stay put, the extra strip is background;" with "The cells of a None view widen into the strip when the bar hides and give the room back when it shows (owner, 2026-11-01, issue #35; it overrules the earlier 'stay put'); their heights do not change, the digits refit to the wider cell and never get smaller;".

- [ ] **Step 5: Commit**

```bash
git add plotter/qml/CellPage.qml plotter/qml/Main.qml plotter/tests/qml/tst_views.qml docs/superpowers/specs/2026-10-31-plotter-views-design.md
git commit -m "feat(plotter): None view cells follow the tab bar (#35)"
```

---

### Task 6: The lock swallows native pinch and keys, and pulses the padlock on every swallowed input (#45)

Owner (2026-11-01): "fix now, with one addition. [...] Fix: a `PinchHandler` on the overlay, focus plus `Keys.onPressed` accepting every key while locked. Tests: wheel over the map, two-finger touch pinch, key press, each with the chart's zoom and gesture count unchanged; then the unlock hold still works. QtTest cannot synthesize a native gesture, so the desktop pinch gets a manual check in the README bring-up list. Owner addition: any swallowed input while locked gives a visible cue on the lock icon (a brief pulse or flash of the hold target), the same for touch, wheel, pinch and key, so the user learns the screen is locked rather than dead."

**Files:**
- Modify: `plotter/qml/LockOverlay.qml`
- Modify: `plotter/README.md` `## Bring-up checks` (one bullet)
- Modify: `docs/superpowers/specs/2026-10-31-plotter-views-design.md` section 6.8 (one sentence)
- Test: `plotter/tests/qml/tst_views.qml` (lock tests)

**Interfaces:**
- Produces, `LockOverlay`: `property int swallowed` (inputs stopped since the lock went on; reset to 0 when the overlay shows), `readonly property bool pulsing` (the pulse animation is running), `function swallow()` (increments `swallowed`, restarts the pulse). The overlay takes active focus when shown (`forceActiveFocus()`), and `Keys.onPressed` accepts every key and calls `swallow()`. A `PinchHandler { target: null }` on the overlay calls `swallow()` when it becomes active (a touchpad pinch arrives as a native gesture, which only a handler sees). The `MultiPointTouchArea.onPressed` and `WheelHandler.onWheel` call `swallow()` too. The hold target's `TapHandler` does not (a hold is the one allowed interaction).
- The pulse: a `SequentialAnimation` on `holdTarget.scale`, 1 to 1.25 in 120 ms, back to 1 in 180 ms (`transformOrigin` stays `Center`). `restart()` on every swallow so a run of inputs keeps it moving.

- [ ] **Step 1: Failing test** after `test_lockSwallowsTouchPinchAndWheel`:

```qml
    // Every input the lock stops pulses the padlock (owner: the screen is locked, not dead): a tap,
    // a wheel turn, a pinch and a key press. The unlock hold does not count. A key reaches nothing.
    function test_lockPulsesOnEverySwallowedInputAndTakesKeys() {
        const main = makeMain(1024, 600)
        const map = item(main, "mapArea")
        const overlay = item(main, "lockOverlay")
        waitForRendering(main.contentItem)
        fixture.touchLock.lockNow()
        compare(overlay.swallowed, 0)
        verify(overlay.activeFocus, "the overlay holds the key focus while locked")
        verify(!overlay.pulsing)

        touchTap(map)
        compare(overlay.swallowed, 1, "a tap")
        verify(overlay.pulsing, "the tap pulses the padlock")
        mouseWheel(map, map.width / 2, map.height / 2, 0, 120)
        compare(overlay.swallowed, 2, "a wheel turn")
        const n = overlay.swallowed
        pinchOut(map)
        verify(overlay.swallowed > n, "a pinch")
        const k = overlay.swallowed
        keyClick(Qt.Key_Plus)
        keyClick(Qt.Key_Escape)
        compare(overlay.swallowed, k + 2, "key presses")
        compare(chartStub.zooms.length, 0, "nothing reached the chart")
        compare(main.chartMap.gestures, 0)
        compare(main.chartMap.scales.length, 0)
        compare(main.page, "view")
        verify(overlay.activeFocus, "still focused after the inputs")

        const holdTarget = item(main, "lockHold")
        const before = overlay.swallowed
        mousePress(holdTarget)
        fixture.advance(1500)
        mouseRelease(holdTarget)
        verify(!fixture.touchLock.locked, "the hold still unlocks")
        compare(overlay.swallowed, before, "the hold is not a swallowed input")
        tryVerify(() => !overlay.pulsing, 1000, "the pulse ends")
        mouseWheel(map, map.width / 2, map.height / 2, 0, 120)
        compare(chartStub.zooms.length, 1, "the wheel zooms once unlocked")
    }
```

Run `tst_qml -input plotter/tests/qml/tst_views.qml`: fails at `overlay.swallowed` (undefined). No QML test uses `keyClick` or `activeFocus` yet: if `activeFocus` reads false because the offscreen test window is not active, call `main.contentItem.Window.window.requestActivate()` once after `makeMain` and wait with `tryVerify(() => overlay.activeFocus, 1000)`; do not drop the assertion.

- [ ] **Step 2: Implement** `LockOverlay.qml` as in Interfaces. Update the file comment: "every touch, mouse press, wheel turn, pinch (touch or touchpad) and key press stops here and pulses the padlock". `onVisibleChanged: if (visible) { place(); swallowed = 0; forceActiveFocus() }`.

- [ ] **Step 3: Run the three lock tests and `test_lockShowsTheBarFirst`**: pass. Run the whole `tst_qml` once: pass (a focus change must not break the editor's keyboard tests in `tst_editor.qml`).

- [ ] **Step 4: README bring-up bullet**: "- Lock against a touchpad pinch (dev desktop only; the panel is touch): with the lock on, a two-finger touchpad pinch over the chart must not zoom and must pulse the padlock. QtTest cannot send a native gesture (`QNativeGestureEvent`), so `tst_views` covers touch, mouse, wheel and keys, and this one is checked by hand."

- [ ] **Step 5: Spec 6.8**, one sentence after "The Lock button and the 1.5 s hold to unlock stay.": "While locked, every input (touch, mouse, wheel, native pinch, keys) stops at the overlay and pulses the padlock; the unlock hold is the only interaction (owner, 2026-11-01, issue #45: 'Lock means the only option for interaction is to unlock')."

- [ ] **Step 6: Commit**

```bash
git add plotter/qml/LockOverlay.qml plotter/tests/qml/tst_views.qml plotter/README.md docs/superpowers/specs/2026-10-31-plotter-views-design.md
git commit -m "feat(plotter): lock swallows native pinch and keys; every swallowed input pulses the padlock (#45)"
```

---

### Task 7: Resize handle centered on the inner corner, with a double-headed arrow (#29)

Owner (2026-11-01): "Center the disc on the slot's inner corner (half over the slot's corner padding, half over the chart), so the unit shows behind it. Bars and banners: centered on the inner edge's midpoint as now, straddling the edge. Add a subtle double-headed arrow inside the disc pointing at opposing corners (the resize directions); for a bar the arrow runs perpendicular to the inner edge. Lighter blue than the disc. Same 12 mm touch target; editor tests adjusted to the new handle position; editor renders retaken."

**Files:**
- Modify: `plotter/qml/SlotView.qml:9-10` (comment), `:110-134` (handle), `:137` (contentItem gains `clip: slot.horizontalBar`)
- Modify: `plotter/qml/ChartPage.qml:253-255` (`clip: horizontalBar` removed from the slot; the comment moves with it)
- Modify: `plotter/qml/Theme.qml` (`editHandleArrow` in the three palettes and the flat property)
- Modify: `docs/superpowers/specs/2026-10-31-plotter-views-design.md` section 6.7, the handle sentence
- Test: `plotter/tests/qml/tst_editor.qml` (`test_dragHandleResizesLive` plus one new test); `plotter/tests/qml/tst_theme.qml` runs unchanged

**Interfaces:**
- Produces, handle `Item` (objectName `handle-<slotId>`, 12 mm square, as now):
  ```qml
  x: slot.horizontalBar ? (slot.width - width) / 2 : slot.leftSide ? slot.width - width / 2 : -width / 2
  y: slot.verticalBar ? (slot.height - height) / 2 : slot.topSide ? slot.height - height / 2 : -height / 2
  // Degrees clockwise from the x axis: the resize axis.
  readonly property real arrowAngle: slot.horizontalBar ? 90 : slot.verticalBar ? 0
                                   : (slot.slotId === "TL" || slot.slotId === "BR") ? 45 : 135
  ```
  Inside it, after the disc `Rectangle`, a `Canvas` with `objectName: "handleArrow-" + slot.slotId`, `anchors.fill: parent`, `rotation: parent.arrowAngle`, `property color stroke: Theme.editHandleArrow` (repaint on change), drawing a horizontal double-headed arrow through the center: shaft from 0.22 to 0.78 of the width, heads 0.14 of the width long at 30 degrees, line width `Math.max(2, Units.mm(0.6))`, round caps.
- `Theme.editHandleArrow`: day `#8cc4ff`, dusk `#a8ccff`, night `#ff2020` (the night rule allows no channel other than red above 0x20; `tst_theme` checks every token).
- The clip: `SlotView`'s `contentItem` gets `clip: slot.horizontalBar` (a bar's text is clipped to the bar); `ChartPage.qml:255` loses `clip: horizontalBar`, so the handle, a sibling of the content item, is not clipped.

- [ ] **Step 1: Failing tests** in `tst_editor.qml`. In `test_dragHandleResizesLive`, replace the line `verify(hb.x + hb.w > tl.width - 1 && hb.y + hb.h > tl.height - 1, "on TL's inner (bottom right) corner")` with:

```qml
        fuzzyCompare(hb.x + hb.w / 2, tl.width, 1, "centered on TL's inner corner, x")
        fuzzyCompare(hb.y + hb.h / 2, tl.height, 1, "centered on TL's inner corner, y")
```

New test after it:

```qml
    // The handle is centered on the inner corner (corners) or the midpoint of the inner edge (bars),
    // half over the slot and half over the chart, and carries an arrow along the resize axis.
    function test_handleSitsOnTheInnerCornerOrEdgeWithAnArrow() {
        const main = makeMain(1280, 800)
        main.editView("shipped-nav")
        const page = m(main, "chartPage")
        const center = { TL: s => [s.width, s.height], TR: s => [0, s.height], BL: s => [s.width, 0], BR: s => [0, 0],
                         Top: s => [s.width / 2, s.height], Bottom: s => [s.width / 2, 0],
                         Left: s => [s.width, s.height / 2], Right: s => [0, s.height / 2] }
        const angle = { TL: 45, BR: 45, TR: 135, BL: 135, Top: 90, Bottom: 90, Left: 0, Right: 0 }
        for (const id of ["TL", "TR", "BL", "BR", "Top", "Bottom", "Left", "Right"]) {
            fixture.draft.setSlot(id, true, "sog", 8)
            waitForRendering(page)
            const slot = m(main, "slot-" + id)
            mouseClick(slot)
            const handle = find(page, "handle-" + id)
            verify(handle.visible, id + " handle")
            const hb = H.box(handle, slot)
            const [cx, cy] = center[id](slot)
            fuzzyCompare(hb.x + hb.w / 2, cx, 1, id + " center x")
            fuzzyCompare(hb.y + hb.h / 2, cy, 1, id + " center y")
            verify(Math.abs(hb.w - Units.mm(12)) < 0.5, id + " 12 mm")
            const arrow = find(handle, "handleArrow-" + id)
            verify(arrow.visible, id + " arrow")
            compare(arrow.rotation, angle[id], id + " arrow along the resize axis")
            verify(Qt.colorEqual(arrow.stroke, Theme.editHandleArrow), id + " arrow color")
            verify(!Qt.colorEqual(Theme.editHandleArrow, Theme.editOutline), "lighter than the disc")
            // Done closes the sheet (it would cover the slots in the other half) and clears the selection.
            mouseClick(find(m(main, "viewEditor"), "sheetDone"))
            verify(!handle.visible, id + " handle gone with the selection")
        }
    }
```

Run `tst_qml -input plotter/tests/qml/tst_editor.qml`: fails at "centered on TL's inner corner, x".

- [ ] **Step 2: Implement** the handle, the arrow, the theme token and the clip move as in Interfaces. Update the `SlotView.qml` header comment lines 9 and 10 ("centered on its inner corner ... half over the chart, with a double-headed arrow along the resize axis").

- [ ] **Step 3: Run `tst_editor.qml`, `tst_theme.qml`, `tst_pages.qml`, `tst_views.qml`**: pass. `test_dragHandleResizesLive` drags from the new center and must still reach 6 mm and the clamp.

- [ ] **Step 4: Spec 6.7**: replace "shows a round handle on its inner corner (corner slots), inner edge (bars and banners): drag it" with "shows a round 12 mm handle centered on its inner corner (corner slots: half over the slot's padding, half over the chart, so the unit shows behind it) or on the midpoint of its inner edge (bars, straddling the edge), with a subtle lighter-blue double-headed arrow along the resize axis (owner, 2026-11-01, issue #29): drag it".

- [ ] **Step 5: Commit**

```bash
git add plotter/qml/SlotView.qml plotter/qml/ChartPage.qml plotter/qml/Theme.qml plotter/tests/qml/tst_editor.qml docs/superpowers/specs/2026-10-31-plotter-views-design.md
git commit -m "feat(plotter): resize handle centered on the inner corner with a resize arrow (#29)"
```

---

### Task 8: US English in strings and docs; the word list in a review checklist (#36)

Owner (2026-11-01): "fix now, strings and docs only. In scope: the three user-visible strings (Favorite on/off, Favorite: row, Meters), the object names tests use (`menu-favourite`, `row-favourite`, `favouriteNote`), the README and the views spec swept with a word list, and the word list added to the review checklist. Out of scope: code identifiers (`favouriteCapacity`, `setFavourite`, `FavouriteRole`) and the stored JSON key `"favourite"` stay; the key moves only with a schema migration (#32)."

There is no review checklist file in the repository today (the reviews ran from prompts in the ledger). This task creates `docs/superpowers/review-checklist.md` and the plan's Global Constraints point at it. The owner may prefer another home; say so on the PR.

**Files:**
- Modify: `plotter/qml/TileMenu.qml:86-88` (`menu-favorite`, "Favorite off" / "Favorite on")
- Modify: `plotter/qml/SetupSheet.qml:172-177` (`row-favorite`, "Favorite: ", `favoriteNote`)
- Modify: `plotter/qml/SettingsPage.qml:24` ("Meters")
- Modify: `plotter/tests/qml/tst_views.qml:473-480`, `plotter/tests/qml/tst_editor.qml:725,736,836,909-923,965-976` (object names and texts)
- Modify: `plotter/README.md` (lines 27, 29, 30, 36, 40, 129, 137, 153, 216: favourite, metres, Licences; line 141 `"favourite": true` is the stored key and stays)
- Modify: `docs/superpowers/specs/2026-10-31-plotter-views-design.md` (favourite x21, colour x2, centre x1, minimises x1; the storage JSON key in 6.12 stays)
- Create: `docs/superpowers/review-checklist.md`

- [ ] **Step 1: Tests first**: change the object names and expected texts in `tst_views.qml` and `tst_editor.qml` (`menu-favorite`, `"Favorite off"`, `"Favorite on"`, `row-favorite`, `"Favorite: On"`, `"Favorite: Off"`, `favoriteNote`). Run `tst_qml -input plotter/tests/qml/tst_views.qml` and `tst_editor.qml`: fail (items not found).

- [ ] **Step 2: Strings and object names** in the three QML files. Run both test files: pass. Run `tst_pages.qml` too (its Settings unit tests compare no label text today, so it should pass unchanged).

- [ ] **Step 3: Docs sweep**. Word list (US from UK): favorite (favourite), color (colour), center (centre), meter (metre), gray (grey), license (licence, the noun), behavior (behaviour), neighbor (neighbour), canceled (cancelled), modeled (modelled), labeled (labelled), signaled (signalled), minimize and the -ize family (minimise, initialise, organise, recognise, normalise, serialise, visualise, customise, optimise), analyze (analyse), catalog (catalogue). Apply to `plotter/README.md` and the views spec, prose only. Keep: the stored key `"favourite"` (README line 141 and spec 6.12), code identifiers in backticks (`favouriteCapacity`, `setFavourite`, `FavouriteRole`), quoted owner words, commit hashes.

Gate:

```bash
grep -niE "favourite|colour|centre|metre|grey|licence|behaviour|neighbour|cancell|modell|labell|signall|minimis|initialis|organis|recognis|normalis|serialis|visualis|customis|optimis|analys|catalogue" plotter/README.md docs/superpowers/specs/2026-10-31-plotter-views-design.md
```

Expected: only lines that hold the stored key or a backticked identifier; list them in the commit message. A second grep over `plotter/qml/*.qml` for string literals: `grep -nE '"[^"]*(Favourite|Metres|colour|centre)[^"]*"' plotter/qml/*.qml` prints nothing.

- [ ] **Step 4: `docs/superpowers/review-checklist.md`**: a short file with two sections. "Writing": US English in user-visible strings, comments and docs, with the word list above and the exceptions (identifiers, stored keys, third-party text, quoted words); no em-dash character anywhere. "Reviewing" (the standing rules, one line each): the reviewer posts their own PR review (COMMENT, inline threads); threads are resolved one by one after a verified fix, never in bulk; no merge with open threads or red CI; one independent adversarial review of the branch before merge. Add one line to the root `README.md` `## Build and test` section pointing at it.

- [ ] **Step 5: Commit**

```bash
git add plotter/qml/TileMenu.qml plotter/qml/SetupSheet.qml plotter/qml/SettingsPage.qml plotter/tests/qml/tst_views.qml plotter/tests/qml/tst_editor.qml plotter/tests/qml/tst_pages.qml plotter/README.md README.md docs/superpowers/specs/2026-10-31-plotter-views-design.md docs/superpowers/review-checklist.md
git commit -m "docs(plotter): US English in user-visible strings, README and the views spec; review checklist with the word list (#36)"
```

---

### Task 9: Renders, final checks, review and merge gate

**Files:**
- Modify: `docs/plotter/renders/views/editor-*.png`, `slot-*.png`, `setup-*.png`, `settings-*.png` (16 files retaken)
- Create: `docs/plotter/renders/views/big-barhidden-day-1024x600.png`, `big-barhidden-day-1280x800.png`
- Modify: `plotter/README.md` render paragraph (one clause for `big-barhidden`)

- [ ] **Step 1: Retake the renders** with the README recipe (`plotter/tools/run-dev.sh "" --palette P --window WxH --screenshot FILE --screenshot-after-ms 7000 --exit-after-ms 8000`, `CM_PACKS_DIR` set as the recipe says): `--editor` for `editor-*`, `--sheet slot` for `slot-*` (TL selected: the handle on its inner corner with the arrow), `--sheet setup` for `setup-*` ("Favorite: On"), `--page settings` for `settings-*` ("Meters"), each day and night at 1024x600 and 1280x800. Add `big-barhidden-day-<WxH>.png`: `--view "Big #"` at 10000 ms (after the 8 s hide), day only, both sizes. For Review Focus 3 add one `slot-top-day-1280x800.png` showing the Top bar selected with its handle straddling the inner edge. `--sheet slot` selects TL, so get it by hand: run the dev app, open the editor on Navigation, turn the Top bar on in its slot sheet, keep the sheet open and take the screenshot (any screenshot tool; the file name as given). Say in the ledger how it was taken.

- [ ] **Step 2: Look at every retaken render** (Read tool on the PNGs) and confirm: the handle disc is centered on TL's inner corner with the unit visible behind it and the arrow along the diagonal; the Top bar's handle (if rendered) shows its outer half over the chart; "Favorite: On" in the Setup sheet; "Meters" in Settings; the Big # cells reach the right edge with the bar hidden. Fix and retake anything wrong.

- [ ] **Step 3: README render paragraph**: add `big-barhidden` to the list of names taken at 10000 ms, beside `nav-barhidden`.

- [ ] **Step 4: Whole-tree gates**

```bash
ctest --test-dir build-plotter --output-on-failure
git diff 6839d19 --name-only | xargs grep -ln "$(printf '\xe2\x80\x94')" ; echo "em-dash files above (expect none)"
git diff 6839d19 -- '*.md' '*.qml' '*.h' '*.cpp' '*.py' '*.yml' | grep '^+' | grep -niE "favourite|colour|centre|metres|licence|behaviour|neighbour|minimis" ; echo "new British spellings above (expect only the stored key)"
```

Expected: all tests pass; no em-dash; no new British spelling outside the stored key and identifiers.

- [ ] **Step 5: Commit, push, mark the PR ready**

```bash
git add docs/plotter/renders/views plotter/README.md
git commit -m "docs(plotter): renders for the handle, Favorite, Meters and the Big view with the bar hidden"
git push
gh pr ready
```

- [ ] **Step 6: Review and merge gate.** One independent adversarial review of the whole branch (a fresh reviewer on the most capable model, given the plan and the eight issues, not this session's conclusions); the reviewer posts their own PR review with inline threads. Fix wave with a commit per thread or per group; each thread resolved only after its fix is verified by a rerun test or a render; adjudication comment on the PR. CI green on the final head (the second run must hit the maplibre cache; record the URL). Ledger updated. The owner merges.

---

## Self-review notes

- **Coverage:** #44 Task 1; #37 Task 2 (four items); #38 Task 3 (two items); #43 items 1 to 3 and the item 5 README line Task 4, item 4 untouched (plan 4); #35 Task 5 (barInset, spec 6.5, test beside the slots test); #45 Task 6 (PinchHandler, keys, pulse, tests, README manual check); #29 Task 7 (centered handle, arrow, lighter blue, tests, spec 6.7) with renders in Task 9; #36 Task 8 (three strings, three object names, README and spec sweep, checklist). Owner additions all placed: #45 pulse (Task 6), #29 arrow (Task 7), #36 scope limits (Task 8), #43 item 5 README line (Task 4).
- **Names used across tasks:** `activeTotals()` and `m_activeVisible` only in Task 4; `barInset` on CellPage matches ChartPage's name; `swallowed`, `pulsing`, `swallow()` only in Task 6; `editHandleArrow`, `arrowAngle`, `handleArrow-<id>` only in Task 7; object names `menu-favorite`, `row-favorite`, `favoriteNote` in Task 8 and the tests it edits. Task 9's renders depend on Tasks 5, 7 and 8 being merged into the branch first, which the order gives.
- **Owner calls settled 2026-11-01:** (1) Task 5's digit refit stands: cells grow when the bar hides and shrink back when it shows, digits refit with them. (2) `docs/superpowers/review-checklist.md` is the checklist's home. (3) #43 item 4 is issue #46 (plan 4); #43 closes with this PR. Rule for the future: a split issue's deferred part gets its own issue with a ref back to the original.
- **Proportion:** nine tasks, each a few files; the test code is given in full because the assertions are the decisions (edges, counts, positions); the implementation bodies are left to the implementer except the two geometry bindings in Task 7 and the key format in Task 1.
