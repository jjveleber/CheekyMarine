# Seabed legend

Generated from `chartpack/src/chartpack/seabed/legend.py` (`legend_markdown`); do not edit by hand.

The charts pack `seabed` layer labels each ENC seabed area (`SBDARE`) and weed or kelp feature
(`WEDKLP`), each USGS usSEABED sediment sample (`SAMPLE`) and each USGS CMECS substrate polygon (`CMECS`)
with the chart abbreviations below. Each pack's `legend.json` lists the ones it uses and their sources.

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

## USGS survey classes

The same abbreviations label the USGS sources, main constituent first. usSEABED (USGS Data Series 182)
samples carry a Folk grain-size class. A "slightly gravelly" or "slightly cobbley" class, from either
source, reads as its main classes only. A class not listed here keeps its raw value in the tile and
has no label.

| Folk code | Folk class | Label |
|---|---|---|
| M | mud | M |
| S | sand | S |
| G | gravel | G |
| sM | sandy mud | M.S |
| mS | muddy sand | S.M |
| gM | gravelly mud | M.G |
| gS | gravelly sand | S.G |
| mG | muddy gravel | G.M |
| sG | sandy gravel | G.S |
| gmS | gravelly muddy sand | S.M.G |
| msG | muddy sandy gravel | G.S.M |
| (g)M | slightly gravelly mud | M |
| (g)S | slightly gravelly sand | S |
| (g)mS | slightly gravelly muddy sand | S.M |
| (g)sM | slightly gravelly sandy mud | M.S |
| H | hard ground | h |

CMECS substrate polygons (USGS Southern Salish Sea habitat maps, Data Series 935) carry the finest
substrate level the map gives. Coarser levels that do not say which grain dominates ("gravelly",
"gravel mix", "fine unconsolidated substrate" and so on) and names with no Chart No. 1 term are drawn
as an outline with no label.

| CMECS substrate | Label |
|---|---|
| rock substrate | Rk |
| bedrock | Rk |
| boulder | Blds |
| cobble | Cb |
| gravel | G |
| sand | S |
| mud | M |
| muddy sand | S.M |
| sandy mud | M.S |
| gravelly sand | S.G |
| gravelly mud | M.G |
| slightly gravelly sand | S |
| slightly gravelly mud | M |
| slightly gravelly muddy sand | S.M |
| sandy gravel | G.S |
| sandy cobble | Cb.S |
| muddy cobble | Cb.M |
| muddy sandy cobble | Cb.S.M |
| cobbley sand | S.Cb |
| slightly cobbley sand | S |
| cobbley sandy mud | M.S.Cb |
