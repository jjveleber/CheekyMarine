# Plan 8: chart coverage wave 2 (British Columbia)

Issues: #90 (BC packs), #92 (ETOPO reader), #18 (SCAMIN and contour latitude), #89 (licence research, closes with this plan). #91 (protected delivery) leaves plan 8 (section 2). Builds on plan 7: `docs/superpowers/specs/2026-11-08-chart-coverage-plan7-design.md` (called "plan 7 spec" below).

Region review map (BC areas approved 2026-11-08): https://claude.ai/artifact/J2hnEnQ3P79ZB7xJMbcJK5 , approval: https://github.com/jjveleber/CheekyMarine/issues/83#issuecomment-6724880220

Research this spec rests on, all on #89: the first two comments (CHS ENC, NONNA, GEBCO, ETOPO; the free CHS chart service) and "open stand-ins for chart objects in BC" (https://github.com/jjveleber/CheekyMarine/issues/89#issuecomment-6798801773).

## 1. Intent

Plan 7 covered the US waters the owner uses. North of the border the plotter is blank: Canadian water is clipped out of every pack. Plan 8 covers the British Columbia coast, inlets and islands, plus offshore water to about 100 mi, on the plan 7 machinery (several packs drawn as one chart, tile ownership, fine and coarse depth, CI-only builds).

The owner wants BC to look like US water. The data does not allow that today: the official Canadian chart objects (buoys, lights, rocks, wrecks, restricted areas) belong to the Canadian Hydrographic Service (CHS), which sells them and does not allow redistribution. The owner will not pay for charts and has parked CHS data. So plan 8 ships what open data supports:

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
- NOAA chart cells that reach into Canadian water are no longer clipped at the border. Where they reach, their chart objects show on the Canadian side. "Something is better than nothing", on the condition that the screen shows where that coverage ends.
- Other open stand-ins found by the research (Coast Guard List of Lights, DFO traffic routes and anchorages, protected areas, place names, marinas, OpenStreetMap seamarks) are not in plan 8. They stay on #89 as the fallback if CHS data never comes.
- Acceptance: the owner takes photos of the Garmin at BC spots of the owner's choosing and gives them to the session, which compares them with the plotter. A live side-by-side on the water comes later, when the boat is back, and is not part of this plan.
- The BC on-chart notice obeys the existing "show chart notice" setting, like the US notice. With the setting off it is hidden. The CHS notice on the About page and in the pack NOTICE files does not depend on that setting.
- Carried from plan 7: no paid data; no local pack builds (CI only); install every pack; depths fixed at chart datum; maps shown to the owner use plain-language shading and legends.

## 3. Goals, non-goals, anti-goals

Goals:
- Ten BC packs built and released in CI, each with a charts and a bathy part, each under the 1.5 GB cap.
- Fish view across BC: contours and depth bands at the plan 7 levels, fine where NONNA 10 m exists, coarse elsewhere, no blank water inside the pack areas.
- Nav view across BC: depth shading, contours, spot depths, drying areas, land, a "no survey data" shading, and a notice that most hazards and navaids are not shown.
- NOAA chart objects on the Canadian side where NOAA cells reach, with a drawn edge and a legend entry.
- The US packs along the border and the overview pack rebuilt so the border shows no clipped edge, no gap and no doubled drawing.
- The CHS notice and the open licence credits in the packs and in the app.
- #18 fixed: no latitude hard-coded to 48 N.

Non-goals:
- CHS chart objects of any kind, by purchase, harvest or live display.
- Stand-in navaids, routes, anchorages, protected areas, names or marinas from open sources.
- Protected delivery (#91).
- Alaska. Live tide or currents. Choosing which areas to install.
- Fishing contours deeper than 1,000 ft (as plan 7).

Anti-goals (failures even if it technically works):
- BC water that looks charted and safe when it is only unsurveyed. Empty NONNA must never read as deep or clear water.
- A BC Nav view that could be mistaken for an official chart: with the chart notice setting on, no BC notice, or one that is easy to miss. The "No survey data" shading and the legend do not depend on that setting.
- A depth line from NONNA in the wrong place by more than the 10 ft contour budget (section 8 sets where this applies).
- A seam at the border or between BC packs with a gap, doubled lines, a cut feature or a visible depth step beyond what section 8 allows.
- Any plan 7 anti-goal coming back: pauses, blank tiles or flicker at pack edges, or fast panning slower than today, now with 16 region packs installed.
- A missing CHS notice in any pack that holds NONNA-derived data, or on the About page when such a pack is installed.
- A fetch from any host against its robots.txt, or a bulk fetch that gets the project blocked.
- A pack that can only be built on the dev machine.

## 4. Pack areas

From the approved map. Boxes are W, S, E, N. Exact edges move to the zoom-10 ownership grid (plan 7 spec 5.2), so each grows outward to whole grid tiles and the grid order settles overlaps. Bathy estimates are the map's upper bounds at zoom 14.

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

The offshore polygons are in the map's data (the builder copies them from the artifact into the region files).

Ownership rules, added to plan 7 spec 5.2:
- Zoom-10 tiles that hold both US and Canadian water stay with their US pack (plan 7). Those US packs are rebuilt with Canadian-side data (section 9). Tiles whose water is only Canadian go to a BC pack.
- The BC packs join `chartpack/regions/grid.toml` after the US packs, so no wave 1 tile changes owner. The order among BC packs is the builder's call.
- The `overview` pack is rebuilt over the whole area, US and BC.
- A pack that exceeds the 1.5 GB cap first lowers its fine max zoom (section 6), and only then splits into two areas on the grid (plan 7 spec 6).

## 5. Data sources

All open, all fetched by CI with plain HTTPS and no account. Verified facts are on #89; items marked "check" are builder checks before first use.

| Source | Use | Licence | Fetch |
|---|---|---|---|
| NONNA-10 (CHS) | fine depth | Open Government Licence, Canada, plus the CHS NONNA Licence | WCS `https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs`, coverage `nonna__NONNA 10 Coverage` |
| NONNA-100 (CHS) | coarse depth | same | same WCS, coverage `nonna__NONNA 100 Coverage` |
| CRM volume 8 (NOAA) | coarse depth south of 49 N | US Government work | as plan 7 |
| ETOPO 2022 15 arc-second (NOAA) | coarse depth where nothing else reaches (#92) | CC0 | one tile: `ETOPO_2022_v1_15s_N60W135_surface.tif` (31 MB, URL on #92) |
| BC Freshwater Atlas Coastlines | BC shoreline and land | Open Government Licence, British Columbia | WFS on `openmaps.gov.bc.ca`, layer `WHSE_BASEMAPPING.FWA_COASTLINES_SP`, paged with `sortBy=OBJECTID` |
| NOAA ENC cells that reach into Canada | chart objects in the border strip and Dixon Entrance; bands 1 and 2 offshore | US Government work | as plan 7 |

Checks before first use (each is a plan task with its result posted on #90; a failed check stops that source and goes to the owner):
1. NONNA WCS: read the host's robots.txt; find the largest request the server accepts; confirm the sign and nodata conventions (the #89 samples held negative values for depth and positive for drying heights); confirm the native grid (EPSG:3857, about 19 m and 153 m pixels).
2. NOAA Canadian-side content: read the NOAA ENC terms and the cell metadata for any restriction on content that came from CHS. #89 found none stated but did not settle it.
3. Freshwater Atlas coastline: which tide level the line follows, and whether closed land polygons can be built from the lines without gaps.

Fetch manners (all Canadian hosts): one connection, requests in sequence, a pause between requests, an honest User-Agent naming the project and repo, back off on errors, stop for good on HTTP 403 or 429 and report. Fetched source data is cached between CI runs so a rebuild does not pull the whole coast again (builder picks the cache: Actions cache or a release asset of raw tiles; NONNA's licence allows redistribution with the notice).

## 6. Depth for the Fish view (#90, #92)

Merge order, finest first: NONNA-10, NONNA-100, CRM, ETOPO. A finer source wins wherever it has data.

Fine and coarse (plan 7 spec 5.3a), applied to BC:
- fine (`bathy`, `dem`): NONNA-10 water only. Default max zoom 13 for both (designer's call: a 10 m grid does not support the zoom 14 detail that 3 m CUDEM does, and zoom 13 cuts pack size about four times). The builder may raise it to 14 for a pack that stays under the cap, if renders show a gain.
- coarse (`bathy-coarse`, `dem-coarse`): NONNA-100, then CRM, then ETOPO, drawn under the fine layers and stretched past their max zoom. Max zoom 12 at most; the builder may lower it where only ETOPO exists (15 arc-seconds is about 460 m) as long as no water inside a pack area draws blank at any zoom.
- The number of sources and layers in the style stays fixed. If the builder needs a third tier for ETOPO-only water, that is a change to this spec and goes to the owner first.

Contour levels and bands are plan 7's, in feet: every 10 ft to 300 ft with the 5 ft fine levels, every 50 ft to 600 ft, every 100 ft to 1,000 ft, deepest band "deeper than 1,000 ft".

The two offshore packs are coarse only. NONNA holes inside inshore packs (the shelf off Tofino, parts of Dixon Entrance, nearshore strips) fall through to the coarse sources. In Fish view, water drawn from ETOPO or from CRM north of its good coverage is rough; the legend says so in plain words ("rough depth, worldwide grid").

Where even the coarse merge has no value over water (not expected: ETOPO is global), the tile shows the "no survey data" shading of section 7.

## 7. The BC Nav view

### 7.1 What it draws

BC charts packs carry the same vector source and layers as US charts packs, filled from different data, so the app and the Nav styles treat BC like any other region (designer's call).

- Depth areas (the chart-style blue bands) and depth contours: derived from the merged depth of section 6, at the levels the US Nav view uses for ENC depth areas and contours.
- Spot depths: sampled from NONNA-10 and NONNA-100 only, never from CRM or ETOPO, thinned per zoom like ENC soundings, and biased shallow (the shallowest value in each thinning cell), as a chart would.
- Drying areas: NONNA values above chart datum draw as the intertidal band.
- Land and shoreline: polygons and coastline built from the Freshwater Atlas lines.
- No survey data: water (not land) where neither NONNA grid has a value. It draws as a distinct shading that cannot be read as deep water, in all three palettes (day, dusk, night), with the legend entry "No survey data". Coarse filler depth may still tint it in Fish view, but in the eight inshore packs the Nav view never draws CRM or ETOPO as depth areas (designer's call: on a chart-like view, rough worldwide depth must not look surveyed, and a 460 m grid is unreliable in narrow inlets). Only the two offshore packs draw Nav depth areas from the coarse sources. A NONNA hole on the outer shelf of an inshore pack therefore shows "No survey data" next to the offshore pack's depth bands; that seam is accepted.

### 7.2 NOAA objects on the Canadian side

The clip `chartpack/regions/clip/canada-wa.geojson` no longer removes NOAA chart objects. Known reach (#89 stand-ins comment, section 10): `US3WA1EF` at 1:180,000 over Haro Strait, Victoria, the southern Gulf Islands and Boundary Pass to about 49.08 N; `US3WA1EE` and `US3WA1ED` at 1:350,000 along the north side of the Strait and off southwest Vancouver Island to about 48.77 N; `US3AK1DX` and `US3AK1DY` at 1:350,000 over Dixon Entrance down to 54.0 N; bands 1 and 2 over all offshore water.

Rules:
- Inside a NOAA cell's coverage on the Canadian side, its point, line and area objects (lights, buoys, beacons, rocks, wrecks, obstructions, restricted and caution areas, traffic lanes, cables) show as in US water.
- Depth and land do not double. Where NONNA has data, depth areas, contours and spot depths come from NONNA and the NOAA cell's are dropped. Where NONNA is empty, the NOAA cell's depth objects show and the area is not marked "No survey data". Canadian land and shoreline come from the Freshwater Atlas; US land stays NOAA's.
- The edge of NOAA band 3 and finer coverage on the Canadian side is drawn as a line with a legend entry in plain words: "US chart data ends here (coarse scale). Beyond: most hazards and navaids not shown." Bands 1 and 2 do not count as coverage for this edge.
- Bands 1 and 2 (`US1GLBDD` at 1:3,500,000, `US2PACWX` at 1:700,000) cover all of BC. In BC water outside band 3 coverage (designer's call, following "something is better than nothing"): their point and line objects (the major lights and the like) are kept and draw as the quilt draws them today; their depth areas, contours, soundings and land are dropped in the eight inshore packs, so they never cancel "No survey data" and never stand in for the shoreline. In the two offshore packs and in `overview` their depth objects are kept where NONNA is empty. This is why the notices say "most", not "all".

Alaskan water (designer's call): `bc-north` and `bc-offshore-north` reach past the Dixon Entrance line, and no US pack owns tiles there. Alaska is not a goal, so nothing is added for it and nothing is clipped out: the NOAA cells already listed draw on both sides, depth comes from the merge order of section 6 (NONNA wherever it has data, else coarse), and land comes from the Freshwater Atlas where it has land, else from the NOAA cells. No boundary line is needed north of the existing clip polygon, which stops at 49.5 N and is only used for the CUDEM and NONNA rule of section 9.

### 7.3 Saying what is not there

- Nav view, when any water drawn from BC data outside NOAA band 3 coverage is on screen: "BC: depth and shoreline only. Most hazards and navaids not shown. Not for navigation." When the only BC water on screen is inside the NOAA strip: "BC: coarse US chart data. Not for navigation."
- Fish view, when any NONNA-derived depth is on screen: "BC: CHS survey depths, chart datum. Not for navigation." in place of today's banner (section 8 explains "chart datum").
- The trigger is what is on screen, not the view center (designer's call): a view over Haro Strait that shows both countries gets the BC notice.
- The notice uses the existing notice bar and obeys its "show chart notice" setting (`noticeShown` in `plotter/qml/ChartPage.qml`), by the owner's decision (section 2).
- How the app knows the area (pack metadata, a coverage polygon in the pack, or a tile property) is the builder's call. The notice must not depend on one style string for the whole merged chart, since US and BC tiles share one style after the merge.

## 8. Datum

- NONNA is already on Canadian chart datum. No shift is applied (plan 7 spec 8 planned for this).
- Canadian chart datum (lower low water, large tide) sits a little lower than US MLLW. At the border the two meet. The builder measures the step along the Haro Strait and Boundary Pass seam and in the Strait and posts it on #90. If the step moves a contour by more than the 10 ft budget anywhere, it goes to the owner before packs are tagged; otherwise it is accepted and noted in the pack NOTICE.
- CRM in Canadian water south of 49 N is converted as in plan 7 (EGM2008 to NAVD88 to MLLW with the Washington stations). It is used only where NONNA has nothing.
- ETOPO heights are EGM2008 like CRM. For plan 8 they get one approximate shift per pack area to chart datum (designer's call; the builder picks the values from published Canadian tide station datums and records the source and licence in the NOTICE). ETOPO is a 460 m grid; the 10 ft anti-goal does not apply to it.
- The 10 ft contour anti-goal applies to water drawn from NONNA-10. NONNA-100, CRM and ETOPO water is "rough depth" and labeled so.

## 9. Border and seams

- US packs whose owned tiles hold Canadian water are rebuilt: at least `north-sound`, `strait` and `wa-coast` (the builder confirms the list from the grid). Charts: NOAA objects unclipped (7.2), Canadian land from the Freshwater Atlas, Canadian depth from NONNA per 7.2. Bathy: NONNA, then CUDEM and CRM by the merge order, with no clipped edge.
- Where CUDEM (US, 3 m) and NONNA-10 both have data near the border, CUDEM wins on the US side of the boundary and NONNA on the Canadian side (designer's call: each country's survey on its own water, and each datum on its own side).
- `overview` is rebuilt over US and BC: charts from NOAA bands 1 to 3 plus derived BC depth and land at low zoom, bathy from one coarse merge. The plan 7 rule that overview bathy sources must be `["crm"]` is widened to the coarse sources.
- The ENC fallback contours that plan 7 clips in Canadian water (plan 7 PR D) are not needed where NONNA covers; the builder removes or keeps the clip so that no contour draws twice.
- Seams between BC packs follow plan 7: each pack reads every source tile that meets its owned tiles, so features cross whole.

## 10. Latitude (#18)

`scamin.py` (`_COS_LAT`) and `bathy/contours.py` (`zoom_tolerance_deg`) hard-code 48 N. BC runs from 48.3 N to 55 N.

- The latitude comes from where the feature is, not from a constant. Designer's call: use the latitude of the feature or of its tile row instead of one value per region, so two packs never disagree along a seam. The issue text proposes the region bbox center; the builder may use that only if renders at a seam between two BC packs show no feature appearing at different zooms on the two sides.
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

Also in the NOTICE files and About: "Contains information licensed under the Open Government Licence – British Columbia." with a link to that licence (shoreline), the ETOPO 2022 citation (#92), and the existing NOAA lines. The builder re-reads each licence page on the day and records the date, as `chartpack/NOTICE` does today.

## 12. App and installer

Plan 7 already loads any number of packs and merges them at install. Plan 8 adds:
- the area-aware notices of 7.3 and the "chart datum" banner of section 8;
- legend entries: "No survey data", "US chart data ends here", "Rough depth, worldwide grid";
- the About page text of section 11;
- nothing else by intent. The builder avoids a pack schema change if the new layers and metadata fit schema 2. If a change is needed, the builder raises the pack schema and the plotter's accepted range together, an older plotter refuses the new packs with the existing per-pack reason, and every wave 1 pack is rebuilt at the new schema, `sound-south` and `sound-central` too (designer's call: the set check in `installer/lock-tool.sh` that all packs of a kind share one schema stays strict). That lengthens the release list of section 13 and applies the #18 change to all packs.

With 16 region packs plus `overview`, the install-time merge and the merged files grow several times over plan 7's (2.4 GB, 5 s on the test laptop). The plan measures merge time, disk use and fast-pan frame time on the test laptop with all packs before the set is released, against the plan 7 numbers on #84. The installer's free-space check (#96) must pass on CapnButts.

## 13. Releases

- BC packs: `charts-<region>-v1.0.0` and `bathy-<region>-v1.0.0` through `chartpack-release.yml`, dry runs first (`workflow_dispatch` from main).
- Rebuilt US packs and `overview`: a minor version bump.
- Then a plotter release if the app changed, and a set release listing every pack, as a pre-release.
- Tags need the owner's OK first and are pushed one per `git push`, about 2 minutes apart, with a run confirmed per tag.
- CI fit: every BC pack must build on the GitHub runner (16 GB RAM, 14 GB disk, 6 h) within the plan 7 fit guard. NONNA raw data for one pack must fit the disk with margin; the builder streams or chunks where it does not.

## 14. Order

1. Source checks (section 5) and a small CI spike: fetch one inlet from the NONNA WCS and one page of the coastline WFS in a `workflow_dispatch` run; post sizes, timings and limits on #90.
2. #18 latitude.
3. Readers: NONNA (fine and coarse), ETOPO (#92), coastline to land polygons; merge order and datum rules.
4. Derived Nav layers, "no survey data", NOAA unclipped with the coverage edge.
5. App: notices, legend, About. Pack schema if needed.
6. Region files and grid for the ten BC packs; rebuilt US border packs and `overview`; dry runs; size and fit checks.
7. Renders for the owner (section 15), then tags, releases, set release.
8. Test laptop measurements, CapnButts install, Garmin photo comparison.

## 15. Done

- Ten BC packs, the rebuilt US border packs and `overview` released from CI, each file under 1.5 GB, each with the notices of section 11.
- A set release installs them all on CapnButts; About lists them and shows the CHS notice.
- Renders posted on #90 for the owner, with plain-language captions, at least: Victoria and Haro Strait (border seam, NOAA strip), Active Pass, Vancouver harbor and Indian Arm, Desolation Sound, Knight Inlet head, Barkley Sound, Nootka Sound (NONNA-100 only), the shelf off Tofino (NONNA hole), Bella Bella, Prince Rupert, Dixon Entrance (NOAA strip, NONNA hole), Masset, the 49 N line where CRM ends, and one view in each offshore pack. Nav and Fish for each; day and night for at least three.
- Test laptop: fast panning across the border seam and across a corner where BC packs meet shows no blank tiles, no doubled or cut lines, and frame times in line with plan 7's (numbers posted).
- Garmin comparison: the owner provides photos of the Garmin at BC spots. For each photo the session renders the same place and zoom and posts the pair on #90 with what matches and what differs. Pass (designer's proposal, the owner judges): depth contours and spot depths agree with the Garmin within the contour budget where NONNA-10 has data; the shoreline lines up; wherever the Garmin shows detail the plotter lacks, the plotter's screen says so. Differences become follow-up issues.
- The owner pans BC on CapnButts and says the Nav and Fish views are acceptable.
- Owed after the plan: a live side-by-side with the Garmin in BC water (added to the boat checks).

## 16. Issue housekeeping

- #89 closes with this plan: its research is done. The parked CHS question and the stand-in fallback move to a new issue with a reference back (designer's call), which stays out of plan 8.
- #91 loses the `plan 8` label and stays open, parked with the CHS question (it is only needed if unpublishable data ever arrives).
- #90 is the plan's log: checks, spike numbers, renders, the Garmin comparison.

## 17. Left to the builder

The NONNA request size and cache (5), fine max zoom per pack and the coarse max zoom (6), how soundings are thinned (7.1), how land polygons are built from coastline lines (7.1), how the app learns the area for notices (7.3), the ETOPO shift values and their source (8), the list of US packs to rebuild (9), per-feature or per-row latitude (10), whether schema 2 is enough (12), and the order of BC packs in the grid (4). Everything marked "designer's call" was set by the designer, not the owner, and the owner may change it.
