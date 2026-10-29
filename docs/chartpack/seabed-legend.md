# Seabed legend

Generated from `chartpack/src/chartpack/seabed/codes.py` (`legend_markdown`); do not edit by hand.

The charts pack `seabed` layer labels each ENC seabed area (`SBDARE`) and weed or kelp feature
(`WEDKLP`) with the chart abbreviations below. Each pack's `legend.json` lists the ones it uses.

Sources: US Chart No. 1, 13th edition, section J "Nature of the Seabed" (NOAA and NGA, public domain),
NOAA column where it differs from INT, INT otherwise; codes from the IHO S-57 Edition 3.1 attribute
catalogue (Appendix A chapter 2: NATSUR 113, NATQUA 114, CATWED 70).

Mixtures (Chart No. 1 J 12.2): the main constituent comes first, the types are joined with a dot, and
each qualifier is written in front of the type in the same list position, so NATSUR `4,1` with NATQUA
`1` reads `fS.M`, fine sand with mud. A qualifier with no type (S-57 allows NATQUA alone) is shown on
its own, for example `h`, hard bottom. Kelp is drawn with its J 13.2 symbol beside the word Kelp; a
weed or kelp feature with no category reads `Wd` (J 13.1, weed including kelp).

| Abbreviation | Meaning | Kind | S-57 code | Chart No. 1 |
|---|---|---|---|---|
| M | mud | type | NATSUR 1 | J 2 |
| Cy | clay | type | NATSUR 2 | J 3 |
| Si | silt | type | NATSUR 3 | J 4 |
| S | sand | type | NATSUR 4 | J 1 |
| St | stones | type | NATSUR 5 | J 5 |
| G | gravel | type | NATSUR 6 | J 6 |
| P | pebbles | type | NATSUR 7 | J 7 |
| Cb | cobbles | type | NATSUR 8 | J 8 |
| Rk | rock | type | NATSUR 9 | J 9.1, NOAA (INT R) |
| marsh | marsh | type | NATSUR 10 | none in section J, the S-57 meaning is shown |
| La | lava | type | NATSUR 11 | J l, NOAA supplementary |
| snow | snow | type | NATSUR 12 | none in section J, the S-57 meaning is shown |
| ice | ice | type | NATSUR 13 | none in section J, the S-57 meaning is shown |
| Co | coral | type | NATSUR 14 | J 10 |
| swamp | swamp | type | NATSUR 15 | none in section J, the S-57 meaning is shown |
| bog | bog or moor | type | NATSUR 16 | none in section J, the S-57 meaning is shown |
| Sh | shells | type | NATSUR 17 | J 11 |
| Blds | boulders | type | NATSUR 18 | J 9.2, NOAA (INT Bo) |
| Kelp | kelp | type | CATWED 1 | J 13.2, NOAA |
| Wd | weed | type | CATWED 2 | J 13.1 |
| Sg | seagrass | type | CATWED 3 | J 13.3 |
| Wd | weed | type | CATWED 4 | J 13.1 (sargasso is a seaweed) |
| f | fine | qualifier | NATQUA 1 | J 30 |
| m | medium | qualifier | NATQUA 2 | J 31 |
| c | coarse | qualifier | NATQUA 3 | J 32 |
| bk | broken | qualifier | NATQUA 4 | J 33 |
| sy | sticky | qualifier | NATQUA 5 | J 34 |
| so | soft | qualifier | NATQUA 6 | J 35 |
| sf | stiff | qualifier | NATQUA 7 | J 36 |
| vol | volcanic | qualifier | NATQUA 8 | J 37, NOAA (INT v) |
| Ca | calcareous | qualifier | NATQUA 9 | J 38, NOAA (INT ca) |
| h | hard | qualifier | NATQUA 10 | J 39 |
