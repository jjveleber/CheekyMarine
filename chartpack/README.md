# chartpack

Builds MBTiles chart packs from NOAA ENC cells, bathymetry grids and USGS bottom composition for the
CheekyMarine chartplotter. Subcommands: `fetch-enc`, `fetch-seabed`, `build-enc`, `fetch-bathy`,
`build-bathy`, `check`, `manifest`, `archive`, `render`, `cells`.

## What it builds

Two packs per region, each a directory `<pack>-<region>-<version>/`:

- `charts-<region>-<version>`: `enc.mbtiles` (the quilted ENC cells of the region's bands 3 to 5, plus
  the optional USGS `seabed` layer) and the navigation styles `nav-day`, `nav-dusk`, `nav-night`.
- `bathy-<region>-<version>`: `bathy.mbtiles` (depth contours, depth bands, coverage) and `dem.mbtiles`
  (terrain), and the fishing styles `fish-day`, `fish-dusk`, `fish-night`.

Both carry sprites, glyphs, `README.md`, `NOTICE` and `manifest.json`. The charts pack also carries
`legend.json`. A region file (`regions/<region>.toml`) names the cells, the bounding box and the versions;
nothing else in the tool is specific to one place.

## Dev setup

System dependencies (apt): `gdal-bin python3-gdal` (the Python GDAL bindings are not
in `pyproject.toml`; the venv must see them via `--system-site-packages`), plus
`g++ make zlib1g-dev libsqlite3-dev` to build tippecanoe.

```bash
scripts/install-tippecanoe.sh        # tippecanoe 2.79.0 and tile-join to ~/.local/bin
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'    # add ',render' for Playwright
.venv/bin/pytest -q
```

numpy is pinned to the apt version (1.26.4) because python3-gdal is built against it. Playwright
and Chromium are optional: only the `render` subcommand and the tests marked `render` need them
(`.venv/bin/pip install -e '.[render]'`, then `.venv/bin/playwright install chromium`).

## Commands

Run from `chartpack/`. `--cache` is the download cache (ENC zips, CUDEM list, CRM, seabed zips), `--work` is
scratch space, `OUT` is the directory the pack directory is created in. A build writes
`OUT/<pack>-<region>-<version>/`, so every later command takes that nested path.

```bash
R=regions/puget-north.toml
chartpack cells $R --band 5 --cache cache                  # catalog cells meeting the bbox, for editing the region file
chartpack fetch-enc $R --cache cache                       # ENC zips, newest edition and updates
chartpack fetch-seabed $R --cache cache                    # USGS bottom composition zips
chartpack build-enc $R work/charts --cache cache --work work/tmp
chartpack fetch-bathy $R --cache cache                     # CUDEM tile list, CRM for the bbox
chartpack build-bathy $R work/bathy --cache cache --work work/tmp
chartpack check work/charts/charts-puget-north-1.0.0 --enc-cache cache
chartpack check work/bathy/bathy-puget-north-1.0.0
chartpack manifest work/charts/charts-puget-north-1.0.0 --region $R   # rewrite manifest.json (builds already do this)
chartpack archive work/charts/charts-puget-north-1.0.0 dist           # dist/charts-puget-north-1.0.0.tar and SHA256SUMS
chartpack archive work/bathy/bathy-puget-north-1.0.0 dist
chartpack render work/charts/charts-puget-north-1.0.0 work/bathy/bathy-puget-north-1.0.0 --views $R --out renders
```

`render` takes one or more pack directories and draws the region's `[[render.views]]` with MapLibre in
headless Chromium (`--styles nav-day,fish-day` limits the styles).

## Region files

`regions/<region>.toml`:

```toml
name = "puget-north"
charts_version = "1.0.0"          # tag charts-puget-north-v1.0.0
bathy_version = "1.0.0"           # tag bathy-puget-north-v1.0.0
bbox = [-122.9, 47.5, -122.1, 48.3]   # W, S, E, N
clip = "clip/canada-wa.geojson"   # optional: polygon of water to remove from the bathy
coarse_fallback = "crm"           # optional: "crm" (default) or "enc" for contours where CUDEM is absent

[enc]                             # ENC cells by band (band3, band4, band5)
band4 = ["US4WA1HK"]

[bathy]
sources = ["cudem", "crm"]
dem_maxzoom = 14

[datum]                           # NOAA CO-OPS station and offsets to approximate MLLW, in metres
station = "9447130"
navd88_to_mllw_m = 0.715
msl_to_mllw_m = 2.02

[seabed]                          # optional: sources enc (always), usseabed, usgs-cmecs
sources = ["enc", "usseabed", "usgs-cmecs"]
cmecs_blocks = ["admiralty-inlet", "seattle", "burien"]

[[render.views]]                  # optional: what `render` draws
name = "everett"
lon = -122.23
lat = 47.98
zooms = [11, 13, 15]
```

The `clip` path is resolved relative to the directory of the region file, not the current directory
(`regions/clip/canada-wa.geojson` for the example). `scripts/make-clip.py` builds a clip polygon.

## Downloads

NOAA's server may answer a plain fetch of `https://charts.noaa.gov/ENCs/<CELL>.zip`
with 403. Retry with this User-Agent header:

```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36
```

`fetch-seabed` downloads the USGS bottom composition zips a region's `[seabed]` table names
(`sources` with `usseabed` and `usgs-cmecs`, `cmecs_blocks` from `admiralty-inlet`, `seattle`,
`tacoma`, `burien`) into `<cache>/seabed/`; `build-enc` reads them from there. Their published
sizes are pinned in `seabed/usseabed.py` and `seabed/cmecs.py`, so a damaged or revised file fails
the fetch. A region without `[seabed]` uses the ENC bottom marks only.

## Tests

Tests marked `online` need network and run only with `CHARTPACK_ONLINE=1`. Tests
marked `render` need Playwright and Chromium and are skipped otherwise.

Licences of Python dependencies are listed in `NOTICE`.

## Pack contract

A charts pack is a directory `charts-<region>-<version>/` holding `enc.mbtiles`, `styles/*.json`,
`sprites/`, `glyphs/`, `legend.json`, `manifest.json`, `README.md` and `NOTICE`. A bathy pack is
`bathy-<region>-<version>/` with `bathy.mbtiles` and `dem.mbtiles` in place of `enc.mbtiles` and no
`legend.json`. Both ship as a tar with a `SHA256SUMS` file.

- Style source names are `enc` (charts pack), `bathy` and `dem` (bathy pack). Each source has
  `"url": "mbtiles://<name>"`, resolved to the `<name>.mbtiles` file in the pack.
- The app rewrites exactly three things in a style and nothing else:
  1. each source URL `mbtiles://enc`, `mbtiles://bathy`, `mbtiles://dem` becomes a URL the app can
     read that pack file from;
  2. `sprite`, `pack://sprites/<name>` (`nav` or `fish`), becomes the pack's `sprites/<name>` location;
  3. `glyphs`, `pack://glyphs/{fontstack}/{range}.pbf`, becomes the pack's `glyphs/` location.
- Depth thresholds appear only in the `filter` of the layers named `depare-deep`, `depare-medium`,
  `depare-shallow`, `depare-vshallow`, `depcnt-safety`, `soundg-shallow`, `soundg-deep`,
  `hazard-danger` and `hazard-danger-outline` (the named depth layers). `metadata.cheekymarine` in each
  style records the thresholds (`depths`, whose `layers` lists the depth layers the style
  actually ships), the drawn `safety_contour_m`, `units`, `palette` and `notice`. `hazard-danger` draws
  the red dotted ring round a hazard that is awash, drying, of unknown depth or shallower than
  the safety depth; `hazard-danger-outline` draws a line or area hazard's outline red on the same
  rule.
- MBTiles metadata carries `cheekymarine:schema` (currently 1), `cheekymarine:pack`,
  `cheekymarine:region`, `cheekymarine:version`, `cheekymarine:sources` (the ENC cells
  with edition, update and issue date), `cheekymarine:valdco`, `cheekymarine:seabed` (the
  distinct seabed codes in the tiles) and `cheekymarine:built`.
- Schema policy: the tile schema and the manifest format carry `schema: 1`. The number is bumped on a
  layer removal or an attribute rename, not on additions. The app refuses a pack whose schema it does not know.
- The optional `seabed` layer holds bottom composition with its chart abbreviation in `label`
  (absent when the source class has none). `src` and `class` say where a feature comes from:
  `enc` with `SBDARE` or `WEDKLP` (quilted like the other ENC layers, with `cell` and `band`);
  `usseabed` with `SAMPLE`, a USGS sediment sample point with its Folk class in `folk`;
  `usgs-cmecs` with `CMECS`, a USGS substrate polygon with its CMECS name in `substrate`. The
  USGS features are not quilted and have no `cell` or `band`. Areas and lines carry `extent`,
  their size in 256 px Web Mercator pixels at zoom 0 (square root of the area, or the length),
  and are in the tiles from the zoom at which they are about 48 px across.
  `legend.json` (`{"schema": 1, "entries": [{"abbr", "meaning", "kind", "sources"}]}`) explains
  every abbreviation the pack's labels use; `docs/chartpack/seabed-legend.md` is the full table.
- Depth values are stored in the tiles in metres as charted; feet and rounding happen
  only in style expressions.
- Notices the app must show with the pack. Each style carries its notice in
  `metadata.cheekymarine.notice`, and `manifest.json` repeats it in `notice`. The nav styles say:
  `Derived from NOAA ENC. Not an official chart. Not certified for navigation.`
  The fish styles say:
  `Fishing chart: survey depths, approx. MLLW. Not certified for navigation.`
  The pack `NOTICE` file adds the data sources and licences, and says: `This pack is a derived product.
  It is not an official chart.` and `It is not certified for navigation. Do not rely on it as the only
  means of navigation.`
- Data is derived from NOAA ENC (and, in the bathy pack, NOAA NCEI CUDEM and CRM). It is not an
  official chart and is not certified for navigation.

## Verification

CI (`chartpack-ci.yml`) runs the unit tests (no network; tests marked `online` need `CHARTPACK_ONLINE=1`)
and validates the generated nav and fish styles against the MapLibre style spec. `chartpack check` runs on a
built pack and checks its structure: manifest, file hashes, MBTiles metadata, layers, the safety data
(with `--enc-cache`, that the charted hazards of the source cells are in the tiles) and the styles
against the tile schema, sprites and glyphs. The renders do not prove anything: they are for the owner's eyes,
to judge legibility and colour before a release.

## Cutting a release

1. Bump `charts_version` and/or `bathy_version` in `regions/<region>.toml` and commit.
2. Tag the commit `charts-<region>-vX.Y.Z` or `bathy-<region>-vX.Y.Z` (the version must equal the
   region file's, `scripts/check-pack-tag.sh TAG` checks it) and push the tag. Tag only a commit whose `chartpack-ci` run is green: the release
   workflow does not rerun the tests.
3. `.github/workflows/chartpack-release.yml` fetches, builds, checks and archives the pack and attaches
   `<pack>-<region>-<version>.tar` and `SHA256SUMS` to a GitHub release. If the build does not fit the
   runner, run the commands above on the dev machine and attach the tar by hand.

The `v*` tags belong to n2kd (`release.yml`) and are independent of pack tags.

## Credits

Admiralty Inlet seabed habitat data: U.S. Geological Survey, Southern Salish Sea Habitat Map Series,
Data Series 935, CMECS substrate polygons, Admiralty Inlet, Open-File Report 2015-1073,
doi:10.3133/ofr20151073. Other USGS and NOAA sources are listed in `NOTICE`.
