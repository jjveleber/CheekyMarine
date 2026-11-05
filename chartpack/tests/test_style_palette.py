from chartpack.style.palette import PALETTES, TOKENS


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_every_palette_has_every_token():
    for name, p in PALETTES.items():
        assert set(p) == set(TOKENS), name


def test_owner_water_and_land_colours():
    assert PALETTES["day"]["DEPDW"] == "#F4EEE2" and PALETTES["night"]["DEPDW"] == "#000000"
    assert PALETTES["day"]["LANDA"] == "#EFD98A" and PALETTES["night"]["LANDA"] == "#180404"


def test_night_water_is_dark():
    day, night = PALETTES["day"]["DEPDW"], PALETTES["night"]["DEPDW"]
    assert luminance(night) < 0.15 and luminance(day) > 0.9
    assert int(day[1:3], 16) > int(day[5:7], 16)  # day deep water is warm
    assert int(night[1:3], 16) >= max(int(night[3:5], 16), int(night[5:7], 16))  # night leans red


def test_night_is_red_only():
    for token, colour in PALETTES["night"].items():
        assert int(colour[3:5], 16) <= 0x20 and int(colour[5:7], 16) <= 0x20, token
        assert int(colour[1:3], 16) >= int(colour[3:5], 16), token  # the red channel is the largest


def test_night_depth_fills_brighten_toward_shallow():
    night = PALETTES["night"]
    tints = [luminance(night[t]) for t in ("DEPDW", "DEPMD", "DEPMS", "DEPVS")]
    assert all(a < b for a, b in zip(tints, tints[1:]))


def test_day_depth_fills_unchanged():
    assert [PALETTES["day"][t] for t in ("DEPDW", "DEPMD", "DEPMS", "DEPVS")] == ["#F4EEE2", "#DCEEF9", "#B8DCF2", "#8EC3E6"]


def test_dusk_is_day_mixed_toward_black():
    assert PALETTES["dusk"]["CHWHT"] == "#8c8c8c"
    assert PALETTES["dusk"]["CHBLK"] == "#000000"


def test_night_ink_is_brighter_than_fills():
    night = PALETTES["night"]
    fills = max(int(night[t][1:3], 16) for t in ("DEPDW", "DEPMD", "DEPMS", "DEPVS", "DEPIT", "LANDA", "LANDF"))
    for token in ("CHGRD", "SNDG1", "SNDG2", "CHBLK", "CHWHT", "CSTLN", "OUTLW", "NINFO"):
        red = int(night[token][1:3], 16)
        assert red >= 0xA0 and red > fills, token


def test_night_amber_changes_text_navaid_fill_and_coastline_tokens():
    from chartpack.style.palette import night_palette

    red, amber = night_palette("red"), night_palette("amber")
    assert red == PALETTES["night"]
    assert {t for t in TOKENS if red[t] != amber[t]} == {
        "TXTSH", "TXTDP", "LITGN", "LITYW", "LITWH", "DEPMD", "DEPMS", "DEPVS", "DEPIT", "LANDA", "LANDF", "CSTLN"}
    assert (amber["LITGN"], amber["LITYW"], amber["LITWH"]) == ("#20A040", "#D0B000", "#C0C0C0")
    for token in ("TXTSH", "TXTDP"):
        r, g, b = (int(amber[token][i : i + 2], 16) for i in (1, 3, 5))
        assert r >= 0xC0 and 0x70 <= g <= 0xA8 and b <= 0x20, token


def test_night_amber_fills_brighten_toward_shore():
    from chartpack.style.palette import night_palette

    amber = night_palette("amber")

    def lum(token):
        r, g, b = (int(amber[token][i : i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    chain = [lum(t) for t in ("DEPDW", "DEPMD", "DEPMS", "DEPVS")]
    assert chain == sorted(set(chain))
    assert lum("DEPIT") > lum("DEPVS") and lum("LANDA") > lum("DEPVS")
    for token in ("DEPIT", "LANDA", "LANDF"):
        assert int(amber[token][3:5], 16) <= 0x28 and int(amber[token][5:7], 16) <= 0x28, token


def test_white_navaids_use_litwh():
    from chartpack.style.fish import fish_style
    from chartpack.style.nav import nav_style

    day = PALETTES["day"]
    assert day["LITWH"] == day["CHWHT"] and PALETTES["night"]["LITWH"] == PALETTES["night"]["CHWHT"]
    layers = [l for l in nav_style("day")["layers"] if "match" in str(l.get("paint", {}).get("icon-color", ""))]
    assert layers
    for layer in layers:
        expr = layer["paint"]["icon-color"]
        assert expr[2:4] == ["1", day["LITWH"]], layer["id"]
    hill = next(l for l in fish_style("day")["layers"] if l["type"] == "hillshade")
    assert hill["paint"]["hillshade-highlight-color"] == day["CHWHT"]


def test_text_layers_use_text_tokens():
    from chartpack.style.fish import fish_style
    from chartpack.style.nav import nav_style

    day = PALETTES["day"]
    assert day["TXTSH"] == day["SNDG1"] and day["TXTDP"] == day["SNDG2"]
    for style in (nav_style("day"), fish_style("day")):
        for layer in style["layers"]:
            if layer["type"] == "symbol" and "text-field" in layer.get("layout", {}):
                assert layer["paint"]["text-color"] in (day["TXTSH"], day["TXTDP"]), layer["id"]
