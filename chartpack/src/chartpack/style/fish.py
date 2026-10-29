"""The generated fishing style: bathy bands, hillshade and contours over a thin ENC base.

Zoom thinning: MapLibre evaluates layer filters while parsing a tile, so a filter cannot follow
the map zoom (["zoom"] is only valid as the top-level input of a step or interpolate in a paint
or layout expression, and then it cannot be combined with a per-feature property). The
`minzoom` feature property is therefore matched with one layer per tier, each carrying the
layer `minzoom`: the layer appears at that zoom and the filter keeps only that tier's features.
"""

from chartpack.bathy.contours import BANDS, DEPTHS_FT, FINE_FT, MAJOR_FT, min_zoom
from chartpack.style.nav import (
    HAZARD_DEPTH_LAYERS,
    Depths,
    _hazards,
    _land_and_areas,
    _navaids_and_lights,
    seabed_layers,
)
from chartpack.style.palette import PALETTES

NOTICE = "Fishing chart: survey depths, approx. MLLW. Not certified for navigation."

# Tiers of the `minzoom` feature property: minor contours carry max(min_zoom, band low zoom).
# Bands need no tiers: the tiles hold one complete band set per zoom range (bands_by_zoom).
MINOR_TIERS = sorted({max(min_zoom(ft), lo) for ft in DEPTHS_FT + FINE_FT if ft not in MAJOR_FT for lo, hi, _ in BANDS if min_zoom(ft) <= hi})


def _tier(n: int) -> list:
    return ["==", ["get", "minzoom"], n]


def _band_color(p: dict) -> list:
    """Shallow to deep by the band's lower depth: DEPVS, DEPMS, DEPMD, DEPDW."""
    return ["step", ["get", "depth_min_ft"], p["DEPVS"], 30, p["DEPMS"], 90, p["DEPMD"], 180, p["DEPDW"]]


def _band(p: dict) -> dict:
    return {"id": "band-fill", "type": "fill", "source": "bathy", "source-layer": "band",
            "paint": {"fill-color": _band_color(p), "fill-antialias": False}}


def _not_enc() -> list:
    return ["!=", ["get", "source"], "enc"]


def _contours(p: dict) -> list[dict]:
    layers = [
        {"id": "contour-enc", "type": "line", "source": "bathy", "source-layer": "contour",
         "filter": ["==", ["get", "source"], "enc"],
         "paint": {"line-color": p["CHGRD"], "line-width": 0.8, "line-dasharray": [4, 2]}},
    ]
    for n in MINOR_TIERS:
        layers.append({
            "id": f"contour-minor-z{n}", "type": "line", "source": "bathy", "source-layer": "contour",
            "minzoom": n, "filter": ["all", _not_enc(), ["!", ["get", "major"]], _tier(n)],
            "paint": {"line-color": p["CHGRD"], "line-width": 0.6},
        })
    layers.append({
        "id": "contour-major", "type": "line", "source": "bathy", "source-layer": "contour",
        "filter": ["all", _not_enc(), ["get", "major"]],
        "paint": {"line-color": p["CHBLK"], "line-width": 1.2},
    })
    return layers


def _label(layer_id: str, filter_: list, p: dict, minzoom: int | None = None) -> dict:
    layer = {
        "id": layer_id, "type": "symbol", "source": "bathy", "source-layer": "contour", "filter": filter_,
        "layout": {"symbol-placement": "line", "symbol-spacing": 400,
                   "text-field": ["to-string", ["get", "depth_ft"]], "text-font": ["Noto Sans Bold"],
                   "text-size": 11},
        "paint": {"text-color": p["CHBLK"], "text-halo-color": p["DEPDW"], "text-halo-width": 1.5},
    }
    if minzoom is not None:
        layer["minzoom"] = minzoom
    return layer


def _labels(p: dict) -> list[dict]:
    layers = [_label("contour-label", ["all", _not_enc(), ["get", "major"]], p)]
    layers += [
        _label(f"contour-label-z{n}", ["all", _not_enc(), ["!", ["get", "major"]], _tier(n)], p, n)
        for n in MINOR_TIERS
    ]
    return layers


def _pick(layers: list[dict], *ids: str) -> list[dict]:
    return [l for l in layers if l["id"] in ids]


def fish_style(palette: str, depths: Depths = Depths()) -> dict:
    """A complete MapLibre style v8 dict over the enc, bathy and dem sources."""
    p = PALETTES[palette]
    hillshade = {
        "id": "hillshade", "type": "hillshade", "source": "dem",
        "paint": {"hillshade-exaggeration": 0.5, "hillshade-shadow-color": p["CHGRD"],
                  "hillshade-highlight-color": p["CHWHT"], "hillshade-illumination-direction": 335},
    }
    water_base = {"id": "water-base", "type": "fill", "source": "enc", "source-layer": "depare",
                  "paint": {"fill-color": p["DEPMD"]}}
    layers = [
        {"id": "background", "type": "background", "paint": {"background-color": p["NODTA"]}},
        water_base,
        _band(p),
        hillshade,
        *_pick(_land_and_areas(p), "lndare", "coalne"),
        *_contours(p),
        *_labels(p),
        *seabed_layers(p),
        *_pick(_navaids_and_lights(p), "light"),
        *_hazards(p, palette, depths),
    ]
    return {
        "version": 8,
        "name": f"CheekyMarine fish {palette}",
        "metadata": {"cheekymarine": {
            "depths": {"shallow_m": depths.shallow_m, "safety_m": depths.safety_m,
                       "deep_m": depths.deep_m, "layers": list(HAZARD_DEPTH_LAYERS)},
            "units": "ft",
            "palette": palette,
            "notice": NOTICE,
        }},
        "sources": {
            "enc": {"type": "vector", "url": "mbtiles://enc"},
            "bathy": {"type": "vector", "url": "mbtiles://bathy"},
            "dem": {"type": "raster-dem", "url": "mbtiles://dem", "encoding": "terrarium", "tileSize": 256},
        },
        "sprite": "pack://sprites/fish",
        "glyphs": "pack://glyphs/{fontstack}/{range}.pbf",
        "layers": layers,
    }
