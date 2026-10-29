"""Bottom composition codes to chart abbreviations (spec 6.10).

Codes: the S-57 attribute catalogue, IHO S-57 Edition 3.1 Appendix A chapter 2 (NATSUR 113, NATQUA 114,
CATWED 70). Abbreviations: US Chart No. 1 section J (NOAA/NGA, 13th edition), the NOAA column where it
differs from INT (Rk, Blds, vol, Ca), the INT column otherwise. Codes with no section J entry (land
surfaces in NATSUR) are labelled with the S-57 meaning itself. docs/chartpack/seabed-legend.md is
generated from these tables.
"""

# code -> (abbreviation, plain meaning)
NATSUR: dict[int, tuple[str, str]] = {
    1: ("M", "mud"),
    2: ("Cy", "clay"),
    3: ("Si", "silt"),
    4: ("S", "sand"),
    5: ("St", "stones"),
    6: ("G", "gravel"),
    7: ("P", "pebbles"),
    8: ("Cb", "cobbles"),
    9: ("Rk", "rock"),
    10: ("marsh", "marsh"),
    11: ("La", "lava"),
    12: ("snow", "snow"),
    13: ("ice", "ice"),
    14: ("Co", "coral"),
    15: ("swamp", "swamp"),
    16: ("bog", "bog or moor"),
    17: ("Sh", "shells"),
    18: ("Blds", "boulders"),
}

NATQUA: dict[int, tuple[str, str]] = {
    1: ("f", "fine"),
    2: ("m", "medium"),
    3: ("c", "coarse"),
    4: ("bk", "broken"),
    5: ("sy", "sticky"),
    6: ("so", "soft"),
    7: ("sf", "stiff"),
    8: ("vol", "volcanic"),
    9: ("Ca", "calcareous"),
    10: ("h", "hard"),
}

# WEDKLP category. Kelp is written "Kelp" beside the kelp symbol as in the NOAA column of J 13.2.
CATWED: dict[int, tuple[str, str]] = {
    1: ("Kelp", "kelp"),
    2: ("Wd", "weed"),
    3: ("Sg", "seagrass"),
    4: ("Wd", "weed"),
}

# The US Chart No. 1 entry each abbreviation is taken from ("J 9.1" is section J item 9.1).
CHART_NO1: dict[str, dict[int, str]] = {
    "NATSUR": {
        1: "J 2",
        2: "J 3",
        3: "J 4",
        4: "J 1",
        5: "J 5",
        6: "J 6",
        7: "J 7",
        8: "J 8",
        9: "J 9.1, NOAA (INT R)",
        10: "none in section J, the S-57 meaning is shown",
        11: "J l, NOAA supplementary",
        12: "none in section J, the S-57 meaning is shown",
        13: "none in section J, the S-57 meaning is shown",
        14: "J 10",
        15: "none in section J, the S-57 meaning is shown",
        16: "none in section J, the S-57 meaning is shown",
        17: "J 11",
        18: "J 9.2, NOAA (INT Bo)",
    },
    "NATQUA": {
        1: "J 30",
        2: "J 31",
        3: "J 32",
        4: "J 33",
        5: "J 34",
        6: "J 35",
        7: "J 36",
        8: "J 37, NOAA (INT v)",
        9: "J 38, NOAA (INT ca)",
        10: "J 39",
    },
    "CATWED": {
        1: "J 13.2, NOAA",
        2: "J 13.1",
        3: "J 13.3",
        4: "J 13.1 (sargasso is a seaweed)",
    },
}


def split_codes(value: str | None) -> list[str]:
    """A GDAL comma list split into its items; empty items are kept (a NATQUA position with no quality)."""
    return value.split(",") if value else []


def _abbr(table: dict, name: str, code: str) -> str:
    try:
        return table[int(code)][0]
    except (ValueError, KeyError):
        raise ValueError(f"{name} {code} is not in the S-57 attribute catalogue") from None


def label(natsur: str | None, natqua: str | None) -> str | None:
    """The chart label of a seabed area: "4,1" + "1" -> "fS.M" (US Chart No. 1 J 12.2: main constituent
    first, each qualifier written before the type in the same list position). A quality with no type
    ("10" alone) is labelled on its own; qualifiers beyond the last type go before the last type."""
    types = [_abbr(NATSUR, "NATSUR", c) for c in split_codes(natsur) if c]
    quals = [_abbr(NATQUA, "NATQUA", c) if c else "" for c in split_codes(natqua)]
    if not types:
        return ".".join(q for q in quals if q) or None
    last = len(types) - 1
    return ".".join("".join(quals[i:] if i == last else quals[i:i + 1]) + t for i, t in enumerate(types))


def weed_label(catwed: int | None) -> str:
    """The chart label of a weed or kelp feature; no category is weed, J 13.1 "weed (including kelp)"."""
    return "Wd" if catwed is None else _abbr(CATWED, "CATWED", str(catwed))
