# chartpack (ENC and bathymetry tile packs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python tool, `chartpack`, that turns NOAA ENC cells and NOAA bathymetry grids into versioned, checksummed MBTiles packs with MapLibre styles, proves the packs against the source data in CI, renders screenshots for the owner, and publishes packs as GitHub releases.

**Architecture:** One Python package `chartpack` with a CLI of independent subcommands (`fetch-enc`, `build-enc`, `fetch-bathy`, `build-bathy`, `check`, `manifest`, `archive`, `render`). ENC cells are read with GDAL's S-57 driver, mapped to a fixed tile schema, quilted by usage band per zoom, and tiled with tippecanoe with every dropping feature turned off for safety layers. Bathymetry is CUDEM 1/9 arc-second windows merged over a CRM fallback, shifted to approximate MLLW, contoured with the owner's wa-creel rules, and shipped as vector contours and bands plus a terrarium raster DEM. Styles are generated from one Python description so the two modes and three palettes cannot drift. Everything except downloads is tested offline on two committed ENC cells and one committed CUDEM window.

**Tech Stack:** Python 3.12 (`/usr/bin/python3` on Ubuntu 24.04, venv with `--system-site-packages` for `python3-gdal` 3.8.4), numpy, contourpy, shapely 2, scipy (distance transform), Pillow, freetype-py, mapbox-vector-tile (tests), pytest; tippecanoe 2.79.0 (felt fork, built from source); maplibre-gl-js and Playwright for renders only; GitHub Actions `ubuntu-24.04`.

**Spec:** `docs/superpowers/specs/2026-10-28-chartpack-design.md` (parent: `docs/superpowers/specs/2026-10-28-cheekymarine-design.md` sections 6.3, 6.9, 8, 9)

## Global Constraints

- No GPL or LGPL code or assets anywhere. Allowed and used: GDAL (MIT), tippecanoe (BSD-2), numpy (BSD-3), contourpy (BSD-3), shapely (BSD-3), scipy (BSD-3), Pillow (MIT-CMU), freetype-py (BSD-3, FreeType under the FreeType License), mapbox-vector-tile (MIT), pytest (MIT), maplibre-gl-js (BSD-3), Playwright (Apache-2.0), Noto Sans (SIL OFL 1.1). cairosvg and svglib are LGPL: not used. Every new dependency's licence is checked before it is added and listed in `chartpack/NOTICE`.
- Data: NOAA ENC (US Government work; derived product, cite "NOAA ENC", show "not certified for navigation"), NCEI CUDEM 1/9 arc-second (DOI 10.25921/ds9v-ky35, not subject to copyright), NCEI CRM Vol. 8 2025, NOAA Maritime Limits and Boundaries (CC0), NOAA CO-OPS datums.
- Depth values from the ENC are stored in the tiles in metres exactly as charted, as decimal strings compared byte-equal in tests. Rounding and feet happen only in style expressions.
- Layers `depare`, `depcnt`, `hazard`, `navaid`, `light`, `coalne`, `lndare` are never thinned or dropped: tippecanoe `-r1 --no-feature-limit --no-tile-size-limit --no-tiny-polygon-reduction --no-simplification-of-shared-nodes --detect-shared-borders`. Thinning of `soundg`, `area`, `line` is only by per-feature `tippecanoe:minzoom` computed from `SCAMIN`.
- Zoom ranges: band 2 and 3 at zoom 6 to 10, band 4 at 11 to 12, band 5 at 13 to 16; pack maxzoom 16. Bathy contours zoom 10 to 16, DEM zoom 10 to 14 (15 only if the pack stays under 300 MB).
- Fishing contour levels (feet): every 10 to 300, then 400, 500, 600; majors 60, 120, 180, 300, 600; base ten 30, 60, 90, 120, 150, 180, 240, 300, 400, 600; plus 5 ft steps 5 to 60 where CUDEM covers. `minzoom`: majors 10, base ten 12, 20 ft steps and 500 at 13, 10 ft at 14, 5 ft at 15.
- Datum: depth below approximate MLLW = -(elevation) - offset, with `navd88_to_mllw_m = 0.715` for CUDEM and `msl_to_mllw_m = 2.02` for CRM (Seattle 9447130), from the region file.
- Depth thresholds in styles: shallow 6 ft, safety 10 ft, deep 30 ft (1.8288, 3.048, 9.144 m), only inside the `filter` of layers named `depare-deep`, `depare-medium`, `depare-shallow`, `depare-vshallow`, `depcnt-safety`, `soundg-shallow`, `soundg-deep`, `hazard-danger`.
- Pack contract: style source names `enc`, `bathy`, `dem` with URLs `mbtiles://enc` etc., `sprite` `pack://sprites/<name>`, `glyphs` `pack://glyphs/{fontstack}/{range}.pbf`. The app rewrites those three things and nothing else. Schema version 1 in MBTiles metadata and manifest.
- Versions live in the region file (`charts_version`, `bathy_version`); release tags are `charts-<region>-vX.Y.Z` and `bathy-<region>-vX.Y.Z`.
- TDD: every task writes its failing test first. Unit tests never touch the network; online tests are skipped unless `CHARTPACK_ONLINE=1`. Commit after each task. Every task is reviewed by an independent subagent before the next starts.
- Pack size: 300 MB target, 1 GB hard cap per pack.

## Review Focus

Inputs the spec implies but no feature test would naturally cover. Each has a test pinned to the owning task.

1. **A cell zip with a gap in its update sequence** (`.000`, `.001`, `.003`). Expected: build fails naming the cell and the missing update; never a pack built from a stale base. Task 2.
2. **A rock with no `VALSOU`** (unknown depth) and a `COLOUR` list with several values. Expected: the hazard is present in the tile with `VALSOU` absent (not 0), lists joined with commas, and the danger filter treats an unknown-depth rock as dangerous. Tasks 3 and 6.
3. **A depth area crossing a tile edge.** Expected: both tiles carry the polygon with the same `DRVAL1`, and the union at the top zoom still covers the cell with no seam gap. Task 5.
4. **A CUDEM NoData hole inside the water** (`-9999`). Expected: filled from CRM, never contoured as a 9999 m cliff; the hole is recorded in `coverage` as `crm`. Task 10.
5. **An interrupted download** (CRM GeoTIFF or ENC zip truncated). Expected: the cache entry is rejected by size or signature and refetched; a build never reads a partial file. Tasks 2 and 9.

---

## File Structure

```
chartpack/
  pyproject.toml                       package metadata, pinned deps, console script `chartpack`
  README.md                            dev setup, commands, the pack contract (section "Pack contract")
  NOTICE                               data sources and dependency licences
  regions/test-cell.toml               US4WA1HK only (tests)
  regions/puget-north.toml             areas 8-2, 9, 10
  regions/clip/canada-wa.geojson       Canadian-side polygon for clipping (generated once, committed)
  symbols/*.svg                        our Chart No. 1 derived symbols
  fonts/NotoSans-Regular.ttf, NotoSans-Bold.ttf, OFL.txt
  scripts/install-tippecanoe.sh        builds 2.79.0 into ~/.local/bin (also used by CI)
  scripts/make-clip.py                 NOAA boundary shapefile -> regions/clip/canada-wa.geojson
  src/chartpack/__init__.py            __version__
  src/chartpack/cli.py                 argparse, one function per subcommand
  src/chartpack/region.py              Region dataclass, load_region(path)
  src/chartpack/cache.py               download(url, dest, expected_size=None) with partial-file rejection
  src/chartpack/mbtiles.py             MBTiles open/create, get_tile, put_tile, metadata read/write, y flip
  src/chartpack/enc/catalog.py         ENCProdCat.xml -> CellInfo
  src/chartpack/enc/fetch.py           zip download, layout check, update-sequence check
  src/chartpack/enc/schema.py          LAYERS table, SCHEMA_VERSION, attribute lists
  src/chartpack/enc/reader.py          read_cell(zip_path) -> iterator of (layer, Feature)
  src/chartpack/enc/scamin.py          minzoom_for_scamin(scamin, band)
  src/chartpack/enc/quilt.py           quilt(cells) -> features with minzoom/maxzoom (uses BAND_ZOOMS from scamin.py)
  src/chartpack/enc/tiles.py           write GeoJSONSeq, run tippecanoe, write metadata
  src/chartpack/bathy/cudem.py         tile list, tiles_for_bbox, read_window
  src/chartpack/bathy/crm.py           WCS URL, fetch_crm(bbox)
  src/chartpack/bathy/merge.py         merge_to_mllw(...) -> Grid, coverage polygons, clip
  src/chartpack/bathy/contours.py      wa-creel port: levels, min_zoom, chaikin, build_contours
  src/chartpack/bathy/bands.py         filled bands
  src/chartpack/bathy/dem.py           terrarium encode/decode, build_dem_mbtiles
  src/chartpack/bathy/tiles.py         bathy.mbtiles via tippecanoe, ENC fallback contours
  src/chartpack/style/palette.py       TOKENS, PALETTES["day"|"dusk"|"night"]
  src/chartpack/style/nav.py           nav_style(palette, depths) -> dict
  src/chartpack/style/fish.py          fish_style(palette, depths) -> dict
  src/chartpack/style/sdf.py           bitmap -> signed distance field (shared by sprites and glyphs)
  src/chartpack/style/sprites.py       SVGs -> sprite PNG + JSON (SDF)
  src/chartpack/style/glyphs.py        TTF -> PBF glyph ranges
  src/chartpack/style/validate.py      schema/sprite/glyph cross-checks
  src/chartpack/pack/manifest.py       manifest.json
  src/chartpack/pack/check.py          structural checks on a built pack
  src/chartpack/pack/archive.py        tar + SHA256SUMS
  src/chartpack/render/server.py       local HTTP server over MBTiles, sprites, glyphs
  src/chartpack/render/render.py       Playwright screenshots
  src/chartpack/render/page.html       maplibre-gl-js page
  tests/conftest.py                    fixture paths, tmp work dirs, `online` marker
  tests/fixtures/US4WA1HK.zip, US5SEAKL.zip, cudem_possession_bar.tif, ridge.npy
  tests/fixtures/golden/*.json         counts per layer per zoom, regenerated with --update-golden
  tests/test_*.py                      one per module
.github/workflows/chartpack-ci.yml     pytest offline + tippecanoe cache
.github/workflows/chartpack-release.yml tag -> build -> check -> release
docs/chartpack/renders/puget-north/*.png
```

Naming: modules lower-case, functions `snake_case`, dataclasses for records. Geometry is passed as GeoJSON dicts (`{"type": ..., "coordinates": ...}`) between modules and as shapely geometries inside a module. All coordinates are WGS84 lon/lat until tippecanoe.

---

### Task 1: Package scaffold, region loader, fixtures, CI

**Files:**
- Create: `chartpack/pyproject.toml`, `chartpack/README.md`, `chartpack/NOTICE`, `chartpack/src/chartpack/__init__.py`, `chartpack/src/chartpack/cli.py`, `chartpack/src/chartpack/region.py`, `chartpack/regions/test-cell.toml`, `chartpack/scripts/install-tippecanoe.sh`, `chartpack/tests/conftest.py`, `.github/workflows/chartpack-ci.yml`
- Create fixtures: `chartpack/tests/fixtures/US4WA1HK.zip`, `chartpack/tests/fixtures/US5SEAKL.zip` (downloaded once from `https://charts.noaa.gov/ENCs/<CELL>.zip`, committed; record each cell's `EDTN`/`UPDN` from its DSID in `tests/fixtures/README.md`)
- Test: `chartpack/tests/test_region.py`, `chartpack/tests/test_cli.py`
- Modify: `.gitignore` (add `chartpack/.venv/`, `chartpack/work/`, `chartpack/cache/`)

**Interfaces:**
- Produces:
  ```python
  # region.py
  @dataclass(frozen=True)
  class Region:
      name: str; charts_version: str; bathy_version: str
      bbox: tuple[float, float, float, float]        # W, S, E, N
      cells: dict[int, list[str]]                     # band -> cell names
      bathy_sources: list[str]                         # ["cudem", "crm"]
      coarse_fallback: str                             # "crm" (default): draw contours from CRM where CUDEM is absent; "enc": use ENC contours there instead
      clip: Path | None                                # polygon GeoJSON of water to remove
      dem_maxzoom: int
      navd88_to_mllw_m: float; msl_to_mllw_m: float; datum_station: str
      views: list[View]                                # name, lon, lat, zooms
  def load_region(path: Path) -> Region
  ```
  `chartpack --version` prints `chartpack 0.1.0`. `chartpack.__version__ == "0.1.0"`. Console script `chartpack` dispatches to `cli.main(argv) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_region.py
def test_load_test_cell_region(regions_dir):
    r = load_region(regions_dir / "test-cell.toml")
    assert r.name == "test-cell"
    assert r.cells == {4: ["US4WA1HK"]}
    assert r.bbox == (-122.4, 47.7, -122.1, 48.0)
    assert r.navd88_to_mllw_m == 0.715 and r.msl_to_mllw_m == 2.02
    assert r.dem_maxzoom == 14 and r.coarse_fallback == "crm"
    assert r.charts_version == "0.1.0"

def test_missing_key_is_an_error(tmp_path):
    (tmp_path / "bad.toml").write_text('name = "x"\n')
    with pytest.raises(RegionError, match="charts_version"):
        load_region(tmp_path / "bad.toml")

# tests/test_cli.py
def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"chartpack {__version__}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chartpack && /usr/bin/python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q`
Expected: FAIL, `ModuleNotFoundError` or `ImportError` for `chartpack.region`

- [ ] **Step 3: Write `pyproject.toml`**: name `chartpack`, version `0.1.0`, `requires-python = ">=3.12"`, dependencies pinned with `==` to the versions pip resolves on the day (numpy, contourpy, shapely, scipy, Pillow, freetype-py), `[project.optional-dependencies] dev = [pytest, mapbox-vector-tile]`, `render = [playwright]`, `[project.scripts] chartpack = "chartpack.cli:main"`, setuptools `src` layout. `python3-gdal` comes from the system site-packages and is noted in README, not in pyproject.

- [ ] **Step 4: Write `region.py`** with `Region`, `View(name, lon, lat, zooms)`, `RegionError`, `load_region` using `tomllib`; every key required except `clip` (default none), `coarse_fallback` (default `"crm"`) and `views` (default empty). TOML layout:

```toml
name = "test-cell"
charts_version = "0.1.0"
bathy_version = "0.1.0"
bbox = [-122.4, 47.7, -122.1, 48.0]
[enc]
band4 = ["US4WA1HK"]
[bathy]
sources = ["cudem", "crm"]
dem_maxzoom = 14
[datum]
station = "9447130"
navd88_to_mllw_m = 0.715
msl_to_mllw_m = 2.02
[[render.views]]
name = "possession-bar"
lon = -122.37
lat = 47.90
zooms = [11, 13, 15]
```

- [ ] **Step 5: Write `cli.py`** with `main(argv=None) -> int`, `--version`, and subparsers for `fetch-enc`, `build-enc`, `fetch-bathy`, `build-bathy`, `check`, `manifest`, `archive`, `render`, `cells`, each calling a function that raises `NotImplementedError` until its task lands. `__init__.py` holds `__version__ = "0.1.0"`.

- [ ] **Step 6: Download and commit the fixture cells**, write `tests/fixtures/README.md` with cell, edition, update, issue date and download date, and `tests/conftest.py` with fixtures `fixtures_dir`, `regions_dir`, `work_dir` (tmp) and a `pytest.mark.online` skip unless `CHARTPACK_ONLINE=1`.

- [ ] **Step 7: Write `scripts/install-tippecanoe.sh`**: clone `https://github.com/felt/tippecanoe` at tag `2.79.0`, `make -j`, install `tippecanoe` and `tile-join` to `${PREFIX:-$HOME/.local}/bin`, print `tippecanoe --version`.

- [ ] **Step 8: Write `.github/workflows/chartpack-ci.yml`**: on push and pull_request; `ubuntu-24.04`; `apt-get install gdal-bin python3-gdal`; cache `~/.local/bin/tippecanoe` keyed on the tag; run `install-tippecanoe.sh` on cache miss; `python3 -m venv --system-site-packages .venv`, `pip install -e '.[dev]'`, `pytest -q`. Also add the chartpack job to the repo README's build section in one sentence.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd chartpack && .venv/bin/pytest -q`
Expected: `3 passed`

- [ ] **Step 10: Commit**

```bash
git add chartpack .github/workflows/chartpack-ci.yml .gitignore README.md
git commit -m "build(chartpack): scaffold package, region loader, fixture cells, CI"
```

---

### Task 2: ENC catalog and cell fetch

**Files:**
- Create: `chartpack/src/chartpack/cache.py`, `chartpack/src/chartpack/enc/__init__.py`, `chartpack/src/chartpack/enc/catalog.py`, `chartpack/src/chartpack/enc/fetch.py`
- Create fixture: `chartpack/tests/fixtures/ENCProdCat_excerpt.xml` (the `<cell>` elements for the 7 band-4 cells and US5SEAKL, cut from the live `https://charts.noaa.gov/ENCs/ENCProdCat.xml`, plus one `Cancelled` cell US5WA13M)
- Test: `chartpack/tests/test_cache.py`, `chartpack/tests/test_enc_catalog.py`, `chartpack/tests/test_enc_fetch.py`

**Interfaces:**
- Produces:
  ```python
  # cache.py
  def download(url: str, dest: Path, *, expected_size: int | None = None, timeout: float = 120) -> Path
      # writes dest.part then renames; raises DownloadError if the size mismatches or the stream ends early
  # enc/catalog.py
  @dataclass(frozen=True)
  class CellInfo: name: str; band: int; status: str; edtn: int; updn: int; isdt: date; zip_url: str; zip_size: int; polygon: list[tuple[float, float]]
  def parse_catalog(xml_bytes: bytes) -> dict[str, CellInfo]
  def cells_in_bbox(catalog: dict[str, CellInfo], bbox, band: int) -> list[str]   # Active only, polygon intersects bbox
  CATALOG_URL = "https://charts.noaa.gov/ENCs/ENCProdCat.xml"
  # enc/fetch.py
  def fetch_cells(names: list[str], catalog: dict[str, CellInfo], cache_dir: Path) -> list[Path]
      # downloads <cache_dir>/enc/<NAME>-<edtn>.<updn>.zip if absent; verifies layout; returns zip paths
  def check_zip_layout(zip_path: Path, name: str) -> tuple[int, int]   # (edtn, highest updn); raises CellError on missing .000 or a gap in .001..N
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
def test_partial_download_is_rejected(tmp_path, http_server_that_truncates):   # serve 1000 bytes with Content-Length 2000
    with pytest.raises(DownloadError):
        download(url, tmp_path / "f.bin", expected_size=2000)
    assert not (tmp_path / "f.bin").exists() and not (tmp_path / "f.bin.part").exists()

# tests/test_enc_catalog.py
def test_parse_excerpt(fixtures_dir):
    cat = parse_catalog((fixtures_dir / "ENCProdCat_excerpt.xml").read_bytes())
    c = cat["US4WA1HK"]
    assert (c.band, c.status) == (4, "Active")
    assert c.zip_url == "https://charts.noaa.gov/ENCs/US4WA1HK.zip"
    assert c.edtn >= 1 and c.updn >= 0 and len(c.polygon) >= 4
def test_cells_in_bbox_excludes_cancelled(fixtures_dir):
    cat = parse_catalog(...)
    assert "US5WA13M" not in cells_in_bbox(cat, (-122.9, 47.5, -122.1, 48.3), 5)
    assert "US5SEAKL" in cells_in_bbox(cat, (-122.4, 47.9, -122.3, 48.0), 5)

# tests/test_enc_fetch.py
def test_layout_of_fixture(fixtures_dir):
    assert check_zip_layout(fixtures_dir / "US5SEAKL.zip", "US5SEAKL") == (EDTN_FROM_README, 1)
def test_update_gap_is_an_error(tmp_path, fixtures_dir):
    # rebuild US5SEAKL.zip with .001 renamed to .003
    with pytest.raises(CellError, match="US5SEAKL.*002"):
        check_zip_layout(gapped_zip, "US5SEAKL")
def test_fetch_uses_cache(tmp_path, fixtures_dir, monkeypatch):   # monkeypatch download to copy the fixture; second call must not call download
@pytest.mark.online
def test_live_catalog_lists_test_cell():
    cat = parse_catalog(download(CATALOG_URL, tmp / "cat.xml").read_bytes())
    assert cat["US4WA1HK"].status == "Active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cache.py tests/test_enc_catalog.py tests/test_enc_fetch.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `cache.download`** with `urllib.request`, a browser `User-Agent` header (the one in `chartpack/README.md` under "Downloads"), streaming to `dest.part`, rename on success, delete `.part` on any failure.

- [ ] **Step 4: Implement `catalog.py`** with `xml.etree`; band is the second character of the name; `polygon` from the `cov` panel vertices; `isdt` parsed from the catalog's date string; `cells_in_bbox` uses shapely `Polygon.intersects(box)`.

- [ ] **Step 5: Implement `fetch.py`**: `check_zip_layout` lists `ENC_ROOT/<NAME>/<NAME>.NNN` entries, requires `.000`, requires `.001..N` contiguous, returns `(edtn, N)` with `edtn` read from the catalog by the caller (the zip layout check reads only names). `fetch_cells` names the cache file by catalog `edtn.updn` so a new update is a new file; old files are left in place.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cache.py tests/test_enc_catalog.py tests/test_enc_fetch.py -q`
Expected: all pass, the online test skipped

- [ ] **Step 7: Wire `chartpack fetch-enc REGION --cache DIR`** to download the catalog, resolve the region's cells, fetch them, print one line per cell `NAME edtn.updn isdt`. Add `chartpack cells REGION --band N` printing `cells_in_bbox` for the owner's region file.

- [ ] **Step 8: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): ENC catalog parsing and cached cell fetch with layout checks"
```

---

### Task 3: ENC reader and tile schema

**Files:**
- Create: `chartpack/src/chartpack/enc/schema.py`, `chartpack/src/chartpack/enc/reader.py`
- Create fixture: `chartpack/tests/fixtures/golden/US4WA1HK_layers.json` (counts per output layer, regenerated by `pytest --update-golden`)
- Test: `chartpack/tests/test_enc_reader.py`

**Interfaces:**
- Produces:
  ```python
  # schema.py
  SCHEMA_VERSION = 1
  @dataclass(frozen=True)
  class LayerSpec: name: str; classes: tuple[str, ...]; attributes: tuple[str, ...]; geometry: str  # "point"|"line"|"polygon"|"any"
  LAYERS: tuple[LayerSpec, ...]      # exactly the table in spec 6.3: depare, depcnt, soundg, coalne, lndare, hazard, navaid, light, area, line, meta
  SAFETY_LAYERS = ("depare", "depcnt", "hazard", "navaid", "light", "coalne", "lndare")
  # reader.py
  @dataclass
  class Feature: layer: str; geometry: dict; props: dict      # props always include "cell", "band", "class"; numbers kept as Decimal-safe strings for DRVAL1/DRVAL2/VALDCO/VALSOU/depth
  @dataclass
  class CellMeta: name: str; band: int; edtn: int; updn: int; isdt: str; covr: dict   # covr = union of M_COVR CATCOV=1 as GeoJSON polygon
  def read_cell(zip_path: Path, *, apply_updates: bool = True) -> tuple[CellMeta, list[Feature]]
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_layer_counts_match_golden(fixtures_dir, golden):
    meta, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    counts = Counter(f.layer for f in feats)
    assert counts == golden("US4WA1HK_layers.json")        # --update-golden rewrites

def test_depare_values_are_exact_strings(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    d = [f for f in feats if f.layer == "depare"]
    assert d and all(isinstance(f.props["DRVAL1"], str) for f in d)
    # cross-check against GDAL directly on the same cell: every (DRVAL1, DRVAL2) pair seen by ogr is present
    assert {(f.props["DRVAL1"], f.props["DRVAL2"]) for f in d} == ogr_depare_pairs(fixtures_dir / "US4WA1HK.zip")

def test_every_hazard_present_with_attributes(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    h = [f for f in feats if f.layer == "hazard"]
    assert Counter(f.props["class"] for f in h) == ogr_class_counts(fixtures_dir / "US4WA1HK.zip", ["UWTROC", "WRECKS", "OBSTRN"])
    assert all("WATLEV" in f.props or f.props["class"] == "OBSTRN" for f in h)   # UWTROC and WRECKS carry WATLEV
    rock_without_depth = next(f for f in h if f.props["class"] == "UWTROC" and "VALSOU" not in f.props)   # exists in this cell; else pick another fixture cell
    assert "VALSOU" not in rock_without_depth.props          # never 0, never None-as-string

def test_soundings_are_split_points_with_depth(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    s = [f for f in feats if f.layer == "soundg"]
    assert all(f.geometry["type"] == "Point" and "depth" in f.props for f in s)
    assert len(s) == ogr_sounding_point_count(fixtures_dir / "US4WA1HK.zip")

def test_lists_are_comma_joined(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    n = next(f for f in feats if f.layer == "navaid" and "," in f.props.get("COLOUR", ""))
    assert all(part.isdigit() for part in n.props["COLOUR"].split(","))

def test_update_changes_output(fixtures_dir):
    with_u = read_cell(fixtures_dir / "US5SEAKL.zip")
    without = read_cell(fixtures_dir / "US5SEAKL.zip", apply_updates=False)
    assert with_u[0].updn == 1 and without[0].updn == 0
    assert features_digest(with_u[1]) != features_digest(without[1])

def test_cell_meta_and_covr(fixtures_dir):
    meta, _ = read_cell(fixtures_dir / "US4WA1HK.zip")
    assert (meta.name, meta.band) == ("US4WA1HK", 4)
    assert shape(meta.covr).is_valid and shape(meta.covr).bounds == pytest.approx((-122.4, 47.7, -122.1, 48.0), abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_enc_reader.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Write `schema.py`** as the spec 6.3 table, with the exact class lists and attribute lists from the spec (DRGARE joins `depare`; SLCONS joins `coalne`; SEAARE in `area` keeps `OBJNAM` only).

- [ ] **Step 4: Implement `read_cell`**: extract the zip to a temp dir, `gdal.OpenEx(path_to_000, open_options=["SPLIT_MULTIPOINT=ON", "ADD_SOUNDG_DEPTH=ON", "LNAM_REFS=ON", "RECODE_BY_DSSI=ON", "LIST_AS_STRING=ON", f"UPDATES={'APPLY' if apply_updates else 'IGNORE'}"])`, read `DSID` for `EDTN`/`UPDN`/`ISDT`, iterate the layers named in `LAYERS`, keep only the listed attributes that are not null, format numeric depth attributes with `repr`-free decimal formatting (`format(v, ".15g")` on the GDAL value, which keeps `0.5` as `"0.5"` and `10` as `"10"`), geometry via `ExportToJson`. Band from the name's second character.

- [ ] **Step 5: Add the `golden` fixture and `--update-golden` option in `conftest.py`** (writes the JSON when the flag is given, otherwise compares).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_enc_reader.py -q --update-golden && .venv/bin/pytest tests/test_enc_reader.py -q`
Expected: all pass; the golden file is committed and reviewed in the PR

- [ ] **Step 7: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): S-57 reader mapped to the tile schema, with golden counts"
```

---

### Task 4: SCAMIN thinning and usage-band quilting

**Files:**
- Create: `chartpack/src/chartpack/enc/scamin.py`, `chartpack/src/chartpack/enc/quilt.py`
- Test: `chartpack/tests/test_enc_scamin.py`, `chartpack/tests/test_enc_quilt.py`

**Interfaces:**
- Consumes: `Feature`, `CellMeta` from Task 3.
- Produces:
  ```python
  # scamin.py
  BAND_ZOOMS = {2: (6, 10), 3: (6, 10), 4: (11, 12), 5: (13, 16)}
  def minzoom_for_scamin(scamin: int | None, band: int) -> int
      # scale denominator -> web mercator zoom at 48 N: zoom = round(log2(559082264 * cos(48deg) / scamin)); clamped to [BAND_ZOOMS[band][0], 16]; None -> BAND_ZOOMS[band][0]
  # quilt.py
  def quilt(cells: list[tuple[CellMeta, list[Feature]]]) -> list[Feature]
      # per zoom range R with primary band P: emit features of band P with minzoom/maxzoom = R;
      # features of band b < P clipped by the union of covr of bands in (b, P] present in R, emitted with R;
      # bands above P are not emitted in R. Props gain "tippecanoe": {"minzoom": lo, "maxzoom": hi}.
      # Thinned layers (soundg, area, line) use max(minzoom_for_scamin, lo) as minzoom.
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_enc_scamin.py
@pytest.mark.parametrize("scamin,band,expected", [(None, 4, 11), (179999, 4, 11), (44999, 4, 12), (11999, 5, 15), (5999, 5, 16), (1, 5, 16)])
def test_minzoom_for_scamin(scamin, band, expected): assert minzoom_for_scamin(scamin, band) == expected

# test_enc_quilt.py  (synthetic cells: unit squares, covr polygons, one feature each)
def test_primary_band_fills_its_range(): ...        # band 4 feature gets minzoom 11, maxzoom 12
def test_lower_band_clipped_where_higher_exists():   # band 4 covr covers left half of band 3 cell: at z6-10 band 3 keeps all; at z11-12 band 3 emitted only for right half
def test_lower_band_fills_in_where_higher_absent():  # at z13-16 with no band 5 anywhere, band 4 feature emitted with (13, 16)
def test_higher_band_not_drawn_below_its_range():    # band 5 feature never has minzoom < 13
def test_soundings_use_scamin(): ...                 # soundg with SCAMIN 44999 in band 4 -> minzoom 12
def test_quilt_on_real_cells(fixtures_dir):          # US4WA1HK + US5SEAKL: inside US5SEAKL covr, every band-4 depare emitted for (13,16) is clipped away (empty or outside)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_enc_scamin.py tests/test_enc_quilt.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `scamin.py`** with the formula above (559082264.028 is the scale denominator at zoom 0 for 256 px tiles at the equator).

- [ ] **Step 4: Implement `quilt.py`** with shapely: `unary_union` of the higher-band covr, `difference` per lower-band feature, drop empty results, split `GeometryCollection` results back into simple parts. Point features are kept only if inside the remaining area.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_enc_scamin.py tests/test_enc_quilt.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): SCAMIN zoom thinning and usage-band quilting"
```

---

### Task 5: ENC tiles (enc.mbtiles)

**Files:**
- Create: `chartpack/src/chartpack/mbtiles.py`, `chartpack/src/chartpack/enc/tiles.py`
- Create fixture: `chartpack/tests/fixtures/golden/US4WA1HK_tiles.json` (counts per layer per zoom)
- Test: `chartpack/tests/test_mbtiles.py`, `chartpack/tests/test_enc_tiles.py`

**Interfaces:**
- Consumes: `quilt`, `read_cell`, `LAYERS`, `SAFETY_LAYERS`.
- Produces:
  ```python
  # mbtiles.py
  class MBTiles:  # context manager over sqlite3
      @classmethod
      def create(cls, path: Path, *, fmt: str) -> "MBTiles"      # fmt "pbf" | "png"
      @classmethod
      def open(cls, path: Path) -> "MBTiles"
      def put_tile(self, z: int, x: int, y: int, data: bytes) -> None   # xyz in, stored TMS
      def get_tile(self, z: int, x: int, y: int) -> bytes | None
      def tiles_at(self, z: int) -> Iterator[tuple[int, int, bytes]]
      def metadata(self) -> dict[str, str]
      def set_metadata(self, items: dict[str, str]) -> None
  def decode_pbf(data: bytes) -> dict[str, list[dict]]     # gunzip if needed, mapbox_vector_tile.decode; test helper, lives in mbtiles.py so check.py can use it too
  # enc/tiles.py
  def build_enc_mbtiles(cells: list[tuple[CellMeta, list[Feature]]], out: Path, *, region: Region, work: Path) -> Path
      # writes one GeoJSONSeq per layer under work/, runs tippecanoe once per layer group (safety group with the no-drop flags, thinned group with -r1 too but honouring tippecanoe:minzoom), tile-join into out, then writes metadata
  ENC_METADATA_KEYS = ("cheekymarine:schema", "cheekymarine:pack", "cheekymarine:region", "cheekymarine:version", "cheekymarine:sources", "cheekymarine:built")
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_mbtiles.py
def test_roundtrip_and_tms_flip(tmp_path):
    with MBTiles.create(tmp_path / "t.mbtiles", fmt="pbf") as m:
        m.put_tile(3, 1, 2, b"abc")
    with MBTiles.open(tmp_path / "t.mbtiles") as m:
        assert m.get_tile(3, 1, 2) == b"abc"
        assert m.get_tile(3, 1, 5) is None
        row = m._conn.execute("select tile_row from tiles").fetchone()[0]
        assert row == (2**3 - 1) - 2

# test_enc_tiles.py   (module-scoped fixture builds the test-cell pack once)
def test_counts_match_golden(enc_pack, golden): ...   # per layer per zoom 11..16 == golden("US4WA1HK_tiles.json")
def test_every_hazard_in_every_zoom_of_its_band(enc_pack, fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    expected = Counter((f.props["class"], f.props.get("VALSOU"), f.props.get("WATLEV")) for f in feats if f.layer == "hazard")
    for z in range(11, 17):                                   # band 4 at 11-12 and fill-in at 13-16 (no band 5 in test-cell)
        got = Counter()
        for x, y, data in enc_pack.tiles_at(z):
            for feat in decode_pbf(data)["hazard"]: 
                p = feat["properties"]; got[(p["class"], p.get("VALSOU"), p.get("WATLEV"))] += 1
        assert set(got) == set(expected), z                   # nothing missing, nothing invented (a point can appear in tile buffers more than once, so compare keys)
def test_depare_values_byte_equal(enc_pack, fixtures_dir): ...  # set of (DRVAL1, DRVAL2) strings in z16 tiles == set from read_cell
def test_depare_plus_lndare_cover_cell(enc_pack, fixtures_dir):
    meta, _ = read_cell(...)
    union = unary_union([tile_polys...] at z16 for depare+lndare, converted from tile coords to lon/lat)
    covr = shape(meta.covr)
    assert covr.difference(union).area / covr.area < 1e-4
    assert overlap_area(depare polys) / covr.area < 1e-4
def test_polygon_crossing_tile_edge_is_in_both_tiles(enc_pack): ...  # pick a depare whose bbox spans two z16 tiles; assert present in both with the same DRVAL1
def test_metadata(enc_pack):
    md = enc_pack.metadata()
    assert md["format"] == "pbf" and md["cheekymarine:schema"] == "1" and md["cheekymarine:pack"] == "charts"
    assert json.loads(md["cheekymarine:sources"]) == [{"cell": "US4WA1HK", "edtn": E, "updn": U, "isdt": "..."}]
    assert {l["id"] for l in json.loads(md["json"])["vector_layers"]} == {l.name for l in LAYERS}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mbtiles.py tests/test_enc_tiles.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `mbtiles.py`** (schema: `metadata(name text, value text)`, `tiles(zoom_level, tile_column, tile_row, tile_data)`, unique index; `put_tile` flips `y` to `2**z - 1 - y`).

- [ ] **Step 4: Implement `enc/tiles.py`**: safety layers run as `tippecanoe -o safety.mbtiles -Z6 -z16 -r1 --no-feature-limit --no-tile-size-limit --no-tiny-polygon-reduction --no-simplification-of-shared-nodes --detect-shared-borders --extend-zooms-if-still-dropping -L name:file ...`; thinned layers the same minus `--detect-shared-borders`, both honouring per-feature `tippecanoe` minzoom/maxzoom; `tile-join -o out.mbtiles -pk -pC safety.mbtiles thinned.mbtiles`; then `set_metadata` with the `cheekymarine:*` keys, `name`, `bounds` from the region bbox, `minzoom 6`, `maxzoom 16`. Fail loudly (non-zero exit, stderr shown) if tippecanoe is missing.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mbtiles.py tests/test_enc_tiles.py -q --update-golden && .venv/bin/pytest tests/test_mbtiles.py tests/test_enc_tiles.py -q`
Expected: all pass (the build takes under a minute on the test cell)

- [ ] **Step 6: Wire `chartpack build-enc REGION OUT --cache DIR --work DIR`** to read the cached cells, quilt, build `OUT/enc.mbtiles`. Add the Review Focus 3 case (polygon across a tile edge) to the golden regeneration note in `tests/fixtures/README.md`.

- [ ] **Step 7: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): build enc.mbtiles with no-drop safety layers and metadata"
```

---

### Task 6: Palette and navigation style

**Files:**
- Create: `chartpack/src/chartpack/style/__init__.py`, `chartpack/src/chartpack/style/palette.py`, `chartpack/src/chartpack/style/nav.py`, `chartpack/src/chartpack/style/validate.py`
- Test: `chartpack/tests/test_style_palette.py`, `chartpack/tests/test_style_nav.py`

**Interfaces:**
- Consumes: `LAYERS` (Task 3), `MBTiles.metadata` (Task 5).
- Produces:
  ```python
  # palette.py
  TOKENS = ("DEPDW", "DEPMD", "DEPMS", "DEPVS", "DEPIT", "LANDA", "LANDF", "CSTLN", "CHBLK", "CHGRD", "CHMGD", "CHWHT", "SNDG1", "SNDG2", "LITRD", "LITGN", "LITYW", "NINFO", "OUTLW", "DNGHL", "ADINF", "RESBL", "TRFCD", "NODTA")
  PALETTES: dict[str, dict[str, str]]     # "day" | "dusk" | "night" -> token -> "#rrggbb"; every palette has every token
  # nav.py
  @dataclass(frozen=True)
  class Depths: shallow_m: float = 1.8288; safety_m: float = 3.048; deep_m: float = 9.144
  DEPTH_LAYERS = ("depare-deep", "depare-medium", "depare-shallow", "depare-vshallow", "depcnt-safety", "soundg-shallow", "soundg-deep", "hazard-danger")
  def nav_style(palette: str, depths: Depths = Depths(), *, units: str = "ft") -> dict      # a complete MapLibre style v8 dict
  def depth_filter(layer: str, depths: Depths) -> list                                      # the filter expression for each DEPTH_LAYERS name
  # validate.py
  def check_style_against_schema(style: dict, layers: tuple[LayerSpec, ...]) -> list[str]  # errors: unknown source-layer, unknown attribute in filter/expression
  def check_style_sprites_glyphs(style: dict, sprite_json: dict, glyph_fonts: set[str]) -> list[str]
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_style_palette.py
def test_every_palette_has_every_token():
    for name, p in PALETTES.items(): assert set(p) == set(TOKENS), name
def test_night_water_is_dark(): assert luminance(PALETTES["night"]["DEPDW"]) < 0.1 and luminance(PALETTES["day"]["DEPDW"]) > 0.9

# test_style_nav.py
def test_style_is_v8_with_contract_sources():
    s = nav_style("day")
    assert s["version"] == 8 and s["sources"]["enc"] == {"type": "vector", "url": "mbtiles://enc"}
    assert s["sprite"] == "pack://sprites/nav" and s["glyphs"] == "pack://glyphs/{fontstack}/{range}.pbf"
def test_depth_layers_exist_and_only_they_carry_thresholds():
    s = nav_style("day"); ids = {l["id"] for l in s["layers"]}
    assert set(DEPTH_LAYERS) <= ids
    assert s["metadata"]["cheekymarine"]["depths"] == {"shallow_m": 1.8288, "safety_m": 3.048, "deep_m": 9.144, "layers": list(DEPTH_LAYERS)}
    for l in s["layers"]:
        if l["id"] not in DEPTH_LAYERS: assert "3.048" not in json.dumps(l) and "9.144" not in json.dumps(l)
def test_depth_filters():
    d = Depths()
    assert depth_filter("depare-deep", d) == [">=", ["to-number", ["get", "DRVAL1"]], 9.144]
    assert depth_filter("depare-vshallow", d) == ["<", ["to-number", ["get", "DRVAL1"]], 1.8288]
    assert depth_filter("hazard-danger", d) == ["any", ["!", ["has", "VALSOU"]], ["<", ["to-number", ["get", "VALSOU"]], 3.048], ["in", ["get", "WATLEV"], ["literal", ["1", "2", "4", "5"]]]]
def test_feet_labels():
    s = nav_style("day"); soundg = next(l for l in s["layers"] if l["id"] == "soundg-deep")
    assert soundg["layout"]["text-field"] == ["to-string", ["round", ["*", ["to-number", ["get", "depth"]], 3.28084]]]
def test_style_references_only_schema(): assert check_style_against_schema(nav_style("day"), LAYERS) == []
def test_three_palettes_same_layers(): assert [l["id"] for l in nav_style("day")["layers"]] == [l["id"] for l in nav_style("night")["layers"]]
def test_hazards_above_everything(): ids = [l["id"] for l in nav_style("day")["layers"]]; assert ids[-2:] == ["hazard", "hazard-danger"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_style_palette.py tests/test_style_nav.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Write `palette.py`** with these starting day values (owner decision B: our own, tuned later on the renders): DEPDW `#FFFFFF`, DEPMD `#DCEEF9`, DEPMS `#B8DCF2`, DEPVS `#8EC3E6`, DEPIT `#A8D5A2`, LANDA `#F1E7C8`, LANDF `#D9CA90`, CSTLN `#5E5E50`, CHBLK `#000000`, CHGRD `#6B7A82`, CHMGD `#C800C8`, CHWHT `#FFFFFF`, SNDG1 `#000000`, SNDG2 `#7A8690`, LITRD `#E2231A`, LITGN `#1A9E3F`, LITYW `#E9C400`, NINFO `#E26D00`, OUTLW `#000000`, DNGHL `#E2231A`, ADINF `#8E6A00`, RESBL `#2D5BA8`, TRFCD `#C800C8`, NODTA `#C8C8C8`. Dusk: each day colour mixed 45 percent toward black. Night: DEPDW `#000000`, DEPMD `#0A1F33`, DEPMS `#123A5A`, DEPVS `#1B5280`, DEPIT `#1E3A1E`, LANDA `#2A2616`, LANDF `#3A3420`, CSTLN `#8A8A7A`, CHBLK `#C0C0C0`, CHGRD `#7A8690`, CHMGD `#A000A0`, CHWHT `#C0C0C0`, SNDG1 `#C0C0C0`, SNDG2 `#7A8690`, LITRD `#B01C14`, LITGN `#157F32`, LITYW `#B89A00`, NINFO `#B05500`, OUTLW `#C0C0C0`, DNGHL `#B01C14`, ADINF `#705400`, RESBL `#24488A`, TRFCD `#A000A0`, NODTA `#404040`. Each entry carries a comment naming what the token paints.

- [ ] **Step 4: Implement `nav.py`**: layer order bottom to top: `background` (DEPDW), `depare-deep`, `depare-medium`, `depare-shallow`, `depare-vshallow`, `depare-intertidal` (DRVAL1 < 0, DEPIT), `lndare` (LANDA), `coalne` (CSTLN), `area-*` fills at low opacity (ACHARE ADINF, RESARE RESBL, TSSLPT TRFCD), `line-*` (cables and pipelines dashed CHMGD), `depcnt` (CHGRD, 0.8 px), `depcnt-safety` (CHBLK, 2 px, filter `VALDCO == safety_m` or the next deeper available contour value computed at build time from the cell's set of VALDCO; store the chosen value in `metadata.cheekymarine.safety_contour_m`), `soundg-deep` (SNDG2) and `soundg-shallow` (SNDG1) text layers using `"text-font": ["Noto Sans Regular"]`, `navaid` symbols (`icon-image` by `class`+`BOYSHP`/`BCNSHP`, `icon-color` from the first `COLOUR` code through `match`: 1 CHWHT, 2 CHBLK, 3 LITRD, 4 LITGN, 6 LITYW, default CHGRD), `light` (flare icon, `icon-color` by COLOUR), `area-names` (SEAARE OBJNAM, Noto Sans Bold), `hazard` (plain icons by class), `hazard-danger` (isolated-danger icon). `units="m"` swaps the feet expression for `["get", "depth"]`.

- [ ] **Step 5: Implement `validate.py`** by walking every layer's `source-layer`, `filter`, `layout`, `paint` for `["get", X]` / `["has", X]` and checking `X` against the layer's attributes plus `class`, `cell`, `band`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_style_palette.py tests/test_style_nav.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): palette and generated navigation style with named depth layers"
```

---

### Task 7: Symbols, SDF sprites and glyphs

**Files:**
- Create: `chartpack/symbols/*.svg` (buoy-can, buoy-nun, buoy-spherical, buoy-pillar, buoy-spar, beacon-lateral, beacon-cardinal, beacon-generic, light-flare, rock-awash, rock-submerged, wreck-dangerous, wreck-nondangerous, obstruction, isolated-danger, anchorage, marina; each 24 by 24 units, black shapes on transparent, drawn after US Chart No. 1), `chartpack/fonts/NotoSans-Regular.ttf`, `chartpack/fonts/NotoSans-Bold.ttf`, `chartpack/fonts/OFL.txt`
- Create: `chartpack/src/chartpack/style/sdf.py`, `chartpack/src/chartpack/style/sprites.py`, `chartpack/src/chartpack/style/glyphs.py`
- Test: `chartpack/tests/test_style_sdf.py`, `chartpack/tests/test_style_sprites.py`, `chartpack/tests/test_style_glyphs.py`

**Interfaces:**
- Produces:
  ```python
  # sdf.py
  def bitmap_to_sdf(alpha: np.ndarray, *, buffer: int = 3, radius: float = 8.0, cutoff: float = 0.25) -> np.ndarray   # uint8, shape (h+2b, w+2b); the MapLibre/fontnik convention
  # sprites.py
  def rasterize_svg(path: Path, size: int) -> np.ndarray     # alpha mask uint8 (h, w); implemented by parsing the SVG's simple shapes (circle, rect, polygon, path with M/L/Z/A) with Pillow's ImageDraw: no SVG library
  def build_sprites(symbols_dir: Path, out_dir: Path, name: str) -> dict   # writes <name>.png, <name>.json, <name>@2x.png, <name>@2x.json; entries {"width","height","x","y","pixelRatio","sdf": true}
  # glyphs.py
  def build_glyphs(font_path: Path, fontstack: str, out_dir: Path, ranges: tuple[tuple[int, int], ...] = ((0, 255), (256, 511))) -> list[Path]
      # out_dir/<fontstack>/<start>-<end>.pbf per range, protobuf hand-encoded per the MapLibre glyphs.proto (glyphs{stacks{name, range, glyphs{id, bitmap, width, height, left, top, advance}}}), 24 px, buffer 3
  def parse_glyph_pbf(data: bytes) -> dict   # test helper decoder
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_style_sdf.py
def test_sdf_of_filled_square():
    a = np.zeros((20, 20), np.uint8); a[5:15, 5:15] = 255
    s = bitmap_to_sdf(a)
    assert s.shape == (26, 26) and s[13, 13] > 200 and s[0, 0] < 30 and 100 < s[8, 13] < 200   # inside high, far outside low, edge mid

# test_style_sprites.py
def test_all_symbols_rasterize_nonblank(symbols_dir):
    for svg in sorted(symbols_dir.glob("*.svg")): assert rasterize_svg(svg, 24).max() == 255, svg.name
def test_sprite_sheet(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert set(idx) == {p.stem for p in symbols_dir.glob("*.svg")}
    assert all(e["sdf"] is True and e["pixelRatio"] == 1 for e in idx.values())
    assert Image.open(tmp_path / "nav@2x.png").size == tuple(2 * v for v in Image.open(tmp_path / "nav.png").size)
def test_nav_style_icons_exist(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert check_style_sprites_glyphs(nav_style("day"), idx, {"Noto Sans Regular", "Noto Sans Bold"}) == []

# test_style_glyphs.py
def test_glyph_range_roundtrip(tmp_path, fonts_dir):
    paths = build_glyphs(fonts_dir / "NotoSans-Regular.ttf", "Noto Sans Regular", tmp_path)
    assert [p.name for p in paths] == ["0-255.pbf", "256-511.pbf"] and paths[0].parent.name == "Noto Sans Regular"
    g = parse_glyph_pbf(paths[0].read_bytes())
    assert g["name"] == "Noto Sans Regular" and g["range"] == "0-255"
    seven = g["glyphs"][ord("7")]
    assert seven["advance"] > 0 and len(seven["bitmap"]) == (seven["width"] + 6) * (seven["height"] + 6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_style_sdf.py tests/test_style_sprites.py tests/test_style_glyphs.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Draw the SVGs** using only `circle`, `rect`, `polygon`, `line` and `path` with M, L, A, Z commands so the in-house rasterizer can draw them. Reference US Chart No. 1 (public domain) for shapes; keep them bold at 24 px.

- [ ] **Step 4: Implement `sdf.py`** with `scipy.ndimage.distance_transform_edt` on the inside and outside masks; value = `255 * clamp((radius - signed_distance) / radius + cutoff... )` following the fontnik mapping: `sdf = 255 - 255 * clamp((d / radius) + cutoff, 0, 1)` where `d` is positive outside.

- [ ] **Step 5: Implement `sprites.py`** (pack symbols in a row, 2 px gutter; `@2x` rasterized at 48 px) and **`glyphs.py`** with `freetype-py` at 24 px, rendering each glyph in the range to an alpha bitmap, SDF per Step 4, protobuf written with a tiny varint/length-delimited encoder (field numbers from the proto: glyphs=1 (stacks: name=1, range=2, glyphs=3), glyph: id=1, bitmap=2, width=3, height=4, left=5, top=6, advance=7).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_style_sdf.py tests/test_style_sprites.py tests/test_style_glyphs.py -q`
Expected: all pass

- [ ] **Step 7: Add OFL.txt and the two Noto Sans files** (from the Google Fonts repository, OFL 1.1), note them in `NOTICE`.

- [ ] **Step 8: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): Chart No. 1 derived SDF sprites and Noto Sans glyph ranges"
```

---

### Task 8: Pack assembly for charts and the render tool

**Files:**
- Create: `chartpack/src/chartpack/pack/__init__.py`, `chartpack/src/chartpack/pack/assemble.py`, `chartpack/src/chartpack/render/__init__.py`, `chartpack/src/chartpack/render/server.py`, `chartpack/src/chartpack/render/render.py`, `chartpack/src/chartpack/render/page.html`
- Test: `chartpack/tests/test_pack_assemble.py`, `chartpack/tests/test_render_server.py`, `chartpack/tests/test_render.py` (marked `render`, skipped unless Playwright and Chromium are installed)

**Interfaces:**
- Consumes: `build_enc_mbtiles`, `nav_style`, `build_sprites`, `build_glyphs`, `MBTiles`.
- Produces:
  ```python
  # pack/assemble.py
  def assemble_charts_pack(region: Region, enc_mbtiles: Path, out_dir: Path) -> Path
      # out_dir/<charts-pack-root>/{enc.mbtiles, styles/nav-day.json, nav-dusk.json, nav-night.json, sprites/nav*.{png,json}, glyphs/<font>/<range>.pbf, README.md, NOTICE}
  # render/server.py
  class PackServer:   # threading HTTP server on 127.0.0.1:<free port>
      def __init__(self, pack_dirs: list[Path]) ...
      def style_url(self, style_name: str) -> str   # serves the style with sources rewritten to http://127.0.0.1:PORT/tiles/<source>/{z}/{x}/{y}.<ext>, sprite and glyphs to local URLs
      def start(self) -> None; def stop(self) -> None
  # render/render.py
  def render_views(pack_dirs: list[Path], views: list[View], styles: list[str], out_dir: Path, *, size=(1024, 600)) -> list[Path]
      # one PNG per (view, zoom, style): out_dir/<view>-z<zoom>-<style>.png, via Playwright Chromium loading page.html?style=<url>&lon&lat&zoom
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_pack_assemble.py
def test_charts_pack_layout(test_region, enc_pack_path, tmp_path):
    root = assemble_charts_pack(test_region, enc_pack_path, tmp_path)
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert "enc.mbtiles" in names and "styles/nav-night.json" in names and "sprites/nav@2x.json" in names
    assert "glyphs/Noto Sans Regular/0-255.pbf" in names and "glyphs/Noto Sans Bold/256-511.pbf" in names
    assert "README.md" in names and "NOTICE" in names
def test_shipped_style_matches_sprite_and_glyphs(charts_pack_root): ...   # check_style_sprites_glyphs on every styles/*.json == []

# test_render_server.py
def test_server_serves_tile_and_rewritten_style(charts_pack_root):
    s = PackServer([charts_pack_root]); s.start()
    try:
        style = json.loads(urlopen(s.style_url("nav-day")).read())
        assert style["sources"]["enc"]["tiles"][0].startswith("http://127.0.0.1:") and "url" not in style["sources"]["enc"]
        assert style["sprite"].startswith("http://127.0.0.1:") and style["glyphs"].endswith("/glyphs/{fontstack}/{range}.pbf")
        z, x, y = a_tile_that_exists(charts_pack_root / "enc.mbtiles", 13)
        r = urlopen(f"{base}/tiles/enc/{z}/{x}/{y}.pbf"); assert r.status == 200 and r.headers["Content-Encoding"] == "gzip"
    finally: s.stop()

# test_render.py
@pytest.mark.render
def test_render_produces_nonblank_png(charts_pack_root, test_region, tmp_path):
    out = render_views([charts_pack_root], test_region.views, ["nav-day"], tmp_path)
    img = np.asarray(Image.open(out[0]).convert("L"))
    assert img.std() > 10          # not a flat colour
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pack_assemble.py tests/test_render_server.py tests/test_render.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `assemble.py`**: write the three nav styles via `nav_style`, sprites via `build_sprites(symbols_dir, root/"sprites", "nav")`, glyphs for both fonts, copy `enc.mbtiles`, write the pack `README.md` (the pack contract section verbatim from `chartpack/README.md`) and `NOTICE`.

- [ ] **Step 4: Implement `server.py`** with `http.server.ThreadingHTTPServer`; routes `/styles/<name>.json`, `/tiles/<source>/{z}/{x}/{y}.(pbf|png)` (pbf served with `Content-Encoding: gzip` since tippecanoe gzips), `/sprites/...`, `/glyphs/...`, `/page.html`, `/vendor/maplibre-gl.js|css` (vendored copies of a pinned maplibre-gl-js release at least two weeks old, BSD-3, under `chartpack/src/chartpack/render/vendor/`, licence file alongside).

- [ ] **Step 5: Write `page.html`** (full-window map, reads `style`, `lon`, `lat`, `zoom` from the query string, sets `window.__rendered = true` on the map's `idle` event) and **`render.py`** (Playwright sync API, viewport 1024 by 600, `wait_for_function("window.__rendered")`, screenshot). `chartpack render PACKDIR... --views REGION --styles nav-day,nav-night --out DIR`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pip install -e '.[dev,render]' && .venv/bin/playwright install chromium && .venv/bin/pytest tests/test_pack_assemble.py tests/test_render_server.py tests/test_render.py -q`
Expected: all pass (the render test runs locally; CI marks `render` as skipped)

- [ ] **Step 7: Render the test cell** at the region's views for all three nav palettes, look at them, adjust palette values and line weights once if something is unreadable, commit the PNGs under `docs/chartpack/renders/test-cell/`.

- [ ] **Step 8: Commit**

```bash
git add chartpack docs/chartpack/renders/test-cell
git commit -m "feat(chartpack): charts pack assembly and headless render tool"
```

---

### Task 9: Bathymetry fetch: CUDEM windows and CRM subset

**Files:**
- Create: `chartpack/src/chartpack/bathy/__init__.py`, `chartpack/src/chartpack/bathy/cudem.py`, `chartpack/src/chartpack/bathy/crm.py`
- Create fixtures: `chartpack/tests/fixtures/cudem_urllist_excerpt.txt` (the 78 Washington lines of `urllist8483.txt`), `chartpack/tests/fixtures/cudem_possession_bar.tif` (300 by 300 window of `ncei19_n48x00_w122x50_2023v1.tif` around -122.38, 47.90, cut once with `gdal_translate -projwin`, DEFLATE, under 500 KB)
- Test: `chartpack/tests/test_bathy_cudem.py`, `chartpack/tests/test_bathy_crm.py`

**Interfaces:**
- Produces:
  ```python
  # bathy/cudem.py
  URLLIST = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_2014_8483/urllist8483.txt"
  @dataclass(frozen=True)
  class CudemTile: name: str; url: str; north: float; west: float; year: int; version: int
      @property
      def bounds(self) -> tuple[float, float, float, float]     # W, S, E, N = (west, north-0.25, west+0.25, north)
  def parse_urllist(text: str) -> list[CudemTile]
  def tiles_for_bbox(tiles: list[CudemTile], bbox) -> list[CudemTile]
  @dataclass
  class Grid: data: np.ndarray; nodata: float; transform: tuple[float, ...]; crs: str   # row 0 = north, float32
  def read_window(src: str, bbox) -> Grid       # src = local path or /vsicurl/ URL; gdal.Translate to an in-memory dataset with projWin, returns the array
  # bathy/crm.py
  def crm_wcs_url(bbox) -> str                  # the THREDDS WCS GetCoverage URL for z, GeoTIFF_Float, OGC:CRS84
  def fetch_crm(bbox, cache_dir: Path) -> Path  # cache_dir/crm/crm_<W>_<S>_<E>_<N>.tif, validated by opening with GDAL after download
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_bathy_cudem.py
def test_parse_and_bounds(fixtures_dir):
    tiles = parse_urllist((fixtures_dir / "cudem_urllist_excerpt.txt").read_text())
    t = next(t for t in tiles if t.name == "ncei19_n47x75_w122x50_2023v1")
    assert t.bounds == (-122.5, 47.5, -122.25, 47.75) and (t.year, t.version) == (2023, 1)
def test_tiles_for_puget_north(fixtures_dir):
    names = {t.name for t in tiles_for_bbox(parse_urllist(...), (-122.9, 47.5, -122.1, 48.3))}
    assert {"ncei19_n48x00_w122x50_2023v1", "ncei19_n47x75_w122x50_2023v1", "ncei19_n48x25_w122x25_2024v1", "ncei19_n48x50_w122x75_2024v1"} <= names
    assert "ncei19_n46x25_w124x25_2024v1" not in names
def test_read_window_fixture(fixtures_dir):
    g = read_window(str(fixtures_dir / "cudem_possession_bar.tif"), (-122.39, 47.89, -122.37, 47.91))
    assert g.data.dtype == np.float32 and g.nodata == -9999.0
    water = g.data[g.data != g.nodata]; assert water.min() < -5 and water.max() > -200   # Possession Bar: real depths, NAVD88 metres, negative down
@pytest.mark.online
def test_vsicurl_window_is_small(): ...   # read a 100x100 window over Possession Bar via /vsicurl/, assert it returns in < 60 s and values match the fixture at one point

# test_bathy_crm.py
def test_wcs_url():
    assert crm_wcs_url((-122.9, 47.5, -122.1, 48.3)) == "https://www.ngdc.noaa.gov/thredds/wcs/crm/cudem/crm_vol8_2025.nc?service=WCS&version=1.0.0&request=GetCoverage&coverage=z&crs=OGC:CRS84&bbox=-122.9,47.5,-122.1,48.3&format=GeoTIFF_Float"
def test_truncated_tif_is_rejected(tmp_path, monkeypatch): ...   # monkeypatch download to write 100 bytes; fetch_crm raises DownloadError and leaves no file
@pytest.mark.online
def test_fetch_small_crm_box(tmp_path): ...   # 0.05 deg box, opens with GDAL, 1 band float32
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bathy_cudem.py tests/test_bathy_crm.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `cudem.py`** (regex `ncei19_n(\d+)x(\d+)_w(\d+)x(\d+)_(\d{4})v(\d)`; `read_window` sets `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` and `GDAL_HTTP_USERAGENT` for `/vsicurl/`) and **`crm.py`** (download then `gdal.Open` must succeed and report one float32 band, else delete and raise).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bathy_cudem.py tests/test_bathy_crm.py -q`
Expected: all pass, online tests skipped

- [ ] **Step 5: Wire `chartpack fetch-bathy REGION --cache DIR`**: download `urllist8483.txt` into the cache, pick the region's tiles, fetch CRM for the region bbox, print the tile names and the CRM file.

- [ ] **Step 6: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): CUDEM tile selection and window reads, CRM WCS subset"
```

---

### Task 10: Merge to an MLLW grid, coverage and clip

**Files:**
- Create: `chartpack/src/chartpack/bathy/merge.py`, `chartpack/scripts/make-clip.py`, `chartpack/regions/clip/canada-wa.geojson`
- Create fixture: `chartpack/tests/fixtures/ridge.npy` (synthetic 200 by 200 float32 elevation grid: a north-south ridge rising from -120 m to -20 m with land (+5 m) along the east edge and a 10 by 10 NoData hole at (50, 50))
- Test: `chartpack/tests/test_bathy_merge.py`

**Interfaces:**
- Consumes: `Grid`, `read_window`, `CudemTile`, `Region`.
- Produces:
  ```python
  # bathy/merge.py
  def to_mllw_depth(elev: np.ndarray, nodata: float, offset_m: float) -> np.ndarray   # depth = -elev - offset; nodata -> nan
  def merge_to_mllw(primary: list[tuple[Grid, str]], fallback: Grid, fallback_offset_m: float, primary_offset_m: float, bbox, *, res_deg: float = 1/3600/3) -> tuple[Grid, np.ndarray]
      # returns (depth grid in metres below MLLW on a regular lon/lat grid at res_deg, source index array: 0 none, 1 primary, 2 fallback)
  def fill_land(depth: np.ndarray, land_depth_m: float = -0.3) -> np.ndarray        # cells with depth < land_depth (i.e. above water) set to land_depth so contours close at the shore
  def coverage_polygons(source: np.ndarray, transform, labels: dict[int, dict]) -> list[dict]   # GeoJSON features {"source": "cudem"|"crm", "resolution_m", "date"}; polygonized at 1/120 deg
  def clip_mask(transform, shape, clip_geojson: dict) -> np.ndarray                   # True where the cell must be removed (inside the Canadian polygon)
  def tag_source(features: list[dict], source: np.ndarray, transform, names: dict[int, str]) -> list[dict]
      # sets props["source"] from the source index sampled at the feature's representative point ("cudem" | "crm"); features over index 0 are dropped
  def uncovered_area(source: np.ndarray, transform, *, treat_fallback_as_uncovered: bool) -> shapely.Geometry
      # polygon of index 0 cells, plus index 2 cells when treat_fallback_as_uncovered (region.coarse_fallback == "enc")
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_to_mllw_depth_navd88():
    assert to_mllw_depth(np.array([-10.0], np.float32), -9999.0, 0.715)[0] == pytest.approx(9.285, abs=1e-4)
    assert np.isnan(to_mllw_depth(np.array([-9999.0], np.float32), -9999.0, 0.715)[0])
def test_nodata_hole_filled_from_fallback(ridge_grid, flat_fallback):   # fallback is -50 m everywhere
    depth, src = merge_to_mllw([(ridge_grid, "cudem")], flat_fallback, 2.02, 0.715, bbox)
    assert not np.isnan(depth[hole]).any() and (src[hole] == 2).all() and (src[~hole & water] == 1).all()
    assert abs(depth[hole].mean() - (50 - 2.02)) < 0.01
def test_fill_land_closes_lines(ridge_grid): ...   # after fill_land, no cell is below -0.3 (above water) and the east edge equals -0.3
def test_coverage_polygons(ridge_grid, flat_fallback):
    feats = coverage_polygons(src, transform, {1: {"source": "cudem", "resolution_m": 3, "date": "2023"}, 2: {"source": "crm", "resolution_m": 30, "date": "2025"}})
    assert {f["properties"]["source"] for f in feats} == {"cudem", "crm"}
def test_tag_source_and_uncovered(ridge_grid, flat_fallback):
    depth, src = merge_to_mllw(...); feats = [line_over(hole), line_over(ridge_water)]
    tagged = tag_source(feats, src, transform, {1: "cudem", 2: "crm"})
    assert [f["properties"]["source"] for f in tagged] == ["crm", "cudem"]
    assert uncovered_area(src, transform, treat_fallback_as_uncovered=False).is_empty
    assert uncovered_area(src, transform, treat_fallback_as_uncovered=True).contains(point_in(hole))
def test_clip_removes_canadian_side(regions_dir):
    clip = json.loads((regions_dir / "clip/canada-wa.geojson").read_text())
    m = clip_mask(transform_for((-123.5, 48.0, -122.5, 48.9)), (90, 100), clip)
    assert m[cell_at(48.75, -123.3)] and not m[cell_at(47.9, -122.4)]     # Canadian Gulf Islands side removed, Possession Bar kept
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bathy_merge.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Write `scripts/make-clip.py`**: download `https://maritimeboundaries.noaa.gov/downloads/USMaritimeLimitsAndBoundariesSHP.zip`, take the polylines with `NOTE` containing "US/Canada" within lon -125.5 to -122 and lat 48 to 49.1 (B0098 and its neighbours), join them into one line, close it northward along 49.5 N into a polygon that is the Canadian side, write `regions/clip/canada-wa.geojson`. Run it once, commit the output.

- [ ] **Step 4: Implement `merge.py`**: `gdal.Warp` each primary window and the fallback onto the target grid (`outputBounds=bbox`, `xRes=yRes=res_deg`, `resampleAlg` bilinear for CRM, nearest for CUDEM), convert each to MLLW depth, take the primary where finite else the fallback; `coverage_polygons` with `gdal.Polygonize` on a coarsened source array.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bathy_merge.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): merge CUDEM over CRM into an MLLW depth grid with coverage and clip"
```

---

### Task 11: Contours and depth bands (wa-creel rules)

**Files:**
- Create: `chartpack/src/chartpack/bathy/contours.py`, `chartpack/src/chartpack/bathy/bands.py`
- Test: `chartpack/tests/test_bathy_contours.py`, `chartpack/tests/test_bathy_bands.py`

**Interfaces:**
- Consumes: depth grid (metres below MLLW, nan = removed) and its transform from Task 10.
- Produces:
  ```python
  # bathy/contours.py
  M_TO_FT = 3.28084
  DEPTHS_FT = list(range(10, 301, 10)) + [400, 500, 600]
  FINE_FT = list(range(5, 61, 10))                       # 5, 15, 25, ... 55: the 5 ft steps between the 10 ft lines
  MAJOR_FT = frozenset({60, 120, 180, 300, 600})
  BASE_FT = frozenset({30, 60, 90, 120, 150, 180, 240, 300, 400, 600})
  def min_zoom(depth_ft: int) -> int                       # majors 10, base 12, %20==0 or 500 -> 13, %10==0 -> 14, else 15
  def chaikin_line(points, passes=1) -> list[tuple[float, float]]
  def simplify(points, tol_deg) -> list[tuple[float, float]]     # Douglas-Peucker via shapely
  def build_contours(depth_m: np.ndarray, transform, *, levels_ft: list[int], smooth_passes=1, simplify_deg=0.0002, min_points=6) -> list[dict]
      # GeoJSON LineString features with props depth_ft, major, minzoom; land already filled; nan cells treated as outside
  def contours_by_zoom(depth_m, transform, *, fine: bool) -> list[dict]
      # runs build_contours on grids downsampled per zoom band: z10-11 from 150 m, z12-13 from 30 m, z14-16 from the native grid; each feature gets tippecanoe minzoom/maxzoom for its band and keeps minzoom = max(min_zoom(depth), band low)
  # bathy/bands.py
  def build_bands(depth_m, transform, *, levels_ft: list[int], simplify_deg=0.0002) -> list[dict]
      # GeoJSON Polygon features with depth_min_ft, depth_max_ft (None above the last level), minzoom = min_zoom(depth_max_ft or 600)
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_bathy_contours.py
@pytest.mark.parametrize("d,z", [(60, 10), (30, 12), (40, 13), (500, 13), (70, 14), (25, 15)])
def test_min_zoom(d, z): assert min_zoom(d) == z
def test_chaikin_keeps_endpoints(): pts = [(0, 0), (1, 1), (2, 0)]; out = chaikin_line(pts); assert out[0] == (0, 0) and out[-1] == (2, 0) and len(out) == 4
def test_ridge_contours_at_expected_depths(ridge_depth):            # ridge from 120 m to 20 m: every 10 ft line between 66 and 390 ft present
    feats = build_contours(ridge_depth, transform, levels_ft=DEPTHS_FT)
    depths = {f["properties"]["depth_ft"] for f in feats}
    assert {70, 100, 200, 300} <= depths and 10 not in depths and 600 not in depths
    assert all(len(f["geometry"]["coordinates"]) >= 6 for f in feats)
def test_lines_close_at_shore(ridge_depth_with_land): ...            # after fill_land, the 10 ft line touches the land edge: its endpoints are on the grid boundary or it is a ring
def test_deterministic(ridge_depth): assert json.dumps(build_contours(...)) == json.dumps(build_contours(...))
def test_contours_by_zoom_assigns_bands(ridge_depth):
    feats = contours_by_zoom(ridge_depth, transform, fine=True)
    assert {(f["tippecanoe"]["minzoom"], f["tippecanoe"]["maxzoom"]) for f in feats} <= {(10, 11), (12, 13), (14, 16)}
    assert any(f["properties"]["depth_ft"] == 25 for f in feats if f["tippecanoe"]["minzoom"] == 14)   # fine levels only in the native band
    assert not any(f["properties"]["depth_ft"] == 25 for f in feats if f["tippecanoe"]["minzoom"] == 10)

# test_bathy_bands.py
def test_bands_tile_the_grid(ridge_depth):
    feats = build_bands(ridge_depth, transform, levels_ft=DEPTHS_FT)
    union = unary_union([shape(f["geometry"]) for f in feats])
    assert abs(union.area - grid_water_area) / grid_water_area < 0.01
    assert all(f["properties"]["depth_min_ft"] < (f["properties"]["depth_max_ft"] or 10**6) for f in feats)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bathy_contours.py tests/test_bathy_bands.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Port `contours.py` from `~/projects/wa-creel/app/onwater/contours.py`** (the owner's code; same Chaikin, same thresholds; `contourpy.contour_generator(..., line_type="Separate")`; levels converted `ft / M_TO_FT`; nan handled by `contourpy`'s mask support), add `contours_by_zoom` with block-mean downsampling (`numpy` reshape mean, ignoring nan), and **`bands.py`** with `contourpy` `fill_type="OuterOffset"` and shapely for the polygons.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bathy_contours.py tests/test_bathy_bands.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): fishing contours and depth bands with the wa-creel rules"
```

---

### Task 12: Terrarium DEM tiles (dem.mbtiles)

**Files:**
- Create: `chartpack/src/chartpack/bathy/dem.py`
- Test: `chartpack/tests/test_bathy_dem.py`

**Interfaces:**
- Consumes: `MBTiles`, depth grid from Task 10.
- Produces:
  ```python
  # bathy/dem.py
  def terrarium_encode(elev_m: np.ndarray) -> np.ndarray      # (h, w, 3) uint8: v = elev + 32768; R = v // 256, G = v % 256, B = frac * 256
  def terrarium_decode(rgb: np.ndarray) -> np.ndarray
  def build_dem_mbtiles(depth_m: np.ndarray, transform, out: Path, *, minzoom: int = 10, maxzoom: int = 14, tile_size: int = 256) -> Path
      # elevation = -depth (nan -> 0), warped to EPSG:3857 per zoom with gdal.Warp, cut into 256 px PNG tiles, metadata format=png, cheekymarine:encoding=terrarium
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_terrarium_roundtrip():
    e = np.array([[-123.45, 0.0, 12.5]], np.float32)
    assert np.allclose(terrarium_decode(terrarium_encode(e)), e, atol=1 / 256)
def test_dem_mbtiles_roundtrip(ridge_depth, tmp_path):
    p = build_dem_mbtiles(ridge_depth, transform, tmp_path / "dem.mbtiles", minzoom=10, maxzoom=12)
    with MBTiles.open(p) as m:
        md = m.metadata(); assert md["format"] == "png" and md["cheekymarine:encoding"] == "terrarium" and md["maxzoom"] == "12"
        x, y, data = next(m.tiles_at(12))
        rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
        dec = terrarium_decode(rgb)
        assert rgb.shape == (256, 256, 3) and dec.min() < -5          # water is negative elevation
        # one known cell: the deepest ridge point decodes within 0.1 m of -(depth)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bathy_dem.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `dem.py`**: write the elevation grid to an in-memory GeoTIFF (`/vsimem/`), for each zoom `gdal.Warp` to EPSG:3857 at `res = 2 * pi * 6378137 / (256 * 2**z)` over the bbox snapped to tile edges, slice into tiles, encode, `Image.fromarray(...).save(png)`, `put_tile`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bathy_dem.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): terrarium raster-dem tiles for on-device hillshade"
```

---

### Task 13: Bathy vector tiles, ENC fallback contours, fishing style, bathy pack

**Files:**
- Create: `chartpack/src/chartpack/bathy/tiles.py`, `chartpack/src/chartpack/style/fish.py`
- Modify: `chartpack/src/chartpack/pack/assemble.py` (add `assemble_bathy_pack`)
- Test: `chartpack/tests/test_bathy_tiles.py`, `chartpack/tests/test_style_fish.py`

**Interfaces:**
- Consumes: `contours_by_zoom`, `build_bands`, `coverage_polygons`, `read_cell` (for ENC `depcnt`), `MBTiles`, `nav_style` helpers (`depth_filter`, `PALETTES`).
- Produces:
  ```python
  # bathy/tiles.py
  BATHY_LAYERS = ("contour", "band", "coverage")
  def enc_fallback_contours(enc_cells: list[tuple[CellMeta, list[Feature]]], uncovered: shapely.Geometry) -> list[dict]
      # ENC depcnt lines clipped to `uncovered` (from merge.uncovered_area), props depth_ft = round(VALDCO * M_TO_FT), major False, minzoom 10, source "enc"
  def build_bathy_mbtiles(contours: list[dict], bands: list[dict], coverage: list[dict], out: Path, *, region: Region, work: Path) -> Path
      # tippecanoe -Z10 -z16 -r1 --no-feature-limit --no-tile-size-limit for contour and coverage; band with --detect-shared-borders; metadata cheekymarine:pack=bathy, cheekymarine:sources = CUDEM tiles (name, year, version, sha256 of the window read is not available: record name and url) + CRM request URL + datum offsets
  # style/fish.py
  def fish_style(palette: str, depths: Depths = Depths()) -> dict
      # sources enc, bathy, dem (raster-dem, encoding terrarium, tileSize 256); layers: background, band-* fills (colour ramp from DEPVS through DEPDW by depth_min_ft), hillshade (source dem, hillshade-exaggeration 0.5), lndare, coalne, contour-enc (dashed, CHGRD, filter source == "enc"), contour-minor, contour-major (filter major), contour-label (symbol-placement line, text in feet from depth_ft, halo CHWHT 1.5 px, text-font Noto Sans Bold), light, hazard, hazard-danger; depare/depcnt/soundg/navaid/area/line from enc are absent
  ```

- [ ] **Step 1: Write the failing tests**

```python
# test_bathy_tiles.py (module fixture: ridge grid as "cudem" and a flat fallback, both covering only the south-west quarter of the test-cell bbox, plus the test-cell ENC; region coarse_fallback "crm")
def test_bathy_layers_and_metadata(bathy_pack):
    md = bathy_pack.metadata(); assert md["cheekymarine:pack"] == "bathy" and {l["id"] for l in json.loads(md["json"])["vector_layers"]} == set(BATHY_LAYERS)
def test_contour_sources(bathy_pack):
    srcs = {f["properties"]["source"] for z in range(10, 17) for _, _, d in bathy_pack.tiles_at(z) for f in decode_pbf(d).get("contour", [])}
    assert {"cudem", "enc"} <= srcs                                        # ENC fills the three quarters with no grid at all
def test_enc_fallback_only_outside_coverage(): ...   # every source=="enc" contour geometry is disjoint from the cudem coverage polygon
def test_major_minor_minzoom(bathy_pack): ...        # at z10 only majors present; at z14 a 70 ft line present
def test_coverage_layer(bathy_pack): ...             # coverage features at z10 carry source and resolution_m

# test_style_fish.py
def test_fish_sources(): s = fish_style("day"); assert set(s["sources"]) == {"enc", "bathy", "dem"} and s["sources"]["dem"] == {"type": "raster-dem", "url": "mbtiles://dem", "encoding": "terrarium", "tileSize": 256}
def test_fish_hides_nav_clutter(): ids = {l["id"] for l in fish_style("day")["layers"]}; assert not ids & {"depare-deep", "soundg-deep", "navaid"} and {"hillshade", "contour-major", "contour-label", "hazard-danger"} <= ids
def test_fish_depth_layers_metadata(): assert fish_style("day")["metadata"]["cheekymarine"]["depths"]["layers"] == ["hazard-danger"]
def test_fish_notice(): assert fish_style("day")["metadata"]["cheekymarine"]["notice"] == "Fishing chart: survey depths, approx. MLLW. Not certified for navigation."
def test_fish_schema(): assert check_style_against_schema(fish_style("day"), LAYERS + BATHY_LAYER_SPECS) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bathy_tiles.py tests/test_style_fish.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `bathy/tiles.py`** (add `BATHY_LAYER_SPECS` as `LayerSpec`s for `contour` (depth_ft, major, minzoom, source), `band` (depth_min_ft, depth_max_ft, minzoom), `coverage` (source, resolution_m, date) in `enc/schema.py` next to `LAYERS` so validation is one function) and **`style/fish.py`**; the nav style gets the same `metadata.cheekymarine.notice` = "Derived from NOAA ENC. Not an official chart. Not certified for navigation." (add that test to `test_style_nav.py`).

- [ ] **Step 4: Add `assemble_bathy_pack(region, bathy_mbtiles, dem_mbtiles, out_dir) -> Path`** writing `bathy.mbtiles`, `dem.mbtiles`, `styles/fish-{day,dusk,night}.json`, `sprites/fish*` (same symbols, name `fish`), `glyphs/`, `README.md`, `NOTICE`. Test: layout list, and `check_style_sprites_glyphs` clean for every fish style.

- [ ] **Step 5: Wire `chartpack build-bathy REGION OUT --cache DIR --work DIR`**: read CUDEM windows for the region's tiles, CRM, merge, clip, fill land, contours by zoom (fine where source is cudem), `tag_source`, bands, coverage, ENC fallback over `uncovered_area(..., treat_fallback_as_uncovered=region.coarse_fallback == "enc")` (reads the cached ENC cells), `bathy.mbtiles`, `dem.mbtiles` with `region.dem_maxzoom`, then `assemble_bathy_pack`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bathy_tiles.py tests/test_style_fish.py tests/test_pack_assemble.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): bathy vector tiles with ENC fallback, fishing style, bathy pack"
```

---

### Task 14: Manifest, check and archive

**Files:**
- Create: `chartpack/src/chartpack/pack/manifest.py`, `chartpack/src/chartpack/pack/check.py`, `chartpack/src/chartpack/pack/archive.py`
- Test: `chartpack/tests/test_pack_manifest.py`, `chartpack/tests/test_pack_check.py`, `chartpack/tests/test_pack_archive.py`

**Interfaces:**
- Consumes: pack roots from Task 8 and 13, `MBTiles`, `decode_pbf`, `read_cell`.
- Produces:
  ```python
  # pack/manifest.py
  def write_manifest(pack_root: Path, *, pack: str, region: Region, sources: list[dict], notice: str, built: datetime) -> dict
      # {"pack", "region", "version", "schema": 1, "built", "files": [{"name", "bytes", "sha256"}] for every file except manifest.json, "sources", "notice"}; bathy adds "charts_schema": 1
  # pack/check.py
  def check_pack(pack_root: Path, *, enc_zips: list[Path] | None = None) -> list[str]
      # errors: manifest missing/invalid; sha256 mismatch; mbtiles metadata keys missing; vector_layers != schema; a safety layer empty at a zoom inside its band range; for charts with enc_zips given: hazard key set at top zoom != source; depare+lndare coverage of covr < 0.9999; style files invalid against schema/sprites/glyphs
  # pack/archive.py
  def archive_pack(pack_root: Path, out_dir: Path) -> tuple[Path, Path]    # <pack>-<region>-<version>.tar (no compression: mbtiles do not shrink) and SHA256SUMS
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_manifest_lists_every_file_with_sha(charts_pack_root): ...      # names == all files except manifest.json; sha256 recomputed matches
def test_check_passes_on_built_pack(charts_pack_root, fixtures_dir): assert check_pack(charts_pack_root, enc_zips=[fixtures_dir / "US4WA1HK.zip"]) == []
def test_check_catches_a_removed_hazard(charts_pack_root_copy, fixtures_dir):   # delete one hazard feature from one z16 tile via sqlite rewrite
    errs = check_pack(charts_pack_root_copy, enc_zips=[...]); assert any("hazard" in e for e in errs)
def test_check_catches_corrupt_file(charts_pack_root_copy): ...        # flip a byte in a sprite png -> sha256 error
def test_archive(charts_pack_root, tmp_path):
    tar, sums = archive_pack(charts_pack_root, tmp_path)
    assert tar.name == "charts-test-cell-0.1.0.tar" and tarfile.open(tar).getnames()[0].startswith("charts-test-cell-0.1.0/")
    assert sums.read_text().split()[1] == tar.name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pack_manifest.py tests/test_pack_check.py tests/test_pack_archive.py -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement the three modules** and wire `chartpack manifest PACKDIR`, `chartpack check PACKDIR [--enc-cache DIR]`, `chartpack archive PACKDIR OUT`. `build-enc` and `build-bathy` call `write_manifest` at the end so a built pack is always complete.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pack_manifest.py tests/test_pack_check.py tests/test_pack_archive.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add chartpack
git commit -m "feat(chartpack): pack manifest, structural checks and tar archive"
```

---

### Task 15: Region puget-north, first full build, renders, size measurement

**Files:**
- Create: `chartpack/regions/puget-north.toml`, `docs/chartpack/renders/puget-north/*.png`, `docs/chartpack/2026-10-28-puget-north-first-build.md` (sizes, timings, decisions)
- Test: `chartpack/tests/test_regions.py`

**Interfaces:**
- Consumes: everything above through the CLI.

- [ ] **Step 1: Write the failing test**

```python
def test_puget_north_region_is_consistent(regions_dir, fixtures_dir):
    r = load_region(regions_dir / "puget-north.toml")
    cat = parse_catalog((fixtures_dir / "ENCProdCat_excerpt.xml").read_bytes())   # extend the excerpt with every cell the region names
    for band, names in r.cells.items():
        for n in names:
            assert cat[n].status == "Active" and cat[n].band == band and shape(polygon(cat[n])).intersects(box(*r.bbox)), n
    assert r.cells[4] == ["US4WA1GJ", "US4WA1GK", "US4WA1HJ", "US4WA1HK", "US4WA1II", "US4WA1IJ", "US4WA1IK"]
    assert r.cells[3] == ["US3WA1DF", "US3WA1DG", "US3WA1EF", "US3WA1EG"]
    assert len(r.views) == 4 and {v.name for v in r.views} == {"everett", "possession-bar", "point-no-point", "jeff-head"}
```

- [ ] **Step 2: Write `regions/puget-north.toml`**: bbox `[-122.9, 47.5, -122.1, 48.3]`, `charts_version = "1.0.0"`, `bathy_version = "1.0.0"`, band 3 and 4 as in the test, band 5 from `chartpack cells puget-north --band 5` run against the live catalog (expected to include US5SEAJJ, JK, JL, KI, KJ, KK, KL, KM, KN, KO, LH, LI, LJ, LK, LL, LN, MH, MI, MJ, MK, NF, NG, NH, NI, NJ, IJ, IK, IL, HI, HJ, HK, HL, GI, GJ, GK, GL, FH, FI, FJ, FK, FL, EH, EI, EJ, EK, EL; commit what the catalog says), `clip = "clip/canada-wa.geojson"`, `dem_maxzoom = 14`, datum Seattle 9447130 with the two offsets, four views: everett (-122.23, 47.98), possession-bar (-122.37, 47.90), point-no-point (-122.52, 47.92), jeff-head (-122.47, 47.75), zooms `[11, 13, 15]`. Extend `ENCProdCat_excerpt.xml` with those cells.

- [ ] **Step 3: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_regions.py -q`
Expected: pass

- [ ] **Step 4: Full build on the dev machine**:

```bash
chartpack fetch-enc regions/puget-north.toml --cache cache
chartpack build-enc regions/puget-north.toml work/charts --cache cache --work work/tmp
chartpack fetch-bathy regions/puget-north.toml --cache cache
chartpack build-bathy regions/puget-north.toml work/bathy --cache cache --work work/tmp
chartpack check work/charts --enc-cache cache && chartpack check work/bathy
chartpack archive work/charts dist && chartpack archive work/bathy dist
du -sh work/charts/* work/bathy/*
```

Expected: both checks print nothing and exit 0; record sizes and wall times in `docs/chartpack/2026-10-28-puget-north-first-build.md`. If the bathy pack is over 300 MB, note it and apply the levers in order (DEM maxzoom is already 14; next 5 ft contours only at z15; then band maxzoom 14); over 1 GB is a failure to fix before continuing.

- [ ] **Step 5: Render** `chartpack render work/charts work/bathy --views regions/puget-north.toml --styles nav-day,nav-night,fish-day,fish-night --out docs/chartpack/renders/puget-north` (48 PNGs). Look at all of them. Fix anything unreadable in palette or line weights once, rebuild the styles only, re-render, commit the PNGs.

- [ ] **Step 6: Commit**

```bash
git add chartpack/regions chartpack/tests docs/chartpack
git commit -m "feat(chartpack): puget-north region, first full build notes and renders"
```

---

### Task 16: Release workflow and documentation

**Files:**
- Create: `.github/workflows/chartpack-release.yml`, `chartpack/scripts/check-pack-tag.sh`
- Modify: `chartpack/README.md` (commands, pack contract, release procedure), `README.md` (one paragraph on chart packs and a link), `THIRD_PARTY_NOTICES` (pointer to `chartpack/NOTICE`)
- Test: `chartpack/tests/test_check_pack_tag.py` (runs the shell script)

**Interfaces:**
- Produces: `scripts/check-pack-tag.sh TAG` exits 0 and prints `PACK=charts REGION=puget-north VERSION=1.0.0` for `charts-puget-north-v1.0.0` when `regions/puget-north.toml` has `charts_version = "1.0.0"`; exits 1 with a message otherwise.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("tag,ok", [("charts-test-cell-v0.1.0", True), ("bathy-test-cell-v0.1.0", True), ("charts-test-cell-v9.9.9", False), ("v0.2.0", False), ("charts-nowhere-v0.1.0", False)])
def test_check_pack_tag(tag, ok, chartpack_dir):
    r = subprocess.run([chartpack_dir / "scripts/check-pack-tag.sh", tag], capture_output=True, text=True, cwd=chartpack_dir)
    assert (r.returncode == 0) == ok, r.stdout + r.stderr
    if ok: assert "VERSION=0.1.0" in r.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_check_pack_tag.py -q`
Expected: FAIL (script missing)

- [ ] **Step 3: Write `check-pack-tag.sh`** (bash, parses `^(charts|bathy)-([a-z0-9-]+)-v([0-9]+\.[0-9]+\.[0-9]+)$`, reads the matching `*_version` from `regions/<region>.toml` with a `sed` that tolerates spaces) and **`chartpack-release.yml`**: `on: push: tags: ['charts-*', 'bathy-*']`; job `version` runs the script and exports outputs; job `build` (needs version): apt gdal, tippecanoe from cache or script, venv, `fetch-*`, `build-*`, `check`, `archive`, upload artifact; job `publish` with `contents: write`: `softprops/action-gh-release@v2` with the tar and `SHA256SUMS`, `generate_release_notes: true`. The `ci.yml` C++ workflow is untouched. Note the dev-machine fallback in the workflow comments: if the build job exceeds the runner, the owner runs `archive` locally and attaches the tar by hand; the `check` job still runs on the uploaded tar.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_check_pack_tag.py -q`
Expected: pass

- [ ] **Step 5: Write the documentation**: `chartpack/README.md` sections: What it builds, Dev setup (apt packages, venv with `--system-site-packages`, tippecanoe script, Playwright optional), Commands, Region files, Pack contract (source names, the three rewrites, named depth layers and `metadata.cheekymarine`, notice strings, schema policy), Verification (what CI proves, what the renders are for), Cutting a release (bump `*_version` in the region file, tag, push). Root `README.md` gains a "Chart packs" paragraph linking there. Run the full test suite once more.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass, online and render tests skipped

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/chartpack-release.yml chartpack README.md THIRD_PARTY_NOTICES
git commit -m "ci(chartpack): pack release workflow on charts-*/bathy-* tags, docs"
```

---

## Self-review notes

- Spec coverage: 6.1 CLI and region file (Tasks 1, 15); 6.2 catalog, cells, updates, fixtures (Task 2, 3); 6.3 schema, quilting, no-drop, SCAMIN, metres (Tasks 3, 4, 5); 6.4 CUDEM primary, CRM fallback, datum, clip (Tasks 9, 10); 6.5 merge, contours, bands, DEM, ENC fallback (Tasks 10, 11, 12, 13); 6.6 palette, nav and fish styles, named depth layers, symbols, sprites, glyphs, notices (Tasks 6, 7, 13); 6.7 pack layout, manifest, versions, tags, workflow (Tasks 8, 13, 14, 16); 6.8 every listed test has a home (Tasks 2 to 14); 6.9 renders (Tasks 8, 15); non-goal "nothing hard-coded to Washington" (region file carries cells, sources, clip, datum: Tasks 1, 10, 15).
- Review Focus: 1 in Task 2 (`test_update_gap_is_an_error`), 2 in Tasks 3 and 6 (`test_every_hazard_present_with_attributes`, `test_depth_filters`), 3 in Task 5 (`test_polygon_crossing_tile_edge_is_in_both_tiles`), 4 in Task 10 (`test_nodata_hole_filled_from_fallback`), 5 in Tasks 2 and 9 (`test_partial_download_is_rejected`, `test_truncated_tif_is_rejected`).
- Names used across tasks: `Feature`, `CellMeta`, `read_cell`, `quilt`, `MBTiles`, `decode_pbf`, `build_enc_mbtiles`, `nav_style`, `fish_style`, `Depths`, `depth_filter`, `DEPTH_LAYERS`, `check_style_against_schema`, `check_style_sprites_glyphs`, `build_sprites`, `build_glyphs`, `Grid`, `read_window`, `merge_to_mllw`, `fill_land`, `coverage_polygons`, `clip_mask`, `build_contours`, `contours_by_zoom`, `build_bands`, `build_dem_mbtiles`, `build_bathy_mbtiles`, `BATHY_LAYER_SPECS`, `assemble_charts_pack`, `assemble_bathy_pack`, `write_manifest`, `check_pack`, `archive_pack`, `PackServer`, `render_views`: each defined once in its Interfaces block and used by those names later.
- Open choices left to the implementer on purpose: tippecanoe detail and buffer flags beyond the no-drop set, sprite packing layout, exact SDF radius for 48 px icons, Douglas-Peucker tolerances per zoom band, which tile in the DEM test is "known", the HTTP server's threading details.
