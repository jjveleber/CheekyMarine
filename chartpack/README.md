# chartpack

Builds MBTiles chart packs from NOAA ENC cells and bathymetry grids for the
CheekyMarine chartplotter. Subcommands (`fetch-enc`, `build-enc`, `fetch-bathy`,
`build-bathy`, `check`, `manifest`, `archive`, `render`, `cells`) are stubs until
their tasks land.

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
