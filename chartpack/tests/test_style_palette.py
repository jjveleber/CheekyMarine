from chartpack.style.palette import PALETTES, TOKENS


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_every_palette_has_every_token():
    for name, p in PALETTES.items():
        assert set(p) == set(TOKENS), name


def test_night_water_is_dark():
    assert luminance(PALETTES["night"]["DEPDW"]) < 0.1
    assert luminance(PALETTES["day"]["DEPDW"]) > 0.9


def test_dusk_is_day_mixed_toward_black():
    assert PALETTES["dusk"]["CHWHT"] == "#8c8c8c"
    assert PALETTES["dusk"]["CHBLK"] == "#000000"
