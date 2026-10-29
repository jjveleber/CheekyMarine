"""Colour tokens for the navigation style (day, dusk, night). Our own palette, tuned later on renders."""

TOKENS = (
    "DEPDW", "DEPMD", "DEPMS", "DEPVS", "DEPIT", "LANDA", "LANDF", "CSTLN", "CHBLK", "CHGRD", "CHMGD", "CHWHT",
    "SNDG1", "SNDG2", "LITRD", "LITGN", "LITYW", "NINFO", "OUTLW", "DNGHL", "ADINF", "RESBL", "TRFCD", "NODTA",
)

_DAY = {
    "DEPDW": "#FFFFFF",  # deep water fill
    "DEPMD": "#DCEEF9",  # medium depth water fill
    "DEPMS": "#B8DCF2",  # medium-shallow water fill
    "DEPVS": "#8EC3E6",  # very shallow water fill
    "DEPIT": "#A8D5A2",  # intertidal area fill
    "LANDA": "#F1E7C8",  # land area fill
    "LANDF": "#D9CA90",  # land features
    "CSTLN": "#5E5E50",  # coastline
    "CHBLK": "#000000",  # black chart ink (safety contour, black navaids)
    "CHGRD": "#6B7A82",  # grey chart ink (depth contours, default navaid)
    "CHMGD": "#C800C8",  # magenta chart ink (cables, pipelines, routes)
    "CHWHT": "#FFFFFF",  # white chart ink (white navaids)
    "SNDG1": "#000000",  # soundings at or shallower than the safety depth
    "SNDG2": "#7A8690",  # soundings deeper than the safety depth
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

_NIGHT = {
    "DEPDW": "#000000",  # deep water fill
    "DEPMD": "#0A1F33",  # medium depth water fill
    "DEPMS": "#123A5A",  # medium-shallow water fill
    "DEPVS": "#1B5280",  # very shallow water fill
    "DEPIT": "#1E3A1E",  # intertidal area fill
    "LANDA": "#2A2616",  # land area fill
    "LANDF": "#3A3420",  # land features
    "CSTLN": "#8A8A7A",  # coastline
    "CHBLK": "#C0C0C0",  # chart ink in place of black
    "CHGRD": "#7A8690",  # grey chart ink (depth contours, default navaid)
    "CHMGD": "#A000A0",  # magenta chart ink (cables, pipelines, routes)
    "CHWHT": "#C0C0C0",  # white chart ink (white navaids)
    "SNDG1": "#C0C0C0",  # soundings at or shallower than the safety depth
    "SNDG2": "#7A8690",  # soundings deeper than the safety depth
    "LITRD": "#B01C14",  # red lights and navaids
    "LITGN": "#157F32",  # green lights and navaids
    "LITYW": "#B89A00",  # yellow lights and navaids
    "NINFO": "#B05500",  # orange information text
    "OUTLW": "#C0C0C0",  # outlines
    "DNGHL": "#B01C14",  # danger highlight
    "ADINF": "#705400",  # anchorage area fill
    "RESBL": "#24488A",  # restricted area fill
    "TRFCD": "#A000A0",  # traffic separation scheme fill
    "NODTA": "#404040",  # no data
}


def _toward_black(colour: str, fraction: float) -> str:
    channels = (round(int(colour[i : i + 2], 16) * (1 - fraction)) for i in (1, 3, 5))
    return "#" + "".join(f"{c:02x}" for c in channels)


# Derived from day so the two cannot drift.
PALETTES: dict[str, dict[str, str]] = {
    "day": _DAY,
    "dusk": {token: _toward_black(colour, 0.45) for token, colour in _DAY.items()},
    "night": _NIGHT,
}
