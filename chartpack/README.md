# chartpack

Builds MBTiles chart packs from NOAA ENC cells and bathymetry grids for the
CheekyMarine chartplotter. Subcommands: `fetch-enc`, `build-enc`, `fetch-bathy`,
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

## Tests

Tests marked `online` need network and run only with `CHARTPACK_ONLINE=1`. Tests
marked `render` need Playwright and Chromium and are skipped otherwise.

Licences of Python dependencies are listed in `NOTICE`.

## Pack contract

A charts pack is a directory `charts-<region>-<version>/` holding `enc.mbtiles`,
`styles/*.json`, `sprites/`, `glyphs/`, `README.md` and `NOTICE`.

- Style source names are `enc` (and, in later packs, `bathy` and `dem`). Each source
  has `"url": "mbtiles://<name>"`, resolved to the `<name>.mbtiles` file in the pack.
- `sprite` is `pack://sprites/<name>` and `glyphs` is `pack://glyphs/{fontstack}/{range}.pbf`.
  The app rewrites these three things (source URLs, sprite, glyphs) and nothing else.
- Depth thresholds appear only in the `filter` of the layers named `depare-deep`,
  `depare-medium`, `depare-shallow`, `depare-vshallow`, `depcnt-safety`, `soundg-shallow`,
  `soundg-deep` and `hazard-danger`. `metadata.cheekymarine` in each style records the
  thresholds (`depths`, whose `layers` lists the depth layers the style actually ships),
  the drawn `safety_contour_m`, `units` and `palette`. The shipped styles carry no
  `hazard-danger` layer until the app has route navigation.
- MBTiles metadata carries `cheekymarine:schema` (currently 1), `cheekymarine:pack`,
  `cheekymarine:region`, `cheekymarine:version`, `cheekymarine:sources` (the ENC cells
  with edition, update and issue date), `cheekymarine:valdco` and `cheekymarine:built`.
- Depth values are stored in the tiles in metres as charted; feet and rounding happen
  only in style expressions.
- Data is derived from NOAA ENC. It is not an official chart and is not certified for
  navigation. The app must show that notice with the pack.
