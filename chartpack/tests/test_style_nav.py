import json

import pytest

from chartpack.enc.schema import BATHY_LAYER_SPECS, LAYERS
from chartpack.style.fish import fish_style
from chartpack.style.nav import DEPTH_LAYERS, HAZARD_SHAPES, Depths, depth_filter, nav_style
from chartpack.style.palette import PALETTES
from chartpack.style.validate import check_style_against_schema, check_style_sprites_glyphs

ICONS = {
    "buoy-can", "buoy-nun", "buoy-spherical", "buoy-pillar", "buoy-spar", "beacon-lateral", "beacon-cardinal",
    "beacon-generic", "light-flare", "isolated-danger", "kelp", "resare-tick",
} | {f"hazard-{shape}{danger}-{palette}" for shape in HAZARD_SHAPES for danger in ("", "-danger") for palette in PALETTES}
FONTS = {"Noto Sans Regular", "Noto Sans Bold"}


def test_style_is_v8_with_contract_sources():
    s = nav_style("day")
    assert s["version"] == 8 and s["sources"]["enc"] == {"type": "vector", "url": "mbtiles://enc"}
    assert s["sprite"] == "pack://sprites/nav" and s["glyphs"] == "pack://glyphs/{fontstack}/{range}.pbf"


def test_depth_layers_exist_and_only_they_carry_thresholds():
    s = nav_style("day")
    ids = {l["id"] for l in s["layers"]}
    assert set(DEPTH_LAYERS) <= ids
    assert s["metadata"]["cheekymarine"]["depths"] == {"shallow_m": 1.8288, "safety_m": 3.048, "deep_m": 9.144, "layers": list(DEPTH_LAYERS)}
    for l in s["layers"]:
        if l["id"] not in DEPTH_LAYERS:
            text = json.dumps(l)
            assert "1.8288" not in text and "3.048" not in text and "9.144" not in text


def test_depth_filters():
    d = Depths()
    assert depth_filter("depare-deep", d) == [">=", ["to-number", ["get", "DRVAL1"]], 9.144]
    assert depth_filter("depare-vshallow", d) == ["<", ["to-number", ["get", "DRVAL1"]], 1.8288]
    assert depth_filter("hazard-danger", d) == ["any", ["!", ["has", "VALSOU"]], ["<", ["to-number", ["get", "VALSOU"]], 3.048], ["in", ["coalesce", ["get", "WATLEV"], 0], ["literal", [1, 2, 4, 5]]]]  # ints: the reader stores S-57 enumerations as ints


def _ev(e, props):
    """Tiny evaluator for the expression subset used by the hazard-danger filter."""
    if not isinstance(e, list):
        return e
    op, a = e[0], e[1:]
    if op == "literal":
        return a[0]
    if op == "get":
        return props.get(a[0])
    if op == "has":
        return a[0] in props
    if op == "coalesce":
        return next((v for v in (_ev(x, props) for x in a) if v is not None), None)
    if op == "to-number":
        return float(_ev(a[0], props))
    if op == "any":  # short-circuits like MapLibre, so to-number never sees a missing VALSOU
        return any(_ev(x, props) for x in a)
    vals = [_ev(x, props) for x in a]
    if op == "!":
        return not vals[0]
    if op == "<":
        return vals[0] < vals[1]
    if op == "==":
        return vals[0] == vals[1]
    if op == "in":
        return vals[0] in vals[1]
    raise NotImplementedError(op)


def test_hazard_danger_filter_behaviour():
    f = depth_filter("hazard-danger", Depths())
    assert _ev(f, {"WATLEV": 1, "VALSOU": "20"}) is True
    assert _ev(f, {"WATLEV": 3, "VALSOU": "20"}) is False
    assert _ev(f, {"WATLEV": 3}) is True
    assert _ev(f, {"WATLEV": 3, "VALSOU": "2"}) is True


def test_feet_labels():
    s = nav_style("day")
    expected = ["to-string", ["round", ["*", ["to-number", ["get", "depth"]], 3.28084]]]
    for lid in ("soundg-deep", "soundg-shallow"):
        assert next(l for l in s["layers"] if l["id"] == lid)["layout"]["text-field"] == expected
    m = nav_style("day", units="m")
    assert next(l for l in m["layers"] if l["id"] == "soundg-deep")["layout"]["text-field"] == ["get", "depth"]


def test_style_references_only_schema():
    assert check_style_against_schema(nav_style("day"), LAYERS) == []


def test_schema_check_flags_unknown_names():
    s = {"layers": [{"id": "x", "source-layer": "nope"}, {"id": "y", "source-layer": "depcnt", "filter": ["has", "BOGUS"]}]}
    assert len(check_style_against_schema(s, LAYERS)) == 2


def test_three_palettes_same_layers():
    assert [l["id"] for l in nav_style("day")["layers"]] == [l["id"] for l in nav_style("night")["layers"]]


def test_hazards_above_everything():
    ids = [l["id"] for l in nav_style("day")["layers"]]
    assert ids[-4:] == ["hazard-outline", "hazard-danger-outline", "hazard", "hazard-danger"]


def test_background_is_no_data():
    for palette in PALETTES:
        for s in (nav_style(palette), fish_style(palette)):
            bg = s["layers"][0]
            assert bg["type"] == "background" and bg["paint"]["background-color"] == PALETTES[palette]["NODTA"]


def _layer(style, lid):
    return next(l for l in style["layers"] if l["id"] == lid)


STYLES = [(make, palette) for make in (nav_style, fish_style) for palette in sorted(PALETTES)]


@pytest.mark.parametrize("make,palette", STYLES)
def test_hazard_danger_ring_is_shipped(make, palette):
    """R32/R34: the red danger ring is back, on the hazard-danger filter, which the app's safety depth moves."""
    s = make(palette)
    for lid in ("hazard-danger", "hazard-danger-outline"):
        assert _layer(s, lid)["filter"] == depth_filter("hazard-danger", Depths())
        assert lid in s["metadata"]["cheekymarine"]["depths"]["layers"]
    deeper = make(palette, Depths(safety_m=5.0))
    assert _layer(deeper, "hazard-danger")["filter"] == depth_filter("hazard-danger", Depths(safety_m=5.0))
    assert depth_filter("hazard-danger-outline", Depths()) == depth_filter("hazard-danger", Depths())


def test_fish_ships_only_the_hazard_depth_layers():
    assert fish_style("day")["metadata"]["cheekymarine"]["depths"]["layers"] == ["hazard-danger", "hazard-danger-outline"]


@pytest.mark.parametrize("make,palette", STYLES)
def test_hazard_marks_one_shape_per_class_fixed_size(make, palette):
    """R34: one black mark per class (no WATLEV or CATWRK variants); the danger layer shows the same mark in its
    red ring as one image, so the ring and the mark always show or hide together."""
    s = make(palette)
    for lid, suffix in (("hazard", ""), ("hazard-danger", "-danger")):
        layout = _layer(s, lid)["layout"]
        assert layout["icon-image"] == ["match", ["get", "class"],
                                        "UWTROC", f"hazard-rock{suffix}-{palette}",
                                        "WRECKS", f"hazard-wreck{suffix}-{palette}",
                                        f"hazard-obstruction{suffix}-{palette}"]
        assert "icon-size" not in layout  # one size at every zoom: the sprite image is drawn at 1:1


@pytest.mark.parametrize("make,palette", STYLES)
def test_hazard_declutter_below_z15(make, palette):
    """R32: below z15 overlapping hazards hide each other; from z15 every hazard is drawn. Hazards are the top
    symbol layers, so they are placed first and no other symbol hides them."""
    s = make(palette)
    by_zoom = ["step", ["zoom"], False, 15, True]
    for lid in ("hazard", "hazard-danger"):
        layout = _layer(s, lid)["layout"]
        assert layout["icon-allow-overlap"] == by_zoom and layout["icon-ignore-placement"] == by_zoom
        assert layout["icon-padding"] == 0
    ids = [l["id"] for l in s["layers"]]
    symbols = [l["id"] for l in s["layers"] if l["type"] == "symbol"]
    assert symbols[-2:] == ["hazard", "hazard-danger"] and ids[-1] == "hazard-danger"


@pytest.mark.parametrize("make,palette", STYLES)
def test_hazard_lines_and_areas_get_a_dotted_outline(make, palette):
    """R35: line and area hazards: a thin dotted CHBLK outline, DNGHL where the danger rule holds."""
    s, p = make(palette), PALETTES[palette]
    plain, danger = _layer(s, "hazard-outline"), _layer(s, "hazard-danger-outline")
    for layer, colour in ((plain, p["CHBLK"]), (danger, p["DNGHL"])):
        assert layer["type"] == "line" and layer["source-layer"] == "hazard"
        assert layer["paint"]["line-color"] == colour and layer["paint"]["line-width"] <= 1
        assert layer["paint"]["line-dasharray"] == [1, 2]
    assert "filter" not in plain  # a line layer draws only the lines and polygon edges


def test_resare_is_dashed_outline_with_ticks():
    """R31: RESARE outline CHMGD dashed [8, 4] (cables keep [4, 2]) with T ticks along it pointing inside."""
    s = nav_style("day")
    resare = [l for l in s["layers"] if "RESARE" in json.dumps(l.get("filter", []))]
    assert [l["type"] for l in resare] == ["line", "symbol"]
    line, ticks = resare
    assert line["paint"]["line-color"] == PALETTES["day"]["CHMGD"] and line["paint"]["line-dasharray"] == [8, 4]
    assert _layer(s, "line-cable")["paint"]["line-dasharray"] == [4, 2]
    assert ticks["filter"] == line["filter"] and ticks["source-layer"] == "area"
    assert ticks["layout"]["symbol-placement"] == "line" and ticks["layout"]["symbol-spacing"] == 100
    assert ticks["layout"]["icon-image"] == "resare-tick" and ticks["paint"]["icon-color"] == PALETTES["day"]["CHMGD"]


def test_safety_contour_metadata():
    assert nav_style("day")["metadata"]["cheekymarine"]["safety_contour_m"] == 3.048
    s = nav_style("day", safety_contour_m=3.5)
    assert s["metadata"]["cheekymarine"]["safety_contour_m"] == 3.5
    assert next(l for l in s["layers"] if l["id"] == "depcnt-safety")["filter"][-1] == 3.5


def test_sprites_and_glyphs_checked():
    s = nav_style("day")
    assert check_style_sprites_glyphs(s, {k: {} for k in ICONS}, FONTS) == []
    assert check_style_sprites_glyphs(s, {k: {} for k in ICONS - {"obstruction"}}, FONTS - {"Noto Sans Bold"}) != []


def test_nav_notice():
    assert nav_style("day")["metadata"]["cheekymarine"]["notice"] == (
        "Derived from NOAA ENC. Not an official chart. Not certified for navigation."
    )


def test_styles_show_seabed():
    for palette in PALETTES:
        for s in (nav_style(palette), fish_style(palette)):
            ids = [l["id"] for l in s["layers"]]
            seabed = [l for l in s["layers"] if l.get("source-layer") == "seabed"]
            assert {l["id"] for l in seabed} == {"seabed", "seabed-kelp", "seabed-cmecs"}
            # CMECS substrate polygons: a thin grey outline plus their label, never a fill (spec 6.10)
            outline = next(l for l in seabed if l["id"] == "seabed-cmecs")
            assert outline["type"] == "line" and outline["filter"] == ["==", ["get", "class"], "CMECS"]
            assert outline["paint"]["line-color"] == PALETTES[palette]["CHGRD"] and outline["paint"]["line-width"] <= 0.75
            assert not [l for l in seabed if l["type"] == "fill"]
            assert ids.index("seabed-cmecs") < ids.index("seabed")
            text = next(l for l in seabed if l["id"] == "seabed")
            assert text["type"] == "symbol" and text["layout"]["text-field"] == ["get", "label"]
            assert text["layout"]["text-font"] == ["Noto Sans Regular"] and text["paint"]["text-color"] == PALETTES[palette]["SNDG2"]
            kelp = next(l for l in seabed if l["id"] == "seabed-kelp")
            assert kelp["layout"]["icon-image"] == "kelp" and kelp["layout"]["text-field"] == ["get", "label"]
            assert kelp["filter"] == ["all", ["==", ["get", "class"], "WEDKLP"], ["==", ["get", "CATWED"], 1]]
            assert text["filter"] == ["!", kelp["filter"]]
            for layer in seabed:
                if layer["type"] == "symbol":
                    assert layer["layout"]["text-size"] < 11  # soundings are 11
                assert ids.index(layer["id"]) < ids.index("hazard")
                if layer["type"] == "symbol":
                    assert layer["paint"]["text-color"] == PALETTES[palette]["SNDG2"]  # R30
                    assert layer["layout"]["text-size"] == 10 and layer["paint"]["text-halo-width"] == 1.5
                if "soundg-deep" in ids:
                    assert ids.index(layer["id"]) < min(ids.index("soundg-deep"), ids.index("soundg-shallow"))
            assert check_style_against_schema(s, LAYERS + BATHY_LAYER_SPECS) == []
            assert check_style_sprites_glyphs(s, {k: {} for k in ICONS}, FONTS) == []


@pytest.mark.parametrize("make,palette", STYLES)
def test_seabed_labels_thin_below_z15(make, palette):
    """R37: below z15 bottom labels keep about 40 px apart (20 px padding each); from z15 the default 2 px."""
    s = make(palette)
    for lid in ("seabed", "seabed-kelp"):
        assert _layer(s, lid)["layout"]["text-padding"] == ["step", ["zoom"], 20, 15, 2]


def _sort_key(expr, props):
    if expr[0] != "case":
        raise NotImplementedError(expr)
    for cond, out in zip(expr[1:-1:2], expr[2:-1:2]):
        if _ev(cond, props):
            return -float(props["extent"]) if out == ["-", ["to-number", ["get", "extent"]]] else out
    return expr[-1]


def test_seabed_sort_key_areas_by_size_then_enc_points_then_samples():
    """R37: symbol-sort-key places areas first (bigger first), then ENC points, then usSEABED samples."""
    for lid in ("seabed", "seabed-kelp"):
        key = _layer(nav_style("day"), lid)["layout"]["symbol-sort-key"]
        assert key == _layer(fish_style("day"), lid)["layout"]["symbol-sort-key"]
        ranked = [_sort_key(key, props) for props in (
            {"src": "usgs-cmecs", "extent": "0.05"}, {"src": "enc", "extent": "0.01"},
            {"src": "enc"}, {"src": "usseabed"})]
        assert ranked == sorted(ranked) and len(set(ranked)) == 4
