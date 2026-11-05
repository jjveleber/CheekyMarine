# Puget Sound AIS traffic fixture

`puget-2024-07-13.csv` is real vessel traffic for the `ais-density` synth scenario.

- Source: Martin, Brass, Dornback, Fontenault, 2025, Nationwide Automatic Identification System 2024,
  NOAA Office for Coastal Management. Daily GeoParquet file
  `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-07-13.parquet`
  (July 13, 2024, a Saturday; about 294 MB).
- License: CC0 1.0.
- Area: bbox `-122.55,47.70,-122.25,48.00` (west, south, east, north; Possession Sound to Elliott Bay).
- Window: 2024-07-13 20:20:00 to 20:50:00 UTC. It is the busiest 30 minutes (76 distinct MMSIs) of
  20:00 to 22:00 UTC among windows starting on the 10 minutes; the first of the tied windows won.
- Thinning: one row per vessel per 20 s (`--thin-s 20`), which already gives a small file.
- Result: 853 rows, 76 vessels, 55 KB.
- Columns: `mmsi,t,lat,lon,sog_kn,cog,heading,name,type,length,cls`. `t` is seconds from the window start.
  An empty field is not available (heading 511 is written empty). Names are ASCII only (other
  characters became `?`). `cls` is the AIS transceiver class, A or B.
- Source column names in the 2024 files: `mmsi`, `base_date_time`, `geometry` (WKB point, lon/lat),
  `sog`, `cog`, `heading`, `vessel_name`, `vessel_type`, `length`, `transceiver`. The extractor maps
  these to the CSV columns.

Regenerate (pyarrow is needed for this one tool only; use a scratch venv):

    python3 -I plotter/tools/extract_ais.py --parquet ais-2024-07-13.parquet \
      --bbox=-122.55,47.70,-122.25,48.00 --start 2024-07-13T20:20:00 --end 2024-07-13T20:50:00 \
      --out plotter/tests/fixtures/ais/puget-2024-07-13.csv --thin-s 20
