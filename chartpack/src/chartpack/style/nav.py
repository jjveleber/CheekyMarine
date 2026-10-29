"""The generated navigation style: a MapLibre style v8 dict over the enc vector source."""

from dataclasses import dataclass

from chartpack.style.palette import PALETTES

FEET_PER_METRE = 3.28084


@dataclass(frozen=True)
class Depths:
    shallow_m: float = 1.8288
    safety_m: float = 3.048
    deep_m: float = 9.144


# The only layers whose filters may carry depth thresholds.
DEPTH_LAYERS = (
    "depare-deep", "depare-medium", "depare-shallow", "depare-vshallow",
    "depcnt-safety", "soundg-shallow", "soundg-deep", "hazard-danger",
)
# hazard-danger shows only during route navigation, which the plotter does not have yet, so the
# shipped styles carry no such layer (spec 6.6 owner revisions); its filter stays for plan 3.
SHIPPED_DEPTH_LAYERS = tuple(layer for layer in DEPTH_LAYERS if layer != "hazard-danger")

BUOY_CLASSES = ["BOYLAT", "BOYCAR", "BOYSAW", "BOYISD", "BOYSPP"]


def _num(attribute: str) -> list:
    return ["to-number", ["get", attribute]]


def depth_filter(layer: str, depths: Depths, safety_contour_m: float | None = None) -> list:
    """The filter expression for one DEPTH_LAYERS layer."""
    safety_contour = depths.safety_m if safety_contour_m is None else safety_contour_m
    filters = {
        "depare-deep": [">=", _num("DRVAL1"), depths.deep_m],
        "depare-medium": ["all", [">=", _num("DRVAL1"), depths.safety_m], ["<", _num("DRVAL1"), depths.deep_m]],
        "depare-shallow": ["all", [">=", _num("DRVAL1"), depths.shallow_m], ["<", _num("DRVAL1"), depths.safety_m]],
        "depare-vshallow": ["<", _num("DRVAL1"), depths.shallow_m],
        "depcnt-safety": ["==", _num("VALDCO"), safety_contour],
        "soundg-shallow": ["<", _num("depth"), depths.safety_m],
        "soundg-deep": [">=", _num("depth"), depths.safety_m],
        # unknown or shallower than safety depth, or awash/dry/covers-and-uncovers (WATLEV 1, 2, 4, 5);
        # WATLEV is an int in the tiles and `in` does not coerce, so the literals are ints
        "hazard-danger": [
            "any",
            ["!", ["has", "VALSOU"]],
            ["<", _num("VALSOU"), depths.safety_m],
            ["in", ["coalesce", ["get", "WATLEV"], 0], ["literal", [1, 2, 4, 5]]],
        ],
    }
    return filters[layer]


def _is_class(*classes: str) -> list:
    return ["in", ["get", "class"], ["literal", list(classes)]]


def _first_colour_code() -> list:
    # COLOUR is a comma-joined string such as "3,1". MapLibre has no split, so cut at the first comma
    # (a plain 1-char slice would turn "10" into "1").
    colour = ["to-string", ["coalesce", ["get", "COLOUR"], ""]]
    return ["case", ["in", ",", colour], ["slice", colour, 0, ["index-of", ",", colour]], colour]


def _colour_by_code(p: dict, default: str) -> list:
    return [
        "match", _first_colour_code(),
        "1", p["CHWHT"], "2", p["CHBLK"], "3", p["LITRD"], "4", p["LITGN"], "6", p["LITYW"],
        p[default],
    ]


def _fill(layer_id: str, source_layer: str, colour: str, filter_=None, opacity: float = 1.0) -> dict:
    layer = {"id": layer_id, "type": "fill", "source": "enc", "source-layer": source_layer,
             "paint": {"fill-color": colour, "fill-opacity": opacity}}
    if filter_ is not None:
        layer["filter"] = filter_
    return layer


def _line(layer_id: str, source_layer: str, colour: str, width: float, filter_=None, dash=None) -> dict:
    layer = {"id": layer_id, "type": "line", "source": "enc", "source-layer": source_layer,
             "paint": {"line-color": colour, "line-width": width}}
    if filter_ is not None:
        layer["filter"] = filter_
    if dash:
        layer["paint"]["line-dasharray"] = dash
    return layer


def _depth_areas(p: dict, depths: Depths) -> list[dict]:
    colours = {"depare-deep": p["DEPDW"], "depare-medium": p["DEPMD"],
               "depare-shallow": p["DEPMS"], "depare-vshallow": p["DEPVS"]}
    layers = [_fill(lid, "depare", colour, depth_filter(lid, depths)) for lid, colour in colours.items()]
    layers.append(_fill("depare-intertidal", "depare", p["DEPIT"], ["<", _num("DRVAL1"), 0]))
    return layers


def _land_and_areas(p: dict) -> list[dict]:
    return [
        _fill("lndare", "lndare", p["LANDA"]),
        _line("coalne", "coalne", p["CSTLN"], 1.2),
        _fill("area-achare", "area", p["ADINF"], _is_class("ACHARE"), 0.25),
        _line("area-resare", "area", p["CHMGD"], 1, _is_class("RESARE"), [4, 2]),
        _fill("area-tsslpt", "area", p["TRFCD"], _is_class("TSSLPT"), 0.25),
        _line("line-cable", "line", p["CHMGD"], 1, _is_class("CBLSUB", "CBLARE", "PIPSOL", "PIPARE"), [4, 2]),
        _line("line-route", "line", p["CHMGD"], 1, _is_class("FERYRT", "NAVLNE", "RECTRC", "TSSLPT")),
    ]


def _contours(p: dict, depths: Depths, safety_contour_m: float | None) -> list[dict]:
    return [
        _line("depcnt", "depcnt", p["CHGRD"], 0.8),
        _line("depcnt-safety", "depcnt", p["CHBLK"], 2, depth_filter("depcnt-safety", depths, safety_contour_m)),
    ]


_KELP = ["all", ["==", ["get", "class"], "WEDKLP"], ["==", ["get", "CATWED"], 1]]


def seabed_layers(p: dict) -> list[dict]:
    """Bottom composition labels (spec 6.10): chart abbreviations in grey ink, smaller than soundings and
    drawn below them, so a sounding wins where the two collide. Kelp gets its Chart No. 1 symbol. USGS
    CMECS substrate polygons get a thin outline and their label, never a fill, which would change the
    depth colours."""
    text = {"text-field": ["get", "label"], "text-font": ["Noto Sans Regular"], "text-size": 10}
    paint = {"text-color": p["CHGRD"], "text-halo-color": p["DEPDW"], "text-halo-width": 1.5}
    return [
        {"id": "seabed-cmecs", "type": "line", "source": "enc", "source-layer": "seabed",
         "filter": ["==", ["get", "class"], "CMECS"],
         "paint": {"line-color": p["CHGRD"], "line-width": 0.5, "line-dasharray": [2, 2]}},  # dashed: not a contour
        {"id": "seabed", "type": "symbol", "source": "enc", "source-layer": "seabed", "filter": ["!", _KELP],
         "layout": text, "paint": paint},
        {"id": "seabed-kelp", "type": "symbol", "source": "enc", "source-layer": "seabed", "filter": _KELP,
         "layout": {**text, "icon-image": "kelp", "text-anchor": "left", "text-offset": [0.9, 0]},
         "paint": {**paint, "icon-color": p["CHGRD"]}},
    ]


def _soundings(p: dict, depths: Depths, units: str) -> list[dict]:
    text_field = ["get", "depth"] if units == "m" else ["to-string", ["round", ["*", _num("depth"), FEET_PER_METRE]]]
    layers = []
    for lid, colour in (("soundg-deep", p["SNDG2"]), ("soundg-shallow", p["SNDG1"])):
        layers.append({
            "id": lid, "type": "symbol", "source": "enc", "source-layer": "soundg",
            "filter": depth_filter(lid, depths),
            "layout": {"text-field": text_field, "text-font": ["Noto Sans Regular"], "text-size": 11},
            "paint": {"text-color": colour, "text-halo-color": p["DEPDW"], "text-halo-width": 1},
        })
    return layers


def _buoy_icon() -> list:
    return ["match", _num_or_zero("BOYSHP"),
            1, "buoy-nun", 2, "buoy-can", 3, "buoy-spherical", 4, "buoy-pillar", 5, "buoy-spar",
            "buoy-pillar"]


def _num_or_zero(attribute: str) -> list:
    return ["to-number", ["get", attribute], 0]


def _navaids_and_lights(p: dict) -> list[dict]:
    navaid_icon = ["match", ["get", "class"],
                   BUOY_CLASSES, _buoy_icon(),
                   "BCNLAT", "beacon-lateral", "BCNCAR", "beacon-cardinal",
                   "beacon-generic"]
    return [
        {"id": "navaid", "type": "symbol", "source": "enc", "source-layer": "navaid",
         "layout": {"icon-image": navaid_icon, "icon-allow-overlap": True},
         "paint": {"icon-color": _colour_by_code(p, "CHGRD")}},
        {"id": "light", "type": "symbol", "source": "enc", "source-layer": "light",
         "layout": {"icon-image": "light-flare", "icon-allow-overlap": True},
         "paint": {"icon-color": _colour_by_code(p, "LITYW")}},
        {"id": "area-names", "type": "symbol", "source": "enc", "source-layer": "area",
         "filter": ["all", _is_class("SEAARE"), ["has", "OBJNAM"]],
         "layout": {"text-field": ["get", "OBJNAM"], "text-font": ["Noto Sans Bold"], "text-size": 13},
         "paint": {"text-color": p["CHGRD"], "text-halo-color": p["DEPDW"], "text-halo-width": 1}},
    ]


def _hazards(p: dict) -> list[dict]:
    rock = ["match", _num_or_zero("WATLEV"), [4, 5], "rock-awash", "rock-submerged"]
    wreck = ["match", _num_or_zero("CATWRK"), 1, "wreck-nondangerous", "wreck-dangerous"]
    plain = ["match", ["get", "class"], "UWTROC", rock, "WRECKS", wreck, "obstruction"]
    return [
        {"id": "hazard", "type": "symbol", "source": "enc", "source-layer": "hazard",
         "layout": {"icon-image": plain, "icon-allow-overlap": True},
         "paint": {"icon-color": p["CHBLK"]}},
    ]


def nav_style(palette: str, depths: Depths = Depths(), *, units: str = "ft", safety_contour_m: float | None = None) -> dict:
    """A complete MapLibre style v8 dict.

    safety_contour_m is the contour drawn as the safety contour (the next deeper available VALDCO,
    computed at build time from the cells); None means the safety depth itself.
    """
    p = PALETTES[palette]
    layers = [
        {"id": "background", "type": "background", "paint": {"background-color": p["NODTA"]}},
        *_depth_areas(p, depths),
        *_land_and_areas(p),
        *_contours(p, depths, safety_contour_m),
        *seabed_layers(p),
        *_soundings(p, depths, units),
        *_navaids_and_lights(p),
        *_hazards(p),
    ]
    return {
        "version": 8,
        "name": f"CheekyMarine nav {palette}",
        "metadata": {"cheekymarine": {
            "depths": {"shallow_m": depths.shallow_m, "safety_m": depths.safety_m,
                       "deep_m": depths.deep_m, "layers": list(SHIPPED_DEPTH_LAYERS)},
            "safety_contour_m": depths.safety_m if safety_contour_m is None else safety_contour_m,
            "units": units,
            "palette": palette,
            "notice": "Derived from NOAA ENC. Not an official chart. Not certified for navigation.",
        }},
        "sources": {"enc": {"type": "vector", "url": "mbtiles://enc"}},
        "sprite": "pack://sprites/nav",
        "glyphs": "pack://glyphs/{fontstack}/{range}.pbf",
        "layers": layers,
    }
