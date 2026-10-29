from chartpack.enc.schema import BATHY_LAYER_SPECS, LAYERS
from chartpack.style.fish import fish_style
from chartpack.style.nav import Depths
from chartpack.style.validate import check_style_against_schema


def _layer(style, lid):
    return next(l for l in style["layers"] if l["id"] == lid)


def test_fish_sources():
    s = fish_style("day")
    assert set(s["sources"]) == {"enc", "bathy", "dem"}
    assert s["sources"]["dem"] == {"type": "raster-dem", "url": "mbtiles://dem", "encoding": "terrarium", "tileSize": 256}
    assert s["sources"]["bathy"] == {"type": "vector", "url": "mbtiles://bathy"}
    assert s["sprite"] == "pack://sprites/fish"


def test_fish_hides_nav_clutter():
    s = fish_style("day")
    ids = {l["id"] for l in s["layers"]}
    assert not ids & {"depare-deep", "soundg-deep", "navaid"}
    assert {"hillshade", "contour-major", "contour-label", "water-base"} <= ids and "hazard-danger" not in ids
    enc_layers = {l["source-layer"] for l in s["layers"] if l.get("source") == "enc"}
    assert enc_layers == {"depare", "lndare", "coalne", "light", "hazard", "seabed"}


def test_fish_layer_order():
    ids = [l["id"] for l in fish_style("night")["layers"]]
    assert ids[:2] == ["background", "water-base"] and ids[-1] == "hazard"
    assert ids.index("hillshade") > max(i for i, x in enumerate(ids) if x.startswith("band-"))
    assert ids.index("lndare") > ids.index("hillshade") and ids.index("contour-enc") > ids.index("coalne")


def test_water_base_has_no_depth_filter():
    base = _layer(fish_style("day"), "water-base")
    assert "filter" not in base and base["source-layer"] == "depare"


def test_bands_are_one_unfiltered_fill_over_water_base():
    """The bathy tiles carry a complete band set per zoom range, so one layer draws every band."""
    s = fish_style("day")
    bands = [l for l in s["layers"] if l.get("source-layer") == "band"]
    assert [l["id"] for l in bands] == ["band-fill"]
    assert bands[0]["type"] == "fill" and "filter" not in bands[0] and "minzoom" not in bands[0]
    ids = [l["id"] for l in s["layers"]]
    assert ids.index("water-base") < ids.index("band-fill")


def test_hillshade_paint():
    p = _layer(fish_style("day"), "hillshade")
    assert p["source"] == "dem" and p["paint"]["hillshade-exaggeration"] == 0.5
    assert p["paint"]["hillshade-illumination-direction"] == 335


def test_contour_layers():
    s = fish_style("day")
    assert _layer(s, "contour-enc")["filter"] == ["==", ["get", "source"], "enc"]
    assert _layer(s, "contour-enc")["paint"]["line-dasharray"]
    assert _layer(s, "contour-major")["paint"]["line-width"] == 1.2
    label = _layer(s, "contour-label")
    assert label["layout"]["symbol-placement"] == "line"
    assert label["layout"]["text-field"] == ["to-string", ["get", "depth_ft"]]
    assert label["layout"]["text-font"] == ["Noto Sans Bold"] and label["paint"]["text-halo-width"] == 1.5


def test_thinning_uses_layer_minzoom_not_zoom_in_filters():
    s = fish_style("day")
    thinned = [l for l in s["layers"] if l["id"].startswith(("contour-minor-z", "contour-label-z"))]
    assert thinned
    for l in thinned:
        assert "'zoom'" not in repr(l["filter"])
        tests = l["filter"][1:] if l["filter"][0] == "all" else [l["filter"]]
        assert ["==", ["get", "minzoom"], l["minzoom"]] in tests


def test_fish_depth_layers_metadata():
    md = fish_style("day")["metadata"]["cheekymarine"]
    assert md["depths"]["layers"] == [] and md["depths"]["safety_m"] == Depths().safety_m
    assert "safety_contour_m" not in md and md["units"] == "ft" and md["palette"] == "day"


def test_fish_notice():
    notice = fish_style("day")["metadata"]["cheekymarine"]["notice"]
    assert notice == "Fishing chart: survey depths, approx. MLLW. Not certified for navigation."


def test_fish_schema():
    for palette in ("day", "dusk", "night"):
        assert check_style_against_schema(fish_style(palette), LAYERS + BATHY_LAYER_SPECS) == []
