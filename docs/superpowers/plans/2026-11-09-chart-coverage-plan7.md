# Plan 7: chart coverage wave 1 (US waters) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The plotter shows five wave 1 region packs plus an overview pack as one seamless chart (Nav and Fish), all built and released in CI, with offshore depth to 1,000 ft and depths at chart datum per area.

**Architecture:** Every zoom-10 tile has exactly one owner pack (`chartpack/regions/grid.toml` priority order). Region packs hold zoom 10 and deeper for their owned tiles; the `overview` pack holds zoom 9 and shallower. Bathy packs split depth into fine (CUDEM) and coarse (CRM-only, zoom 12 max) sources. The installer merges the installed packs of each kind into one MBTiles per file name inside the set dir (by calling `cheekyplotter --merge-packs`), so the app keeps one source per style source name. The spike in Task 2 confirms merge over app routing before Tasks 4 to 8 are written in stone.

**Tech Stack:** Python 3.12 (chartpack: numpy, GDAL, shapely, contourpy, pyproj, tippecanoe 2.79.0), C++23 and Qt 6.8 (Quick, Sql, Test) with MapLibre Native Qt, bash (installer), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-08-chart-coverage-plan7-design.md` (approved 2026-11-08). Region map: https://claude.ai/artifact/J2hnEnQ3P79ZB7xJMbcJK5

## Global Constraints

- Never use an em-dash character anywhere: code, comments, QML strings, commit messages, docs, issue and PR text.
- US English in new text (color, center, meter, favorite). Existing British identifiers keep their names.
- No local pack builds: every released pack is built by `.github/workflows/chartpack-release.yml` on `ubuntu-24.04`. Re-cutting already released packs for the spike (Task 2) is not a build.
- CHS data stays parked (#89). No Canadian data of any kind; the Canadian side stays clipped.
- No paid data. No GPL code or data. Check the license of every new grid or file before adding it (geoid grids in Task 13).
- Pack cap: 1.5 GB per pack file (`1_500_000_000` bytes). GitHub runner: 16 GB RAM, 14 GB disk, 6 h.
- Contour budget: no depth line off by more than 10 ft anywhere in the wave 1 area, lakes included.
- Pack schema becomes 2 for both kinds (`chartpack/src/chartpack/enc/schema.py` `SCHEMA_VERSION = 2`); plotter `PLOTTER_PACK_SCHEMA_MIN 2`, `PLOTTER_PACK_SCHEMA_MAX 2`; lock file `schema=2`.
- Versions: every new region pack starts at `1.0.0`; plotter `0.3.0`; set `0.3.0` (pre-release).
- Grid zoom is 10 everywhere (`GRID_ZOOM = 10`). Region packs: charts zoom 10 to 16, bathy fine zoom 10 to 16 (DEM 10 to `dem_maxzoom`), bathy coarse zoom 10 to 12. Overview: charts zoom 6 to 9, bathy coarse zoom 6 to 9.
- Plotter build and test: `cmake -S . -B build-plotter -G Ninja -DCM_BUILD_PLOTTER=ON -DCMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64;$HOME/.local/maplibre-qt"`, `cmake --build build-plotter`, `ctest --test-dir build-plotter --output-on-failure` (prefix with `env -u LD_LIBRARY_PATH PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin` if linuxbrew is on PATH).
- chartpack tests: `cd chartpack && PATH="$HOME/.local/bin:$PATH" .venv/bin/pytest -q`. Installer tests: `cd installer/tests && python3 -m pytest -q` (as `installer-ci.yml` runs them).
- Report a pass only from the test runner's own exit status of a fresh run, never from piped output or an old log.
- Results and measurements go on the GitHub issue they belong to (#84 for the spike and seams, #85 for build stats).
- PRs, in order: A (#84, Tasks 1 to 8), B (#85, Tasks 9 and 10), C (#87 and #88, Tasks 11 to 14), D (#14 and #16, Task 15), E (#86 region files, Task 16), F (set lock, Task 18). Each gets one independent adversarial review before merge (reviewer posts its own PR review; threads resolved one by one after verified fixes).

## Review Focus

1. Rolling back from a 0.3.0 set to the installed 0.2.1 set (lock schema 1, one pack per kind, no `merged` dir) with the new installer must work and leave 0.2.1 runnable. Test in Task 7 (`test_rollback_to_schema1_set`).
2. A merged dir that does not match the usable packs (a pack refused at scan, or packs copied in by hand after install) must never be mixed with single packs: the app uses the newest single pack of that kind and shows a notice. Test in Task 5 (`staleMergeFallsBackWithNotice`).
3. A tile present in two packs of one kind (a bad ownership build) must fail the merge with both pack names, and leave no partial merged file. Test in Task 4 (`duplicateTileFailsAndLeavesNothing`).
4. A region box edge lying exactly on a zoom-10 tile line, or two boxes that overlap (near -123.3 W), must leave no tile unowned between them and none owned twice. Test in Task 3 (`test_shared_edge_has_one_owner`, `test_overlap_goes_to_first_in_order`).
5. Fish mode panned off every bathy pack (the Canadian side, or past -127 W) must show the chart without depth layers, never a blank or a crash. Test in Task 5 (`fishOutsideBathyLoads`) and render view in Task 16.

---

### Task 0: Branch (controller, not a subagent)

- [ ] **Step 1:** After the spec and plan PR merges, `git switch -c plan7-stitch origin/main`. Later PRs branch from `main` after the previous PR merges: `plan7-size`, `plan7-depth`, `plan7-fixes`, `plan7-regions`, `plan7-set`.
- [ ] **Step 2:** Confirm the test laptop session is online: ListAgents shows `laptop-chart`. If it is offline, ask the owner to start it before Task 2.

---

## PR A: several packs as one chart (#84)

### Task 1: `--pan-path` dev option for repeatable fast panning

Spike and seam checks need the same fast pan every run. A hidden dev option drives the camera along waypoints.

**Files:**
- Create: `plotter/src/core/PanPath.h`, `plotter/src/core/PanPath.cpp`
- Modify: `plotter/src/app/main.cpp` (options near line 120, timer near the `--frame-stats` block at line 348), `plotter/CMakeLists.txt` (sources and test)
- Test: `plotter/tests/tst_panpath.cpp`

**Interfaces:**
- Produces:
  - `struct PanPoint { double lat, lon, zoom; };`
  - `std::expected<QList<PanPoint>, QString> parsePanPath(const QString& text);` text is `lat,lon,zoom;lat,lon,zoom;...`, at least 2 points.
  - `PanPoint panAt(const QList<PanPoint>& path, qint64 legMs, qint64 tMs);` linear in lat, lon and zoom along each leg, looping back to the first point after the last leg.
  - CLI: `--pan-path TEXT` and `--pan-leg-ms N` (default 1500), hidden like `--frame-stats`. While set, a 16 ms timer sets follow off and moves the map center and zoom to `panAt(...)`.

- [ ] **Step 1: Write the failing tests** in `tst_panpath.cpp`: `parsesTwoPoints` (`"47.9,-122.35,12;48.0,-122.2,14"` gives 2 points, values exact), `rejectsOnePoint` (error), `rejectsBadNumber` (`"47.9,x,12;48,-122,13"` error naming `x`), `midLegIsLinear` (`panAt(path, 1000, 500)` gives lat 47.95, lon -122.275, zoom 13), `loopsBackToStart` (with 2 points the loop is 2 legs; `tMs = 2000` gives the first point).
- [ ] **Step 2:** Run `ctest --test-dir build-plotter -R tst_panpath --output-on-failure`. Expected: FAIL (missing file or symbols).
- [ ] **Step 3:** Implement `PanPath.cpp` and wire the options in `main.cpp`.
- [ ] **Step 4:** Run the full ctest. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): --pan-path dev option for repeatable fast panning (#84)`.

### Task 2: Timed spike on the test laptop (merge versus app routing)

Throwaway code on branch `plan7-spike` (from `plan7-stitch` after Task 1); it is never merged. Only the numbers and the decision are kept.

**Files (spike branch only):**
- Create: `chartpack/scripts/spike_recut.py` (stdlib `sqlite3` only), `chartpack/scripts/spike_router.py` (stdlib `http.server` and `sqlite3` only)

**What the scripts do:**
- `spike_recut.py SRC_PACK_DIR OUT_DIR --corner LAT,LON`: takes the released `charts-puget-north-1.1.0` and `bathy-puget-north-1.1.0` packs (downloaded from their GitHub releases, not built) and writes five copies of each MBTiles: four region files that each own the zoom-10 tiles in one quadrant around the zoom-10 grid corner nearest `--corner` (zoom 10 and deeper), and one overview file with zoom 9 and shallower. Each file keeps the source metadata. It then merges the five back into one file per kind and prints the merge wall time, merged size and source size. Use the corner nearest 47.95 N, -122.35 W (Possession bar to Everett).
- `spike_router.py OUT_DIR --port 8765`: serves `/<source>/<z>/<x>/<y>` from the owner file of each tile (zoom-10 ancestor lookup, built once at start from each file's zoom-10 rows), with a TileJSON at `/<source>.json`. A matching style copy points each source's `url` at `http://127.0.0.1:8765/<source>.json`. This is the upper bound for app routing: an in-app endpoint would do the same lookup without a process hop.

- [ ] **Step 1:** Write both scripts on `plan7-spike`, push the branch.
- [ ] **Step 2:** Send the run to `laptop-chart` via SendMessage, as one numbered list: pull `plan7-spike`, build the plotter, download the two puget-north 1.1.0 release tars from GitHub, run `spike_recut.py`, then three runs of 60 s each with `--pan-path` over the four-pack corner (`47.98,-122.48,11;47.90,-122.25,14;47.98,-122.48,15;47.90,-122.25,12` or the corner's real coordinates printed by the script), `--pan-leg-ms 1200`, `--frame-stats`, `--exit-after-ms 60000`, wrapped in `/usr/bin/time -v`:
  1. baseline: the original one-pack dirs;
  2. merged: the merged files from the script, placed as the pack's `enc.mbtiles`, `bathy.mbtiles`, `dem.mbtiles`;
  3. routed: `spike_router.py` running and the style copy pointing at it.
  For each: frame interval p50, p95, p99 and max, frames over 50 ms, max RSS, and a screenshot at the corner. Plus the merge wall time and disk use.
- [ ] **Step 3:** Post the numbers as a comment on #84 with a plain-language summary and the decision.
- [ ] **Step 4: Decision rule.** Keep merge (spec 5.3 approach 1) unless one holds: merged p95 is more than 10% over baseline, merged shows blank tiles in the screenshot, or the measured merge rate scaled to the wave 1 total (charts plus bathy, estimated 3.3 GB from spec section 4) takes over 5 minutes on the laptop. If merge fails, STOP: post the finding to the owner and amend Tasks 4 to 7 for routing before any further work.
- [ ] **Step 5:** Delete `plan7-spike` from the remote after the comment is posted.

### Task 3: Tile ownership in chartpack

**Files:**
- Create: `chartpack/src/chartpack/grid.py`, `chartpack/regions/grid.toml`
- Modify: `chartpack/src/chartpack/region.py` (new fields), `chartpack/src/chartpack/enc/tiles.py` (zoom range), `chartpack/src/chartpack/enc/schema.py` (`SCHEMA_VERSION = 2`), `chartpack/src/chartpack/cli.py` (`_build_enc` prunes to owned tiles)
- Test: `chartpack/tests/test_grid.py`, `chartpack/tests/test_region.py`, `chartpack/tests/test_enc_tiles.py`

**Interfaces:**
- Produces:
  - `GRID_ZOOM = 10`
  - `tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]` (W, S, E, N)
  - `tiles_meeting(bbox, z: int = GRID_ZOOM) -> set[tuple[int, int]]`: tiles whose interior meets the bbox interior (an edge touch does not count).
  - `assign(regions: list[Region], order: list[str], clip: shapely.Geometry | None) -> dict[tuple[int, int], str]`: each zoom-10 tile meeting any non-overview region box goes to the first name in `order` whose box meets it; a tile fully inside `clip` goes to no one.
  - `load_grid(path: Path) -> list[str]` reads `grid.toml`: `zoom = 10` (must equal `GRID_ZOOM`) and `order = [...]`.
  - `owned_tiles(region: Region, regions_dir: Path) -> set[tuple[int, int]] | None` (None for the overview).
  - `keep_tiles(path: Path, owned: set[tuple[int, int]] | None, *, minzoom: int, maxzoom: int) -> None`: deletes rows outside `minzoom..maxzoom` and, when `owned` is set, rows at zoom 10 or deeper whose zoom-10 ancestor is not owned; then `VACUUM`. Sets metadata `minzoom`, `maxzoom` and `bounds` (union of owned tile bounds, or the region bbox for the overview).
  - `Region.overview: bool` (TOML `overview = true`, default false). Region packs build zoom 10 to 16; the overview builds zoom 6 to 9.
  - `build_enc_mbtiles(..., zooms: tuple[int, int])` replaces the fixed `MINZOOM, MAXZOOM` in the tippecanoe call.
- `grid.toml` for wave 1: `zoom = 10`, `order = ["sound-central", "sound-south", "north-sound", "strait", "wa-coast"]`. With `strait` before `wa-coast`, `wa-coast` is a plain box (-127, 46.15, -123.75, 48.6).

- [ ] **Step 1: Write the failing tests** in `test_grid.py`, using small fake regions:
  - `test_tile_bounds_round_trip`: `tile_bounds(10, 163, 357)` contains (47.9, -122.4) and `tiles_meeting` of a tiny box around that point is `{(163, 357)}`.
  - `test_shared_edge_has_one_owner`: two regions sharing an edge on the latitude of a zoom-10 tile line: every tile meeting either box has exactly one owner, and no tile between them is unowned.
  - `test_overlap_goes_to_first_in_order`: two overlapping boxes; tiles in the overlap go to the first in `order`.
  - `test_tile_inside_clip_is_unowned` and `test_tile_partly_inside_clip_is_owned`.
  - `test_keep_tiles_prunes_unowned_and_out_of_range`: an MBTiles fixture with rows at z9, z10 and z12 under owned and unowned tiles; after `keep_tiles`, only z10 and z12 rows under owned tiles remain and metadata `minzoom` is `10`.
  - `test_overview_keeps_only_low_zooms`: `owned=None, minzoom=6, maxzoom=9` keeps z6 to z9 rows only.
  - `test_grid_zoom_must_be_10`: `zoom = 11` in a grid file raises `RegionError`.
  In `test_enc_tiles.py`, `test_zoom_range_reaches_tippecanoe` asserts the command has `-Z 10 -z 16` for a region and `-Z 6 -z 9` for an overview (patch `run`).
- [ ] **Step 2:** Run the chartpack tests. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement `grid.py`, the region field, the zoom range and the `_build_enc` call: build over the region's cells, then `keep_tiles(enc, owned_tiles(region, args.region.parent), ...)`. Set `SCHEMA_VERSION = 2` and update any test that pins schema 1.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): zoom-10 tile ownership and overview zoom range, pack schema 2 (#84)`.

### Task 4: `PackMerge`: one MBTiles per file name from several packs

**Files:**
- Create: `plotter/src/core/PackMerge.h`, `plotter/src/core/PackMerge.cpp`
- Modify: `plotter/src/app/main.cpp` (`--merge-packs DIR`, handled before the `QGuiApplication` at line 92 with a `QCoreApplication`), `plotter/CMakeLists.txt`
- Test: `plotter/tests/tst_packmerge.cpp`

**Interfaces:**
- Consumes: `PackInfo`, `PackCatalog::scan` (`plotter/src/core/PackCatalog.h`).
- Produces:
  - `inline const QStringList kChartsFiles{"enc.mbtiles"};`, `inline const QStringList kBathyFiles{"bathy.mbtiles", "dem.mbtiles", "bathy-coarse.mbtiles", "dem-coarse.mbtiles"};` (in `PackCatalog.h`, used by scan, merge and the controller).
  - `std::expected<void, QString> mergePacks(const QList<PackInfo>& usable, const QString& outDir);` For each kind with two or more packs, writes `outDir/<kind>/<file>` for every file of that kind. Rows are copied with plain `INSERT` (no `OR REPLACE`); a duplicate `(zoom_level, tile_column, tile_row)` fails with `tile z/x/y is in both <packA> and <packB>`. Metadata: `format` from the first member; `minzoom` min and `maxzoom` max over members that have tiles; `bounds` union; `json` with `vector_layers` united by `id` (first wins); `cheekymarine:valdco` sorted union (charts); `cheekymarine:members` a sorted JSON array of member dir names. Each file is written as `<file>.tmp` and renamed at the end; on any error no file of that kind is left in `outDir/<kind>`.
  - `QStringList mergeMembers(const QString& mbtilesPath);` reads `cheekymarine:members` (empty on any error).
  - CLI: `cheekyplotter --merge-packs DIR` scans `DIR`, merges the usable packs (newest per region) into `DIR/merged`, prints one line per written file, exits 0, or prints the error and exits 1.

- [ ] **Step 1: Write the failing tests** in `tst_packmerge.cpp` with fixture packs built in a `QTemporaryDir` (a helper writes an MBTiles with given rows and metadata through `QSqlDatabase`):
  - `mergesDisjointRows`: two charts packs with rows at (10,163,357) and (10,164,357); merged `enc.mbtiles` has both rows, `minzoom` 10, `members` `["charts-a-1.0.0","charts-b-1.0.0"]`.
  - `unitesMetadata`: `minzoom` 6 and 10 give 6; `maxzoom` 9 and 16 give 16; valdco `[5,10]` and `[10,20]` give `[5,10,20]`; vector layers `depare` plus `depare, soundg` give two layers.
  - `duplicateTileFailsAndLeavesNothing`: the same row in both packs fails naming both packs, and `outDir/charts` has no `.mbtiles` or `.tmp` file.
  - `memberWithNoTilesKeepsOthersZooms`: an overview bathy with empty fine files does not pull fine `minzoom` down.
  - `singlePackKindIsNotMerged`: one charts pack writes nothing under `outDir/charts`.
- [ ] **Step 2:** Run `ctest -R tst_packmerge`. Expected: FAIL.
- [ ] **Step 3:** Implement `PackMerge.cpp` and the CLI path.
- [ ] **Step 4:** Run the full ctest. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): merge several packs per kind into one MBTiles per file (#84)`.

### Task 5: The app loads every usable pack

**Files:**
- Modify: `plotter/src/core/PackCatalog.h/.cpp` (`usable`, bathy files, schema 2), `plotter/src/core/StyleLoader.h/.cpp` (`rewriteStyle` takes a source file map), `plotter/src/core/ChartController.h/.cpp`, `plotter/CMakeLists.txt` (schema 2), `plotter/tests/fixtures/styles/fish-*.json` (four sources)
- Test: `plotter/tests/tst_packcatalog.cpp`, `plotter/tests/tst_styleloader.cpp`, `plotter/tests/tst_chartcontroller.cpp`

**Interfaces:**
- Consumes: `kChartsFiles`, `kBathyFiles`, `mergeMembers` (Task 4).
- Produces:
  - `static QList<PackInfo> PackCatalog::usable(const QList<PackInfo>& packs, QStringView kind);` the newest non-refused version of each region, sorted by region.
  - `std::expected<QJsonObject, QString> rewriteStyle(QJsonObject style, const QString& packDir, const QHash<QString, QString>& sourceFiles);` sources must be named `enc`, `bathy`, `dem`, `bathy-coarse` or `dem-coarse`, each with url `mbtiles://<name>`; each is replaced with `tileUrl(sourceFiles[name])`; a name missing from the map is `source <name> needs a pack that is not there`. Sprite and glyph handling is unchanged.
  - `ChartController` picks, per kind: one usable pack, its own files; several, the files in `<packs>/merged/<kind>/` when `mergeMembers` equals the usable pack dir names; otherwise the newest single pack (highest version, then region name) and `notice` = `Chart packs are not merged. Run sudo cheekymarine install again.` Styles, sprites and glyphs come from the newest usable pack of each kind. Zoom range is min of `minZoom` and max of `maxZoom` over usable charts packs. `valdco` and `legend` are unions (legend deduplicated by `abbr` and `kind`). `fishAvailable()` is true when any bathy pack is usable. The packs dir comes in through a new constructor argument `const QString& packsDir`.
  - `AppInfo`: `chartsPack` and `bathyPack` become `packsInUse` (list of `{kind, region, version}`).

- [ ] **Step 1: Write the failing tests:**
  - `tst_packcatalog`: `usableTakesNewestPerRegion` (a 1.0.0 and 1.1.0 of region a, 1.0.0 of b gives a 1.1.0 and b 1.0.0); `bathyNeedsFourFiles` (missing `dem-coarse.mbtiles` refuses with `missing dem-coarse.mbtiles`); `schemaOneRefused` (`schema 1 not supported`).
  - `tst_styleloader`: `rewritesCoarseSources` (`bathy-coarse` url becomes `mbtiles://<abs path>`); `missingSourceFileIsError`; `unknownSourceIsError` keeps passing with a new name `fooo`.
  - `tst_chartcontroller`: `loadsMergedFilesForSeveralPacks` (two charts and two bathy packs plus matching merged dirs: the loaded style's `enc` url points at `merged/charts/enc.mbtiles`); `staleMergeFallsBackWithNotice` (merged members list a pack that is not installed: url points at the newest single pack and `notice` is the text above); `singlePackUsesOwnFiles`; `zoomAndValdcoAreUnions` (charts minZoom 6 and 10, maxZoom 9 and 16 give minZoom 6, maxZoom 18 with the existing `kOverzoom`); `fishOutsideBathyLoads` (fish style loads with only an overview bathy pack whose fine files are empty, no refusal).
- [ ] **Step 2:** Run the three test binaries. Expected: FAIL.
- [ ] **Step 3:** Implement. Update the fish fixture styles to declare the four bathy sources (Task 12 changes the real styles to match). Set `PLOTTER_PACK_SCHEMA_MIN 2` and `MAX 2`; update the fixtures that write schema 1.
- [ ] **Step 4:** Run the full ctest. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): load every usable pack, merged or single (#84)`.

### Task 6: About page lists every pack

**Files:**
- Modify: `plotter/src/core/AppInfo.h/.cpp`, `plotter/qml/AboutPage.qml` (lines 55 to 66)
- Test: `plotter/tests/tst_appinfo.cpp` (or the existing AppInfo test file), `plotter/tests/qml/tst_aboutpage.qml` if one exists, else a C++ check of the model

**Interfaces:**
- Consumes: `packsInUse` (Task 5).
- Produces: About shows a `Chart packs` heading with one line per pack in use, `packLine(p)` as today, sorted charts first then bathy, then by region; `No chart packs installed` when empty. Refused packs list unchanged.

- [ ] **Step 1: Write the failing test** `aboutListsEveryPack`: six charts and six bathy packs in use give twelve lines in that order.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full ctest. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): About lists every pack in use (#84)`.

### Task 7: Installer and lock schema 2

**Files:**
- Modify: `installer/cheekymarine.sh` (`fetch_parts` line 153, `check_linked_packs` line 134, `unpack_set` line 227, `check_pack_schema` line 257, rollback and version around line 767 to 800), `installer/lock-tool.sh`, `installer/cheekymarine.lock` (schema 2 shape, still the 0.2.1 parts until Task 18), `installer/README.md` (lock format), `.github/workflows/set-release.yml` (release notes list every pack), `installer/tests/harness.py` (fake plotter handles `--merge-packs`)
- Test: `installer/tests/test_lock.py`, `installer/tests/test_download.py`, `installer/tests/test_switch.py`, `installer/tests/test_rollback.py`

**Interfaces:**
- Consumes: `cheekyplotter --merge-packs DIR` (Task 4).
- Produces:
  - Lock schema 2 keys: `schema=2`, `set`, `n2kd.*`, `plotter.*` as today, and per pack `pack.<kind>-<region>.version`, `.tag`, `.asset`, `.sha256`, `.schema`. Any number of packs, at least one charts pack.
  - `lock_packs`: prints the pack ids (`charts-sound-central`, ...) in lock order.
  - After `unpack_set` and `check_pack_schema`, before the flip: `"$CM_SET_DIR/plotter/bin/cheekyplotter" --merge-packs "$CM_SET_DIR/packs"` with `QT_QPA_PLATFORM=offscreen`; a non-zero exit dies with `pack merge failed: <its output>` and nothing is flipped.
  - `lock-tool.sh check|fill` iterate n2kd, plotter and every `pack.*` id; `check` requires every `pack.*.schema` inside the plotter range, and all packs of one kind to share one schema (spec 5.4); test `test_check_rejects_mixed_schema_per_kind` in `test_lock.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_lock.py`: `test_schema2_lists_packs` (three packs give three ids in order); `test_check_rejects_pack_schema_out_of_range`; `test_schema1_lock_is_refused_for_install` (`die` names schema 1).
  - `test_download.py`: `test_fetches_every_pack` (a lock with three packs downloads three tars, skips one already in the store).
  - `test_switch.py`: `test_merge_runs_before_flip` (the fake plotter records the call; `merged/` exists in the new set dir before `current` moves); `test_merge_failure_leaves_current` (fake plotter exits 1: `current` unchanged, message contains `pack merge failed`).
  - `test_rollback.py`: `test_rollback_to_schema1_set` (a previous set laid out as 0.2.1 with one charts and one bathy link and no `merged` dir: rollback flips to it and `version` prints its set).
- [ ] **Step 2:** Run the installer tests. Expected: new tests FAIL.
- [ ] **Step 3:** Implement. Rewrite the committed lock to the schema 2 shape with the current 0.2.1 parts, then `installer/lock-tool.sh embed installer/cheekymarine.lock installer/cheekymarine.sh <tmp>` and copy back so `test_committed_script_embeds_committed_lock` passes.
- [ ] **Step 4:** Run the installer tests and `installer/tests/e2e.sh` if `installer-ci.yml` runs it. Expected: PASS.
- [ ] **Step 5:** Commit `feat(installer): lock schema 2 with any number of packs, merge before flip (#84)`.

### Task 8: PR A

- [ ] **Step 1:** Push `plan7-stitch`, open PR A (`Refs #84`; #84 closes with Task 17's seam check, so not `Fixes`). Body: what changed, the spike comment link, test commands run with their results.
- [ ] **Step 2:** One independent adversarial review that posts its own PR review; adjudicate, fix, resolve threads one by one; merge.

---

## PR B: pack size and CI fit (#85)

### Task 9: Size cap in `chartpack check`

**Files:**
- Modify: `chartpack/src/chartpack/pack/check.py`
- Test: `chartpack/tests/test_pack_check.py`

**Interfaces:**
- Produces: `PACK_CAP_BYTES = 1_500_000_000`; `check_pack` reports `pack is <n> bytes, over the 1.5 GB cap` when the sum of the manifest's file bytes exceeds it. For schema 2, bathy packs must list the four files of `kBathyFiles` (Task 4); fine files may hold zero tiles only when the manifest region is `overview`.

- [ ] **Step 1: Write the failing tests** `test_over_cap_is_reported` (patch `PACK_CAP_BYTES` to 100 on a fixture pack), `test_bathy_needs_coarse_files`, `test_empty_fine_files_only_for_overview`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): 1.5 GB pack cap in check (#85)`.

### Task 10: Runner fit in CI, no local builds

**Files:**
- Create: `chartpack/scripts/fit-guard.sh`
- Modify: `.github/workflows/chartpack-release.yml` (remove the dev-machine fallback note at lines 6 to 8; add `workflow_dispatch` with inputs `pack` and `region` that builds, checks and uploads an artifact without publishing; run the build steps through the guard; attach `build-stats.json` to the release), `docs/superpowers/specs/2026-10-28-chartpack-design.md` (Pack size section, line 45)
- Test: `chartpack/tests/test_fit_guard.py`

**Interfaces:**
- Produces: `fit-guard.sh OUT_JSON -- CMD...` runs CMD under `/usr/bin/time -v`, then writes `{"max_rss_kb", "elapsed_s", "disk_free_kb"}` to OUT_JSON and exits 1 with `runner fit: <what> over the limit` when max RSS > 12 GiB (12582912 kB), free disk on the work volume < 2 GiB, or elapsed > 5 h. Otherwise it exits with CMD's status.
- Spec text for the Pack size section: the 1.5 GB cap per pack file, splits only on the ownership grid (never by kind halves or zoom ranges), every pack builds on `ubuntu-24.04` within the guard limits, and no local builds (owner, 2026-11-08).

- [ ] **Step 1: Write the failing tests** in `test_fit_guard.py` (run the script with `CMD` = small shell commands and a fake `time` shim on PATH printing a chosen `Maximum resident set size`): `test_passes_and_writes_stats`, `test_rss_over_limit_fails`, `test_command_failure_passes_through`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the script, the workflow changes and the spec text.
- [ ] **Step 4:** Run the chartpack tests and `actionlint` on the workflow if installed (else `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/chartpack-release.yml`). Expected: PASS.
- [ ] **Step 5:** Commit `ci(chartpack): runner fit guard, dry-run builds, no local builds (#85)`.
- [ ] **Step 6:** Push `plan7-size`, open PR B (`Refs #85`; #85 closes when Task 16's builds pass the guard). Review, fix, merge as in Task 8.

---

## PR C: offshore depth and datum (#87, #88)

### Task 11: Contour levels to 1,000 ft

**Files:**
- Modify: `chartpack/src/chartpack/bathy/contours.py` (`DEPTHS_FT`, `MAJOR_FT`, `BASE_FT`, `min_zoom`), `chartpack/src/chartpack/bathy/bands.py` (deepest band), `chartpack/src/chartpack/style/fish.py` if a band color list is keyed by level
- Test: `chartpack/tests/test_bathy_contours.py`, `chartpack/tests/test_bathy_bands.py`, `chartpack/tests/test_style_fish.py`

**Interfaces:**
- Produces:
  - `DEPTHS_FT = list(range(10, 301, 10)) + list(range(350, 601, 50)) + list(range(700, 1001, 100))`
  - `MAJOR_FT = frozenset({60, 120, 180, 300, 400, 500, 600, 800, 1000})`
  - `BASE_FT` adds 350, 450, 550, 700, 900 (shown from z12); 400, 500, 600, 800, 1000 are majors (from z10).
  - Bands: the last band is `depth_min_ft 1000, depth_max_ft None` ("deeper than 1,000 ft"); `min_zoom(hi or 1000)`.
  - No contour deeper than 1,000 ft is emitted.

- [ ] **Step 1: Write the failing tests:** `test_levels_match_spec` (the list above exactly), `test_no_contour_past_1000` (a synthetic grid sloping to 500 m gives no `depth_ft` > 1000), `test_majors_offshore` (`min_zoom(500) == 10`, `min_zoom(450) == 12`), `test_deepest_band_is_past_1000`, and in `test_style_fish.py` a band color exists for every band.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): contour levels to 1,000 ft (#87)`.

### Task 12: Fine and coarse bathy, built per owned tile

**Files:**
- Create: `chartpack/src/chartpack/bathy/blocks.py`
- Modify: `chartpack/src/chartpack/cli.py` (`_fetch_bathy`, `_build_bathy`), `chartpack/src/chartpack/bathy/crm.py` (fetch per block, and at a set resolution for the overview), `chartpack/src/chartpack/bathy/dem.py` (`skip_empty`), `chartpack/src/chartpack/bathy/contours.py` (`COARSE_BANDS`, `OVERVIEW_BANDS`), `chartpack/src/chartpack/bathy/tiles.py` (two outputs, zoom ranges), `chartpack/src/chartpack/pack/assemble.py` (four files), `chartpack/src/chartpack/style/fish.py` (four sources, coarse layers under fine)
- Test: `chartpack/tests/test_bathy_blocks.py`, `chartpack/tests/test_bathy_dem.py`, `chartpack/tests/test_bathy_tiles.py`, `chartpack/tests/test_pack_assemble.py`, `chartpack/tests/test_style_fish.py`

**Interfaces:**
- Consumes: `owned_tiles`, `tile_bounds`, `keep_tiles` (Task 3); levels (Task 11).
- Produces:
  - `iter_blocks(owned: set[tuple[int, int]], margin_deg: float = 0.02) -> Iterator[tuple[tuple[int, int], tuple[float, float, float, float], tuple[float, float, float, float]]]`: per owned zoom-10 tile, its core bounds and its read bounds (core plus margin).
  - `build_block(core, read, cudem_tiles, crm_path, datum) -> BlockResult` with `fine_contours`, `fine_bands`, `coarse_contours`, `coarse_bands` (features clipped to `core`), and `fine_grid`, `coarse_grid` (with transforms) for the DEMs. Fine is the CUDEM-then-CRM merge as today restricted to CUDEM cells (source index 1); coarse is CRM at 1 arc-second where the block has no CUDEM cell (source index 2 cells, coarsened). Memory per block stays under 3 GB (one zoom-10 tile at 1/9 arc-second is about 11k by 8k cells).
  - `COARSE_BANDS = ((10, 11, 150.0), (12, 12, 30.0))`, `OVERVIEW_BANDS = ((6, 9, 300.0),)` with major levels only.
  - `build_dem_mbtiles(..., skip_empty: bool = False)`: with `skip_empty`, a tile whose source cells are all nan is not written.
  - Bathy pack files: `bathy.mbtiles` (fine vector, z10 to 16), `dem.mbtiles` (fine, z10 to `dem_maxzoom`), `bathy-coarse.mbtiles` (z10 to 12; overview z6 to 9), `dem-coarse.mbtiles` (same). Every file goes through `keep_tiles` with the owned set. The overview writes empty fine files with metadata only.
  - Fish style sources `enc`, `bathy`, `dem`, `bathy-coarse`, `dem-coarse`; each bathy layer has a `-coarse` twin on the coarse source placed directly below the fine layers. The layer list is fixed: it does not depend on the packs.

- [ ] **Step 1: Write the failing tests** with the synthetic ridge grids of `tests/make_ridge.py`:
  - `test_iter_blocks_cover_owned_exactly` (cores of 4 owned tiles tile their union, no overlap).
  - `test_block_features_clipped_to_core` (no coordinate of any feature outside `core`).
  - `test_fine_and_coarse_split_by_source` (a grid half CUDEM, half CRM: fine features only in the CUDEM half, coarse only in the CRM half).
  - `test_coarse_maxzoom_is_12` (`bathy-coarse.mbtiles` metadata `maxzoom` is `12`, no rows deeper).
  - `test_dem_skip_empty` (an all-nan quarter writes no tile there).
  - `test_overview_has_empty_fine_files`.
  - `test_fish_style_coarse_under_fine` (index of each `-coarse` layer is below the first fine bathy layer; sources are exactly the five names).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. `_build_bathy` loops `iter_blocks`, appends each block's features to the four GeoJSONSeq files and its DEM tiles to the two DEM files, then runs tippecanoe once per output and `keep_tiles`.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): fine and coarse bathy per owned tile, CRM capped at zoom 12 (#87)`.

### Task 13: Datum per area, CRM from EGM2008

**Files:**
- Create: `chartpack/src/chartpack/datum/__init__.py`, `chartpack/src/chartpack/datum/offsets.py`, `chartpack/src/chartpack/datum/geoid.py`, `chartpack/regions/datum/wa-stations.toml`
- Modify: `chartpack/src/chartpack/region.py` (`[datum] file = "datum/wa-stations.toml"` replaces the constants), `chartpack/src/chartpack/bathy/merge.py` (`to_mllw_depth` takes an array offset), `chartpack/src/chartpack/bathy/blocks.py`, `chartpack/src/chartpack/bathy/tiles.py` (manifest `datum` entry lists the stations file and its sha256), `chartpack/NOTICE` (geoid grid credits)
- Test: `chartpack/tests/test_datum_offsets.py`, `chartpack/tests/test_datum_geoid.py`, `chartpack/tests/test_bathy_merge.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Station: id: str; name: str; lat: float; lon: float; navd88_to_mllw_m: float`
  - `load_datum(path: Path) -> Datum` with `stations: list[Station]` and `lakes: list[Lake]` (Task 14).
  - `navd88_to_mllw_grid(stations, transform, shape) -> np.ndarray` (float32): inverse distance weighting, power 2, over the 3 nearest stations, computed on a 0.05 degree grid and bilinear-resampled to `shape`. Far offshore the nearest coastal stations dominate (spec 8 asks for the nearest station there; this is continuous and the test below bounds the difference).
  - `SOURCE_VERTICAL = {"cudem": "navd88", "crm": "egm2008"}`; plan 8 adds sources with `"mllw"` (no shift).
  - `egm2008_to_navd88_m(transform, shape, cache: Path) -> np.ndarray`: `N_egm2008 - N_geoid18` per cell, from PROJ-data grids `us_nga_egm08_25.tif` and `us_noaa_g2018u0.tif` fetched from `https://cdn.proj.org/` into the cache (verify both are public domain before use and credit them in `NOTICE`). CRM heights become NAVD88 by adding this, then MLLW like CUDEM.
  - `wa-stations.toml`: NOAA CO-OPS stations with published NAVD88 and MLLW, from the CO-OPS datums API (`https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/<id>/datums.json?units=metric`), each with `source` URL and retrieval date. Start from Seattle 9447130, Tacoma 9446484, Olympia 9446969 (or the nearest with datums), Port Townsend 9444900, Friday Harbor 9449880, Bellingham 9449211, Port Angeles 9444090, Neah Bay 9443090, La Push 9442396, Toke Point 9440910 or Westport 9441102, Astoria or Columbia mouth 9439040. The builder confirms the list and records any substitution in the file.

- [ ] **Step 1: Write the failing tests:**
  - `test_offset_equals_station_at_station` (at each station's own cell the grid is within 0.01 m of its value).
  - `test_offset_between_two_stations_is_between` (midway between two stations the value lies between theirs).
  - `test_far_offshore_close_to_nearest` (synthetic stations: a point 50 km west of the nearest station is within 0.15 m of it when the next station differs by 0.3 m).
  - `test_seattle_offset_matches_today` (with the real `wa-stations.toml`, the Seattle cell is 0.715 m within 0.01).
  - `test_crm_goes_through_navd88` (a constant EGM2008 grid with a patched geoid difference of 0.5 m gives depths 0.5 m shallower than the old MSL path would, sign checked by hand in the test comment).
  - `test_stations_file_has_sources` (every station has a `source` URL and `retrieved` date).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Fetch the CO-OPS datums for the station list and record them in `wa-stations.toml` (fetching data is allowed; packs are still built only in CI).
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): MLLW offsets per area from CO-OPS stations, CRM via NAVD88 (#88)`.

### Task 14: Lake Union and Lake Washington depths

**Files:**
- Create: `chartpack/regions/datum/lakes.geojson`
- Modify: `chartpack/regions/datum/wa-stations.toml` (`[[lakes]]` entries), `chartpack/src/chartpack/datum/offsets.py`, `chartpack/src/chartpack/bathy/blocks.py`
- Test: `chartpack/tests/test_datum_offsets.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Lake: name: str; low_level_navd88_m: float; source: str`
  - `[[lakes]]` in the datum file: `name`, `low_level_navd88_m` (the low end of the US Army Corps of Engineers managed range for Lake Washington and Lake Union, converted to NAVD88; record the Corps datum value, the conversion and both source URLs), `source`.
  - `lakes.geojson`: one Polygon per lake named as in the TOML, east of the Hiram M. Chittenden Locks, taken from the ENC (`LAKARE` or the depth areas of the US5SEA cells) or the USGS National Hydrography Dataset (public domain). Not OpenStreetMap (ODbL).
  - Inside a lake polygon, depth = `low_level_navd88_m - elev_navd88`; outside, the station offset applies.

- [ ] **Step 1: Write the failing tests** `test_lake_depth_from_low_level` (a synthetic lake polygon over a flat bottom at NAVD88 0 m with low level 6.0 m gives 6.0 m depth inside and the station path outside), `test_lake_file_names_match` (every polygon name has a `[[lakes]]` entry and the reverse).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement and add the real data with sources.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): lake depths from the managed low level (#88)`.
- [ ] **Step 6:** Push `plan7-depth`, open PR C (`Refs #87`, `Refs #88`; both close with Task 17). Review, fix, merge as in Task 8.

---

## PR D: #14 and #16

### Task 15: Honor `bathy_sources`; clip ENC fallback contours

**Files:**
- Modify: `chartpack/src/chartpack/region.py` (validate `bathy.sources`), `chartpack/src/chartpack/cli.py` (`_fetch_bathy`, `_build_bathy` use them), `chartpack/src/chartpack/bathy/tiles.py` (`enc_fallback_contours` takes the clip)
- Test: `chartpack/tests/test_region.py`, `chartpack/tests/test_cli.py`, `chartpack/tests/test_bathy_tiles.py`

**Interfaces:**
- Produces:
  - `load_region` raises `RegionError("unknown bathy source: <name>")` for a name not in `SOURCE_VERTICAL` (Task 13), and when `sources` is empty.
  - Fetch and build skip CUDEM when `"cudem"` is not listed and CRM when `"crm"` is not listed (no fine or no coarse output then; the files still exist, empty, so the pack layout stays fixed).
  - `enc_fallback_contours(enc_cells, uncovered, clip: shapely.Geometry | None)`: lines are clipped to `uncovered.difference(clip)`.

- [ ] **Step 1: Write the failing tests** `test_unknown_bathy_source_is_error`, `test_empty_bathy_sources_is_error`, `test_crm_only_region_fetches_no_cudem` (patch `download`, assert no CUDEM url), `test_fallback_contours_clipped` (an ENC line crossing a clip polygon keeps only the part outside it).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `fix(chartpack): honor bathy sources, clip ENC fallback contours (#14, #16)`.
- [ ] **Step 6:** Push `plan7-fixes`, open PR D (`Fixes #14`, `Fixes #16`). Review, fix, merge as in Task 8.

---

## PR E and releases: wave 1 regions (#86)

### Task 16: Region files, CI builds, pack releases

**Files:**
- Create: `chartpack/regions/sound-south.toml`, `sound-central.toml`, `north-sound.toml`, `strait.toml`, `wa-coast.toml`, `overview.toml`
- Modify: `chartpack/regions/clip/canada-wa.geojson` (regenerate with `chartpack/scripts/make-clip.py` so it covers all Canadian water inside the wave 1 boxes, west to -127 W and north to 49.05 N), `chartpack/tests/test_regions.py`, `chartpack/README.md` (region list)
- Delete: `chartpack/regions/puget-north.toml` (retired; its test moves to the new regions)

**Interfaces:**
- Consumes: Tasks 3, 11 to 15.
- Produces: boxes from spec section 4 (`wa-coast` is the box -127, 46.15, -123.75, 48.6; `grid.toml` order cuts the strait out). ENC cells per band from `chartpack cells` against the current catalog: every active cell meeting the region's owned tiles, bands 3 to 5 for Sound regions, bands 1 to 5 for `strait` and `wa-coast`, bands 1 to 3 for `overview`. `bathy.sources = ["cudem", "crm"]` everywhere. `[datum] file = "datum/wa-stations.toml"`. Seabed as in `puget-north` where the CMECS blocks fall in the region. Render views: Everett (47.98, -122.23), Possession bar (47.90, -122.37), Jeff Head (47.75, -122.47), Tacoma Narrows (47.27, -122.55), Friday Harbor (48.54, -123.01), the corner (48.2, -123.3), Neah Bay grounds (48.3, -125.3), Lake Washington (47.62, -122.26), plus the old puget-north views, each in the region that owns it. All versions `1.0.0`.

- [ ] **Step 1: Write the failing tests** in `test_regions.py`:
  - `test_wave1_regions_load` (all six load).
  - `test_every_box_tile_is_owned_or_canadian` (every zoom-10 tile meeting any wave 1 box has an owner unless it is fully inside the clip).
  - `test_no_region_owns_nothing`.
  - `test_views_inside_owned_tiles` (each view's point lies in a tile its region owns).
  - `test_overview_lists_low_bands_only`.
  - `test_puget_north_is_gone`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the region files and the clip.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): wave 1 US regions and overview (#86)`. Push `plan7-regions`, open PR E (`Refs #86`), review, fix, merge.
- [ ] **Step 6: Dry runs.** Run the `chartpack-release` workflow by `workflow_dispatch` for all twelve (kind, region) pairs from `main`. Each must pass `chartpack check` and the fit guard. Post a table of size, max RSS and elapsed per pack on #85. If a pack is over 1.5 GB or over the guard, lower the CRM zoom cap for that region first (spec 7), else split the region on the ownership grid (spec 6) with the owner's OK, and repeat.
- [ ] **Step 7: Render.** Download the dry-run artifacts and run `chartpack render` on them with each region's views, Nav and Fish, day palette. This only reads built packs. Post the images on #86.
- [ ] **Step 8: Release.** Push the twelve tags `charts-<region>-v1.0.0` and `bathy-<region>-v1.0.0` from `main`. Confirm each release has its tar, `SHA256SUMS` and `build-stats.json`. Close #85 with the stats comment link.

### Task 17: Plotter release and seam check on the test laptop

- [ ] **Step 1:** Bump the plotter to `0.3.0`, merge, push tag `plotter-v0.3.0`; confirm the release asset.
- [ ] **Step 2:** On `laptop-chart` (SendMessage, numbered steps): install the plotter release, download the twelve packs from their releases, run `cheekyplotter --merge-packs` on the pack dir and time it, then 60 s `--pan-path` runs with `--frame-stats` under `/usr/bin/time -v` over: the `sound-central`/`north-sound`/`strait` corner (48.2, -123.3), the `sound-central`/`north-sound` seam, and the `sound-south`/`sound-central` seam at 47.45 N; zooms 9 to 15 so the overview edge is crossed too. Screenshots at each seam in Nav and Fish. Baseline: the same runs on puget-north 1.1.0 with plotter 0.2.1 at Possession bar.
- [ ] **Step 3:** Post numbers and screenshots on #84 with a plain-language verdict against spec section 11: no blank tiles, no stutter beyond the one-pack baseline (p95 within 10%), no doubled or cut lines. A failure goes back to the owning task before Task 18.

### Task 18: Set lock 0.3.0 (PR F)

**Files:**
- Modify: `installer/cheekymarine.lock`, `installer/cheekymarine.sh` (embedded lock)

- [ ] **Step 1:** On `plan7-set`, write the schema 2 lock: `set=0.3.0`, n2kd as today, `plotter` 0.3.0, the twelve `pack.*` entries. Run `installer/lock-tool.sh fill installer/cheekymarine.lock`, then `installer/lock-tool.sh check installer/cheekymarine.lock` (expected exit 0), then embed into the script.
- [ ] **Step 2:** Run the installer tests. Expected: PASS.
- [ ] **Step 3:** Commit `chore(installer): set 0.3.0 with wave 1 packs`, open PR F, review, fix, merge, push tag `cheekymarine-v0.3.0`; mark the release pre-release.

### Task 19: Owner check on the tablet

- [ ] **Step 1:** Ask the owner to install set 0.3.0 on CapnButts from the release (`CapnButts-FirstMate` session can read the About page and logs; the owner confirms the screen).
- [ ] **Step 2:** The owner checks Nav and Fish across the packs, especially at the seams and at Jeff Head, Possession bar, Tacoma Narrows, the San Juans, the Strait, the Neah Bay grounds and Lake Washington: contours in the right places, navigation symbols everywhere, nothing missing or doubled at the edges.
- [ ] **Step 3:** Record the result on #86. On the owner's OK, close #84, #86, #87 and #88 with links, and mark the set release as no longer pre-release only if the owner says so.
