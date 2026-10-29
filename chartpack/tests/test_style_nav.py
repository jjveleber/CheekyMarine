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
    assert depth_filter("hazard-danger", d) == ["any", ["!", ["has", "VALSOU"]], ["<", ["to-number", ["get", "VALSOU"]], 3.048], ["in", ["get", "WATLEV"], ["literal", ["1", "2", "4", "5"]]]]


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
