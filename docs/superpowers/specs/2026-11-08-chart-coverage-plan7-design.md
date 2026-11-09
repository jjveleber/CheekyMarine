# Plan 7: chart coverage wave 1 (US waters)

Issues: #84 (multi-pack loading), #85 (pack size and split), #87 (offshore depth), #88 (depth datum per area), #86 (wave 1 regions), plus #14 and #16. Region review: #83 (approved by the owner 2026-11-08). Plan 8 (BC) builds on this: #89, #90, #91, #18.

Region review map (approved): https://claude.ai/artifact/J2hnEnQ3P79ZB7xJMbcJK5

## 1. Intent

Today the plotter shows one region, `puget-north` (-122.9 to -122.1 W, 47.5 to 48.3 N). The owner's boat runs well outside it: Tacoma Narrows, the San Juans, the Strait, and 30 to 40 mi off Neah Bay. Plan 7 covers all US waters the owner uses, out to about 100 mi off the Washington coast, with charts (Nav) and depth contours (Fish), and makes the app show several packs as one chart. Plan 8 then adds British Columbia on the same machinery.

The owner navigates with a Garmin that has paid, current charts. CheekyMarine is the owner's own display: a chart and fishing view that must look right and never stall.

## 2. Owner decisions (2026-11-08)

- Wave 1 coverage: all of Puget Sound including the San Juans, Tacoma Narrows, Lake Union and Lake Washington (navigation only; lake fishing is not important), the Strait of Juan de Fuca (US side), and the Washington coast out to about 100 mi.
- Pack areas as drawn on the approved map (section 4). Puget Sound splits at 47.45 N; `sound-central` replaces `puget-north`.
- `wa-coast` is one pack (owner open to one or two). It splits into shelf and offshore only if the size rule (section 6) forces it.
- Seamless: crossing from one pack's area into the next shows no gap, no doubled lines, no change in look, and no pause. Up to four packs can meet in one view (owner's estimate; the approved boxes meet three at a time, plus the overview). The hardest case is fast finger-panning and zooming, more than boat speed (26 kn).
- Zoomed out, less detail is expected, still one continuous chart.
- Install every pack for now. Picking areas comes later as coverage grows; the design must not block it.
- Updates arrive mostly over home Wi-Fi, sometimes a fast phone hotspot. Download size is not a concern.
- Offshore fishing is 300 to 600 ft deep, mostly 30 to 40 mi out from Neah Bay (other ports later: La Push, Westport, Ilwaco). Depths past 1,000 ft do not matter for fishing. Small bumps offshore do not matter.
- Depths stay fixed at chart datum (the zero of NOAA charts). No live tide in this plan.
- No paid data of any kind. No local pack builds: every pack is built in CI.
- Done when the owner, on the tablet, looks at Nav and Fish across the new packs (especially where packs meet) and the contours and navigation symbols are right.

## 3. Goals, non-goals, anti-goals

Goals:
- The app loads every installed pack and draws them as one chart, Nav and Fish, at every zoom.
- Wave 1 packs built and released in CI: five region packs plus an overview pack (section 4), each with a charts and a bathy part.
- A pack size rule that fits GitHub releases and the CI runner, checked for every pack.
- Offshore depth from CRM with contour levels for 300 to 600 ft fishing.
- Depth datum correct per area, including the lakes.
- The installer and the About page handle several packs per kind.

Non-goals:
- Choosing which areas to install (later; keep the door open).
- Live tide or current data.
- Canadian data of any kind (plan 8). The Canadian side stays clipped.
- A deep-water grid reader (ETOPO 2022). Not needed in wave 1; moves to plan 8 (section 7).

Anti-goals (failures even if it technically works):
- Any pause, blank patch or flicker when the view crosses a pack edge, or with four packs in view.
- Lines or symbols doubled, cut off or shifted at a pack edge.
- Fast panning noticeably slower than with one pack today.
- A depth line in the wrong place by more than the 10 ft contour budget anywhere in the wave 1 area, including the lakes.
- A pack that can only be built on the dev machine.

## 4. Pack areas

From the approved map. Areas are bounding boxes (W, S, E, N), clipped by `chartpack/regions/clip/canada-wa.geojson` and the US/Canada boundary. Size estimates scale from `puget-north` (172 MB charts, 280 MB bathy) and are rough.

| Region | Box | Covers | Charts est. | Bathy est. |
|---|---|---|---|---|
| `sound-south` | -123.25, 46.95, -122.1, 47.45 | Tacoma Narrows, Commencement Bay, Carr and Case inlets, Olympia, lower Hood Canal | ~75 MB | ~116 MB |
| `sound-central` | -123.25, 47.45, -122.1, 48.2 | Seattle, Lake Union, Lake Washington, Jeff Head, Possession bar, Everett, Admiralty Inlet, upper Hood Canal | ~184 MB | ~291 MB |
| `north-sound` | -123.35, 48.2, -122.25, 49.05 | San Juans, Rosario Strait, Deception Pass, Skagit and Padilla bays, Bellingham, east end of the Strait | ~217 MB | ~505 MB |
| `strait` | -124.8, 47.95, -123.25, 48.6 | Strait of Juan de Fuca US side: Port Angeles, Sekiu, Neah Bay | ~30 MB | ~256 MB |
| `wa-coast` | polygon: -127 to -123.75 W, 46.15 to 48.6 N, minus the `strait` box | Columbia bar to Cape Flattery, Grays Harbor, Willapa, out to about 100 mi | ~79 MB | ~772 MB plus offshore at low zoom |
| `overview` | all of the above | low zooms only (section 5.2) | small | small |

Exact edges move to the ownership grid (section 5.2), so each box grows outward to whole grid tiles. Where boxes overlap today (near -123.3 W), the grid decides which pack owns each tile.

`puget-north` is retired: the first set with the new packs no longer lists it, and the installer removes it as it removes any pack no kept set uses.

## 5. Several packs as one chart (#84)

### 5.1 Today

`ChartController` picks one charts pack (`PackCatalog::best`, highest version of any region) and the bathy pack of the same region, rewrites that pack's styles to load `mbtiles://` files (`StyleLoader`), and loads one source per kind. The lock file (`installer/cheekymarine.lock`, schema 1) names exactly one `charts.*` and one `bathy.*` pack.

### 5.2 Tile ownership (designer's call)

Every map tile has exactly one owner pack, so packs never overlap in the data the app reads:
- Ownership grid: zoom 10 tiles. A region pack owns every zoom-10 tile assigned to it, and all deeper tiles under them. Each zoom-10 tile is assigned to exactly one region (a table in the region files or one shared assignment file; builder's choice). Tiles whose water is only Canadian are assigned to no wave 1 pack.
- A region pack contains tiles from zoom 10 up to its max zoom, only for the tiles it owns. Its build reads every source cell that meets those tiles, including cells shared with a neighbor, so features cross the seam whole and each side draws its own part.
- The `overview` pack holds zoom 9 and below for the whole covered area, charts and bathy, built from all wave 1 sources together. Plan 8 rebuilds it to include BC.
- The ENC quilt (which band shows where) is decided per tile from all cells that meet it, so a neighbor's cells never change a pack's look at the seam.
- Ownership is per kind (charts, bathy, each depth source in 5.3a). Zoom-10 tiles that hold both US and Canadian water go to the US pack; their Canadian side stays clipped in plan 7. Plan 8 rebuilds those US packs with NONNA depth for the Canadian side (open licence, so the packs stay public). CHS chart objects are parked (#89); if they ever come, they arrive as their own protected source in the style, not inside a public pack, so this model does not have to change for them.
- `overview` bathy (zoom 9 and below) carries the depth bands and the major contour lines only. Today Fish shows no bathy below zoom 10.

Why: one source per kind in the style, no doubled drawing at seams, and a drawing cost that does not grow with the number of packs. The cost is that pack edges follow the zoom-10 grid (about 0.35 degree of longitude by 0.24 degree of latitude here) instead of round numbers.

### 5.3a Fine and coarse depth sources (designer's call)

A vector or raster source draws a missing tile as empty inside its zoom range; it only stretches tiles past its max zoom. CRM-only water is capped at zoom 12 (section 7) while CUDEM water goes to zoom 16 (vector) and 14 (DEM), so one depth source would leave Fish blank over the Neah Bay grounds when zoomed in. So bathy packs carry two depth layers of sources:
- fine: `bathy` and `dem` as today, CUDEM water only, to today's max zooms;
- coarse: `bathy-coarse` and `dem-coarse`, CRM-only water, max zoom 12, which MapLibre stretches when zoomed in further.

Fish styles draw the coarse layers under the fine ones. The number of sources and layers is fixed (it does not grow with packs). The edge between fine and coarse data is where CUDEM ends, as in today's merge; contours on the two sides come from different grids and may not join exactly there. That is acceptable (owner: offshore detail and small bumps do not matter).

### 5.3 Stitching mechanism (spike first)

The style keeps one `enc` source for charts and the fixed set of depth sources (5.3a), as today. How those sources read from several files is decided by a timed spike at the start of the plan, on the test laptop, with all wave 1 packs (real CI builds, or the existing packs re-cut to the grid for the spike):

1. Planned approach: the installer merges the installed packs of each kind into one MBTiles per kind when a set is installed. With tile ownership the merge is a plain copy of tile rows (plus the union of metadata). The app keeps loading one file per kind.
2. Fallback: the app routes each tile request to the owner pack's file (a MapLibre file source or a local tile endpoint inside the app), with no merged file on disk.

The spike measures: install time to merge, disk use, memory, and frame time while fast-panning across a four-pack corner. The real packs do not exist yet when the spike runs, so the spike re-cuts `puget-north` into four packs along zoom-10 grid lines through a busy area (Possession bar to Everett) and compares against the one-pack file. Real seams are checked in section 11. Approach 1 is kept unless it fails the anti-goals or makes a one-pack update take more than a few minutes. Either way the app never opens or swaps packs while the chart is moving.

### 5.4 App changes

- `PackCatalog` keeps every usable pack per kind, not only the best one. The newest version of each region wins; packs with a schema the app does not accept are refused per pack, with the reason, as today.
- Styles, sprites and glyphs come from the newest installed pack of each kind; all packs of one kind in a set must share the same `schema` (the set build checks this).
- Zoom range, legend entries and the ENC `valdco` list (safety contour) are the union across packs.
- The About page lists every pack with region and version.
- Fish mode is available wherever a bathy pack covers the view; the "no bathy pack for the charts region" fallback becomes per area.

### 5.5 Installer and lock file

The lock file moves to schema 2: one entry per pack, `pack.<kind>-<region>.{version,tag,asset,sha256,schema}`, any number of them. The plotter's `pack_schema_min/max` stays. The set build checks every listed pack. Rollback and pruning work per pack as today. Selecting areas later means listing fewer packs; nothing in this plan should assume every set lists all regions.

## 6. Pack size and CI fit (#85)

- Drop the 300 MB target. New hard cap: 1.5 GB per pack file (headroom under GitHub's 2 GiB release asset limit as charts grow).
- An area that outgrows the cap splits into smaller areas on the ownership grid. Packs never split by kind halves or zoom ranges.
- Every pack must build on the GitHub runner (`ubuntu-24.04`: 16 GB RAM, 14 GB disk, 6 h). The plan adds a check (a CI job or a test against recorded build stats) that each wave 1 pack fits, with margin. Where one does not, the build changes (for example streaming source tiles instead of caching them whole).
- Remove the "dev-machine fallback" note from `.github/workflows/chartpack-release.yml` and say so in the chartpack spec: no local builds (owner).
- Update the chartpack spec's Pack size section (`docs/superpowers/specs/2026-10-28-chartpack-design.md`).

## 7. Offshore depth (#87)

Found during the region review:
- CRM volume 8 (2025) is a 1 arc-second grid that fills -127 to -121.75 W and 44 to 49 N with no gaps, so it reaches the 100 mi line off Washington. Wave 1 needs no deep-water grid.
- CUDEM's outer coast tiles end at -125.0 W. The Neah Bay grounds sit on CRM.
- NOAA ENC band 3 stops at -126.0 W; past it only bands 1 and 2.

Plan 7 work:
- Merge rule stays CUDEM, then CRM. The ETOPO 2022 reader (CC0, one 15 arc-second tile covers all of BC) moves to plan 8 as its own issue with a reference back to #87; #87 closes with this plan.
- Zoom cap for CRM-only areas: CRM-only water is built to zoom 12 at most (builder may lower it if `wa-coast` needs it to fit the cap). CUDEM water keeps today's max zoom.
- Contour levels, everywhere (Sound and offshore alike):
  - every 10 ft to 300 ft (as today, with today's 5 ft fine levels and minzoom thinning);
  - every 50 ft from 300 to 600 ft, with the 100 ft lines drawn as majors (builder's call, the owner may adjust after seeing it);
  - every 100 ft from 600 to 1,000 ft;
  - no fishing contours deeper than 1,000 ft. Depth bands follow the same levels; the deepest band is "deeper than 1,000 ft".

## 8. Depth datum per area (#88)

Today each region applies one constant pair from Seattle (9447130): NAVD88 to MLLW 0.715 m, MSL to MLLW 2.02 m. Across wave 1 the offsets differ by a meter or more.

- Offsets vary across the area, from several NOAA CO-OPS stations covering the wave 1 area (Seattle, Tacoma, Olympia, Port Townsend, Friday Harbor, Bellingham, Port Angeles, Neah Bay, La Push, Toke Point or Westport, and the Columbia mouth, or the nearest stations with published datums; builder confirms the list). Method is the builder's choice among interpolating station offsets over the grid or sub-areas with blended seams. Offshore uses the nearest coastal station.
- CRM 2025 heights are EGM2008 geoid heights (THREDDS metadata), not MSL as the build assumes. Convert them to MLLW correctly (for example through NAVD88 with public geoid grids). Within the 10 ft contour budget.
- Lakes: Lake Union and Lake Washington depths are measured from the lake's own water level, not sea-level chart datum (today they read about 19 ft too shallow). Use the low end of the US Army Corps of Engineers managed lake level, so lake depths are conservative like chart datum (builder's call). The lake outline comes from the ENC or another public source (builder's choice).
- Design for plan 8: a source may need no shift (NONNA is already chart datum).
- The pack notice and the Fish banner still say "approx. MLLW".

## 9. Wave 1 regions (#86), #14, #16

- Region files for the five regions and `overview`, with ENC cells by band from the catalog (all active cells meeting the owned tiles), bathy sources, clip, and render views at the owner's places: Everett, Possession bar, Jeff Head, Tacoma Narrows, Friday Harbor, the `sound-central`/`north-sound`/`strait` corner (48.2 N, -123.3 W), Neah Bay grounds (48.3 N, -125.3 W), plus today's views.
- Far offshore only ENC bands 1 and 2 exist past -126 W; the region files include them for `wa-coast` and `overview`.
- #14: fetch and build use `Region.bathy_sources`; an unknown source is an error.
- #16: fallback ENC contours are clipped by the region clip polygon. Both bite in `north-sound` and `strait`, so they land before those packs build.
- Releases: each region pack goes through `chartpack-release.yml` as today (`charts-<region>-vX.Y.Z`, `bathy-<region>-vX.Y.Z`), then a set release lists them all.

## 10. Order

1. #84 spike (section 5.3), then tile ownership in chartpack and the app and installer changes.
2. #85 size rule and CI fit check.
3. #87 and #88 (contour levels, CRM zoom cap, datum per area, lakes).
4. #14 and #16.
5. #86 region files, CI builds, releases, a set release.
6. Owner check on the tablet (section 11).

## 11. Done

- All wave 1 packs and the overview pack released from CI, each under 1.5 GB.
- A set release installs them all; the About page lists them.
- On the test laptop: fast panning and zooming across the real corner where `sound-central`, `north-sound` and `strait` meet (about 48.2 N, -123.3 W) and along the `sound-central`/`north-sound` and `sound-south`/`sound-central` seams shows no blank tiles, no stutter beyond today's one-pack behavior, and no doubled or cut lines (measured, with numbers posted on the plan's issue).
- The owner checks Nav and Fish on the tablet across the new packs, especially where packs meet: contours in the right places, navigation symbols everywhere, nothing missing or doubled at the edges.

## 12. Left to the builder

The stitching mechanism after the spike (5.3), the ownership assignment format (5.2), the datum method and station list (8), the lake outline source (8), the size check's form (6), and the CRM zoom cap below 12 if needed (7). Everything marked "designer's call" or "builder's call" above was set by the designer, not the owner, and the owner may change it.
