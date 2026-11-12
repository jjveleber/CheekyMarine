import pytest

from chartpack.enc.schema import BATHY_LAYER_SPECS, LAYERS
from chartpack.style.fish import fish_style
from chartpack.style.nav import Depths, nav_style
from chartpack.style.palette import PALETTES
from chartpack.style.validate import check_style_against_schema


def _layer(style, lid):
    return next(l for l in style["layers"] if l["id"] == lid)


def test_fish_sources():
    s = fish_style("day")
    assert set(s["sources"]) == {"enc", "bathy", "dem", "bathy-coarse", "dem-coarse"}
    assert s["sources"]["dem"] == {"type": "raster-dem", "url": "mbtiles://dem", "encoding": "terrarium", "tileSize": 256}
    assert s["sources"]["bathy"] == {"type": "vector", "url": "mbtiles://bathy"}
    assert s["sources"]["dem-coarse"] == {**s["sources"]["dem"], "url": "mbtiles://dem-coarse"}
    assert s["sources"]["bathy-coarse"] == {"type": "vector", "url": "mbtiles://bathy-coarse"}
    assert s["sprite"] == "pack://sprites/fish"


def test_fish_hides_nav_clutter():
    s = fish_style("day")
    ids = {l["id"] for l in s["layers"]}
    assert not ids & {"depare-deep", "soundg-deep", "navaid"}
    assert {"hillshade", "contour-major", "contour-label", "water-base"} <= ids
    enc_layers = {l["source-layer"] for l in s["layers"] if l.get("source") == "enc"}
    assert enc_layers == {"depare", "lndare", "coalne", "light", "hazard", "seabed"}


def test_fish_layer_order():
    ids = [l["id"] for l in fish_style("night")["layers"]]
    assert ids[:2] == ["background", "water-base"] and ids[-1] == "hazard-danger"
    assert ids.index("hillshade") > max(i for i, x in enumerate(ids) if x.startswith("band-"))
    assert ids.index("lndare") > ids.index("hillshade") and ids.index("contour-enc") > ids.index("coalne")


def test_water_base_has_no_depth_filter():
    base = _layer(fish_style("day"), "water-base")
    assert "filter" not in base and base["source-layer"] == "depare"


def test_bands_are_one_unfiltered_fill_over_water_base():
    """The bathy tiles carry a complete band set per zoom range, so one layer draws every band."""
    s = fish_style("day")
    bands = [l for l in s["layers"] if l.get("source-layer") == "band" and l["source"] == "bathy"]
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
    assert md["depths"]["layers"] == ["hazard-danger", "hazard-danger-outline"] and md["depths"]["safety_m"] == Depths().safety_m
    assert "safety_contour_m" not in md and md["units"] == "ft" and md["palette"] == "day"


def test_fish_notice():
    notice = fish_style("day")["metadata"]["cheekymarine"]["notice"]
    assert notice == "Fishing chart: survey depths, approx. MLLW. Not certified for navigation."


def test_fish_schema():
    for palette in ("day", "dusk", "night"):
        assert check_style_against_schema(fish_style(palette), LAYERS + BATHY_LAYER_SPECS) == []


@pytest.mark.parametrize("palette", sorted(PALETTES))
@pytest.mark.parametrize("make", [fish_style, nav_style])
def test_text_halo_differs_from_text(make, palette):
    """A halo in the text colour hides the text (puget-north renders: fish-night contour labels were blobs)."""
    for layer in make(palette)["layers"]:
        paint = layer.get("paint", {})
        if "text-halo-color" in paint:
            assert paint["text-halo-color"] != paint["text-color"], layer["id"]


def test_every_band_has_a_fill_color():
    """Each band bands.py can produce, down to the deepest (1,000 ft and deeper), steps to a palette color."""
    from chartpack.bathy.contours import DEPTHS_FT

    band = _layer(fish_style("day"), "band-fill")
    expr = band["paint"]["fill-color"]
    assert expr[0] == "step"
    stops = expr[3::2]

    def color(depth_min):
        out = expr[2]
        for stop, c in zip(stops, expr[4::2]):
            if depth_min >= stop:
                out = c
        return out

    for lo in [0] + DEPTHS_FT:
        assert isinstance(color(lo), str) and color(lo).startswith("#"), lo
    assert color(1000) == color(300)


def test_fish_style_coarse_under_fine():
    """Every fine bathy layer has a -coarse twin on the coarse source, all of them below the first fine one."""
    s = fish_style("day")
    assert set(s["sources"]) == {"enc", "bathy", "dem", "bathy-coarse", "dem-coarse"}
    layers = s["layers"]
    ids = [l["id"] for l in layers]
    fine = [l for l in layers if l.get("source") in ("bathy", "dem")]
    coarse = [l for l in layers if l.get("source") in ("bathy-coarse", "dem-coarse")]
    assert [l["id"] for l in coarse] == [f"{l['id']}-coarse" for l in fine]
    first_fine = ids.index(fine[0]["id"])
    assert all(ids.index(l["id"]) < first_fine for l in coarse)
    for f, c in zip(fine, coarse):
        assert c["source"] == f"{f['source']}-coarse"
        assert {k: v for k, v in c.items() if k not in ("id", "source")} == {k: v for k, v in f.items() if k not in ("id", "source")}


def test_coarse_tiers_show_every_coarse_z12_level():
    """The coarse z12 band carries every level with its minzoom property: each such tier has a coarse layer
    that appears at that zoom (on the overzoomed z12 tiles) and keeps only that tier."""
    from chartpack.bathy.contours import DEPTHS_FT, MAJOR_FT, min_zoom

    layers = {l["id"]: l for l in fish_style("day")["layers"]}
    for n in sorted({max(min_zoom(ft), 12) for ft in DEPTHS_FT if ft not in MAJOR_FT}):
        for kind in ("contour-minor", "contour-label"):
            layer = layers[f"{kind}-z{n}-coarse"]
            assert layer["source"] == "bathy-coarse" and layer["minzoom"] == n
            assert ["==", ["get", "minzoom"], n] in layer["filter"]


@pytest.mark.parametrize("palette", sorted(PALETTES))
def test_fish_grade_layers_use_patterns(palette):
    """Plan 8 spec 6: the coarse survey and rough grades are marked by a light pattern over the coverage layer, on
    the fine and the coarse source; the patterns carry the palette in their names (baked colors)."""
    s = fish_style(palette)
    ids = [l["id"] for l in s["layers"]]
    for grade in ("coarse-survey", "rough"):
        for suffix, source in (("", "bathy"), ("-coarse", "bathy-coarse")):
            layer = _layer(s, f"grade-{grade}{suffix}")
            assert layer["type"] == "fill" and layer["source"] == source and layer["source-layer"] == "coverage"
            assert layer["filter"] == ["==", ["get", "grade"], grade]
            assert layer["paint"]["fill-pattern"] == f"pat-{grade}-{palette}"
            # over the depth shading, under the land
            assert ids.index(f"hillshade{suffix}") < ids.index(layer["id"]) < ids.index("lndare")


def test_fish_notices_has_bc_string():
    for palette in PALETTES:
        md = fish_style(palette)["metadata"]["cheekymarine"]
        assert md["notices"] == {"bc": "BC: CHS survey depths where available, rough elsewhere. Chart datum. Not for navigation."}
        assert md["notice"] == "Fishing chart: survey depths, approx. MLLW. Not certified for navigation."
