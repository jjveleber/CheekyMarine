# Plan 8: chart coverage wave 2 (British Columbia)

Issues: #90 (BC packs), #92 (ETOPO reader), #18 (SCAMIN and contour latitude), #89 (licence research, closes with this plan). #91 (protected delivery) leaves plan 8 (section 2). Builds on plan 7: `docs/superpowers/specs/2026-11-08-chart-coverage-plan7-design.md` (called "plan 7 spec" below).

Region review map (BC areas approved 2026-11-08): https://claude.ai/artifact/J2hnEnQ3P79ZB7xJMbcJK5 , approval: https://github.com/jjveleber/CheekyMarine/issues/83#issuecomment-6724880220

Research this spec rests on, all on #89: the first two comments (CHS ENC, NONNA, GEBCO, ETOPO; the free CHS chart service) and "open stand-ins for chart objects in BC" (https://github.com/jjveleber/CheekyMarine/issues/89#issuecomment-6798801773). The source checks of plan Task 1 and the owner's decisions on them are on #90 (section 2).

## 1. Intent

Plan 7 covered the US waters the owner uses. North of the border the plotter is close to blank: zoom-10 tiles that lie wholly in Canadian water belong to no pack (`chartpack/src/chartpack/grid.py` drops tiles inside the clip polygon), and bathy is cut at the border. Only in tiles that hold both countries' water do NOAA chart objects already draw on the Canadian side, because the charts build never applied the clip (`_build_enc` in `chartpack/src/chartpack/cli.py`). Those objects are not free to share: the NOAA cells mark their Canadian part as CHS copyright (section 2), so plan 8 removes them. Plan 8 covers the British Columbia coast, inlets and islands, plus offshore water to about 100 mi, on the plan 7 machinery (several packs drawn as one chart, tile ownership, fine and coarse depth, CI-only builds).

The owner wants BC to look like US water. The data does not allow that today: the official Canadian chart objects (buoys, lights, rocks, wrecks, restricted areas) belong to the Canadian Hydrographic Service (CHS), which sells them and does not allow redistribution. The same holds where NOAA cells reach into Canada: the cells carry a CHS license notice over their Canadian part. The owner will not pay for charts and has parked CHS data. So plan 8 ships what open data supports:

- the Fish view in BC equal to the Fish view in US water, from the open CHS NONNA depth grids;
- a Nav view in BC built from the same depth data plus an open shoreline, which says plainly what it does not show.

The owner navigates BC with a Garmin that has paid, current charts. CheekyMarine in BC is a convenience display.

## 2. Owner decisions (2026-11-11 unless dated)

- BC areas as approved on the map on 2026-11-08: eight inshore packs and two offshore packs to about 100 mi (section 4).
- CHS chart data stays parked. No email to CHS, no harvest of the CHS online chart service. The owner may look at CHS again later, outside this plan.
- Plan 8 does not wait for CHS. If CHS data ever comes, it is a later plan.
- NONNA depth ships in public packs. The owner accepts this reading of the NONNA licence clause "The Data shall not be used for navigation": a depth layer that is labeled not for navigation and carries the CHS notice is a permitted derived product; the Garmin is the navigation source.
- So nothing in plan 8 needs protected delivery. #91 leaves plan 8.
- BC Nav view: infer what the depth data supports (depth shading, contours, spot depths, drying areas), add the open BC government shoreline so land is land, and mark water with no survey data.
- No NOAA chart feature of any band is shown on the Canadian side, in any pack (section 7.2). BC Nav shows depth and shoreline only, also in Haro Strait and Dixon Entrance. This reverses an earlier decision (below).
- ETOPO gets one fixed 4 m shift toward chart datum wherever ETOPO is used (section 8). No tide station values are used. This also reverses an earlier decision (below).
- Other open stand-ins found by the research (Coast Guard List of Lights, DFO traffic routes and anchorages, protected areas, place names, marinas, OpenStreetMap seamarks) are not in plan 8. They stay on #89 as the fallback if CHS data never comes.
- Acceptance: the owner takes photos of the Garmin at BC spots of the owner's choosing and gives them to the session, which compares them with the plotter. A live side-by-side on the water comes later, when the boat is back, and is not part of this plan.
- The BC on-chart notice obeys the existing "show chart notice" setting, like the US notice. With the setting off it is hidden. The CHS notice on the About page and in the pack NOTICE files does not depend on that setting.
- Carried from plan 7: no paid data; no local pack builds (CI only); install every pack; depths fixed at chart datum; maps shown to the owner use plain-language shading and legends.

Changed 2026-11-11 after the source checks (owner, https://github.com/jjveleber/CheekyMarine/issues/90#issuecomment-6811436163):
- Reversed: "NOAA chart cells that reach into Canadian water show their chart objects on the Canadian side wherever they reach", which was "something is better than nothing" on the condition that the screen showed where that coverage ends. The source check (plan Task 1 Step 3) found that the NOAA cells carry this notice over their Canadian part: "(c) Fisheries and Oceans Canada 2024. Published by the Canadian Hydrographic Service. A licence is required from the Canadian Hydrographic Service (www.charts.gc.ca) to reproduce or distribute this work." Showing those features would redistribute CHS work. So NOAA chart features on the Canadian side are dropped everywhere, and the drawn edge of NOAA coverage that went with the old decision is gone. The released wave 1 packs `north-sound`, `strait`, `wa-coast` and `overview` (1.0.0) already hold such features in tiles shared with US water; their 1.1.0 rebuild cuts them (section 13).
- Reversed: an ETOPO shift per pack area from published Canadian tide station datums (section 8). The only source found (plan Task 1 Step 5), the CHS water level API, is under the CHS Licence Agreement, not an open license. ETOPO gets one fixed 4 m shift toward chart datum wherever ETOPO is used instead. At the six tide stations read it errs shallow, by up to about 2 m in the south; inlet heads were not checked (section 8).
- Gate 1 (the fetch spike, plan Task 3) passed; the owner said go.

Owner answers on the amendment's questions (owner, 2026-11-11, by dialog):
- Bands 1 and 2 are dropped too. `US1GLBDD`, `US1GLBDC`, `US2PACWX`, `US2PACWY`, `US2PACYU` and `US2PACYW` carry no CHS notice, and on the BC side only about 4% of `US1GLBDD`'s features cite a Canadian source, but the owner chose to drop their lights and hazards in BC as well. Nothing from NOAA is shown inside the Canada polygon (7.2).
- So the Nav notice is final: `BC: depth and shoreline only. Hazards and navaids not shown. Not for navigation.` (the earlier word "most" would understate, with no NOAA objects left in BC).
- The US side of the nine cells whose general notes carry a cell-wide CHS paragraph (`US3WA1ED`, `US3WA1EE`, and band 4 `US4WA1IE`, `US4WA1IF`, `US4WA1JA`, `US4WA1JB`, `US4WA1JC`, `US4WA1JD`, `US4WA1JE`) is kept as is. That paragraph ("this product contains Canadian Hydrographic Service copyrighted works ...") covers notes whose area includes US water and does not say where the Canadian works are. The marked notice area is what is cut (7.2); US water keeps every NOAA feature.

Open owner question (the design waits for this answer):
- Old releases (section 13). Once the 1.1.0 packs and set 0.4.0 are out and verified, the 1.0.0 releases of `charts-north-sound`, `charts-strait`, `charts-wa-coast` and `charts-overview`, and set 0.3.0, which lists them, still hold the CHS-noticed features. The owner decides whether those old releases are withdrawn (deleted or marked).

## 3. Goals, non-goals, anti-goals

Goals:
- The ten approved BC areas built and released in CI as packs, each with a charts and a bathy part, each file under the 1.5 GB cap. An area that is over the cap splits into smaller packs on the grid (section 6), so there may be more than ten packs.
- Fish view across BC: contours and depth bands at the plan 7 levels, fine where NONNA 10 m exists, coarse elsewhere, no blank water inside the pack areas.
- Nav view across BC: depth shading, contours, spot depths, drying areas, land, a "no survey data" shading, and a notice that hazards and navaids are not shown.
- No NOAA chart feature inside the Canada polygon (section 7.2) in any pack, checked by the pack check.
- The US packs along the border and the overview pack rebuilt so the border shows no clipped depth edge, no gap and no doubled drawing, and so the NOAA features their 1.0.0 releases show on the Canadian side are gone. NOAA features stop at the border by design; depth and land continue across it.
- The CHS notice and the open licence credits in the packs and in the app.
- #18 fixed: no latitude hard-coded to 48 N, except the shared downsample constant that section 10 keeps on purpose.

Non-goals:
- CHS chart objects of any kind, by purchase, harvest or live display, or as carried inside NOAA cells.
- Stand-in navaids, routes, anchorages, protected areas, names or marinas from open sources.
- Protected delivery (#91).
- Alaska. Live tide or currents. Choosing which areas to install.
- Fishing contours deeper than 1,000 ft (as plan 7).

Anti-goals (failures even if it technically works):
- BC water that looks charted and safe when it is only unsurveyed. Empty NONNA must never read as deep or clear water.
- A BC Nav view that could be mistaken for an official chart: with the chart notice setting on, no BC notice, or one that is easy to miss. The "No survey data" shading and the legend do not depend on that setting.
- A depth line from NONNA in the wrong place by more than the 10 ft contour budget (section 8 sets where this applies).
- A seam at the border or between BC packs with a gap, doubled lines, a cut feature (other than NOAA features cut at the Canada polygon, section 7.2) or a visible depth step beyond what section 8 allows.
- Any NOAA feature inside the Canada polygon in a released pack.
- Any plan 7 anti-goal coming back: pauses, blank tiles or flicker at pack edges, or fast panning slower than today, now with at least 15 region packs installed (five US, ten or more BC) plus `overview`.
- A missing CHS notice in any pack that holds NONNA-derived data, or on the About page when such a pack is installed.
- A fetch from any host against its robots.txt, or a bulk fetch that gets the project blocked.
- A pack that can only be built on the dev machine.

## 4. Pack areas

From the approved map. Boxes are W, S, E, N. Exact edges move to the zoom-10 ownership grid (plan 7 spec 5.2), so each grows outward to whole grid tiles and the grid order settles overlaps. Bathy estimates are the map's upper bounds for the DEM at zoom 14; the vector file to zoom 16 adds to them, and dry runs give the real sizes.

| Region | Box | Covers | Bathy est. at z14 |
|---|---|---|---|
| `bc-south-georgia` | -123.95, 48.3, -122.2, 49.6 | Victoria, Gulf Islands, Boundary Pass, Vancouver, Burrard Inlet, Indian Arm, Fraser River, Howe Sound | ~0.7 GB |
| `bc-north-georgia` | -125.4, 49.3, -123.3, 50.4 | Sunshine Coast, Jervis Inlet, Comox, Desolation Sound, Discovery Islands | ~0.9 GB |
| `bc-johnstone` | -127.6, 50.25, -124.8, 51.0 | Johnstone Strait, Broughton Archipelago, Knight and Kingcome inlets, Port Hardy | ~0.7 GB |
| `bc-vi-west-south` | -126.6, 48.25, -123.95, 49.5 | Canadian side of the Strait, Port Renfrew, Barkley Sound, Clayoquot Sound | ~1.0 GB |
| `bc-vi-west-north` | -128.6, 49.4, -126.0, 50.9 | Nootka, Kyuquot, Quatsino, Cape Scott | ~2.5 GB |
| `bc-central` | -129.2, 50.85, -126.5, 52.75 | Queen Charlotte Strait north, Cape Caution, Rivers and Smith inlets, Bella Bella, Dean and Burke channels | ~2.8 GB |
| `bc-north` | -131.2, 52.7, -127.8, 54.8 | Princess Royal, Douglas Channel and Kitimat, Grenville Channel, Prince Rupert, Portland Inlet | ~2.9 GB |
| `haida-gwaii` | -133.3, 51.8, -131.2, 54.3 | Haida Gwaii and Hecate Strait | not estimated |
| `bc-offshore-south` | polygon on the map, about -132.86 to -126.6 W, 48.45 to 51.0 N | off Vancouver Island to about 100 mi | small (coarse only) |
| `bc-offshore-north` | polygon on the map, about -135.59 to -129.2 W, 51.0 to 55.0 N | off Haida Gwaii and Queen Charlotte Sound to about 100 mi | small (coarse only) |

The offshore polygons are in the appendix (copied from the map's data).

Ownership rules, added to plan 7 spec 5.2:
- Zoom-10 tiles that hold both US and Canadian water stay with their US pack (plan 7). Those US packs are rebuilt with Canadian-side data (section 9). Tiles whose water is only Canadian go to a BC pack.
- The BC packs join `chartpack/regions/grid.toml` after the US packs, so no wave 1 tile changes owner. The eight inshore packs come before the two offshore packs, because the first listed region that meets a tile owns it (`assign` in `grid.py`) and inshore water must never fall under the offshore packs' rules (7.1). The order among the inshore packs is the builder's call. The offshore regions are polygons, not boxes. Region files hold only a `bbox` today (`wa-coast` is a plain box that loses its shared tiles to the regions listed before it), so a polygon area in the region file is new work in this plan.
- Ownership no longer drops tiles that lie inside the clip polygon.
- Shore water is never offshore. A test asserts that no zoom-10 tile owned by an offshore pack contains any Freshwater Atlas coastline. Where the approved boxes fail it, the inshore box grows by whole tiles until it passes. One case is known: small islands off southeast Haida Gwaii (about -131.13 to -130.96 W, 51.97 to 52.31 N) sit one tile column east of the `haida-gwaii` box, so that box grows east to take them. This is a small change to an approved edge and is listed for the owner.
- Areas are defined by tile ownership, not by the boxes, so the strip a box gains when it grows to whole tiles is covered. "BC inshore area" means: all water in tiles owned by an inshore BC pack, plus the Canadian side of tiles owned by a US pack (for depth sources by the clip polygon `canada-wa.geojson`, section 6; for chart content by the Canada polygon, section 7.2). "Offshore area" means all water in tiles owned by an offshore pack. Rules written for an area apply to that water in every pack that draws it; `overview` uses the same tile ownership to tell the areas apart.
- The `overview` pack is rebuilt over the whole area, US and BC.
- An area that exceeds the 1.5 GB cap splits into smaller packs on the grid (plan 7 spec 6; section 6 says why lowering the zoom is not an option).

## 5. Data sources

All open, all fetched by CI with plain HTTPS and no account. Verified facts are on #89; items marked "check" are builder checks before first use.

| Source | Use | Licence | Fetch |
|---|---|---|---|
| NONNA-10 (CHS) | fine depth | Open Government Licence, Canada, plus the CHS NONNA Licence | WCS `https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs`, coverage `nonna__NONNA 10 Coverage` |
| NONNA-100 (CHS) | coarse depth | same | same WCS, coverage `nonna__NONNA 100 Coverage` |
| CRM volume 8 (NOAA) | coarse depth south of 49 N | US Government work | as plan 7 |
| ETOPO 2022 15 arc-second (NOAA) | coarse depth where nothing else reaches (#92) | CC0 | one tile: `ETOPO_2022_v1_15s_N60W135_surface.tif` (31 MB, URL on #92) |
| BC Freshwater Atlas Coastlines | BC shoreline and land | Open Government Licence, British Columbia | WFS on `openmaps.gov.bc.ca`, layer `WHSE_BASEMAPPING.FWA_COASTLINES_SP`, paged with `sortBy=OBJECTID` |
| NOAA ENC cells that reach into Canada | chart objects in US and Alaskan water only; nothing from them is shown inside the Canada polygon (7.2), which is built from their CHS notices and `US1GLBDD`'s Canadian area | US Government work, except the CHS-noticed Canadian part | as plan 7 |

Checks before first use (each is a plan task with its result posted on #90; a failed check stops that source and goes to the owner):
1. NONNA WCS: read the host's robots.txt; find the largest request the server accepts; confirm the sign and nodata conventions (the #89 samples held negative values for depth and positive for drying heights); confirm the native grid (EPSG:3857, about 19 m and 153 m pixels).
2. NOAA Canadian-side content: read the NOAA ENC terms and the cell metadata for any restriction on content that came from CHS. #89 found none stated but did not settle it.
3. Freshwater Atlas coastline: which tide level the line follows, and whether closed land polygons can be built from the lines without gaps.

Results (plan Task 1, 2026-11-11, on #90): check 1 passed. Check 2 failed: the cells carry a CHS license notice over their Canadian part; the owner's decision is in section 2 and the design in 7.2. Check 3 passed with two findings: the lines join end to end and island rings are closed, but the lines are not consistently directed (island rings and mainland pieces run opposite ways), so land is built without relying on direction (7.1); and the atlas does not document which tide level its line follows.

Fetch manners (all Canadian hosts): one connection, requests in sequence, a pause between requests, an honest User-Agent naming the project and repo, back off on errors, stop for good on HTTP 403 or 429 and report. Fetching is separate from building (designer's call). A `workflow_dispatch` fetch workflow pulls the NONNA grids and the coastline for one region and stores them, losslessly compressed, as assets of a source-data release in this repo (NONNA's licence allows redistribution with the notice, which the release notes carry). Pack builds, dry runs and tag runs read from that release and never call the Canadian hosts. The #89 estimate is about 18 GB of raw Float32 for all of BC, mostly nodata; each stored asset must stay under 2 GiB, split by region or sub-area as needed. The Actions cache is not used for this (10 GB repo limit).

Spike pass rules (section 14 step 1), with numbers posted on #90:
- robots.txt of the WCS host allows the request path; a refusal stops NONNA and goes to the owner;
- one inlet fetched in a CI run, with the request size and pause that will be used;
- the projected fetch time for the largest region is under 3 hours in one run, or the fetch is resumable across runs;
- the compressed size of the largest region's NONNA-10 is known, and the build's peak disk use for it is projected to leave the fit guard's free-space margin on the 14 GB runner (plan 7 PR B: `fit-guard.sh`);
- charts jobs now need depth too (7.1): the projected charts build time for the largest region is inside the fit guard's time limit;
- `overview` builds from NONNA-100, the coarse sources and the stored no-survey masks only, and its projected time and disk are inside the fit guard.
A failed rule changes the design (smaller regions, a lower NONNA request size, streaming) before any reader is written.

## 6. Depth for the Fish view (#90, #92)

Which source wins, by side of the border. The US side is defined positively: water in a tile owned by a US pack that is on the US side of the clip polygon `chartpack/regions/clip/canada-wa.geojson`. Everything else is the Canadian column: every tile owned by a BC pack (inshore or offshore, Alaskan water included, section 7.2) and the Canadian side of US-owned tiles. First source with data wins.

| Tier | US side | Canadian side |
|---|---|---|
| fine | CUDEM | NONNA-10, then CUDEM where it reaches across |
| coarse | CRM, then ETOPO | NONNA-100, then CRM (it ends at 49 N and 127 W), then ETOPO |

NONNA is not used on the US side even where it has data, and CUDEM never overrides NONNA-10 on the Canadian side (designer's call: each country's survey on its own water, each datum on its own side). ETOPO is last in both columns so that no water is left blank; plan 7 found CRM fills the US side, so it should never be reached there.

Fine and coarse (plan 7 spec 5.3a), applied to BC:
- fine (`bathy`, `dem`): NONNA-10 water, built to the same max zooms as US fine water (vector 16, DEM 14). This is forced, not chosen: the install merge refuses fine members whose max zooms differ (`maxzoomMismatch` in `plotter/src/core/PackMerge.cpp`), and a source draws a missing tile blank inside its zoom range, so BC fine tiles that stopped at a lower zoom would leave Fish blank when zoomed in. A 10 m grid gains little past zoom 13; the extra zooms cost size, not correctness.
- So size is handled by area, as plan 7 spec 6 says: a BC area whose bathy file would exceed 1.5 GB splits into two or more packs on the grid. From the map's estimates this is likely for `bc-vi-west-north`, `bc-central` and `bc-north` (about 2.5 to 2.9 GB each at zoom 14). The builder names the parts (for example `bc-central-south`, `bc-central-north`) and settles them from dry-run sizes. The approved areas do not change; only the number of packs does.
- coarse (`bathy-coarse`, `dem-coarse`): max zoom 12 for every pack, as today, stretched past it. ETOPO-only water is built to zoom 12 like CRM-only water; the offshore packs are large in area, so if one exceeds the cap it splits on the grid too.
- The number of sources and layers in the style stays fixed, and so do the max zooms of the four bathy files. Any other answer (a third tier, a different max zoom, relaxing the merge check) is a change to this spec and goes to the owner first.

Contour levels and bands are plan 7's, in feet: every 10 ft to 300 ft with the 5 ft fine levels, every 50 ft to 600 ft, every 100 ft to 1,000 ft, deepest band "deeper than 1,000 ft".

The two offshore packs are coarse only. NONNA holes inside inshore packs (the shelf off Tofino, parts of Dixon Entrance, nearshore strips) fall through to the coarse sources.

Three grades of BC depth, with one name each, used in legends and notices:
- "Survey depth": NONNA-10. The 10 ft contour budget applies.
- "Coarse survey depth (100 m grid)": NONNA-100. Real CHS survey data on a coarse grid; it is the only source in Nootka and Tahsis and on much of the outer slope. Contours there are smoothed and small features are lost.
- "Rough depth, worldwide grid": CRM on the Canadian side and ETOPO. Not survey quality.
Fish view marks the second and third with their own legend entries; the builder picks marks that read in all three palettes (for example a contour dash and a light pattern).

Where even the coarse merge has no value over water (not expected: ETOPO is global), the tile shows the "no survey data" shading of section 7.

## 7. The BC Nav view

### 7.1 What it draws

BC charts packs carry the same vector source and layers as US charts packs, filled from different data, so the app and the Nav styles treat BC like any other region (designer's call).

- Depth areas (the chart-style blue bands) and depth contours: derived from NONNA-10 and NONNA-100 (and, in the offshore area only, the coarse sources). Contour values are a fixed list in meters taken from the values the wave 1 NOAA cells already use, so that the merged `cheekymarine:valdco` list (which the app uses to pick the safety contour, and which the Nav style matches by equality in `chartpack/src/chartpack/style/nav.py`) gains no new value. The builder reads the wave 1 list from the released packs and writes the BC list into the plan; a check asserts every derived contour value is in the wave 1 list. NOAA cells that are new to the build (the Alaskan cells) may carry contour values of their own; the builder posts any such value on #90 and settles it before tagging, with #95 (safety contour per cell) in view, so the safety contour does not vanish outside those cells. Depth area limits use the same values.
- Shoal bias: every grid that feeds Nav depth areas, contours or spot depths is downsampled by taking the shallowest value in each block, never the mean (`zoom_grids` in `chartpack/src/chartpack/bathy/contours.py` uses block means today; Fish may keep them). Nav never shows water deeper than the data says.
- No fill-in: derived Nav depth never extends into water without a NONNA value. No interpolation across holes. The "No survey data" area is computed once at the native NONNA grid and cuts the depth areas and contours at every zoom, so a hole can look larger when zoomed out but never smaller.
- Coarse survey water (NONNA-100 only) draws as depth in Nav, with the legend entry "Coarse survey depth (100 m grid)" and a mark that sets it apart from NONNA-10 water (designer's call: it is survey data, so it is better shown than hidden, but it must not pass for fine survey).
- Spot depths: sampled from NONNA-10 and NONNA-100 only, never from CRM or ETOPO, thinned per zoom like ENC soundings, and biased shallow (the shallowest value in each thinning cell), as a chart would.
- Drying areas: NONNA values above chart datum draw as the intertidal band.
- Land and shoreline: Canadian land and coastline come from the Freshwater Atlas lines and are drawn only inside the Canada polygon (7.2). Outside it (Alaska, and the US side) land and coastline come from the NOAA cells, finest band first. Inside the polygon no NOAA land is drawn, so a place where the atlas has no land is not drawn as land at all: with no NONNA value there it shows as "No survey data". Renders look for such places (section 15).
- Land polygons are built inside the Canada polygon only, without relying on line direction, which the source check found is not consistent (designer's call). The coastline lines, with the atlas's river-mouth closing lines (`EDGE_TYPE` 150, "Construction line, coastline") used like coastline, and the outline of the read box cut to the Canada polygon split that area into faces. Every coastline end must lie on that outline: on the box edge, or on the Canada polygon's boundary where the atlas stops at the border (Blaine, Point Roberts, the Alaska boundary); the face is then closed along it. An end anywhere else fails the build. Two faces that share a coastline line are of opposite kinds; of the two kinds, the one holding more NONNA cells deeper than 2 m is water and the other is land. Then two corrections: a land face of at least 0.05 km2 more than 20% of whose area is wet NONNA cells (a value at or below chart datum) is water, so a river that the atlas closes off as its own face stays water where surveyed, while a smaller face that a closed atlas ring bounds (an islet) always stays land; and land never covers a wet NONNA cell (so a surveyed river such as the Fraser stays water even where the atlas draws no separate face for it). The build fails when the faces cannot be split into two kinds, or when, before the corrections, more than 1% of the deep NONNA cells fall on land. That 1% guard catches a wrong land side and a coastline misplaced seaward (both put the deep water beside the line on land); there the "land never covers wet" cut also keeps the surveyed water from being drawn as land. It does not catch a coastline misplaced landward by less than about 1 km, which puts no deep cell on land (measured on bc-south-georgia: the whole coastline moved 100 m landward gives 0.29% and 300 m gives 0.84%, both passing; 1 km gives 51.43% and stops, as almost no deep cell is left near a line); the strip of real land between the two lines then has no NONNA value and draws as "No survey data", never as surveyed depth, and the renders and the Garmin comparison (section 15) are for it (amended 2026-11-12, #90 PR 127 review). The share is measured over the deep NONNA cells within 500 m of an atlas coastline line, and the build fails when no deep cell lies that close; the deep cells on land farther out are counted in the derive stats instead (amended 2026-11-12, #90: measured within 500 m of the coastline, because surveyed rivers and lakes inside land faces are not a coastline error). It does not catch errors smaller than that share, such as one unsurveyed river drawn as land or a shoreline off by less than a NONNA cell; the renders and the Garmin comparison (section 15) are for those. A box with no coastline is all water. The atlas does not say which tide level its line follows (section 5).
- No survey data: water (not land) in the BC inshore area where neither NONNA grid has a value. Outside the Canada polygon it is drawn only where no NOAA depth area or land area covers the place (7.2). The fetch workflow (section 5) computes this area once per region at the native NONNA-10 grid and stores it as a vector mask beside the source grids, so `overview` and the rebuilt US packs read the mask instead of the 10 m grids. Because `overview` then takes depth from NONNA-100 and the mask from NONNA-10, the fetch workflow reports any water where NONNA-10 has data and NONNA-100 has none (the #89 samples show none). It draws as a distinct shading that cannot be read as deep water, in all three palettes (day, dusk, night), with the legend entry "No survey data". Coarse filler depth may still tint it in Fish view, but in the BC inshore area the Nav view never draws CRM or ETOPO as depth areas (designer's call: on a chart-like view, rough worldwide depth must not look surveyed, and a 460 m grid is unreliable in narrow inlets). Only the offshore area draws Nav depth areas from the coarse sources. A NONNA hole on the outer shelf of an inshore pack therefore shows "No survey data" next to the offshore pack's depth bands; that seam is accepted.

Pack check: `_check_safety_layers` in `chartpack/src/chartpack/pack/check.py` requires every safety layer to have features at each band zoom, and the release workflow runs it. A BC charts pack built from depth and shoreline cannot pass it as written. The region file declares the charts as derived; for a derived pack the check requires depth areas at each zoom, and for an inshore pack also land (an offshore pack may hold neither land nor a no-survey area). A second rule runs on every charts pack that draws BC inshore water, the rebuilt US packs and `overview` included: no derived depth feature lies inside the no-survey area. It is the automated test of the first anti-goal. A third rule runs on every charts pack plan 8 builds: no feature but derived ones lies inside the Canada polygon (7.2), and a matching rule on every bathy pack: no NOAA contour lies inside it. They are the automated test of the owner's decision of section 2. The source comparison of the existing check does not expect source hazards inside the Canada polygon, since they are cut there; it checks every other hazard as today. The safety-layer check stays as strict as today for every US pack, rebuilt ones included.

### 7.2 NOAA chart content and the Canadian side

The NOAA cells that reach into Canada carry a CHS license notice over their Canadian part (section 2), so nothing from them is shown there. Known reach (#89 stand-ins comment, section 10): `US3WA1EF` at 1:180,000 over Haro Strait, Victoria, the southern Gulf Islands and Boundary Pass to about 49.08 N; `US3WA1EE` and `US3WA1ED` at 1:350,000 along the north side of the Strait and off southwest Vancouver Island to about 48.77 N; `US3AK1DX` and `US3AK1DY` at 1:350,000 over Dixon Entrance down to 54.0 N; bands 1 and 2 over all offshore water.

The Canada polygon (designer's call): one fixed polygon file in the repo, `chartpack/regions/clip/canada-chs.geojson`, built by a committed script from the NOAA cells that meet the plan 8 area (a box from 137 W to 120 W and 46 N to 56 N). It is the union of three parts:
- The CHS-notice areas of the seven band 3 cells that carry the notice (`US3WA1ED`, `US3WA1EE`, `US3WA1EF`, `US3AK1DW`, `US3AK1DX`, `US3AK1DY`, `US3AK1EY`). A notice is found by the text "Fisheries and Oceans Canada" in the note's text file. Matching "Canadian Hydrographic Service" alone is a trap: those words also appear in the cell-wide general notes of `US3WA1ED`, `US3WA1EE` and seven band 4 cells, which cover US water, and in the source lines of most cells.
- The Canadian areas (`ADMARE` with `NATION=CA`) of both band 1 cells, `US1GLBDD` (east of 134.4 W) and `US1GLBDC` (west of it), except where one of the seven band 3 cells has coverage: there the band 3 notices alone decide.
- The Canadian areas of every band 4 and band 5 cell, the finest cells.

Band 2 cells are read but not used: outside the band 1 Canadian areas, their only Canadian area is a 21,645 km2 area off Oregon in `US2PACWX` (south of about 47 N, west of 126.4 W) that looks mislabeled and lies outside every pack. The script records in the file each cell it read, with its band, edition, update and issue date, and marks the seven notice cells.

A trial build on 2026-11-11 (the research cells and a fresh download of `US1GLBDC`) gave one valid polygon of about 1.67 million km2 with about 2,500 vertices. Every CHS-notice area lies inside it. The Canadian water west of 134.4 W that only `US1GLBDC` covers (for example 15,188 km2 between 52.3 and 54.0 N, 135.6 and 134.4 W, inside `bc-offshore-north`) lies wholly inside, and so does `bc-offshore-south`. The part of `bc-offshore-north` outside it is Alaskan water north of about 54.0 N.

What this construction gets wrong or accepts:
- Undisputed Alaskan water is not cut. `US1GLBDD`'s Canadian area includes 94.8 km2 north of the A-B line (about 131.2 to 130.9 W, 54.69 to 54.77 N) that `US3AK1DY` puts outside its CHS notice, and in the trial build no finer cell called it Canadian (`US4AK5FP`, which covers it, has no Canadian area). The band 3 cell wins there, so NOAA data stays. This rests on the trial build; the build script asserts it again on every run (plan Task 9).
- The band 4 and 5 Canadian areas add, beyond the other two parts, these pieces over 1 km2 in the trial build: the Juan de Fuca strip (below; `US4WA1JA` 15.3 km2, `US4WA1JB` 23.6 km2) and about 12 km2 in Dixon Entrance from `US4AK5FO` (a thin band at about 54.68 to 54.69 N, 132.0 to 131.4 W, just north of the band 3 notice line), which is cut. Every other band 4 or 5 addition was under 0.3 km2.
- The 39 km2 strip at the western entrance of the Strait of Juan de Fuca (about 125.36 to 124.74 W, 48.35 to 48.51 N) is inside the polygon, so it is cut (designer's call, the safe reading of the research). The finest cells there (band 4 `US4WA1JA`, `US4WA1JB` and `US4WA1JC`) and `US1GLBDD` call it Canadian; band 3 `US3WA1ED` and `canada-wa.geojson` call it US. The strip looks like a disputed seaward area; the cells do not say. Cost: 39 km2 of water that NOAA's band 3 cell calls US loses its NOAA features in `strait` and `wa-coast` (traffic lanes, cables, depth areas, soundings: 50 to 82 features of each cell meet it) and shows derived NONNA depth or "No survey data" instead. Its Fish depth keeps the US sources, because the depth side follows `canada-wa.geojson` (below).
- The disputed Dixon Entrance water south of the A-B line (about 2,800 km2, which NOAA also labels US water) carries the CHS notice, so it is treated as Canadian side: NOAA content is cut there and BC data draws.
- NOAA can change the cells. The polygon does not follow a new or moved notice or boundary until the script is run again; the guards below catch it.

The rule:
- Every NOAA feature of every band (1 to 5) is cut at the polygon in every pack. In charts packs (the BC packs, the rebuilt US packs and `overview`) area and line features are cut at its edge and point features inside are dropped. In bathy packs the ENC fallback contours (NOAA depth contours, section 9) are cut at it. Nothing NOAA remains inside: no depth, no land, no navaids, no hazards, no regulated areas.
- Bottom samples of any source, the USGS ones included, are cut at the polygon too (designer's call). So nothing draws inside the polygon but the derived depth, the atlas land and "No survey data".
- Guards, each of which fails the build: a cell the polygon file lists as carrying the notice yields no notice area, or a note names a text file missing from the cell; any point of any loaded cell's notice area lies more than 20 m from the polygon (so a new NOAA edition cannot slip CHS content in); for every charts pack, the Canadian area of a loaded band 1, 4 or 5 cell (band 1 outside the coverage of the notice cells) lies more than 20 m outside the polygon within the pack's owned tiles (so a piece of Canadian water the polygon misses cannot go unseen).
- Pack check, on every charts pack: no feature lies inside the polygon unless it is derived (it carries a derived source name in `src`) or it is a "No survey data" area; bottom samples are included. On every bathy pack: no ENC contour lies inside it. "Inside" means the feature's geometry meets the polygon shrunk by 4 units of the 4,096-unit tile grid, in every tile at every zoom. Tippecanoe, as the packs are built, keeps each line and polygon within 1 unit of its place and rounds to half a unit, with the same detail at every zoom, so a correctly cut feature stays at least 2.5 units clear of the shrunk polygon; 4 units are about 400 m at zoom 6 and 6 m at zoom 16.

What draws inside the polygon:
- BC inshore area: derived NONNA depth, Freshwater Atlas land and "No survey data" (7.1).
- Offshore area: derived depth from NONNA-100 where it has data, else from the coarse merge (CRM, ETOPO), as 7.1 allows offshore.

Outside the polygon inside BC-owned tiles (undisputed Alaskan water in `bc-north` and `bc-offshore-north`, and any US or high-seas water in the offshore packs), the NOAA cells draw as in US water, depth and land included. Derived depth and "No survey data" are not drawn where a kept NOAA depth area or land area covers the place (one winner per place), and atlas land is not drawn outside the polygon. So Alaskan land comes from the NOAA cells and Canadian land from the atlas.

One line in charts packs: in a charts build the Canada polygon is the only border line. It cuts the NOAA features and bounds the derived depth, the atlas land and "No survey data", and both sides are cut from the same geometry (one keeps the part outside, the other the part inside), so they meet with no gap and no overlap. `chartpack/regions/clip/canada-wa.geojson` keeps two jobs only: the depth-source side in bathy builds (section 6) and tile ownership (section 4); it stops at 49.5 N. The two files describe the same border in Washington water from different NOAA data. Outside the Juan de Fuca strip the trial build found them within 15 m of each other, so the Fish view's depth source may change up to 15 m from the line where the Nav view's chart content changes, which is not visible. In the strip, Nav treats the water as Canadian side and Fish as US side. The build fails if, inside the area `canada-wa.geojson` covers (away from its artificial north, east and west edges) and outside the strip, the two disagree anywhere by a strip wider than 20 m.

Alaskan water: `bc-north` and `bc-offshore-north` reach past the Dixon Entrance line, and no US pack owns tiles there. Alaska is not a goal, so nothing is added for it: outside the polygon the NOAA cells already listed draw as in US water, and Fish depth comes from the merge order of section 6 (NONNA wherever it has data, else coarse).

### 7.3 Saying what is not there

- Nav view, when any BC notice area of the charts files is on screen: "BC: depth and shoreline only. Hazards and navaids not shown. Not for navigation." (owner, section 2).
- BC notice areas (designer's call). For a charts file: the part of the pack's owned tiles (for `overview`, its whole area) that lies inside the Canada polygon, land included. Every NOAA feature is cut there, so this is exactly where the Nav view shows no NOAA content. For a bathy file: the Canadian column of section 6 (every BC-owned tile and the Canadian side of US-owned tiles). So Alaskan water in BC-owned tiles is outside the Nav areas, where the NOAA cells draw, and inside the Fish areas, where depth is on chart datum.
- Fish view, when any BC water is on screen (Canadian side, any depth source): "BC: CHS survey depths where available, rough elsewhere. Chart datum. Not for navigation." in place of today's "survey depths, approx. MLLW" banner, which would be false over worldwide-grid water (section 8 explains "chart datum").
- The splash and any other place that shows the pack notice line today get the same short BC line when a BC pack is installed.
- The trigger is what is on screen, not the view center (designer's call): a view over Haro Strait that shows both countries gets the BC notice.
- The notice uses the existing notice bar and obeys its "show chart notice" setting (`noticeShown` in `plotter/qml/ChartPage.qml`), by the owner's decision (section 2).
- How the app knows the area (pack metadata, a coverage polygon in the pack, or a tile property) is the builder's call. The notice must not depend on one style string for the whole merged chart, since US and BC tiles share one style after the merge.

## 8. Datum

- NONNA is already on Canadian chart datum. No shift is applied (plan 7 spec 8 planned for this).
- Canadian chart datum (lower low water, large tide) sits a little lower than US MLLW. At the border the two meet. The builder measures the step along the Haro Strait and Boundary Pass seam and in the Strait and posts it on #90. If the step moves a contour by more than the 10 ft budget anywhere, it goes to the owner before packs are tagged; otherwise it is accepted and noted in the pack NOTICE.
- CRM and CUDEM on the Canadian side south of 49 N are converted as in plan 7 (to MLLW with the Washington stations). They are used only where NONNA has nothing (section 6 table).
- ETOPO heights are EGM2008 like CRM, taken as mean sea level. For plan 8, wherever ETOPO is used, they get one fixed shift toward chart datum (owner, section 2): depth below chart datum = depth below mean sea level minus 4.0 m. No tide station values are used: the only source found, the CHS water level API, is under the CHS Licence Agreement, not an open license. At the six stations read (Victoria, Tofino, Port Hardy, Bella Bella, Prince Rupert, Daajing Giids), 4.0 m is equal to or greater than the height of mean water level above chart datum (1.88 to 3.99 m), so there the shift errs shallow, by 2.12 m at Victoria down to 0.01 m at Daajing Giids. Inlet heads were not checked; where mean water level lies more than 4 m above chart datum the shift would err deep. An ETOPO water cell whose shifted depth would fall below zero gets depth 0.0: ETOPO never makes a drying area. The pack NOTICE says: "ETOPO depths are shifted by a fixed 4 m toward chart datum; no tide station data is used." ETOPO is a 460 m grid; the 10 ft anti-goal does not apply to it.
- The 10 ft contour anti-goal applies to water drawn from NONNA-10 only. The other two grades (section 6) are labeled.

## 9. Border and seams

- US packs whose owned tiles hold Canadian water are rebuilt: at least `north-sound`, `strait` and `wa-coast` (the builder confirms the list from the grid). Charts: NOAA features cut at the Canada polygon and the derived BC layers inside it (7.1, 7.2), so the CHS-noticed features of their 1.0.0 releases are gone. Bathy: by the table in section 6, with no clipped edge.
- `overview` is rebuilt over US and BC: charts from NOAA bands 1 to 3 under the rules of 7.2, plus derived BC depth (from NONNA-100, which is ample at zoom 9 and below), land and "No survey data" (from the stored masks) at low zoom; bathy from one coarse merge. It never reads NONNA-10. The plan 7 rule that overview bathy sources must be `["crm"]` is widened to the coarse sources.
- The ENC fallback contours (NOAA depth contours drawn in bathy packs where no depth grid reaches, plan 7 PR D) are NOAA features: they are never drawn on the Canadian column of section 6 nor inside the Canada polygon (7.2), in any bathy pack, so no contour draws twice and none comes from NOAA on the Canadian side.
- Seams between BC packs follow plan 7: each pack reads every source tile that meets its owned tiles, so features cross whole.

## 10. Latitude (#18)

`scamin.py` (`_COS_LAT`) and `bathy/contours.py` (`zoom_tolerance_deg`) hard-code 48 N. BC runs from 48.3 N to 55 N.

- The latitude comes from where the feature is, not from a constant. Designer's call: use the latitude of the feature or of its tile row instead of one value per region, so two packs never disagree along a seam. The issue text proposes the region bbox center; the builder may use that only if renders at a seam between two BC packs show no feature appearing at different zooms on the two sides.
- A third constant, `REF_LAT = 48.0` in `bathy/contours.py`, fixes the downsample block factors so every pack uses the same ones. It stays (designer's call): changing it per pack would make neighbors downsample differently at seams. At 54 N the grid cells are about 12% narrower than the factor assumes, which is harmless.
- Wave 1 packs that are not rebuilt (see section 12 for when all are) keep their 1.0.0 output. The change may shift some features by one zoom in rebuilt packs; the builder checks the `sound-central`/`north-sound` seam renders for a visible difference.

## 11. Notices and credits

Required by the CHS NONNA Licence, clause 7, "in a prominent location" on every derived product. Exact text, with the name filled in as "the CheekyMarine project" (designer's call; the owner may prefer their own name):

> This product was made by the CheekyMarine project and contains intellectual property of the Canadian Hydrographic Service (CHS) of the Department of Fisheries and Oceans.
>
> This product does not meet the requirements of the Navigation Safety Regulations, 2020 under the Canada Shipping Act, 2001. Charts and publications issued by or on the authority of CHS must be used to meet the requirements of those regulations.
>
> The copyright in the data are and remain the property of His Majesty the King in Right of Canada and shall not be sold, licensed, leased, assigned or given to a third party.
>
> The incorporation of CHS data in this product does not constitute an endorsement or an approval of this product by the Canadian Hydrographic Service, the Department of Fisheries and Oceans or His Majesty the King in Right of Canada.

Where it goes (designer's call):
- the NOTICE of every pack that holds NONNA-derived data (all BC packs, the rebuilt US packs, `overview`), with "Contains information licensed under the Open Government Licence – Canada." and a link to https://open.canada.ca/en/open-government-licence-canada ;
- the app's About page, in full, whenever such a pack is installed;
- the release notes of each such pack and of the set;
- on the chart itself, the short standing notices of 7.3.

Also in the NOTICE files and About: "Contains information licensed under the Open Government Licence – British Columbia." with a link to that licence (shoreline), the ETOPO 2022 citation (#92) with the fixed-shift line of section 8, and the existing NOAA lines. The builder re-reads each licence page on the day and records the date, as `chartpack/NOTICE` does today.

## 12. App and installer

Plan 7 already loads any number of packs and merges them at install. Plan 8 adds:
- the area-aware notices of 7.3 and the "chart datum" banner of section 8;
- legend entries: "No survey data", "Coarse survey depth (100 m grid)", "Rough depth, worldwide grid";
- the About page text of section 11;
- nothing else by intent. The builder avoids a pack schema change if the new layers and metadata fit schema 2. If a change is needed, the builder raises the pack schema and the plotter's accepted range together, an older plotter refuses the new packs with the existing per-pack reason, and every wave 1 pack is rebuilt at the new schema, `sound-south` and `sound-central` too (designer's call: the set check in `installer/lock-tool.sh` that all packs of a kind share one schema stays strict). That lengthens the release list of section 13 and applies the #18 change to all packs.

With at least 15 region packs plus `overview`, the install-time merge and the merged files grow several times over plan 7's (2.4 GB, 5 s on the test laptop). The plan measures merge time, disk use and fast-pan frame time on the test laptop with all packs before the set is released, against the plan 7 numbers on #84 (same-path p99 33 ms against a 30.7 ms baseline; merge 5 s for 2.4 GB). Pass: no blank tiles; p99 frame time on the plan 7 path within 15% of plan 7's 33 ms; merge time under 5 minutes. The installer's free-space check (#96) must pass on CapnButts.

## 13. Releases

- BC packs: `charts-<region>-v1.0.0` and `bathy-<region>-v1.0.0` through `chartpack-release.yml`, dry runs first (`workflow_dispatch` from main).
- Rebuilt US packs and `overview`: a minor version bump. The 1.1.0 packs no longer hold NOAA features on the Canadian side. Their 1.0.0 releases, and set 0.3.0, which lists them, still do; whether those old releases are withdrawn (deleted or marked) is the owner's decision, taken after the new ones are verified (section 2).
- Then a plotter release if the app changed, and a set release listing every pack, as a pre-release.
- Tags need the owner's OK first and are pushed one per `git push`, about 2 minutes apart, with a run confirmed per tag.
- CI fit: every BC pack must build on the GitHub runner (16 GB RAM, 14 GB disk, 6 h job limit) within the plan 7 fit guard (5 h and 2 GiB free). NONNA raw data for one pack must fit the disk with margin; the builder streams or chunks where it does not.

## 14. Order

1. Source checks (section 5) and a small CI spike: fetch one inlet from the NONNA WCS and one page of the coastline WFS in a `workflow_dispatch` run; post sizes, timings and limits on #90.
2. #18 latitude.
3. Readers: NONNA (fine and coarse), ETOPO (#92), coastline to land polygons; merge order and datum rules.
4. The Canada polygon; derived Nav layers, "no survey data", NOAA cut at the polygon with its guard and pack check.
5. App: notices, legend, About. Pack schema if needed.
6. Region files and grid for the ten BC areas (split where the cap needs it); rebuilt US border packs and `overview`; dry runs; size and fit checks.
7. Renders for the owner (section 15), then tags, releases, set release.
8. Test laptop measurements, CapnButts install, Garmin photo comparison.

## 15. Done

- Packs for the ten BC areas, the rebuilt US border packs and `overview` released from CI, each file under 1.5 GB, each with the notices of section 11.
- A set release installs them all on CapnButts; About lists them and shows the CHS notice.
- Renders posted on #90 for the owner, with plain-language captions, at least: Victoria and Haro Strait (border seam: NOAA content stops at the border, BC depth and shoreline beyond), Active Pass, Vancouver harbor and Indian Arm, Desolation Sound, Knight Inlet head, Barkley Sound, Nootka Sound (NONNA-100 only), the shelf off Tofino (NONNA hole), Bella Bella, Prince Rupert, Dixon Entrance (NOAA content stops at the A-B line; NONNA hole), Masset, the 49 N line where CRM ends, and one view in each offshore pack. Nav and Fish for each. For three views that contain "No survey data" next to depth bands (Tofino shelf, Nootka, Dixon Entrance): day, dusk and night, and in each the no-survey shading must be told apart from every depth band by its pattern, not by color alone. Also: any place inside the Canada polygon where the atlas has no land (7.1), and the zoom-change lines that the latitude rounding of section 10 can cause (plan Task 16).
- Test laptop: fast panning across the border seam and across a corner where BC packs meet shows no blank tiles and no doubled or cut lines, and meets the pass numbers of section 12 (numbers posted).
- The automated checks pass in CI for every pack: no derived depth in no-survey water (7.1), no feature but derived ones inside the Canada polygon in charts packs and no ENC contour inside it in bathy packs (7.2), the unchanged `valdco` list (7.1), tile ownership (4).
- Garmin comparison: the owner provides photos of the Garmin at BC spots. For each photo the session renders the same place and zoom and posts the pair on #90 with what matches and what differs. Pass (designer's proposal, the owner judges): where NONNA-10 has data, the plotter's contour for a depth lies within one 10 ft contour step of the Garmin's line for the same depth, and spot depths at the same place agree within 10 ft; the shoreline lines up to within what the photo can show; wherever the Garmin shows detail the plotter lacks, the plotter's screen says so. Differences become follow-up issues.
- The owner pans BC on CapnButts and says the Nav and Fish views are acceptable.
- Owed after the plan: a live side-by-side with the Garmin in BC water (added to the boat checks).

## 16. Issue housekeeping

- #89 closes with this plan: its research is done. The parked CHS question and the stand-in fallback move to a new issue with a reference back (designer's call), which stays out of plan 8.
- #91 loses the `plan 8` label and stays open, parked with the CHS question (it is only needed if unpublishable data ever arrives).
- #90 is the plan's log: checks, spike numbers, renders, the Garmin comparison.

## 17. Left to the builder

The NONNA request size (5), how over-cap areas split and what the parts are called (6), the marks for the three depth grades (6, 7.1), how soundings are thinned (7.1), how the app learns the area for notices (7.3), the list of US packs to rebuild (9), per-feature or per-row latitude (10), whether schema 2 is enough (12), and the order among the inshore BC packs in the grid (4). Everything marked "designer's call" was set by the designer, not the owner, and the owner may change it.

## Appendix: offshore areas

GeoJSON polygon coordinates (longitude, latitude), from the approved map. The first ring is the outline; further rings are holes around islands.

`bc-offshore-south`:

```json
[[[-132.864,51.0],[-129.2,51.0],[-129.184,50.85],[-128.6,50.85],[-128.595,49.407],[-126.6,49.4],[-126.6,48.45],[-128.302,48.45],[-129.469,49.135],[-130.024,49.683],[-132.44,50.756],[-132.864,51.0]]]
```

`bc-offshore-north`:

```json
[[[-135.106,55.0],[-133.137,55.0],[-133.136,54.952],[-133.065,54.947],[-132.994,54.837],[-132.908,54.838],[-132.932,54.79],[-132.84,54.742],[-132.843,54.699],[-132.745,54.674],[-132.7,54.71],[-132.758,54.742],[-132.735,54.787],[-132.942,54.948],[-132.945,55.0],[-132.551,55.0],[-132.546,54.941],[-132.49,55.0],[-132.434,54.966],[-132.391,55.0],[-132.345,54.895],[-132.216,54.804],[-132.289,54.728],[-132.025,54.696],[-132.01,54.784],[-131.959,54.814],[-132.047,54.899],[-131.98,54.917],[-132.01,54.968],[-131.979,55.0],[-131.01,55.0],[-130.982,54.991],[-130.913,54.8],[-131.199,54.786],[-131.2,54.3],[-133.297,54.291],[-133.298,51.812],[-131.216,51.8],[-131.2,52.138],[-131.141,52.176],[-131.181,52.241],[-131.1,52.272],[-131.2,52.31],[-131.2,52.7],[-129.222,52.7],[-129.2,51.0],[-132.864,51.0],[-134.621,52.413],[-135.44,53.405],[-135.592,53.795],[-135.592,54.064],[-135.361,54.648],[-135.106,55.0]],[[-131.091,52.154],[-131.128,52.096],[-131.056,51.967],[-131.027,51.995],[-131.065,52.084],[-130.963,52.092],[-131.091,52.154]],[[-131.105,52.231],[-131.107,52.172],[-131.01,52.209],[-131.025,52.233],[-131.105,52.231]],[[-131.438,54.956],[-131.349,54.861],[-131.212,54.908],[-131.262,54.995],[-131.438,54.956]],[[-132.663,54.821],[-132.682,54.785],[-132.623,54.761],[-132.617,54.792],[-132.663,54.821]],[[-132.645,54.902],[-132.789,54.893],[-132.718,54.829],[-132.638,54.857],[-132.645,54.902]]]
```

Because the inshore packs come first in the grid order, tiles these polygons share with an inshore box go to the inshore pack.
