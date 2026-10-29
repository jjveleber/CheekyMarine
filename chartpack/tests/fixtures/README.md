# Test fixtures

Two NOAA ENC cells, downloaded once from `https://charts.noaa.gov/ENCs/<CELL>.zip`
on 2026-10-28 and committed unchanged. Each zip holds the base cell `.000` and its
update files (`.001`, ...) under `ENC_ROOT/<CELL>/`.

| Cell | Band | Edition (EDTN) | Update (UPDN) | Issue date (ISDT) | Update files in zip | Downloaded |
|------|------|----------------|---------------|-------------------|---------------------|------------|
| US4WA1HK | 4 | 1 | 3 | 2026-09-09 | .001 .002 .003 | 2026-10-28 |
| US5SEAKL | 5 | 1 | 1 | 2026-04-22 | .001 | 2026-10-28 |

EDTN, UPDN and ISDT were read from the `DSID` layer (`DSID_EDTN`, `DSID_UPDN`,
`DSID_ISDT`) by opening the `.000` with GDAL. GDAL applies the update files on open
by default, so the UPDN shown is the one after all shipped updates.

`US5SEAKL` (Possession Sound, near Everett) does contain a `.001` update file, so it
is used as specified; no substitute cell was needed.

## Golden files

`golden/US4WA1HK_tiles.json` holds the feature count per layer per zoom (11 to 16) of
`enc.mbtiles` built from `US4WA1HK.zip` with `regions/test-cell.toml`. Regenerate it with
`.venv/bin/pytest tests/test_enc_tiles.py --update-golden` after a deliberate change to the
reader, quilting, SCAMIN thinning or tippecanoe flags, and review the diff. Counts include
copies of a feature in neighbouring tile buffers.

Review Focus 3 (a depth area crossing a tile edge) is pinned by
`test_polygon_crossing_tile_edge_is_in_both_tiles` and `test_depare_plus_lndare_cover_cell`
in `tests/test_enc_tiles.py`: it picks a `DEPARE` from this cell whose bbox spans two adjacent
zoom 16 tiles, so it stays valid only while the fixture cell is unchanged. If the cell is
refreshed, regenerate the golden file and re-run those tests.

`cudem_urllist_excerpt.txt` is the 64 Washington lines (folders `wash_pugetsound`, `wash_bellingham`,
`wash_juandefuca`, `wash_outercoast`) of the live `urllist8483.txt` (942 lines in all), fetched 2026-10-28.

`cudem_possession_bar.tif` is a 300 by 300 window (311 KB, DEFLATE, Float32, NoData -9999, NAD83 + NAVD88
compound CRS) cut with `gdal_translate -projwin` centred on -122.38, 47.90 from
`ncei19_n48x00_w122x50_2023v1.tif` (1/9 arc-second). Depths run from -98.5 m to 0.05 m
(NAVD88 metres, negative down).

## Seabed (USGS) fixtures

`seabed/` mimics the `fetch-seabed` cache (`<cache>/seabed/`): each zip has the published file's name
and member names, cut from the real download of 2026-10-29. Licences: chartpack/NOTICE.

- `pac_ext.zip`, `pac_prs.zip`: USGS usSEABED DS 182 (`https://pubs.usgs.gov/ds/2006/182/data/`). Each
  holds the header and unchanged raw lines (CRLF kept) of `PAC_EXT.txt` / `PAC_PRS.txt`: every row inside
  the test cell bbox (19 EXT, 12 PRS, with exact duplicates at 47.9025, -122.38), plus real Puget Sound
  rows outside it (EXT `mS`, `gmS`; PRS `H`, `sG`, `msG`) for the clipping and hard-ground tests.
- `CMECS_*.zip`: USGS DS 935 CMECS substrate shapefiles (NAD83 / UTM 10N, all fields kept), a few
  polygons each cut with `ogr2ogr -where "FID IN (...)"` from the published block zips:
  `CMECS_OffshoreSeattle` FIDs 1637, 1957, 1907, 1644, 1737, 1845 (crosses the test cell's west edge),
  2449 (`na`, land, invalid geometry); `CMECS_AdmiraltyInlet` FIDs 163, 2603, 37, 20, 442, 366, 209, 65,
  146, 221 (all outside the test cell); `CMECS_OffshoreTacoma` FIDs 3601, 3494, 457, 731;
  `CMECS_OffshoreBurien` FIDs 1865, 20, 1599, 1503, 2632, 1000. Their sizes differ from the published
  zips, so tests that fetch them patch the pinned sizes.
