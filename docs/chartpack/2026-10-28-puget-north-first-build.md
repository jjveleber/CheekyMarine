# puget-north: first full build (2026-10-29)

First real-world run of the chartpack pipeline on `chartpack/regions/puget-north.toml`
(bbox -122.9, 47.5, -122.1, 48.3; charts 1.0.0, bathy 1.0.0). Dev machine: WSL2, 16 cores, 56 GB RAM.
These are build notes. The owner signs off the pack after looking at the renders.

## Region

- Cells: every Active catalog cell of bands 3 to 5 whose catalog polygon meets the bbox, read with
  `chartpack cells` from the catalog of 2026-10-29. Band 3: 4 cells, band 4: 11 (the 7 of the spec plus
  US4WA1GI, HI, JI, JJ on the bbox edges), band 5: 86 (83 US5SEA cells plus US5WA1EN, EO, EP). 101 cells.
- Bands 1 and 2 also meet the bbox (US1GLBDD, US2PACWY) and are left out: band 3 covers the whole bbox,
  so the quilt would clip band 2 away everywhere, and band 1 has no zoom range.
- Seabed: `enc`, `usseabed`, `usgs-cmecs` with CMECS blocks admiralty-inlet, seattle, burien (Tacoma has
  no block inside the bbox).
- Views: everett (-122.23, 47.98), possession-bar (-122.37, 47.90), point-no-point (-122.52, 47.92),
  jeff-head (-122.47, 47.75), admiralty-inlet (-122.74, 48.13, inside the CMECS Admiralty Inlet block);
  zooms 11, 13, 15.

## Commands and wall times

Run from `chartpack/` with the caches already present (all 101 ENC zips current, CRM for the bbox).

| Step | Wall time | Notes |
|---|---|---|
| `fetch-enc regions/puget-north.toml --cache cache` | 2.4 s | catalog refetched, every zip already current |
| `fetch-seabed regions/puget-north.toml --cache cache` | 7.3 s | pac_ext, pac_prs, 3 CMECS zips |
| `build-enc regions/puget-north.toml work/charts --cache cache --work work/tmp` | 2 min 19 s | 8 min 51 s CPU |
| `fetch-bathy regions/puget-north.toml --cache cache` | 9.8 s | 15 CUDEM tiles listed, CRM cached |
| `build-bathy regions/puget-north.toml work/bathy --cache cache --work work/tmp` | 3 min 29 s (rebuild 3 min 39 s) | peak RSS 5.0 GB; CUDEM windows over /vsicurl/ |
| `check work/charts/charts-puget-north-1.0.0 --enc-cache cache` | 1 min 13 s | clean after fix 1 below |
| `check work/bathy/bathy-puget-north-1.0.0` | 0.5 s | clean |
| `archive` (each pack) `... dist` | under 1 s each | |
| `render` (60 PNGs) | 31 s | |

## Sizes

| Pack | Directory | Tar | Largest files |
|---|---|---|---|
| charts-puget-north-1.0.0 | 177,353,750 bytes (169 MiB) | 177,377,280 bytes | enc.mbtiles 176,803,840 (zoom 6 to 16, 354,299 tiles) |
| bathy-puget-north-1.0.0 | 279,465,106 bytes (267 MiB) | 279,480,320 bytes | dem.mbtiles 243,003,392 (zoom 10 to 14, 2,128 tiles at z14); bathy.mbtiles 35,926,016 |

Both packs are under the 300 MB target, so none of the size levers was needed (DEM maxzoom stays 14).
The bathy tar is reproducible: archiving the same pack twice gave the same sha256.

## Pipeline problems found and fixed

Each was fixed test first; the full suite is green with `-W error`.

1. **`check` reported a hazard missing that the quilt correctly dropped.** `hazard ('OBSTRN', None, 3)
   at -122.700000,47.777500 from US3WA1DF missing at zoom 16`. The obstruction (band 3, unknown depth,
   always submerged) lies exactly on the seam where US4WA1HI, US4WA1HJ, US5SEAIG and US5SEAIH meet. Each
   finer coverage covers the point but none contains it, while their union contains it. The quilt clips by
   the union (`contains_xy` on `unary_union`), so the point is dropped at zoom 13 to 16, as the spec says
   (where a finer band covers a point, coarser features are clipped out). The check excused a hazard only
   when one single finer cell contained it, so it expected the point. Fix: the check now tests the union of
   the finer coverages, the same rule the quilt uses (`pack/check.py`). Test:
   `test_hazard_on_a_seam_of_finer_cells_is_quilted_away`. No finer cell charts an obstruction within
   15 m of that point; the pack follows the ECDIS rule of the spec there.
2. **`archive` of the two packs into one directory kept only the last pack's checksum.** The brief's own
   step (`archive work/charts dist && archive work/bathy dist`) left a SHA256SUMS with the bathy line only.
   Fix: SHA256SUMS keeps the lines of other tars and replaces this tar's line (`pack/archive.py`); a release
   with one pack still gets one line. Test: `test_archive_keeps_other_packs_sums`.
3. **Fish-night contour labels were unreadable blobs.** The night palette sets CHBLK and CHWHT to the same
   `#C0C0C0`, and the contour labels used CHBLK text on a CHWHT halo. Fix: the halo is DEPDW, the water
   colour, as the nav labels already do (`style/fish.py`); in day that is `#F4EEE2` behind black text. Test:
   `test_text_halo_differs_from_text` over every palette of the nav and fish styles. The bathy pack was
   rebuilt and all 60 PNGs re-rendered after this fix.

The watch item from Task 14 (safety layers empty at a zoom on a multi-band region) did not trigger:
every safety layer has features at every zoom 6 to 16.

## Renders

`docs/chartpack/renders/puget-north/<view>-z<zoom>-<style>.png`, styles nav-day, nav-night, fish-day,
fish-night: 60 PNGs, 1024 by 600. All 60 were looked at (before and after fix 3). What I saw per view:

- **everett**
  - z11: the Snohomish delta and Port Gardner read clearly; dense rock and obstruction symbols along the
    shores and in the delta. Fish styles show majors 600 and 120 labelled.
  - z13: harbour structures, navaids and anchorage detail; no soundings in nav at z13 (band 5 SCAMIN
    puts them at zoom 14 and up). Seabed labels M.S and S.M are faint.
  - z15: soundings and SEAARE names (Snohomish River is labelled twice, one SEAARE from each of two
    cells). The darker wedge at top left is the ACHARE "Port Gardner General Anchorage" fill. The dashed
    magenta line around Port Gardner is a RESARE outline. Fish styles: 5 ft steps (15, 25, 35) in the
    harbour; the band fills inside the harbour show triangular facets that are in the CUDEM data.
- **possession-bar**
  - z11: the traffic separation scheme, the Paine Field aero light on land (a real LIGHTS feature), rock
    clusters along both shores.
  - z13: the bar and its slope; nav shows contours without soundings. Fish styles show the bar well with
    the 20 to 600 ft labels.
  - z15: soundings and contours in nav. Fish contours are angular: long straight runs between corners.
    That is the ported Douglas-Peucker tolerance `SIMPLIFY_DEG = 0.0002` (about 20 m) in
    `bathy/contours.py` on smooth deep-water CUDEM, not a grid artefact (the merge grid is 1/3 arc-second).
    The hillshade here is soft because the CUDEM surface is smooth there (checked on the
    `cudem_possession_bar.tif` fixture). Not changed: it is a spec value carried from wa-creel; listed
    below for the owner.
- **point-no-point**
  - z11: TSS lanes and the precautionary area, navaids on both sides, readable.
  - z13: TSS lanes show a thin straight line across a lane where two cells' lane polygons meet; the seabed
    label G and the light read.
  - z15: SEAARE "Salish Sea" labelled twice (two cells); dashed magenta lines (cables and RESARE outlines
    look the same, see below); sounding 325 sits on the TSS fill, still readable.
- **jeff-head**
  - z11: TSS, the Port Madison and Kingston shores. Near the bottom edge a light-blue box with straight
    north and west edges: the US4WA1GJ DEPARE 9.1 to 182.8 m has those straight edges in the source cell,
    so it is drawn as charted. The TSS lane seam line appears here too.
  - z13: many seabed labels (S.G, S.M, M.S) from the ENC and usSEABED; faint but separate.
  - z15: soundings, Port Madison label, seabed labels; fish shows the 5 ft steps 5 to 55.
- **admiralty-inlet**
  - z11: Port Townsend, Marrowstone and the TSS. The fish styles show the west edge of the bathy bbox
    (-122.9) as a straight line at the left, with no contours west of it.
  - z13: CMECS labels (Cb, S.G, G.S) in the inlet: the bottom-composition polygons are in the render.
  - z15: CMECS polygons and labels (Cb, S, Sh, G) with soundings in nav; fish shows the CMECS outlines
    over the band fills.

### Owner-decision items (left as they are)

| Item | Renders that show it best |
|---|---|
| Night DEPMD/DEPMS darker than night DEPDW (shallower water reads darker than deep) | `everett-z13-nav-night.png`, `possession-bar-z13-nav-night.png`, `jeff-head-z15-nav-night.png` |
| Blds vs Bo abbreviation | not shown in any of the 60: the nearest `Blds` (ENC, -122.5759, 47.9203) lies just west of the `point-no-point-z13` frames, and no `Bo` label falls inside a view |
| Faint CHGRD seabed labels | `jeff-head-z13-nav-day.png`, `admiralty-inlet-z15-nav-day.png`, `admiralty-inlet-z13-nav-night.png` |
| RESARE outline looking like cable lines | `everett-z15-nav-day.png` (RESARE outline only, no cables in view) against `possession-bar-z15-nav-day.png` and `point-no-point-z15-nav-day.png` (cables and RESARE together) |
| The redrawn hazard symbols | `possession-bar-z13-nav-day.png` (rocks along the Possession Point shore), `everett-z11-nav-day.png` and `jeff-head-z11-nav-day.png` (dense clusters at z11) |

### Further observations for the owner (not changed)

- Fish contours are angular at zoom 15 (`possession-bar-z15-fish-day.png`,
  `point-no-point-z15-fish-day.png`): the contour simplification tolerance (0.0002 degrees) is a ported
  spec value.
- Nav shows no soundings at zoom 13 in band 5 areas (`possession-bar-z13-nav-day.png`): the SCAMIN rule.
- Duplicate SEAARE names where two cells carry the same sea area (`everett-z15-nav-day.png`,
  `point-no-point-z15-nav-day.png`), and thin lines across TSS lanes at cell seams
  (`jeff-head-z11-nav-day.png`, `point-no-point-z13-nav-day.png`).
- The fish-night hillshade highlight (CHWHT `#C0C0C0`) shows as a light haze on steep slopes
  (`everett-z13-fish-night.png`, `possession-bar-z15-fish-night.png`).
