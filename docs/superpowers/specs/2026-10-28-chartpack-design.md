# chartpack: ENC and bathymetry tile packs, design

Date: 2026-10-28
Status: builder check done, owner questions answered, awaiting owner approval
Parent: `2026-10-28-cheekymarine-design.md` sections 6.3, 6.9, 8 and phase 1 step 2 of section 9.

## 1. Intent

The plotter renders its own nautical chart from vector tiles built offline. `chartpack` is the tool that builds those tiles: it downloads NOAA ENC cells and NOAA bathymetry grids, converts them to MBTiles plus a MapLibre style, checks the result against the source, and publishes versioned packs as GitHub releases. The device (plan 4) downloads packs over the hotspot; the app (plan 3) renders them.

The owner's one-line requirement (2026-10-28): navigation depths must be correct and hazards (rocks, shoals, wrecks, obstructions) must be present. "Hitting stuff that isn't water is bad in a boat." Every rule in this document about dropping, thinning, simplifying or converting exists to serve that line.

## 2. Goals

1. A navigation chart pack for the owner's water: WDFW Marine Areas 8-2 (Port Gardner, Port Susan, Everett), 9 (Admiralty Inlet, Possession Bar, Point No Point, Double Bluff, Mid-Channel Bank) and 10 (Edmonds, Kingston, Jeff Head, Seattle, Bremerton). Built from the current reschemed NOAA ENC cells, with the first tests on one cell, US4WA1HK (Everett, Possession Sound, Edmonds, Possession Bar).
2. A fishing chart pack for the same water: fine depth contours in feet and shaded relief from the best public survey grid, with hazards kept and nav clutter off.
3. A first real MapLibre style for both modes, S-52 colours for day, dusk and night, our own symbols drawn from US Chart No. 1, shipped inside the packs. Verified by rendered screenshots the owner looks at.
4. Correctness proven by tests against known cells and known grids, not by eye alone.
5. Versioned, checksummed packs published from a GitHub Actions workflow, so a later region (all Puget Sound, San Juans, WA coast) is a region file and a tag, not new code.

## 3. Non-goals

- The app, the device install, the download and A/B swap (plans 3 and 4). This plan ends at a release with a manifest.
- S-101 ENC input. NOAA still issues S-57; dual production starts 2026 and S-57 continues for years (NOAA transition plan, Nov 2023). Noted as a risk, not built.
- Canadian charts and Canadian bathymetry in this plan. Bathymetry and fishing contours are clipped at the US/Canada maritime boundary. The owner intends to extend later into British Columbia, Alaska and Oregon (said 2026-10-28, "we don't need to figure that out now"). Consequence for this plan only: nothing is hard-coded to Washington. The region file names the ENC cells, the bathymetry source stack and the clip boundary, so Oregon and Alaska are new region files (NOAA ENC, the CUDEM `OR` and `AK` folders), and Canada becomes a new ENC reader for licensed CHS data plus a region file, not a change to the tile schema.
- Topmarks, light sectors drawn as arcs, full S-52 conditional symbology, ENC text (TXTDSC) and pick reports. Symbols start simple: shape plus colour.
- Raster chart (RNC) input. NOAA cancelled RNCs.
- Any wa-creel On Water layer (currents, fishing areas). The pack layout leaves room for another pack later; nothing is built for it.

## 4. Anti-goals

- A hazard present in the ENC cell that is missing from the tile at any zoom where that cell is drawn.
- A depth area or sounding whose value differs from the ENC value, including through unit conversion or rounding in the tool. Rounding happens only in the style at display time.
- Depth-area gaps or overlaps introduced by simplification, so that the renderer shows white or the wrong tint where the chart has a depth.
- A fishing contour that could be mistaken for charted depth. Fishing mode is survey data on an approximate chart datum and says so on screen.
- Any copyleft code or asset in the repo or the packs. OpenCPN is reference reading only.

## 5. Constraints

- Runs on the dev machine (Ubuntu 24.04 under WSL2) and on GitHub Actions `ubuntu-24.04`. Network access to NOAA endpoints at build time; none at test time except one marked integration test.
- Licences: GDAL (MIT), tippecanoe felt fork 2.79.0 (BSD-2), contourpy (BSD-3), numpy (BSD-3), rasterio or GDAL Python bindings (BSD-3 / MIT), Pillow (MIT-CMU) or cairosvg for sprites (LGPL-3: avoid; use Pillow plus resvg-py (MIT) or hand-rolled PNG sprite assembly), maplibre-gl-js (BSD-3) and Playwright (Apache-2.0) for screenshot checks only. NOAA ENC, NCEI CUDEM and CRM data are US Government works (CC0 or not subject to copyright). The NOAA ENC user agreement is honoured: derived product, not an official ENC, source cited, "not certified for navigation" shown.
- The style must render on maplibre-native-qt v3.0.0 (core of May 2024): `mbtiles://` sources, `hillshade` from `raster-dem` (terrarium or mapbox encoding), symbols along lines, data-driven expressions. No `color-relief`, no `pmtiles://`, no `global-state`. The screenshot checker uses maplibre-gl-js, which draws more than Native does; the style uses only the subset above.
- Python 3.12 from Ubuntu with `python3-gdal` 3.8.4 from apt (the brew Python 3.14 on the dev machine has no GDAL). Not installed on the dev machine yet; the owner runs `sudo apt install gdal-bin python3-gdal` once (section 9). A venv with `--system-site-packages` for the GDAL bindings; everything else pinned in `pyproject.toml`.
- TDD. Every task starts with a failing test. Every task is reviewed by an independent subagent. The owner reviews and validates; the owner writes no code.
- Pack size: 300 MB per pack is a target for the 8-2/9/10 region, 1 GB per pack is the hard cap (hotspot download). Levers, in order: `dem.mbtiles` maxzoom 15 to 14 (the app overzooms the hillshade), 5 ft contours only at zoom 15, `band` polygons maxzoom 14, then splitting the region. The default build ships the DEM at maxzoom 14 and raises it to 15 only if the measured pack stays under the target. The full WA region later is in the low gigabytes across several packs.
- Builds run on the free GitHub Actions runner (16 GB RAM, 14 GB disk, 6 h). Inputs for the first region: windows from about 12 CUDEM COG tiles (whole tiles would be 2.3 GB), one 33 MB CRM subset; the merged 3 m grid is about 2 GB as float32 and is processed in blocks. If a later region does not fit the runner, the workflow accepts a pack built on the dev machine and only checks and publishes it.

## 6. Decisions

### 6.1 Language and shape (my call)

Python package `chartpack/` in the monorepo, a CLI `chartpack` with subcommands. Reasons: GDAL's S-57 driver and the Python bindings do the ENC reading; the owner's wa-creel contour code (contourpy, numpy) ports straight over; the tool runs offline on a dev machine and in CI, never on the Pi, so the app's single-language argument does not apply. The owner reads Python (wa-creel).

Subcommands, each independently testable, each writing to a work directory:

```
chartpack fetch-enc   REGION          download the region's cells into cache/, skip unchanged (by edition.update)
chartpack build-enc   REGION OUT      cells -> enc.mbtiles (+ styles, sprites)
chartpack fetch-bathy REGION          download the CUDEM windows and the CRM subset into cache/
chartpack build-bathy REGION OUT      grids -> bathy.mbtiles (vector) + dem.mbtiles (raster-dem)
chartpack check       OUT             re-open the pack and verify it against the sources (section 6.8)
chartpack manifest    OUT             write manifest.json with versions, sources, sha256
chartpack render      OUT VIEWS       screenshots through maplibre-gl-js + Playwright (section 6.9)
```

A region is a TOML file under `chartpack/regions/`: name, cell list by usage band, bathy bbox, datum constants, render views. `puget-north.toml` is the first region (8-2, 9, 10). Tests use `test-cell.toml` (US4WA1HK only).

### 6.2 ENC source and cells (verified 2026-10-28)

- Download `https://charts.noaa.gov/ENCs/<CELL>.zip`. Layout `ENC_ROOT/<CELL>/<CELL>.000` plus `.001 ... .NNN` update files and `CATALOG.031`. Change detection by `edtn`/`updn` from `https://charts.noaa.gov/ENCs/ENCProdCat.xml`, never by zip timestamp (zips are rebuilt nightly).
- Puget Sound is fully reschemed. Cells are lat/lon grid rectangles: band 3 is 1.2 degrees, band 4 is 0.3, band 5 is 0.075. Legacy US5WA13M-style cells are cancelled and not used.
- `puget-north.toml` cells:
  - Band 3: US3WA1DF, US3WA1DG, US3WA1EF, US3WA1EG (the 48.0 N and 122.4 W seams cross the area).
  - Band 4: US4WA1GJ, US4WA1GK, US4WA1HJ, US4WA1HK, US4WA1II, US4WA1IJ, US4WA1IK.
  - Band 5: the US5SEA cells over the three areas (the research list; the builder verifies each against the catalog polygon and the region bbox when writing the region file, and the region file lists them explicitly). Port Susan has no band 5 cell; band 4 is its largest scale.
- Updates are applied (GDAL `UPDATES=APPLY`, the default). The pack records each cell's edition, update number and issue date.
- Test fixtures committed to the repo: `US4WA1HK.zip` (approach band, the test cell) and `US5SEAKL.zip` (harbour band, 49 KB, has a `.001` update, used for the update test and the quilting test). Fixture zips are pinned at the edition.update they were committed at; the golden files are regenerated only on purpose.

### 6.3 ENC to vector tiles

Reader: GDAL S-57 driver through the Python bindings, open options `SPLIT_MULTIPOINT=ON,ADD_SOUNDG_DEPTH=ON,LNAM_REFS=ON,RECODE_BY_DSSI=ON`. One intermediate GeoJSONSeq file per output layer per cell, then tippecanoe builds `enc.mbtiles`.

Output layers (the tile schema, versioned as `schema` in the MBTiles metadata and manifest):

| Layer | S-57 classes | Kept attributes |
|---|---|---|
| `depare` | DEPARE, DRGARE | DRVAL1, DRVAL2 (metres, exact) |
| `depcnt` | DEPCNT | VALDCO (metres) |
| `soundg` | SOUNDG split points | depth (metres, exact), SCAMIN |
| `coalne` | COALNE, SLCONS | CATSLC |
| `lndare` | LNDARE | none (flat fill) |
| `hazard` | UWTROC, WRECKS, OBSTRN (point, line, area) | class, VALSOU, WATLEV, CATWRK, CATOBS, EXPSOU, QUASOU |
| `navaid` | BOYLAT, BOYCAR, BOYSAW, BOYISD, BOYSPP, BCNLAT, BCNCAR, BCNSAW, BCNISD, BCNSPP, DAYMAR | class, BOYSHP, BCNSHP, COLOUR, COLPAT, CATLAM, CATCAM, OBJNAM |
| `light` | LIGHTS | COLOUR, LITCHR, SIGPER, SIGGRP, VALNMR, SECTR1, SECTR2, OBJNAM |
| `area` | ACHARE, RESARE, HRBFAC, SMCFAC, MIPARE, TSSLPT, TSEZNE, CTNARE, SEAARE (names only) | class, CATREA, CATHAF, CATSCF, RESTRN, OBJNAM |
| `line` | CBLSUB, CBLARE, PIPSOL, PIPARE, FERYRT, TSSLPT boundaries, NAVLNE, RECTRC | class, OBJNAM |
| `meta` | M_COVR (CATCOV=1), M_QUAL | cell, band, CATZOC |

Every feature carries `cell` and `band`. Attribute names are the S-57 acronyms so the style, the tests and the ENC product spec agree without a translation table. Values that are lists (COLOUR, CATOBS) are joined with commas, as GDAL's `LIST_AS_STRING` gives them.

Quilting across usage bands (my call): each zoom draws exactly one band. Band 2 and 3 at zoom 6 to 10, band 4 at 11 to 12, band 5 at 13 to 16. Within a zoom, where the band's `M_COVR` polygons cover a point, lower-band features are clipped out; where no cell of that band exists (Port Susan at 13+), the next lower band fills in. So the tile at any zoom shows the largest-scale cell available there, once, like an ECDIS. The pack's maxzoom is 16; the app overzooms beyond that.

Never thinned, never dropped: `depare`, `depcnt`, `hazard`, `navaid`, `light`, `coalne`, `lndare`. tippecanoe runs those layers with feature dropping, tiny-polygon reduction and tile size limits off (`-r1`, `--no-tiny-polygon-reduction`, `--no-feature-limit`, `--no-tile-size-limit`, `--no-simplification-of-shared-nodes`, `--detect-shared-borders` so adjacent depth areas simplify to the same edge and leave no slivers). Line simplification at low zoom is allowed for geometry only; attributes are never touched.

Thinned by rule, not by chance: `soundg`, `area` names and `line` get a per-feature `tippecanoe:minzoom` computed from S-57 `SCAMIN` (the scale the hydrographer set as "do not show smaller than"), falling back to the band's lowest zoom. Deterministic, tested, no random drop rate anywhere.

Depths stay in metres in the tiles, exactly as charted. The style converts to feet for display (`round(m * 3.28084)` as an expression); a metres style variant is a build flag. Rationale: one conversion, in one place, visible in the style, never baked into data.

### 6.4 Bathymetry sources (owner decided 2026-10-28: a published grid as primary, CRM as the fallback for sure)

Research on 2026-10-28 (verified by fetching the data) found a published fine grid, so the parent spec's CRM-plus-CoNED choice is replaced:

- **Primary: NCEI CUDEM 1/9 arc-second** (about 3 m), "CUDEM - 1/9 Arc-Second Resolution Bathymetric-Topographic Tiles", DOI 10.25921/ds9v-ky35, US Government work, not subject to copyright. 0.25 degree Cloud Optimized GeoTIFF tiles, NAD83 horizontal, NAVD88 metres vertical, NoData -9999, about 190 MB each. Puget Sound tiles dated 2023v1 and 2024v1, served from Digital Coast (`https://chs.coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/wash_pugetsound/`) and the same files on S3 (`https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_2014_8483/wash_pugetsound/<name>.tif`). Tile names give the north-west corner: `ncei19_n48x00_w122x50_2023v1.tif` covers Possession Bar and Double Bluff; `n48x00_w122x75` and `n48x25_w122x75` Point No Point and Admiralty Inlet; `n47x75_w122x50` Edmonds, Kingston and Jeff Head; `n48x00_w122x25` Port Gardner and Everett; `n48x25_w122x25` and `n48x25_w122x50` Port Susan and Saratoga Passage; `wash_juandefuca/ncei19_n48x25_w123x00_2024v2.tif` Port Townsend. The tool reads only the bbox it needs through GDAL's `/vsicurl/` range requests on the COGs, not whole tiles; the dataset's `urllist8483.txt` is the tile list (folders `wash_pugetsound`, `wash_bellingham`, `wash_juandefuca`, `wash_outercoast`, `columbia_river`).

  Coverage of the whole project region, checked 2026-10-28 against the tile list and by reading depths through `/vsicurl/` in each sub-region: every 0.25 degree tile over Puget Sound from Olympia to Bellingham, Hood Canal, Whidbey and Skagit, the San Juans (2017 and 2024 tiles, Boundary Pass -62 m, Rosario -52 m), the US shore of the Strait of Juan de Fuca from Port Townsend to Neah Bay (off Port Angeles -134 m, off Neah Bay -221 m), and the outer coast from Cape Flattery to the Columbia bar in a strip about 15 to 20 nautical miles wide (off Westport -15 m, off Destruction Island -60 m, Columbia bar -23 m). Not covered, CRM fills: the mid-Strait band 48.25 to 48.50 N between 124.0 and 123.25 W (mostly Canadian water, the US part is deep mid-channel), the shelf beyond the coastal strip, and the land-dominated column east of 122.25 W north of 48.25 N. These same NOS multibeam surveys are what Garmin says it builds its relief shading from.
- **Fallback everywhere: NCEI CRM Vol. 8 2025** (30 m, EGM2008 geoid, roughly MSL), WCS bbox subset from the NGDC THREDDS server as a float GeoTIFF (33 MB for the first area). Fills every cell CUDEM does not cover (the gaps listed above) and any NoData hole.
- Not used: NOAA NBS "Modeling" 4 m tiles (test-and-evaluation product, no stability promise; BlueTopo proper has no Washington tiles and no published date for them), USGS CoNED 1 m (55 GB, interpolated from the same soundings in deep water), NCEI P290 30 m (1934 to 1982 surveys), the NCEI Puget Sound 1/3 arc-second 2014 DEMs (10 m, superseded by CUDEM). The region file names the source stack, so any of these can be added later without code changes to the merge step beyond a reader.

Vertical datum: all grids are shifted to approximate MLLW with a per-region constant from the NOAA CO-OPS datums API (Seattle 9447130: NAVD88 minus MLLW 0.715 m; MSL minus MLLW 2.02 m). Good enough for 10 ft contours; the fishing style labels the datum "approx. MLLW". VDatum is not used.

Clipping: bathymetry and fishing contours are clipped to US waters with the NOAA Maritime Limits and Boundaries shapefile (CC0, `USMaritimeLimitsAndBoundariesSHP.zip`, boundary B0098 for the Strait and Haro/Georgia).

### 6.5 Bathymetry to tiles

Merge: CUDEM where present, CRM elsewhere, into one MLLW depth grid per region at 1/9 arc-second (CRM upsampled; a `coverage` polygon layer records which source covers where, with resolution and date). Land is positive elevation in these grids; cells above 0.3 m are set to +0.3 m so every contour closes against the shore (the wa-creel "-1 m fill" rule, adapted to elevation grids).

Contours (ported from wa-creel `app/onwater/contours.py`, the owner's code): levels every 10 ft to 300, then 400, 500, 600, plus 5 ft steps from 5 to 60 ft where the source is CUDEM. Each line carries `depth_ft`, `major` (60, 120, 180, 300, 600) and `minzoom`: majors from 10, the base ten (30, 60, 90, 120, 150, 180, 240, 300, 400, 600) from 12, 20 ft steps from 13, 10 ft from 14, 5 ft from 15. One Chaikin pass then Douglas-Peucker; lines under six points dropped. Contours are generated per zoom band from a grid downsampled to about 2 pixels per tile pixel at that zoom, so zoom 10 lines come from a 150 m grid and zoom 15 lines from the 3 m grid, which keeps the tile set small without tippecanoe dropping anything.

Depth bands: filled polygons between the same levels (contourpy filled mode), simplified the same way, with `depth_min_ft`, `depth_max_ft`, `minzoom`. These give the depth tint in fishing mode and work in night mode because the colour is in the style, not in a raster.

Relief: `dem.mbtiles`, raster tiles in terrarium encoding (PNG), zoom 10 to 15, built from the merged grid with numpy and GDAL (no rio-rgbify). The app's `hillshade` layer shades it on device, so exaggeration and light direction are style properties.

Fallback where no fine survey exists: the ENC `depcnt` lines inside the uncovered area are copied into the bathy pack's `contour` layer with `source = "enc"`, so the fishing style draws one contour layer and the gap is visible as coarser, differently styled lines, and `coverage` lets the app say "no fine survey here".

Outputs: `bathy.mbtiles` (vector: `contour`, `band`, `coverage`) and `dem.mbtiles` (raster-dem). MBTiles holds one tile format per file, hence two files.

### 6.6 Style and symbols

Shipped in the pack as plain MapLibre style JSON, generated by `chartpack` from one Python description so the three palettes and the two modes do not drift:

- `nav-day.json`, `nav-dusk.json`, `nav-night.json`: sources `enc` only.
- `fish-day.json`, `fish-dusk.json`, `fish-night.json`: sources `enc` (hazards, coastline, land, lights), `bathy`, `dem`.
- Source URLs in the shipped styles are `mbtiles://enc`, `mbtiles://bathy`, `mbtiles://dem`; `sprite` is `pack://sprites/nav` (or `fish`) and `glyphs` is `pack://glyphs/{fontstack}/{range}.pbf`. The app replaces `url`, `sprite` and `glyphs` with the absolute installed paths at load. Those three rewrites are the whole pack-to-app contract; they are documented in the pack README.
- Fonts (my call, from the builder check): Noto Sans Regular and Bold (SIL OFL 1.1), glyph PBF ranges built at pack build time with `fontnik` (BSD-3, node) and shipped under `glyphs/` in each pack. Each pack is self-contained: the bathy pack carries its own `sprites/` and `glyphs/` even though they duplicate the chart pack's few megabytes, so the two packs stay independently versioned. A style test checks every `text-font` against the shipped glyph set.

Colours (owner decided 2026-10-28, option B): our own palette for day, dusk and night, chosen by eye to look like a NOAA chart and the Garmin, organised by the S-52 colour token names (DEPDW, DEPMD, DEPMS, DEPVS, DEPIT, LANDA, CSTLN, CHBLK, CHGRD, LITRD, LITGN, LITYW, NINFO and so on). The free S-52 standard (edition 6.1.1, iho.int) is read for the design rules only: which features take which token and what the night table is for. No IHO colour values are used: the Presentation Library that holds them is sold by IHO and its copyright notice requires written permission to reproduce. No OpenCPN file is opened. The style file names the token next to each colour so a reviewer can check it, and so the values can be swapped in one file if the owner ever obtains the library.

Depth tints follow S-52's four-shade scheme by `DRVAL1`: deeper than the deep contour, between safety and deep, between shallow and safety, shallower than shallow. Defaults: shallow 6 ft, safety 10 ft, deep 30 ft (owner's safety depth per the parent spec). The safety contour line is drawn bold. The three values are literals, but only inside the `filter` of a fixed set of named layers: `depare-deep`, `depare-medium`, `depare-shallow`, `depare-vshallow`, `depcnt-safety`, `soundg-shallow`, `soundg-deep`, `hazard-danger`, `hazard-danger-outline` (and the same names in the fish styles). No paint expression depends on them. The style's `metadata.cheekymarine.depths` records the three values and lists those layer names, so the app (plan 3) applies the owner's setting by replacing the filters of exactly those layers through MapLibre's set-filter API, with no other knowledge of the style. The layer names are part of the schema. `chartpack build-enc --safety-ft` sets the shipped default.

Soundings: labels in feet, S-52 rule that soundings shallower than the safety depth are drawn in black and deeper ones in grey. Hazards: the plain Chart No. 1 style symbol per class. Hazards draw above every other layer in both modes.

Owner revisions after the Task 8 renders (2026-10-29, rulings R15 to R19 in the SDD ledger):

- Deep water `DEPDW`: day `#F4EEE2` (subtle sepia), night `#18253A` (dark blue-grey). Land `LANDA`: day `#EFD98A`, night `#3A3317` (more yellow). Dusk stays derived from day.
- The isolated-danger symbol shows only during route navigation. The plotter has no navigation yet, so the shipped styles carry no `hazard-danger` layer. The filter logic stays in `chartpack` so plan 3 can add the layer when navigation exists; `hazard-danger` leaves the shipped `metadata.cheekymarine.depths.layers` list until then (superseded by R34 below).
- Restricted areas (`RESARE`): magenta dashed outline, no fill. A translucent fill over most of a sound changes the depth colours.
- Background is `NODTA`, so area outside every cell reads as no data, not as deep water (controller's call, shown to the owner in the preview).
- Rock, obstruction and wreck symbols are redrawn by us in the visual style of OpenCPN's chart symbols. OpenCPN (GPL-2) is looked at as a visual reference only: no file, path data or bitmap is copied, and the repo stays MIT. This replaces the earlier "no OpenCPN file is opened" rule for these symbols only.

Owner revisions after the puget-north renders (2026-10-29, rulings R29 to R43 in the SDD ledger):

- R29: night `DEPMD` is `#15304C`.
- R30: seabed labels take the `SNDG2` ink.
- R31: `RESARE` outline is 8 on 4 dash plus inward T marks; cables are 4 on 2.
- R32, R34, R40, R41 (hazard marks): 11 px fixed. The ring shows only when the hazard-danger rule holds. `hazard-danger` and `hazard-danger-outline` are shipped and listed in `metadata.cheekymarine.depths.layers`. Declutter below z15 as in R40: `icon-allow-overlap` and `icon-ignore-placement` are false below z15 and true from z15, so below z15 hazards hide each other and any sounding or label under them. Ring and mark are baked into one RGBA (non-SDF) image per palette (R41), so `icon-color` does not tint hazards.
- R35: line and area hazards get a dotted outline plus the point symbol.
- R33: contour and band geometry is simplified to about one pixel per zoom.
- R42: the quilt rule is kept for the seam obstruction (US3WA1DF, -122.700, 47.7775): the band 3 object is clipped from z11 because the finer band 4 and 5 cells chart it 344 m WNW.

Symbols: our own SVGs in `chartpack/symbols/`, drawn after US Chart No. 1 (public domain): can, nun, spherical, pillar and spar buoys, lateral and cardinal beacons, light flare, rock awash, submerged rock, dangerous wreck, non-dangerous wreck, obstruction, isolated danger, anchorage, marina. Colour comes from `COLOUR` through the style, so one shape per class and a palette per mode. The sprite sheet (PNG at 1x and 2x plus JSON index) is assembled by `chartpack` at build time. Starts small, grows later.

Fishing mode: `depare`, `depcnt` and `soundg` from the ENC are hidden, `band` fill and `hillshade` provide the picture, `contour` lines are thinned by `minzoom`, majors heavier, labels in feet with a halo and `symbol-placement: line`, at most one label per line per screen at mid zoom. Nav aids are hidden; lights and hazards stay. A fixed banner text layer is not possible in a MapLibre style, so the "fishing chart, survey depths approx. MLLW, not certified for navigation" wording is a string in the manifest that the app shows while fishing mode is on. The nav style carries the same mechanism with "derived from NOAA ENC, not an official chart".

### 6.7 Pack layout, versioning, release

Two packs, versioned independently, matching the About page's "chart pack version" and "bathymetry pack version":

```
charts-puget-north-1.0.0.tar          bathy-puget-north-1.0.0.tar   (tags charts-puget-north-v1.0.0, bathy-puget-north-v1.0.0)
  manifest.json                         manifest.json
  enc.mbtiles                           bathy.mbtiles
  styles/nav-{day,dusk,night}.json      dem.mbtiles
  sprites/{nav,nav@2x}.{png,json}       styles/fish-{day,dusk,night}.json
  glyphs/<font>/<range>.pbf             sprites/{fish,fish@2x}.{png,json}
  README.md, NOTICE                     glyphs/<font>/<range>.pbf
                                        README.md, NOTICE
```

`manifest.json`: `{"pack": "charts"|"bathy", "region", "version", "schema": 1, "built": ISO time, "files": [{name, bytes, sha256}], "sources": [...], "notice": "..."}`. Sources list every ENC cell with edition, update and issue date, or every DEM tile with name, date and sha256, plus the CRM request. The same values sit in the MBTiles `metadata` table. The fishing manifest also names the chart pack schema it was built against.

Schema: the tile schema and manifest format carry `schema: 1`; the app refuses a pack whose schema major it does not know (parent spec 6.9). Bumped on layer removal or attribute rename, not on additions.

Release: tag `charts-<region>-vX.Y.Z` or `bathy-<region>-vX.Y.Z` on main runs `.github/workflows/chartpack-release.yml`: check the tag against the pack versions recorded in the region file (`chartpack/regions/<region>.toml` holds `charts_version` and `bathy_version`), build that pack for that region, run `chartpack check`, attach the tar plus `SHA256SUMS`, generate notes. Two regions can therefore each have their own 1.0.0, and plan 4's update checker matches on pack type, region and semver. The existing `v*` tag pattern of the software release is untouched. CI (`ci.yml`) runs the chartpack tests on every push, without the network.

### 6.8 Verification: tests against known cells

No network in unit tests. Fixtures: the two committed cell zips, a synthetic ridge DEM (as in wa-creel), one small real CUDEM window (under 500 KB, cut from `ncei19_n48x00_w122x50_2023v1.tif` over Possession Bar), and golden JSON files regenerated only by an explicit `--update-golden` flag with the diff reviewed in the PR.

ENC tests, on US4WA1HK (and US5SEAKL where noted):

- Every DEPARE in the source appears in `depare` at every zoom of its band with `DRVAL1`/`DRVAL2` byte-equal to the source (compared as decimal strings, not floats).
- Union of `depare` plus `lndare` polygons at the top zoom covers the cell's `M_COVR` within 0.01 percent of area, with no overlap between depth areas above the same tolerance: no gaps, no slivers.
- Every UWTROC, WRECKS and OBSTRN in the source appears in `hazard` at every zoom of its band, with `VALSOU`, `WATLEV` and category attributes equal to the source. Counted both ways: nothing missing, nothing invented.
- Every SOUNDG point appears at the top zoom with its depth equal to the source Z, and the set at lower zooms is exactly the `SCAMIN` rule's prediction.
- Applying the `.001` update to US5SEAKL changes the output in the way the update file says (a feature added, modified or deleted), and the pack metadata reports update 1.
- Quilting: over the US5SEAKL coverage polygon at zoom 13, no band 4 feature from US4WA1HK is present, and at zoom 12 no band 5 feature is present.
- Golden counts per layer per zoom for US4WA1HK, so a tippecanoe or GDAL upgrade that silently drops features fails CI.
- Style: every `source-layer` and attribute the generated styles reference exists in the schema; every `icon-image` exists in the sprite; the style JSON validates against the MapLibre style spec (the `@maplibre/maplibre-gl-style-spec` validator, BSD-3, run through node in CI).

Bathy tests:

- On the synthetic ridge: contour lines at the expected depths, closed where expected, dropped when too short, deterministic bytes; depth bands tile the grid with no gaps; the datum shift moves every level by the constant; land fill closes lines at the shore.
- On the real CUDEM window: NAVD88 tag read and the shift applied, tile name and version carried into `coverage`, clip at a synthetic boundary line removes the Canadian side.
- `dem.mbtiles` round trip: decode a tile's terrarium PNG and recover the depth within 0.1 m.
- `coverage` plus fallback: where the merged grid has CRM only, `contour` features carry `source = "enc"` or `source = "crm"` as configured and never `"cudem"`.

`chartpack check` runs the structural subset of these against any built pack (counts, coverage, metadata) and is the gate in the release workflow.

Integration (network, skipped unless `CHARTPACK_ONLINE=1`): fetch US5SEAKL from NOAA, verify the zip layout and that `edtn.updn` parses from the catalog; open one CUDEM tile through `/vsicurl/` and read a 100 by 100 window over Possession Bar; one WCS request to CRM for a 0.05 degree box.

### 6.9 Verification the owner sees

`chartpack render` opens the built pack in maplibre-gl-js in headless Chromium through Playwright, with a tiny local tile server reading the MBTiles, and screenshots fixed views from the region file: Everett harbour, Possession Bar, Point No Point, Jeff Head; zooms 11, 13, 15; nav and fish; day and night. 48 PNGs under `docs/chartpack/renders/puget-north/` committed with the PR so the owner compares them against the Garmin. These are for eyes, not assertions; the plan keeps the pixel checks out of CI. Note in the README that GL JS renders a superset of what Native Qt draws; the app in plan 3 is the final check.

### 6.10 Bottom composition (owner requirement, 2026-10-29)

Why: the owner wants this done well, for two uses. Bottom fishing: different fish hold over different bottoms. Anchoring: sand and gravel hold, rock and weed do not. The chart shows the bottom type and the owner judges anchoring from it, so no anchoring-quality tag is computed (owner, 2026-10-29).

Display (owner decided): the Garmin and NOAA chart convention of short abbreviations at the spot (S sand, M mud, Rk rock and so on), and every abbreviation can be looked up quickly. Only real data is shown, nothing inferred or interpolated. If no better source exists for an area, the NOAA chart's own bottom marks are enough.

Sources, all layered, each feature tagged with its source (`src`):

1. `enc`: ENC `SBDARE` (seabed area, point/line/area; `NATSUR`, `NATQUA`, `COLOUR`, `WATLEV`) and `WEDKLP` (weed/kelp; `CATWED`). Everywhere, sparse. Baseline.
2. `usseabed`: USGS usSEABED Pacific Coast, Data Series 182 (2006, doi:10.3133/ds182). Sediment sample points from grabs and cores across Puget Sound. Old, and the metadata warns of duplicates across its sources: drop exact duplicates by position and type. The builder picks the EXT (lab) and PRS (parsed description) files and maps their classes to the same abbreviation set.
3. `usgs-cmecs`: USGS Southern Salish Sea Habitat Map Series (Data Series 935): CMECS substrate polygons for Admiralty Inlet (OFR 2015-1073), offshore Seattle (doi:10.5066/P9GVRZ3M), offshore Tacoma (doi:10.5066/P9KA6GH2) and offshore Burien (doi:10.5066/P96T1B44). Continuous areas from video and bathymetry, only in those blocks.

Licence gate: each USGS release is used only after its metadata `Use_Constraints` / access constraints are read and recorded in `chartpack/NOTICE` as public domain (US Government work) or a permissive licence. A source that fails the gate is left out and the decision is written in the SDD ledger; the ENC source alone still ships. WA DNR ShoreZone was considered and rejected: it describes the shoreline, not the bottom, and its licence is unclear.

Tiles (my call): one new layer `seabed` in `enc.mbtiles`, so the pack contract (sources `enc`, `bathy`, `dem`) does not change. Attributes: `src`, `class` (`SBDARE`, `WEDKLP`, `SAMPLE`, `CMECS`), the source's own codes (`NATSUR`, `NATQUA` comma-joined as GDAL gives them; CMECS substrate class name), `label` (the abbreviation, computed at build time because MapLibre expressions cannot split the comma lists). ENC features follow the band quilting like every other ENC layer; USGS features are not quilted. Thinning: ENC by `SCAMIN` like `soundg`; USGS points at a fixed minzoom chosen from the renders. Extended by R37 and R43: seabed areas and ENC seabed lines get a build-time minzoom where they are about 48 px across (area: sqrt of area; line: length; 256 px Web Mercator at latitude 48), combined with `SCAMIN` by max for ENC. Seabed points thin at draw time by collision: labels about 40 px apart below z15, priority bigger areas, then ENC points, then usSEABED samples. The layer is not a safety layer, but it is never randomly dropped. Additions do not bump `schema`.

Abbreviations: from US Chart No. 1 section J (public domain), for example M mud, Cy clay, Si silt, S sand, St stones, G gravel, P pebbles, Cb cobbles, Rk rock, Co coral, Sh shells, Bo boulders, Wd weed, with qualifiers (f fine, m medium, c coarse, bk broken, sy sticky, so soft, sf stiff, h hard) prefixed, and several types joined the chart way (for example `fS.M`). The builder verifies every code against Chart No. 1 and the S-57 attribute catalogue.


Lookup: each charts pack ships `legend.json`: for every abbreviation and qualifier used anywhere in the pack, the meaning in plain words and the sources it appears in. Plan 3's tap-to-identify and legend page read it. The same table is published as `docs/chartpack/seabed-legend.md`.

Style: both nav and fish styles show `seabed` labels in grey chart ink (`CHGRD`), Noto Sans Regular, smaller than soundings, below soundings and hazards in draw order. CMECS polygons draw as a thin outline plus their label, with no fill: a fill would change the depth colours, the same lesson as the restricted areas. Renders at Possession Bar and in one CMECS block go to the owner with Task 15.

## 7. Risks and open technical questions (for the builder)

- tippecanoe is not in apt. Build from the pinned 2.79.0 tag in CI (a few minutes) and cache it; document the dev machine build.
- GDAL 3.8.4's S-57 driver and `SCAMIN` semantics: confirm `SCAMIN` is exposed on split sounding points. If not, carry it from the parent SOUNDG record.
- ENC seams: band 4 cells meet at 48.0 N and 122.4 W; depth areas are cut at the cell edge and the tiles will show the seam if the two cells disagree. Expected behaviour, same as any ECDIS; `--detect-shared-borders` keeps the edge clean.
- CUDEM tiles are 190 MB each; the `/vsicurl/` window reads must be verified to stay small in CI (the integration test measures bytes fetched). If they do not, the fetch step downloads whole tiles into the cache and the runner's 14 GB disk still fits the first region (about 12 tiles).
- Pack size on the first area: measure after the first full build; if `dem.mbtiles` at zoom 15 is too large, cap at 14 and let the app overzoom the hillshade.
- maplibre-native-qt v3.0.0 reads MBTiles through the core file source; the Qt path is reported but not verified end to end. Plan 3 verifies; if it fails, a local tile server in the app is the fallback, and this pack format does not change.

## 8. Left to the builder

- Exact tippecanoe flags per layer, zoom-level detail, buffer sizes.
- Whether to keep intermediate GeoJSONSeq or stream into tippecanoe.
- The sprite assembly method within the licence rule.
- Label density and halo sizes, tuned on the renders.
- Download caching layout and retry policy.
- Task order, within: scaffold and fixtures first, ENC conversion and its tests, quilting, style and sprites, renders, then bathy fetch, merge, contours, bands, DEM, fallback, manifest and release workflow last.

## 9. Owner decisions pending

1. Bathymetry: decided. CUDEM 1/9 arc-second primary, CRM 2025 fallback (section 6.4). The owner asked for a published-state grid rather than NBS test-and-evaluation data and said CRM is the fallback for sure.
2. S-52 colour values: decided, option B (own palette, S-52 token names). See 6.6.
3. Dev machine: done, `gdal-bin` and `python3-gdal` 3.8.4 installed and verified 2026-10-28.
