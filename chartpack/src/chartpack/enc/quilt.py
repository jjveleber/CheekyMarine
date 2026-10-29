"""Usage-band quilting: each zoom range shows its primary band, with lower bands filling the gaps."""

import copy

import shapely
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from chartpack.enc.reader import CellMeta, Feature
from chartpack.enc.scamin import BAND_ZOOMS, minzoom_for_extent, minzoom_for_scamin

THINNED_LAYERS = ("soundg", "area", "line", "seabed")
# (zoom range, primary band), coarse to fine
_RANGES = tuple((BAND_ZOOMS[band], band) for band in (3, 4, 5))


def _band(band: int) -> int:
    """Band 2 (and anything coarser) is treated as band 3; the tile schema has no coarser range."""
    return min(max(band, 3), 5)


def _parts(geom):
    """Simple parts of a shapely result; empty results give nothing."""
    if geom.is_empty:
        return []
    if hasattr(geom, "geoms"):
        return [part for sub in geom.geoms for part in _parts(sub)]
    return [geom]


def _clip(feature: Feature, clip) -> list[dict]:
    """The geometries of the feature outside `clip` (a prepared geometry), as GeoJSON dicts."""
    geom = shape(feature.geometry)
    if geom.geom_type == "Point":
        return [] if shapely.contains_xy(clip, geom.x, geom.y) else [copy.deepcopy(feature.geometry)]
    if not shapely.intersects(clip, geom):
        return [copy.deepcopy(feature.geometry)]
    return [mapping(part) for part in _parts(geom.difference(clip))]


def quilt(cells: list[tuple[CellMeta, list[Feature]]]) -> list[Feature]:
    by_band: dict[int, list[Feature]] = {}
    covr_by_band: dict[int, list] = {}
    for meta, features in cells:
        band = _band(meta.band)
        by_band.setdefault(band, []).extend(features)
        covr_by_band.setdefault(band, []).append(shape(meta.covr))
    out: list[Feature] = []
    for (lo, hi), primary in _RANGES:
        for band, features in by_band.items():
            if band > primary:
                continue
            higher = [c for b in range(band + 1, primary + 1) for c in covr_by_band.get(b, [])]
            clip = unary_union(higher) if higher else None
            if clip is not None:
                shapely.prepare(clip)
            for feature in features:
                minzoom = lo
                if feature.layer in THINNED_LAYERS:
                    minzoom = max(minzoom_for_scamin(feature.props.get("SCAMIN"), band), lo)
                    if "extent" in feature.props:  # seabed areas and lines: from about 48 px across (R37)
                        minzoom = max(minzoom, minzoom_for_extent(feature.props["extent"]))
                    if minzoom > hi:
                        continue
                geometries = [copy.deepcopy(feature.geometry)] if clip is None else _clip(feature, clip)
                for geometry in geometries:
                    props = dict(feature.props)
                    props["tippecanoe"] = {"minzoom": minzoom, "maxzoom": hi}
                    out.append(Feature(feature.layer, geometry, props))
    return out
