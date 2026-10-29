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
