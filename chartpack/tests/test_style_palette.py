from chartpack.style.palette import PALETTES, TOKENS


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_every_palette_has_every_token():
    for name, p in PALETTES.items():
        assert set(p) == set(TOKENS), name


def test_owner_water_and_land_colours():
    assert PALETTES["day"]["DEPDW"] == "#F4EEE2" and PALETTES["night"]["DEPDW"] == "#18253A"
    assert PALETTES["day"]["LANDA"] == "#EFD98A" and PALETTES["night"]["LANDA"] == "#3A3317"


def test_night_water_is_dark():
    day, night = PALETTES["day"]["DEPDW"], PALETTES["night"]["DEPDW"]
    assert luminance(night) < 0.15 and luminance(day) > 0.9
    assert int(day[1:3], 16) > int(day[5:7], 16)  # day deep water is warm
    assert int(night[5:7], 16) > int(night[1:3], 16)  # night deep water leans blue


def test_night_depth_fills_lighten_toward_shallow():
    """R29: night DEPMD #15304C, so the night tints get lighter from deep to very shallow."""
    night = PALETTES["night"]
    assert night["DEPMD"] == "#15304C"
    tints = [luminance(night[t]) for t in ("DEPDW", "DEPMD", "DEPMS", "DEPVS")]
    assert tints == sorted(tints) and len(set(tints)) == 4


def test_day_depth_fills_unchanged():
    assert [PALETTES["day"][t] for t in ("DEPDW", "DEPMD", "DEPMS", "DEPVS")] == ["#F4EEE2", "#DCEEF9", "#B8DCF2", "#8EC3E6"]


def test_dusk_is_day_mixed_toward_black():
    assert PALETTES["dusk"]["CHWHT"] == "#8c8c8c"
    assert PALETTES["dusk"]["CHBLK"] == "#000000"
