# Plan 8: chart coverage wave 2 (British Columbia) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The plotter shows the BC coast and offshore water as part of the same seamless chart: Fish from CHS NONNA depth with coarse fillers, Nav from depth-derived layers plus the open BC shoreline and the NOAA cells that reach into Canada, all built and released in CI with the CHS notice.

**Architecture:** A fetch workflow pulls NONNA grids and the BC coastline once per region and stores them as assets of a source-data release; pack builds read only those assets. Depth sources are picked per side of the border (spec 6 table) inside the existing fine and coarse block build. BC charts packs fill the existing `enc` vector layers from derived features (shoal-biased, no fill-in) plus two optional new layers, so pack schema 2 and the install merge stay as they are. The app picks its on-chart notice from notice areas carried in pack metadata.

**Tech Stack:** Python 3.12 (chartpack: numpy, GDAL, shapely, contourpy, pyproj, tippecanoe 2.79.0), C++23 and Qt 6.8 with MapLibre Native Qt, bash (installer), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-11-chart-coverage-plan8-design.md` (approved 2026-11-11). It builds on `docs/superpowers/specs/2026-11-08-chart-coverage-plan7-design.md` and the plan 7 plan `docs/superpowers/plans/2026-11-09-chart-coverage-plan7.md`. Research: #89. Log issue for every check, number and render: #90.

## Global Constraints

- Never use an em-dash character anywhere: code, comments, QML strings, commit messages, docs, issue and PR text. US English in new text.
- No paid data. No GPL code or data. No CHS chart objects by any route. No stand-in navaids, routes, anchorages, names or marinas (spec 3).
- No local pack builds. Every released pack is built by `.github/workflows/chartpack-release.yml` on `ubuntu-24.04` (16 GB RAM, 14 GB disk, 6 h job limit; fit guard 12 GiB RSS, 2 GiB free disk, 5 h).
- Canadian hosts are called only by the fetch workflow (Task 2), never by a pack build, a dry run, a tag run or a test. Tests use fixtures. Fetch manners: one connection, requests in sequence, 2 s pause after each response, User-Agent `CheekyMarine-pack-builder/<chartpack version> (+https://github.com/jjveleber/CheekyMarine)`, 60 s back-off and one retry on a 5xx or a timeout, stop for good on HTTP 403 or 429. Before the first request to a host, read its robots.txt and refuse a disallowed path.
- Pack cap `PACK_CAP_BYTES = 1_500_000_000` per pack file. An area over the cap splits on the zoom-10 grid. Zoom caps are global and do not change: fine vector 16, fine DEM 14 (`dem_maxzoom = 14`), coarse 12, overview 6 to 9.
- Pack schema stays 2 (`SCHEMA_VERSION = 2`, `PLOTTER_PACK_SCHEMA_MIN 2`, `PLOTTER_PACK_SCHEMA_MAX 2`). Task 9 Step 1 is the gate: if it shows schema 2 cannot hold the change, stop and tell the controller (spec 12: schema 3 means every wave 1 pack is rebuilt and the owner is told).
- Versions: BC packs `1.0.0`; rebuilt US packs and `overview` `1.1.0`; plotter `0.4.0`; set `0.4.0` (pre-release).
- Depth source names (region files, coverage labels, feature `src`): `cudem`, `crm`, `nonna10`, `nonna100`, `etopo`. Grades: `nonna10` is "Survey depth", `nonna100` is "Coarse survey depth (100 m grid)", `crm` on the Canadian side and `etopo` are "Rough depth, worldwide grid".
- Notice strings, exact:
  - Nav, BC outside NOAA band 3 coverage on screen: `BC: depth and shoreline only. Most hazards and navaids not shown. Not for navigation.`
  - Nav, only NOAA-strip BC water on screen: `BC: coarse US chart data. Not for navigation.`
  - Fish, any BC water on screen: `BC: CHS survey depths where available, rough elsewhere. Chart datum. Not for navigation.`
  - Legend: `No survey data`; `US chart data ends here (coarse scale). Beyond: most hazards and navaids not shown.`; `Coarse survey depth (100 m grid)`; `Rough depth, worldwide grid`.
- CHS notice: the four paragraphs of spec section 11, verbatim, with "the CheekyMarine project" as the maker, followed by `Contains information licensed under the Open Government Licence – Canada.` and `https://open.canada.ca/en/open-government-licence-canada`. Shoreline credit: `Contains information licensed under the Open Government Licence – British Columbia.` (those two licence lines contain an en dash, which is part of the required text).
- Contour budget of 10 ft applies to `nonna10` water only.
- chartpack tests: `cd chartpack && PATH="$HOME/.local/bin:$PATH" .venv/bin/python -m pytest -q`. Plotter build and test and installer tests: as in the plan 7 plan's Global Constraints.
- Report a pass only from the test runner's own exit status of a fresh run. Never `rm` a path built from a variable that could be empty; download into fresh directories.
- Tags are pushed one per `git push`, about 2 minutes apart, only after the owner's OK, with a `chartpack-release` run confirmed per tag.
- PRs, in order: A (fetch, Tasks 1 to 2), B (#18, Task 4), C (depth, Tasks 5 to 8), D (Nav, Tasks 9 to 12), E (app, Tasks 13 to 14), F (regions, Task 15), G (set lock, Task 18). Each gets one independent adversarial review before merge; the reviewer posts its own PR review; threads are resolved one by one after verified fixes. Branch from `origin/main` in the worktree `.claude/worktrees/plan8`; the main checkout belongs to another session.

## Review Focus

1. The NONNA WCS answers HTTP 200 with an XML error body, or a truncated TIFF, for one chunk. Expected: the chunk is retried once, then the fetch fails naming the chunk, and no partial asset is uploaded. Test in Task 2 (`test_wcs_error_body_is_not_stored`).
2. NONNA nodata or sign read wrong (nodata as depth 0, or drying heights as depths). Expected: nodata is nan, stored negative values become positive depth, positive values stay drying heights above datum. Test in Task 6 (`test_nonna_sign_and_nodata`).
3. The 0.4.0 set installs over 0.3.0 with `sound-south` and `sound-central` not rebuilt: their files lack the new optional layers and metadata keys. Expected: the merge succeeds and those areas draw as before. Test in Task 13 (`mergeAcceptsMembersWithoutNoticeAreas`).
4. A view that shows US and BC water together, and a pan across the border. Expected: the BC notice whenever any BC notice area meets the viewport, the US notice otherwise, with no change while the set of areas in view is unchanged. Test in Task 13 (`mixedViewGetsBcNotice`, `usOnlyViewKeepsDefault`).
5. The coastline of a region does not close into land polygons at the region edge (lines cut by the box). Expected: the land builder closes rings along the read box, and a ring it cannot close fails the build instead of drawing land as water or "No survey data" over land. Test in Task 9 (`test_land_closes_at_box_edge`, `test_unclosable_ring_fails`).

---

### Task 0: Branch and merge of the spec PR (controller)

- [ ] **Step 1:** PR #118 (spec and this plan) merges after the owner has seen the plan. Delete the branch on merge.
- [ ] **Step 2:** `git fetch origin && git switch -c plan8-fetch origin/main` in the worktree. Later PRs branch from `origin/main` after the previous one merges: `plan8-lat`, `plan8-depth`, `plan8-nav`, `plan8-app`, `plan8-regions`, `plan8-set`.
- [ ] **Step 3:** Start the SDD ledger at `.superpowers/sdd/2026-11-11-chart-coverage-plan8/progress.md`.

---

## PR A: source checks and the fetch workflow (#90)

### Task 1: Source checks (spec 5), results on #90

Research task, no code. One request at a time, 2 s apart, robots.txt first.

- [ ] **Step 1: NONNA WCS.** Read `https://nonna-geoserver.data.chs-shc.ca/robots.txt`. Fetch `GetCapabilities` and `DescribeCoverage` for `nonna__NONNA 10 Coverage` and `nonna__NONNA 100 Coverage`. Record: whether `/geoserver/wcs` is allowed; native CRS and pixel size; nodata value; any stated request limit. Fetch one 0.1 degree box at the head of Toba Inlet from both coverages and record the sign of depths and of drying heights.
- [ ] **Step 2: NONNA index.** Download `NONNA10.zip` and `NONNA100.zip` (URLs on #89) after reading the robots.txt of `api-proxy.edh-cde.dfo-mpo.gc.ca`. Record the field that names each tile and the count of NONNA-10 tiles per BC region box (spec 4).
- [ ] **Step 3: NOAA Canadian-side content.** Read the NOAA ENC terms page and the `DSID`/`M_NPUB`/`M_SREL` records of `US3WA1EF` and `US3AK1DY` in `chartpack/cache`. Record any restriction on content sourced from CHS.
- [ ] **Step 4: Freshwater Atlas coastline.** Read the robots.txt of `openmaps.gov.bc.ca`. Fetch one page (100 features) of `WHSE_BASEMAPPING.FWA_COASTLINES_SP` near Victoria. Record: the tide level the line follows (from the layer metadata), whether island rings are closed, the paging field.
- [ ] **Step 5: ETOPO shift source.** Find an open, robots-allowed source for the height of mean sea level above chart datum at Canadian Pacific tide stations (CHS station data). Record the URL, licence and the values for Victoria, Tofino, Port Hardy, Bella Bella, Prince Rupert and one Haida Gwaii station. If none is open, say so.
- [ ] **Step 6:** Post all results as one comment on #90. A failed check (WCS disallowed, a NOAA restriction, coastline unusable) stops that source: tell the controller, who asks the owner. Step 5 with no open source is not a stop: Task 7 then uses no shift and says so in the NOTICE.

### Task 2: Polite fetching, NONNA and coastline fetchers, the source-data release

**Files:**
- Create: `chartpack/src/chartpack/fetching.py`, `chartpack/src/chartpack/bathy/nonna.py`, `chartpack/src/chartpack/coast.py`, `.github/workflows/chartpack-sources.yml`, `chartpack/regions/test-toba.toml` (a one-inlet region for the spike: bbox -124.6, 50.3, -124.2, 50.6; not in `grid.toml`; `test_regions.py` skips it by name)
- Modify: `chartpack/src/chartpack/cli.py` (new subcommand `fetch-sources`), `chartpack/NOTICE`, `chartpack/README.md`
- Test: `chartpack/tests/test_fetching.py`, `chartpack/tests/test_bathy_nonna.py`, `chartpack/tests/test_coast.py`, fixtures under `chartpack/tests/fixtures/nonna/` (two 64 by 64 Float32 GeoTIFFs written by a `make_nonna.py` helper, one XML error body)

**Interfaces:**
- Consumes: Task 1 results (nodata value, sign, tile name field, paging field). Where a value below is marked (Task 1), use the recorded one.
- Produces:
  - `class FetchStopped(Exception)`; `class PoliteSession: __init__(self, user_agent: str, pause_s: float = 2.0, opener=urllib.request.urlopen, sleep=time.sleep)`; `get(self, url: str) -> bytes` (robots check per host cached, pause after each response, one retry after 60 s on 5xx or timeout, `FetchStopped` on 403, 429 or a disallowed path).
  - `nonna.WCS_BASE = "https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs"`; `nonna.COVERAGE = {"nonna10": "nonna__NONNA 10 Coverage", "nonna100": "nonna__NONNA 100 Coverage"}`.
  - `nonna.wcs_url(product: str, bbox_3857: tuple[float, float, float, float]) -> str` (WCS 2.0.1 `GetCoverage`, `subset=X(..)`, `subset=Y(..)`, `format=image/tiff`).
  - `nonna.index_boxes(index_shp: Path, bbox: tuple[float, float, float, float]) -> list[tuple[float, float, float, float]]`: lon/lat boxes of index tiles meeting `bbox`, sorted.
  - `nonna.fetch_nonna(product: str, boxes: list[tuple], out: Path, session: PoliteSession) -> dict`: one request per box, each checked to be a Float32 GeoTIFF, mosaicked into one tiled, DEFLATE-compressed GeoTIFF at `out` in the native grid (no resampling); returns `{"chunks": n, "bytes": size, "seconds": t}`.
  - `nonna.read_nonna(path: Path, bbox, res_deg: float) -> Grid` (the `Grid` of `bathy/cudem.py`): depth in meters, positive down, nan where nodata; values above datum are negative depth.
  - `coast.fetch_coastline(bbox, out: Path, session: PoliteSession) -> int`: paged WFS GeoJSON from `https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.FWA_COASTLINES_SP/ows`, `sortBy=OBJECTID`, written as one gzip GeoJSONSeq; returns the feature count.
  - CLI: `chartpack fetch-sources --region <file.toml> --out <dir>` writes `nonna10-<region>.tif`, `nonna100-<region>.tif`, `coast-<region>.geojson.gz` and `fetch-stats-<region>.json` (chunks, bytes, seconds per file).
  - Workflow `chartpack-sources.yml`: `workflow_dispatch` with inputs `region` (matches `[a-z0-9-]+`) and `stage` (`fetch` or `derive`; `derive` is added in Task 9). Stage `fetch` runs `fetch-sources`, then `gh release upload sources-bc-1 <files> --clobber` (creating the release on first use with the CHS notice of the Global Constraints as its notes). Each asset must be under 2 GiB or the job fails before upload.

- [ ] **Step 1: Write the failing tests.**
  - `test_robots_disallow_stops` (a fake opener serving `Disallow: /geoserver/`: `get` raises `FetchStopped`, no data request made).
  - `test_pause_after_each_response` (fake `sleep` records `2.0` once per request).
  - `test_403_and_429_stop_for_good`; `test_5xx_retries_once_after_60s`.
  - `test_wcs_url_has_coverage_and_subsets` (asserts `coverageId=nonna__NONNA%2010%20Coverage`, `subset=X(` and `subset=Y(`).
  - `test_wcs_error_body_is_not_stored` (the XML fixture for one chunk, twice: `fetch_nonna` raises naming the box, `out` does not exist).
  - `test_mosaic_keeps_native_values` (two fixture chunks: every cell of the mosaic equals its source cell).
  - `test_index_boxes_filters_and_sorts` (a 3-tile fixture shapefile).
  - `test_coastline_pages_until_short_page`.
  - `test_fetch_sources_cli_writes_stats`.
- [ ] **Step 2:** Run. Expected: FAIL (modules missing).
- [ ] **Step 3:** Implement. `urllib.robotparser` for robots; GDAL for the TIFF check and mosaic (`BuildVRT` then `Translate` with `TILED=YES`, `COMPRESS=DEFLATE`, `PREDICTOR=3`, `BIGTIFF=IF_SAFER`).
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Add the NONNA, coastline and both licence entries to `chartpack/NOTICE` with the date each licence page was read (Task 1). Commit `feat(chartpack): polite fetch of NONNA and the BC coastline to a source-data release (#90)`.
- [ ] **Step 6:** Open PR A, one adversarial review, merge.

### Task 3: Spike in CI (spec 5 pass rules), numbers on #90 (controller)

- [ ] **Step 1:** After PR A merges, dispatch `chartpack-sources.yml` from main: `gh workflow run chartpack-sources.yml -f region=test-toba -f stage=fetch`. Confirm the run's exit status and the three assets on release `sources-bc-1`.
- [ ] **Step 2:** From `fetch-stats-test-toba.json` and the Task 1 tile counts, project for the largest region: fetch time (chunks times measured seconds per chunk), compressed NONNA-10 size, build disk peak (raw Float32 of one block read plus outputs). Post the table on #90.
- [ ] **Step 3: Gate.** Pass needs all of: robots allows the path; projected fetch under 3 h for every region (else add a `--resume` that skips boxes already in a partial mosaic, in a follow-up to PR A, before going on); every asset projected under 2 GiB (else split that region's fetch by sub-box); disk peak leaves 2 GiB free on 14 GB. A failed rule stops the plan here: report to the controller, who takes it to the owner with options.

---

## PR B: latitude (#18)

### Task 4: SCAMIN and contour tolerance from the feature's latitude

**Files:**
- Modify: `chartpack/src/chartpack/enc/scamin.py` (`minzoom_for_scamin`), `chartpack/src/chartpack/enc/quilt.py` (pass the latitude), `chartpack/src/chartpack/bathy/contours.py` (`zoom_tolerance_deg`, its callers)
- Test: `chartpack/tests/test_enc_scamin.py`, `chartpack/tests/test_enc_quilt.py`, `chartpack/tests/test_bathy_contours.py`

**Interfaces:**
- Produces: `minzoom_for_scamin(scamin: int | None, band: int, lat: float) -> int`; `zoom_tolerance_deg(zoom: int, lat: float) -> float`. `lat` is the latitude of the feature's centroid (quilt) or of the block core's center (contours), rounded to the nearest 0.25 degree so both sides of a seam compute the same value. `REF_LAT = 48.0` stays untouched (spec 10).

- [ ] **Step 1: Write the failing tests.**
  - `test_scamin_zoom_matches_old_value_at_48` (for SCAMIN 21999, 89999, 349999 and bands 3, 4, 5: equal to the current function's result).
  - `test_scamin_zoom_shifts_at_54` (at least one of those SCAMIN values gives a different zoom at 54.0 than at 48.0, and none differs by more than 1).
  - `test_tolerance_scales_with_cos_lat` (`zoom_tolerance_deg(12, 54.0) / zoom_tolerance_deg(12, 48.0)` equals `cos(54) / cos(48)` within 1e-9).
  - `test_quilt_same_feature_same_minzoom_across_seam` (one feature given to two quilt calls with different cell sets: same `tippecanoe.minzoom`).
- [ ] **Step 2:** Run. Expected: FAIL (signature).
- [ ] **Step 3:** Implement; update every caller.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `fix(chartpack): SCAMIN and contour tolerance use the feature's latitude (#18)`. Open PR B (closes #18), review, merge.

---

## PR C: BC depth for the Fish view (#90, #92)

### Task 5: Region format and grid: areas, sides, no clip-dropped tiles

**Files:**
- Modify: `chartpack/src/chartpack/region.py`, `chartpack/src/chartpack/grid.py`, `chartpack/src/chartpack/cli.py` (callers of `assign` and `owned_tiles`)
- Test: `chartpack/tests/test_region.py`, `chartpack/tests/test_grid.py`

**Interfaces:**
- Produces:
  - Region file keys: `[area] polygon = [[[lon, lat], ...], ...]` (optional; GeoJSON polygon coordinates; when present, `bbox` must be its bounds); `[charts] kind = "enc" | "derived-inshore" | "derived-offshore"` (default `"enc"`); `bathy.sources` accepts the five source names.
  - `Region.area: shapely.Geometry | None`; `Region.charts_kind: str`.
  - `tiles_meeting_area(geom: shapely.Geometry, z: int = GRID_ZOOM) -> set[tuple[int, int]]`; `assign` uses it for a region with an area, else `tiles_meeting(bbox)`.
  - `assign(regions: list[Region], order: list[str]) -> dict[tuple[int, int], str]`: the `clip` parameter is gone; no tile is dropped for lying inside the clip.
  - `load_grid` rejects an order that lists a `derived-offshore` region before a `derived-inshore` one.
  - `canada_side(clip: shapely.Geometry, tile: tuple[int, int], owner: Region) -> shapely.Geometry`: the part of the tile on the Canadian column of spec 6: the whole tile when `owner.charts_kind != "enc"`, else the tile cut by `clip`.
  - `area_kind(owner: Region) -> str`: `"us"`, `"inshore"` or `"offshore"` for the water of a BC-owned tile; the Canadian side of a US-owned tile is `"inshore"`.
  - `offshore_shore_tiles(owner: dict[tuple[int, int], str], regions: dict[str, Region], coast_tiles: set[tuple[int, int]]) -> set[tuple[int, int]]`: tiles owned by an offshore region that hold coastline (must be empty).

- [ ] **Step 1: Write the failing tests.**
  - `test_tile_inside_clip_is_owned` (a BC box wholly inside a clip polygon keeps its tiles).
  - `test_wave1_owners_unchanged` (with the five wave 1 files and the real `grid.toml`: every tile that had an owner before keeps it; compare against `tests/fixtures/wave1-owners.json`, written once from `origin/main` code).
  - `test_polygon_area_tiles` (the `bc-offshore-south` ring from the spec appendix: a tile at -128.0, 48.0 is not included, one at -130.0, 50.0 is).
  - `test_offshore_before_inshore_is_error`.
  - `test_offshore_owning_shore_tile_is_reported` (a coast tile owned by an offshore region is returned).
  - `test_canada_side_whole_for_bc_owner_cut_for_us_owner`.
  - `test_unknown_bathy_source_is_error` still passes with the new names accepted.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): polygon areas, charts kinds and border sides in the grid (#90)`.

### Task 6: NONNA in the block build, source order by side

**Files:**
- Modify: `chartpack/src/chartpack/bathy/blocks.py` (`build_block`, `BlockResult`, `fine_owned_z12`, labels), `chartpack/src/chartpack/bathy/merge.py` (merge of an ordered source list), `chartpack/src/chartpack/datum/__init__.py` (`SOURCE_VERTICAL`), `chartpack/src/chartpack/cli.py` (`_fetch_bathy` downloads the region's assets from release `sources-bc-1` into the cache; `_build_bathy` passes them)
- Test: `chartpack/tests/test_bathy_blocks.py`, `chartpack/tests/test_bathy_merge.py`, `chartpack/tests/test_bathy_nonna.py`, `chartpack/tests/test_cli.py`

**Interfaces:**
- Consumes: `read_nonna` (Task 2); `canada_side` (Task 5).
- Produces:
  - `@dataclass class BlockSources: cudem_tiles: Sequence[CudemTile]; crm_path: Path | None; nonna10: Path | None; nonna100: Path | None; etopo: Path | None`.
  - `build_block(core, read, sources: BlockSources, datum: AreaDatum, canada: shapely.Geometry | None) -> BlockResult`. `canada` is the Canadian-column geometry over `read` (None: all US). Per cell, first source with data wins: US side fine `cudem`, coarse `crm` then `etopo`; Canadian side fine `nonna10` then `cudem`, coarse `nonna100` then `crm` then `etopo`. The old `clip` argument and its nan mask are gone.
  - `BlockResult` gains `fine_source: np.ndarray` and `coarse_source: np.ndarray` (int8 index into `SOURCE_NAMES = ("none", "cudem", "crm", "nonna10", "nonna100", "etopo")`), and `nonna_valid: np.ndarray | None` (bool, fine grid shape: any NONNA value in the cell, used by Task 10).
  - `SOURCE_VERTICAL` gains `"nonna10": "chart"`, `"nonna100": "chart"`, `"etopo": "egm2008"`; `AreaDatum.__call__` returns zeros for a `"chart"` source.
  - Coverage labels: `LABELS = {"cudem": {...as today}, "crm": CRM_LABEL, "nonna10": {"source": "nonna10", "resolution_m": 10, "date": "2026"}, "nonna100": {"source": "nonna100", "resolution_m": 100, "date": "2026"}, "etopo": {"source": "etopo", "resolution_m": 460, "date": "2022"}}`. The coverage layer gains the property `grade`: `"survey"` (`cudem`, `nonna10`, and `crm` on the US side), `"coarse-survey"` (`nonna100`), `"rough"` (`etopo`, and `crm` on the Canadian side).
  - The fine tier's owned zoom-12 tiles are those with any `cudem` or `nonna10` cell.
  - ENC fallback contours (`enc_fallback_contours`, plan 7 PR D) are not drawn on the Canadian column: every BC and rebuilt region has a coarse source there, so `coarse_fallback` stays `"crm"` and no contour draws twice (spec 9).

- [ ] **Step 1: Write the failing tests** (synthetic grids from `tests/make_ridge.py` and `make_nonna.py`).
  - `test_nonna_sign_and_nodata` (a fixture with nodata, -30.0 and +1.5: `read_nonna` gives nan, 30.0 and -1.5).
  - `test_canadian_side_prefers_nonna10_over_cudem` and `test_us_side_ignores_nonna` (one block split by a `canada` polygon, both sources everywhere: `fine_source` is `nonna10` on one side and `cudem` on the other).
  - `test_cudem_fills_nonna10_holes_on_canadian_side`.
  - `test_coarse_order_canadian_side` (cells with only `nonna100`, only `crm`, only `etopo`, and all three: `coarse_source` is `nonna100`, `crm`, `etopo`, `nonna100`).
  - `test_etopo_last_on_us_side`.
  - `test_no_datum_shift_for_nonna` (depth out equals depth in for a NONNA cell while a CUDEM cell is shifted by the station offset).
  - `test_coverage_grade_per_source`.
  - `test_no_blank_water_in_block` (a block with `etopo` everywhere: every water cell of the coarse grid has a value).
  - `test_build_bathy_reads_assets_not_wcs` (the CLI with a cache holding fixture assets makes no HTTP request; a missing asset is an error naming the file and the fetch workflow).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Keep the plan 7 global grid anchoring and the features-clipped-to-core rule; NONNA is warped from EPSG:3857 to the fine lon/lat grid with nearest-neighbor for the mask and bilinear for values.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): NONNA depth in the block build, sources by side of the border (#90)`.

### Task 7: ETOPO 2022 reader and its datum shift (#92)

**Files:**
- Create: `chartpack/src/chartpack/bathy/etopo.py`, `chartpack/regions/datum/bc-etopo.toml`
- Modify: `chartpack/src/chartpack/cli.py` (`_fetch_bathy`), `chartpack/src/chartpack/bathy/blocks.py` (`AreaDatum` for `etopo`), `chartpack/src/chartpack/region.py` (`[datum] etopo_file`, optional), `chartpack/NOTICE`
- Test: `chartpack/tests/test_bathy_etopo.py`, `chartpack/tests/test_bathy_blocks.py`

**Interfaces:**
- Produces:
  - `etopo.ETOPO_URL = "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_surface_elev_gtif/ETOPO_2022_v1_15s_N60W135_surface.tif"`; `etopo.fetch_etopo(cache_dir: Path) -> Path` (cached; NOAA host, so builds may call it, as they call CRM).
  - `bc-etopo.toml`: `[[stations]] name, lon, lat, msl_above_cd_m` from Task 1 Step 5, with the source URL, licence and read date in a header comment. If Task 1 found no open source: the file holds no stations and a comment says so.
  - `AreaDatum` for `etopo`: EGM2008 height taken as mean sea level; depth below chart datum = depth below mean sea level minus the `msl_above_cd_m` of the nearest station (one value per block, by block center); no shift with no stations.
  - `chartpack/NOTICE`: the ETOPO 2022 citation from #89, and one line stating the shift used or that none is applied.

- [ ] **Step 1: Write the failing tests.** `test_etopo_depth_is_minus_elevation_plus_shift` (elevation -100.0 with a station `msl_above_cd_m` of 3.0 gives depth 103.0: chart datum lies below mean sea level, so depths below it are smaller, and the shift is subtracted: assert 97.0); `test_etopo_no_stations_no_shift`; `test_fetch_etopo_uses_cache` (second call makes no request).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement with `read_window`.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): ETOPO 2022 as the last coarse depth source (#92)`.

### Task 8: Fish style: three grades, the BC notice, the CHS notice in bathy packs

**Files:**
- Modify: `chartpack/src/chartpack/style/fish.py`, `chartpack/src/chartpack/style/sprites.py` (two fill patterns), `chartpack/src/chartpack/pack/assemble.py` (`_bathy_notice`, metadata), `chartpack/src/chartpack/bathy/tiles.py` (metadata passthrough)
- Test: `chartpack/tests/test_style_fish.py`, `chartpack/tests/test_style_sprites.py`, `chartpack/tests/test_pack_assemble.py`

**Interfaces:**
- Produces:
  - Fish layers `grade-coarse-survey` and `grade-rough` (and `-coarse` twins on the coarse source): `fill-pattern` layers over the `coverage` layer filtered by `grade`, patterns `pat-coarse-survey` (sparse dots) and `pat-rough` (diagonal hatch), in all three palettes.
  - Style metadata `metadata.cheekymarine.notices = {"bc": "<Fish BC string>"}` next to the existing `notice`.
  - `CHS_NOTICE: str` in `pack/assemble.py` (the Global Constraints text). `_bathy_notice` appends it when any coverage `source` is `nonna10` or `nonna100`, with the sentence `Canadian depths are on Canadian chart datum and US depths on MLLW; the two differ slightly at the border.` The shoreline credit is not added here (charts only).
  - MBTiles metadata on the four bathy files: `cheekymarine:data_notice` (the CHS notice text, or absent) and `cheekymarine:notice_areas` (a GeoJSON FeatureCollection; each feature `{"properties": {"kind": "bc"}, "geometry": ...}`: the union of the pack's Canadian-column water tiles, simplified to 0.005 degree; an empty collection for a pack with none).

- [ ] **Step 1: Write the failing tests.** `test_fish_grade_layers_use_patterns` (both layers have `fill-pattern`, filter on `grade`); `test_fish_notices_has_bc_string` (exact string); `test_patterns_in_all_palettes`; `test_bathy_notice_has_chs_text_only_with_nonna` (a pack with a `nonna10` coverage has all four CHS paragraphs and the OGL line; a wave 1 style pack has none); `test_notice_areas_metadata_is_geojson`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): Fish depth grades, BC notice and the CHS notice in bathy packs (#90)`. Open PR C (closes #92), review, merge.

---

## PR D: the BC Nav view (#90)

### Task 9: Schema gate, land from the coastline, the no-survey mask (derive stage)

**Files:**
- Create: `chartpack/src/chartpack/enc/nosurvey.py`
- Modify: `chartpack/src/chartpack/coast.py`, `chartpack/src/chartpack/enc/schema.py`, `chartpack/src/chartpack/cli.py` (`derive-sources`), `.github/workflows/chartpack-sources.yml` (stage `derive`)
- Test: `chartpack/tests/test_coast.py`, `chartpack/tests/test_enc_nosurvey.py`, `chartpack/tests/test_pack_check.py`

**Interfaces:**
- Produces:
  - `schema.LAYERS` gains `LayerSpec("nosurvey", (), (), "polygon")` and `LayerSpec("covedge", (), ("kind",), "line")`; `OPTIONAL_LAYERS` gains both; `depare`, `depcnt` and `soundg` gain the attribute `src`.
  - `coast.land_polygons(lines: Iterable[shapely.LineString], box: tuple[float, float, float, float]) -> shapely.MultiPolygon`: polygonize; a line that ends on the box edge is closed along the box on its land side (the atlas lines are directed; Task 1 Step 4 records which side is land); a line that ends inside the box raises `CoastError` naming its end point.
  - `nosurvey.mask(nonna10: Path, nonna100: Path, land: shapely.Geometry, box) -> shapely.MultiPolygon`: water in `box` with no value in either grid, computed at the NONNA-10 native grid, polygonized, land removed, simplified by at most half a cell.
  - `nosurvey.missing_in_100(nonna10: Path, nonna100: Path, box) -> float`: square kilometers where NONNA-10 has data and NONNA-100 has none.
  - CLI `chartpack derive-sources --region <file.toml> --cache <dir> --out <dir>`: reads the fetched assets, writes `land-<region>.geojson.gz`, `nosurvey-<region>.geojson.gz` and `derive-stats-<region>.json` (`missing_in_100_km2`, polygon counts). Workflow stage `derive` downloads the region's assets from `sources-bc-1`, runs it, uploads the three files. No Canadian host is called.

- [ ] **Step 1: Schema gate.** Write `test_schema2_pack_without_new_layers_still_passes`: the fixture pack of `tests/test_pack_check.py`, built without the new layers and without `src`, returns no error from `check_pack` under the edited `schema.py`. If it cannot pass without loosening a safety rule, stop and report (Global Constraints).
- [ ] **Step 2: Write the failing tests.** `test_land_closes_at_box_edge` (an L-shaped coast cut by the box gives one polygon whose area matches the land side); `test_unclosable_ring_fails`; `test_island_ring_is_land`; `test_mask_is_water_without_nonna` (a fixture where the east half has no value in both grids and a land block: mask equals the east half minus land within one cell); `test_mask_never_overlaps_valid_cells`; `test_missing_in_100_reports_area`.
- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4:** Implement.
- [ ] **Step 5:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 6:** Commit `feat(chartpack): land polygons and the no-survey mask as derived source assets (#90)`.

### Task 10: Derived Nav features (shoal-biased, fixed levels, no fill-in)

**Files:**
- Create: `chartpack/src/chartpack/enc/derived.py`, `chartpack/regions/bc-valdco.toml`
- Test: `chartpack/tests/test_enc_derived.py`

**Interfaces:**
- Consumes: `BlockResult` grids and `nonna_valid` (Task 6); land and mask assets (Task 9).
- Produces:
  - `bc-valdco.toml`: `levels_m = [...]`: the union of `cheekymarine:valdco` over the six released wave 1 charts packs (five regions and `overview`), sorted (Step 1).
  - `derived.block_min(depth_m: np.ndarray, transform, block: int) -> tuple[np.ndarray, tuple]`: the shallowest (smallest) value per block; a block with any nan cell among its water cells stays valid only from its valid cells, and an all-nan block is nan.
  - `derived.derived_features(depth_m: np.ndarray, src: np.ndarray, transform, *, core, levels_m: list[float], nosurvey: shapely.Geometry, land: shapely.Geometry, lat: float) -> list[Feature]` (the `Feature` of `enc/reader.py`), producing per zoom band of `bathy/contours.py` `BANDS`:
    - `depare` polygons with `DRVAL1`, `DRVAL2` (consecutive `levels_m`, plus one drying area `DRVAL1 = -H`, `DRVAL2 = 0` where depth is negative, `H` the greatest drying height in the block rounded up to 0.1), and `src`;
    - `depcnt` lines with `VALDCO` in `levels_m` and `src`;
    - `soundg` points with `depth` and `src`, one per 96 px cell at each zoom, the shallowest value in the cell, from `nonna10` or `nonna100` cells only;
    - `lndare` polygons and `coalne` lines from `land`;
    - `nosurvey` polygons (`nosurvey` cut to `core`).
    Every depth geometry is cut by `nosurvey` and `land` before it is returned. `src` is the source name of the cell the value came from; a `depare` or `depcnt` spanning both gets `nonna100` (the coarser).
  - With `kind="derived-offshore"` semantics chosen by the caller: the caller passes the coarse merge as `depth_m` and an empty `nosurvey` and `land`.

- [ ] **Step 1 (controller):** Read `cheekymarine:valdco` from the six wave 1 charts releases: download each pack tar into its own fresh directory, read the `enc.mbtiles` metadata, and delete nothing (the scratchpad is session-scoped). Write `bc-valdco.toml` with the sorted union and post the list on #90.
- [ ] **Step 2: Write the failing tests.**
  - `test_block_min_takes_shallowest` (a 2 by 2 block of 10, 4, 7, nan gives 4).
  - `test_contour_values_are_all_in_levels`.
  - `test_shoal_survives_downsampling` (one 3 m cell in a 50 m plain, downsampled 8 times: the derived `depare` at the coarsest band still has an area with `DRVAL1 <= 3`).
  - `test_no_depth_inside_nosurvey` (no `depare`, `depcnt` or `soundg` geometry intersects the mask interior, at every band).
  - `test_no_depth_on_land`.
  - `test_soundings_only_from_nonna` (a grid whose `src` is `etopo` everywhere yields no `soundg`).
  - `test_drying_area_has_negative_drval1`.
  - `test_src_is_coarser_when_mixed`.
- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4:** Implement with contourpy filled contours on the block-min grids.
- [ ] **Step 5:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 6:** Commit `feat(chartpack): Nav depth areas, contours and soundings derived from NONNA (#90)`.

### Task 11: BC rules for NOAA cells, the coverage edge, the charts build

**Files:**
- Create: `chartpack/src/chartpack/enc/bc.py`
- Modify: `chartpack/src/chartpack/cli.py` (`_build_enc`), `chartpack/src/chartpack/enc/tiles.py` (new layers to tippecanoe), `chartpack/src/chartpack/pack/check.py`, `chartpack/src/chartpack/pack/assemble.py` (charts NOTICE, metadata)
- Test: `chartpack/tests/test_enc_bc.py`, `chartpack/tests/test_pack_check.py`, `chartpack/tests/test_pack_assemble.py`, `chartpack/tests/test_cli.py`

**Interfaces:**
- Consumes: `quilt` output; `canada_side`, `area_kind` (Task 5); `derived_features` (Task 10); assets (Task 9).
- Produces:
  - `@dataclass class BcAreas: canada: shapely.Geometry; inshore: shapely.Geometry; band3: shapely.Geometry; nonna: shapely.Geometry; atlas_land: shapely.Geometry` (`band3`: union of `M_COVR` of band 3 and finer cells; `nonna`: water with a NONNA value, the complement of the mask over water).
  - `bc.apply_rules(features: list[Feature], areas: BcAreas) -> list[Feature]`, applied to the quilt output, by geometry (features are cut, not dropped whole):
    1. `DEPTH = ("depare", "depcnt", "soundg")`, `LAND = ("lndare", "coalne")`.
    2. In `inshore` outside `band3` (so only bands 1 and 2 reach): drop `DEPTH`; drop `LAND` inside `atlas_land`'s extent (the atlas covers that water); keep every other layer.
    3. In `canada` inside `band3`: drop `DEPTH` inside `nonna`; keep it elsewhere; drop `LAND` where the atlas has land.
    4. Outside `canada`, and in offshore water: unchanged.
  - `bc.coverage_edge(areas: BcAreas) -> list[Feature]`: layer `covedge`, the boundary of `band3` inside `canada`, `kind = "us-chart-end"`.
  - `_build_enc` for any region: quilt, `apply_rules`, then add per owned tile the derived features for the tile's Canadian-column water (`derived-inshore` and US packs: from NONNA with the mask and atlas land; `derived-offshore`: from the coarse merge), then tippecanoe as today. A region with `charts.kind = "enc"` and no Canadian water runs exactly the old path.
  - Pack check: for `charts.kind` in the manifest (`"enc"` when absent) `derived-inshore` requires `depare` and `lndare` at each zoom, `derived-offshore` requires `depare`; `"enc"` keeps `_check_safety_layers` unchanged. New `_check_no_depth_in_nosurvey(m: MBTiles) -> list[str]` runs for every charts pack that has a `nosurvey` layer: no `depare`, `depcnt` or `soundg` feature with a `src` attribute intersects a `nosurvey` polygon in the same tile (decoded tile coordinates, 1 unit tolerance).
  - Charts NOTICE: the CHS notice when any feature has `src` `nonna10` or `nonna100`; the shoreline credit when the pack holds atlas land.
  - Charts MBTiles metadata: `cheekymarine:data_notice`; `cheekymarine:notice_areas` with kinds `"bc"` (Canadian-column water outside `band3`) and `"bc-noaa"` (Canadian-column water inside `band3`); `cheekymarine:valdco` as today (derived values are already in the wave 1 list).

- [ ] **Step 1: Write the failing tests.**
  - `test_band2_depth_dropped_inshore_lights_kept` (a band 2 cell with a `depare`, a `lndare` and a `light` over inshore water outside `band3`: only the light remains).
  - `test_band2_land_kept_where_atlas_has_none` (Alaskan side).
  - `test_band3_depth_kept_only_where_nonna_empty` (a band 3 `depare` straddling the NONNA edge is cut at it).
  - `test_us_side_untouched`.
  - `test_coverage_edge_only_inside_canada`.
  - `test_enc_region_without_canada_builds_as_before` (feature list equal to the old path's).
  - `test_derived_inshore_pack_passes_check_without_navaids`; `test_enc_pack_still_needs_all_safety_layers`.
  - `test_depth_inside_nosurvey_fails_check` (a hand-made tile with a `soundg` in a `nosurvey` polygon: one error naming the tile).
  - `test_valdco_gains_no_value_from_derived` (pack metadata `cheekymarine:valdco` of a derived pack is a subset of `bc-valdco.toml`).
  - `test_charts_notice_has_chs_and_bc_credit`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): BC rules for NOAA cells and derived charts packs (#90)`.

### Task 12: Nav style: no-survey shading, coarse survey mark, coverage edge, notices

**Files:**
- Modify: `chartpack/src/chartpack/style/nav.py`, `chartpack/src/chartpack/style/sprites.py`, `chartpack/src/chartpack/style/palette.py`
- Test: `chartpack/tests/test_style_nav.py`, `chartpack/tests/test_style_sprites.py`, `chartpack/tests/test_style_palette.py`

**Interfaces:**
- Produces: Nav layers `nosurvey` (fill with `fill-pattern` `pat-nosurvey`, a cross hatch, drawn above the depth areas and below land), `depare-coarse-survey` (the `pat-coarse-survey` dots over `depare` with `src == "nonna100"`), `covedge` (dashed line, `kind == "us-chart-end"`); style metadata `metadata.cheekymarine.notices = {"bc": "<Nav BC string>", "bc-noaa": "<Nav NOAA strip string>"}`. The three patterns exist in the day, dusk and night sprite sheets with a foreground that differs from every depth band color of that palette by pattern, never by color alone.

- [ ] **Step 1: Write the failing tests.** `test_nav_nosurvey_layer_is_pattern_fill_between_depth_and_land` (layer order); `test_nav_notices_exact_strings`; `test_coarse_survey_layer_filters_on_src`; `test_covedge_layer_is_dashed`; `test_nosurvey_pattern_in_three_sheets`; `test_wave1_style_layers_unchanged_before_new_ones` (the old layer ids keep their relative order).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Run the style validator (`chartpack/src/chartpack/style/validate.py`) in the tests as the existing style tests do.
- [ ] **Step 4:** Run the chartpack tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(chartpack): Nav style for no-survey water, coarse survey and the US chart edge (#90)`. Open PR D, review, merge. Then dispatch `chartpack-sources.yml` stage `derive` for `test-toba` from main and confirm the three assets.

---

## PR E: the app (#90)

### Task 13: Notice areas and the area-aware notice

**Files:**
- Create: `plotter/src/core/NoticeAreas.h`, `plotter/src/core/NoticeAreas.cpp`
- Modify: `plotter/src/core/PackMerge.cpp` (`mergedMetadata`), `plotter/src/core/ChartController.h`, `plotter/src/core/ChartController.cpp`, `plotter/CMakeLists.txt`
- Test: `plotter/tests/tst_noticeareas.cpp`, `plotter/tests/tst_packmerge.cpp`, `plotter/tests/tst_chartcontroller.cpp`

**Interfaces:**
- Consumes: MBTiles metadata `cheekymarine:notice_areas` and `cheekymarine:data_notice`; style metadata `cheekymarine.notices` (Tasks 8, 11, 12).
- Produces:
  - `class NoticeAreas { public: enum Kind { None = 0, Bc = 1, BcNoaa = 2 }; Q_DECLARE_FLAGS(Kinds, Kind) static NoticeAreas fromGeoJson(const QByteArray& json); void add(const NoticeAreas& other); Kinds kindsIn(double west, double south, double east, double north) const; bool isEmpty() const; QByteArray toGeoJson() const; };` Polygons and multipolygons with holes; `kindsIn` tests intersection of the viewport box with each polygon (`QPolygonF::intersects` on outer rings, a box wholly inside a hole does not count). Invalid or missing JSON gives an empty object.
  - `QString pickNotice(const QJsonObject& styleMetadata, NoticeAreas::Kinds kinds)`: `notices.bc` when `Bc` is set; else `notices["bc-noaa"]` when `BcNoaa` is set and the key exists, else `notices.bc` when `BcNoaa` is set; else the existing `notice`. A style without `notices` always gives `notice`.
  - `mergedMetadata` writes `cheekymarine:notice_areas` as the union of the members' features (a member without the key adds nothing) and `cheekymarine:data_notice` as the distinct member texts joined by a blank line.
  - `ChartController`: loads the notice areas of the charts files (Nav) and bathy files (Fish) it shows, at the same point it reads `cheekymarine:valdco`; recomputes `m_notice` with `pickNotice` when the style loads and when the visible bounds change (at most once per 250 ms), emitting `noticeChanged` only on a different string; new `Q_PROPERTY(QStringList dataNotices READ dataNotices CONSTANT)` holding the distinct `cheekymarine:data_notice` texts of every file shown. The notice bar and `noticeShown` in `plotter/qml/ChartPage.qml` are untouched: the BC notice obeys the setting (owner).

- [ ] **Step 1: Write the failing tests.**
  - `tst_noticeareas`: `boxInsidePolygonHits`, `boxOutsideMisses`, `boxInsideHoleMisses`, `boxTouchingEdgeHits`, `twoKindsBothReported`, `invalidJsonIsEmpty`, `roundTripKeepsKinds`.
  - `tst_packmerge`: `mergeUnionsNoticeAreas` (two members, one feature each: merged file has both), `mergeAcceptsMembersWithoutNoticeAreas` (a schema 2 member built without the keys merges; merged collection holds the other member's feature only), `mergeJoinsDistinctDataNotices`.
  - `tst_chartcontroller`: `mixedViewGetsBcNotice`, `usOnlyViewKeepsDefault`, `noaaStripOnlyGetsNoaaNotice`, `fishInBcGetsFishBcNotice`, `noticeChangedNotEmittedWhileKindsSame`, `styleWithoutNoticesKeepsOldBehavior`.
- [ ] **Step 2:** Build and run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `ctest --test-dir build-plotter --output-on-failure`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): area-aware chart notice from pack notice areas (#90)`.

### Task 14: Legend rows, About and Splash, plotter 0.4.0

**Files:**
- Modify: `plotter/src/core/Legend.cpp`, `plotter/src/core/AppInfo.h`, `plotter/src/core/AppInfo.cpp`, `plotter/src/app/main.cpp` (pass `dataNotices`), `plotter/qml/AboutPage.qml`, `plotter/qml/Splash.qml`, `plotter/CMakeLists.txt` (version `0.4.0`)
- Test: `plotter/tests/tst_legend.cpp`, `plotter/tests/tst_legendimages.cpp`, `plotter/tests/qml/tst_qml.cpp`

**Interfaces:**
- Consumes: layer ids `nosurvey`, `depare-coarse-survey`, `covedge` (Task 12), `grade-coarse-survey`, `grade-rough` (Task 8); `ChartController::dataNotices` (Task 13).
- Produces: legend rows with the exact Global Constraints titles: Nav `No survey data` (pattern swatch, `nosurvey`), `Coarse survey depth (100 m grid)` (`depare-coarse-survey`), `US chart data ends here (coarse scale). Beyond: most hazards and navaids not shown.` (line, `covedge`); Fish `Coarse survey depth (100 m grid)` (`grade-coarse-survey`), `Rough depth, worldwide grid` (`grade-rough`). Rows appear only when the style has the layer, as existing rows do. `AppInfo` gains `Q_PROPERTY(QStringList dataNotices ...)`; `AboutPage.qml` shows each text in full under a heading `Data notices` (objectName `dataNotices`) when the list is not empty; `Splash.qml` adds the line `BC: not for navigation. See About for the CHS notice.` when the list is not empty, regardless of `noticeShown` being on, and hides it with the pack notice when `noticeShown` is off.

- [ ] **Step 1: Write the failing tests.** `legendHasNoSurveyRowWhenLayerPresent`, `legendOmitsBcRowsForWave1Style`, `fishLegendHasGradeRows`, `legendImageForPatternSwatchIsNotBlank`; QML: `aboutShowsDataNotices` (the four CHS paragraphs present in the `dataNotices` item's text), `aboutHidesSectionWhenEmpty`, `splashBcLineFollowsNoticeSetting`.
- [ ] **Step 2:** Build and run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `ctest --test-dir build-plotter --output-on-failure`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(plotter): BC legend rows and data notices in About and Splash, 0.4.0 (#90)`. Open PR E, review, merge.

---

## PR F and releases: the regions (#90)

### Task 15: Region files, the grid, rebuilt US packs and overview

**Files:**
- Create: `chartpack/regions/bc-south-georgia.toml`, `bc-north-georgia.toml`, `bc-johnstone.toml`, `bc-vi-west-south.toml`, `bc-vi-west-north.toml`, `bc-central.toml`, `bc-north.toml`, `haida-gwaii.toml`, `bc-offshore-south.toml`, `bc-offshore-north.toml` (boxes and polygons from spec 4 and its appendix)
- Modify: `chartpack/regions/grid.toml`, `north-sound.toml`, `strait.toml`, `wa-coast.toml`, `overview.toml` (versions `1.1.0`, sources, cells), `chartpack/src/chartpack/bathy/blocks.py` (`build_overview` over the coarse sources), `chartpack/src/chartpack/region.py` (overview sources rule), `.github/workflows/chartpack-release.yml` (download the region's source assets from `sources-bc-1` before the build, charts builds too; append the pack's `cheekymarine:data_notice` text to the release notes when it has one)
- Delete: `chartpack/regions/test-toba.toml` (and its three assets stay in the release, unused)
- Test: `chartpack/tests/test_regions.py`, `chartpack/tests/test_grid.py`, `chartpack/tests/test_bathy_blocks.py`

**Interfaces:**
- Produces:
  - Region files: inshore BC `[charts] kind = "derived-inshore"`, `[bathy] sources = ["nonna10", "nonna100", "crm", "etopo"]` (`crm` only where the box reaches south of 49 N: `bc-south-georgia`, `bc-vi-west-south`), `dem_maxzoom = 14`, `[enc]` cells from `chartpack cells` for the owned tiles (bands 1 to 3 as the catalog gives; `US3WA1EF`, `US3WA1EE`, `US3WA1ED`, `US3AK1DX`, `US3AK1DY` where they meet), `[datum] file = "datum/wa-stations.toml"`, `etopo_file = "datum/bc-etopo.toml"`. Offshore: `kind = "derived-offshore"`, `[area] polygon`, `sources = ["nonna100", "crm", "etopo"]` (`crm` for `bc-offshore-south` only).
  - `grid.toml` order: the five wave 1 names unchanged, then `bc-south-georgia`, `bc-vi-west-south`, `bc-north-georgia`, `bc-johnstone`, `bc-vi-west-north`, `bc-central`, `bc-north`, `haida-gwaii`, then `bc-offshore-south`, `bc-offshore-north`.
  - Rebuilt US packs: `north-sound`, `strait`, `wa-coast` add `nonna10`, `nonna100` to `bathy.sources` and keep `clip` (now only the side line). Confirm with `chartpack cells` and the grid that no other wave 1 pack owns a tile with Canadian water; a pack that does joins the list.
  - `overview`: bbox the extent of all owned tiles; `sources = ["nonna100", "crm", "etopo"]`; `load_region` accepts any subset of the coarse sources for an overview and rejects `cudem` and `nonna10`. `build_overview(bbox, sources: BlockSources, datum, canada, nosurvey: shapely.Geometry) -> BlockResult`; its charts build reads the stored masks and land of every BC region, never NONNA-10.
  - Render views (spec 15) in the owning region files: Victoria and Haro Strait, Active Pass, Vancouver harbor and Indian Arm, Desolation Sound, Knight Inlet head, Barkley Sound, Nootka Sound, the shelf off Tofino, Bella Bella, Prince Rupert, Dixon Entrance, Masset, the 49 N line at -126.0 W, one view in each offshore pack. Zooms `[9, 11, 13, 15]` inshore, `[7, 9, 11]` offshore.

- [ ] **Step 1: Write the failing tests.** `test_every_region_file_loads`; `test_every_bc_tile_has_one_owner` (no tile in two regions, no unowned tile inside any inshore box); `test_no_offshore_tile_holds_coastline` (uses a coast-tile fixture `tests/fixtures/bc-coast-tiles.json`, written by the controller from the fetched coastline assets in Step 3; until then the test is skipped with that reason); `test_wave1_owners_unchanged` (Task 5 fixture, now with the real grid); `test_overview_rejects_fine_sources`; `test_overview_charts_never_open_nonna10` (a path spy).
- [ ] **Step 2:** Run, implement, run. Expected: PASS (one skip).
- [ ] **Step 3 (controller): fetch.** After PR F's code is on main: dispatch `chartpack-sources.yml` stage `fetch`, then `derive`, one region at a time, for the eight inshore regions, `north-sound`, `strait`, `wa-coast` and the two offshore regions (NONNA-100 only for offshore). Post each run's stats on #90. Any `missing_in_100_km2` above 1 goes on #90 for the owner to see. Write `bc-coast-tiles.json` from the coastline assets, commit it in a small follow-up PR, and unskip the test. If it fails (known: southeast Haida Gwaii), grow the inshore box by whole tiles until it passes and note the new edge on #90.
- [ ] **Step 4:** Commit `feat(chartpack): BC regions, grid order, rebuilt border packs and overview (#90)`. Open PR F, review, merge.

### Task 16: Dry runs, sizes, splits, renders, tags (controller, with the owner)

- [ ] **Step 1: Dry runs.** From main, `gh workflow run chartpack-release.yml -f pack=<kind> -f region=<name>` for both kinds of every BC region, the three rebuilt US regions and `overview` (28 runs; start no more than three at a time). Download each run's `build-stats.json` into a fresh directory per run. Post a table on #90: file sizes, peak RSS, free disk, time.
- [ ] **Step 2: Size.** Any file over `1_500_000_000` bytes, or a run past the fit guard: split that region on the grid into two (north and south, or as the coast suggests), named `<region>-north` and `<region>-south`, each with its own region file, grid entry in the parent's place, fetch and derive runs, and dry runs. Repeat until every file fits. This goes through a small PR with a review.
- [ ] **Step 3: Checks.** Every dry run's log shows `chartpack check` passing, including `_check_no_depth_in_nosurvey`. The datum step: sample the merged depth on both sides of the border along Haro Strait, Boundary Pass and the Strait (20 points each from the dry-run DEM tiles) and post the differences on #90; a step that moves a 10 ft contour by more than 10 ft goes to the owner before any tag. Post any `valdco` value the Alaskan cells add and settle it under #95 before tags.
- [ ] **Step 4: Renders.** Run `chartpack render` in CI artifacts or from the dry-run packs for every view of spec 15, Nav and Fish; day, dusk and night for the Tofino shelf, Nootka and Dixon Entrance views. Post them on #90 with plain-language captions and legends. Get the owner's OK on the renders.
- [ ] **Step 5: Tags.** With the owner's OK: annotated tags on the dry-run commit, pushed one per `git push`, 2 minutes apart; confirm a `push` run per tag; rerun a NOAA 5xx failure; confirm each release has its tar, `SHA256SUMS` and `build-stats.json`. Charts and bathy `1.0.0` for the BC packs, `1.1.0` for the rebuilt US packs and `overview`.

### Task 17: Plotter release and the test laptop

- [ ] **Step 1:** Tag `plotter-v0.4.0` (owner's OK, one push), confirm the release.
- [ ] **Step 2:** Message `laptop-chart` (ask for an ack): install plotter 0.4.0 and all released packs into a fresh directory, run the merge, then the plan 7 pan path and two new paths (the Haro Strait border seam; the corner where `bc-north-georgia`, `bc-johnstone` and `bc-vi-west-north` meet) with `--frame-stats`. Pass (spec 12): no blank tiles, p99 on the plan 7 path within 15% of 33 ms, merge under 5 minutes. Post numbers and screenshots on #90. A fail goes to the owner with the numbers.

### Task 18: Set lock 0.4.0 (PR G), install, comparison, housekeeping

**Files:**
- Modify: `installer/cheekymarine.lock` (via `installer/lock-tool.sh`), `installer/cheekymarine.sh` (embedded lock), installer tests as in plan 7 Task 18

- [ ] **Step 1:** The set release notes carry the CHS notice of the Global Constraints. Fill the lock with `installer/lock-tool.sh`: `set=0.4.0`, plotter `0.4.0`, one `pack.<kind>-<region>.*` entry per released pack (wave 1 packs that were not rebuilt keep `1.0.0`). Run `lock-tool.sh check` and the installer tests. Expected: PASS. Open PR G, review, merge, tag `cheekymarine-v0.4.0` as a pre-release (owner's OK).
- [ ] **Step 2:** Ask the owner to install set 0.4.0 on CapnButts from the release; confirm with `CapnButts-FirstMate` (read-only, ask for an ack) that About lists every pack and shows the CHS notice, and that the free-space check passed.
- [ ] **Step 3: Owner check.** The owner pans BC on CapnButts, Nav and Fish. Record the verdict on #90.
- [ ] **Step 4: Garmin comparison.** For each Garmin photo the owner provides: render the same place and zoom (Nav or Fish to match), post the pair on #90 with what matches and what differs against the pass rule of spec 15 (contours within one 10 ft step and spot depths within 10 ft where `nonna10` has data; shoreline lines up; missing detail is announced on screen). File follow-up issues for differences.
- [ ] **Step 5: Housekeeping.** File a new issue "BC chart objects: CHS data (parked) and open stand-ins" with links to the three research comments on #89; close #89 with a pointer to it. Remove the `plan 8` label from #91 with a comment (not needed: all plan 8 data is public). Close #90 and #92 (#18 closed by PR B). Add "live side-by-side with the Garmin in BC water" to the boat checks memory. Update the chartpack spec's region and source sections (`docs/superpowers/specs/2026-10-28-chartpack-design.md`) for Canadian data.
