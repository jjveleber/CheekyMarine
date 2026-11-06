"""Colour tokens for the navigation style (day, dusk, night). Our own palette, tuned later on renders."""

TOKENS = (
    "DEPDW", "DEPMD", "DEPMS", "DEPVS", "DEPIT", "LANDA", "LANDF", "CSTLN", "CHBLK", "CHGRD", "CHMGD", "CHWHT",
    "SNDG1", "SNDG2", "TXTSH", "TXTDP", "LITWH", "LITRD", "LITGN", "LITYW", "NINFO", "OUTLW", "DNGHL", "ADINF", "RESBL", "TRFCD", "NODTA",
)

_DAY = {
    "DEPDW": "#F4EEE2",  # deep water fill (subtle sepia)
    "DEPMD": "#DCEEF9",  # medium depth water fill
    "DEPMS": "#B8DCF2",  # medium-shallow water fill
    "DEPVS": "#8EC3E6",  # very shallow water fill
    "DEPIT": "#A8D5A2",  # intertidal area fill
    "LANDA": "#EFD98A",  # land area fill
    "LANDF": "#D9CA90",  # land features
    "CSTLN": "#5E5E50",  # coastline
    "CHBLK": "#000000",  # black chart ink (safety contour, black navaids)
    "CHGRD": "#6B7A82",  # grey chart ink (depth contours, default navaid)
    "CHMGD": "#C800C8",  # magenta chart ink (cables, pipelines, routes)
    "CHWHT": "#FFFFFF",  # white chart ink (white navaids)
    "SNDG1": "#000000",  # soundings at or shallower than the safety depth
    "SNDG2": "#4A5560",  # soundings deeper than the safety depth
    "TXTSH": "#000000",  # text of shallow soundings, place names, contour labels (the bright text)
    "TXTDP": "#4A5560",  # text of deep soundings and seabed codes (the dim text)
    "LITWH": "#FFFFFF",  # white lights and navaids
    "LITRD": "#E2231A",  # red lights and navaids
    "LITGN": "#1A9E3F",  # green lights and navaids
    "LITYW": "#E9C400",  # yellow lights and navaids
    "NINFO": "#E26D00",  # orange information text
    "OUTLW": "#000000",  # outlines
    "DNGHL": "#E2231A",  # danger highlight
    "ADINF": "#8E6A00",  # anchorage area fill
    "RESBL": "#2D5BA8",  # restricted area fill
    "TRFCD": "#C800C8",  # traffic separation scheme fill
    "NODTA": "#C8C8C8",  # no data
}

# Red-only night (#33 variant `red`): red on black keeps the eyes dark-adapted; every channel but red is at most 0x20.
_NIGHT_RED = {
    "DEPDW": "#000000",  # deep water fill (black)
    "DEPMD": "#140000",  # medium depth water fill (lighter than DEPDW, R29)
    "DEPMS": "#260000",  # medium-shallow water fill
    "DEPVS": "#3A0000",  # very shallow water fill
    "DEPIT": "#301010",  # intertidal area fill
    "LANDA": "#180404",  # land area fill
    "LANDF": "#2A0A0A",  # land features
    "CSTLN": "#A00000",  # coastline
    "CHBLK": "#F00000",  # chart ink in place of black
    "CHGRD": "#B00000",  # grey chart ink (depth contours, default navaid)
    "CHMGD": "#900000",  # magenta chart ink (cables, pipelines, routes)
    "CHWHT": "#FF2020",  # white chart ink (white navaids)
    "SNDG1": "#FF2020",  # soundings at or shallower than the safety depth
    "SNDG2": "#D00000",  # soundings deeper than the safety depth
    "TXTSH": "#FF2020",  # text of shallow soundings, place names, contour labels (the bright text)
    "TXTDP": "#D00000",  # text of deep soundings and seabed codes (the dim text)
    "LITWH": "#FF2020",  # white lights and navaids
    "LITRD": "#FF0000",  # red lights and navaids
    "LITGN": "#B00000",  # green lights and navaids
    "LITYW": "#E00000",  # yellow lights and navaids
    "NINFO": "#E00000",  # orange information text
    "OUTLW": "#F00000",  # outlines
    "DNGHL": "#FF0000",  # danger highlight
    "ADINF": "#400000",  # anchorage area fill
    "RESBL": "#500000",  # restricted area fill
    "TRFCD": "#600000",  # traffic separation scheme fill
    "NODTA": "#080000",  # no data
}


def _toward_black(colour: str, fraction: float) -> str:
    channels = (round(int(colour[i : i + 2], 16) * (1 - fraction)) for i in (1, 3, 5))
    return "#" + "".join(f"{c:02x}" for c in channels)


# Amber night (#33, the default; owner choice 2026-11-05 after a look on the test laptop): amber text, dimmed navaid colors,
# shoal band, land and coastline brightening toward shore. Water stays black.
_NIGHT_AMBER = {**_NIGHT_RED,
    "TXTSH": "#E0A000", "TXTDP": "#C08000", "LITGN": "#20A040", "LITYW": "#D0B000", "LITWH": "#C0C0C0",
    "DEPMD": "#200000", "DEPMS": "#3C0000", "DEPVS": "#5A0000", "DEPIT": "#40200A", "LANDA": "#30200A",
    "LANDF": "#3A2810", "CSTLN": "#C06000"}

# Derived from day so the two cannot drift.
PALETTES: dict[str, dict[str, str]] = {
    "day": _DAY,
    "dusk": {token: _toward_black(colour, 0.45) for token, colour in _DAY.items()},
    "night": _NIGHT_AMBER,
}


NIGHT_VARIANTS: dict[str, dict[str, str]] = {"amber": _NIGHT_AMBER, "red": _NIGHT_RED}
DEFAULT_NIGHT = "amber"


def night_palette(variant: str = DEFAULT_NIGHT) -> dict[str, str]:
    return NIGHT_VARIANTS[variant]
