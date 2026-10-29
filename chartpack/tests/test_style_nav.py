import json

from chartpack.enc.schema import LAYERS
from chartpack.style.nav import DEPTH_LAYERS, Depths, depth_filter, nav_style
from chartpack.style.validate import check_style_against_schema, check_style_sprites_glyphs

ICONS = {
    "buoy-can", "buoy-nun", "buoy-spherical", "buoy-pillar", "buoy-spar", "beacon-lateral", "beacon-cardinal",
    "beacon-generic", "light-flare", "rock-awash", "rock-submerged", "wreck-dangerous", "wreck-nondangerous",
    "obstruction", "isolated-danger",
}
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
    assert ids[-2:] == ["hazard", "hazard-danger"]


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
