# chartpack

Builds MBTiles chart packs from NOAA ENC cells and bathymetry grids for the
CheekyMarine chartplotter. Subcommands: `fetch-enc`, `fetch-seabed`, `build-enc`, `fetch-bathy`,
`build-bathy`, `check`, `manifest`, `archive`, `render`, `cells`.

## Setup

System dependencies (apt): `gdal-bin python3-gdal` (the Python GDAL bindings are not
in `pyproject.toml`; the venv must see them via `--system-site-packages`), plus
`g++ make zlib1g-dev libsqlite3-dev` to build tippecanoe.

```bash
scripts/install-tippecanoe.sh        # tippecanoe 2.79.0 and tile-join to ~/.local/bin
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'    # add ',render' for Playwright
.venv/bin/pytest -q
```

numpy is pinned to the apt version (1.26.4) because python3-gdal is built against it.

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

A charts pack is a directory `charts-<region>-<version>/` holding `enc.mbtiles`,
`styles/*.json`, `sprites/`, `glyphs/`, `legend.json`, `README.md` and `NOTICE`.

- Style source names are `enc` (and, in later packs, `bathy` and `dem`). Each source
  has `"url": "mbtiles://<name>"`, resolved to the `<name>.mbtiles` file in the pack.
- `sprite` is `pack://sprites/<name>` and `glyphs` is `pack://glyphs/{fontstack}/{range}.pbf`.
  The app rewrites these three things (source URLs, sprite, glyphs) and nothing else.
- Depth thresholds appear only in the `filter` of the layers named `depare-deep`,
  `depare-medium`, `depare-shallow`, `depare-vshallow`, `depcnt-safety`, `soundg-shallow`,
  `soundg-deep`, `hazard-danger` and `hazard-danger-outline`. `metadata.cheekymarine` in each
  style records the thresholds (`depths`, whose `layers` lists the depth layers the style
  actually ships), the drawn `safety_contour_m`, `units` and `palette`. `hazard-danger` draws
  the red dotted ring round a hazard that is awash, drying, of unknown depth or shallower than
  the safety depth; `hazard-danger-outline` draws a line or area hazard's outline red on the same
  rule.
- MBTiles metadata carries `cheekymarine:schema` (currently 1), `cheekymarine:pack`,
  `cheekymarine:region`, `cheekymarine:version`, `cheekymarine:sources` (the ENC cells
  with edition, update and issue date), `cheekymarine:valdco`, `cheekymarine:seabed` (the
  distinct seabed codes in the tiles) and `cheekymarine:built`.
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
- Data is derived from NOAA ENC. It is not an official chart and is not certified for
  navigation. The app must show that notice with the pack.
