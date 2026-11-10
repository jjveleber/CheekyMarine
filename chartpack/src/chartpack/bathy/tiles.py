"""Build bathy.mbtiles and bathy-coarse.mbtiles: contour, band and coverage layers through tippecanoe and tile-join."""

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape

from chartpack.bathy.contours import M_TO_FT
from chartpack.bathy.cudem import CudemTile
from chartpack.datum.offsets import datum_provenance
from chartpack.enc.quilt import quilt
from chartpack.enc.reader import CellMeta, Feature
from chartpack.enc.schema import COARSE_OPTIONAL_LAYERS, SCHEMA_VERSION
from chartpack.enc.tiles import run
from chartpack.mbtiles import MBTiles
from chartpack.region import Region

BATHY_LAYERS = ("contour", "band", "coverage")
MINZOOM, MAXZOOM = 10, 16  # the fine file
COARSE_ZOOMS = (10, 12)  # bathy-coarse.mbtiles of a region pack: CRM capped at zoom 12

_COMMON = ["-r1", "--no-feature-limit", "--no-tile-size-limit", "-P", "--force"]
_BAND_ONLY = ["--detect-shared-borders", "--no-tiny-polygon-reduction"]


def enc_depcnt(enc_cells: list[tuple[CellMeta, list[Feature]]]) -> list[tuple[shapely.Geometry, int, int, int]]:
    """The cells' depcnt lines as (geometry, depth_ft, minzoom, maxzoom), quilted once for a whole build.

    The cells are quilted by usage band as in the charts pack, so overlapping bands never draw
    the same water twice at one zoom. Each line keeps its band's zoom range, clamped to the
    bathy pack's MINZOOM..MAXZOOM.
    """
    depcnt = [(meta, [f for f in features if f.layer == "depcnt" and "VALDCO" in f.props]) for meta, features in enc_cells]
    lines = []
    for feature in quilt(depcnt):
        lo = max(feature.props["tippecanoe"]["minzoom"], MINZOOM)
        hi = min(feature.props["tippecanoe"]["maxzoom"], MAXZOOM)
        if lo <= hi:
            lines.append((shape(feature.geometry), round(float(feature.props["VALDCO"]) * M_TO_FT), lo, hi))
    return lines


def enc_fallback_contours(depcnt: list[tuple[shapely.Geometry, int, int, int]], uncovered: shapely.Geometry,
                         clip: shapely.Geometry | None) -> list[dict]:
    """enc_depcnt lines clipped to `uncovered` less `clip` (the region's water to leave out), as contour
    Features (one per simple line); `minzoom` mirrors the tippecanoe minzoom."""
    if clip is not None:
        uncovered = uncovered.difference(clip)
    feats = []
    for geom, depth_ft, lo, hi in depcnt:
        for line in _lines(geom.intersection(uncovered)):
            feats.append({
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {"depth_ft": depth_ft, "major": False, "minzoom": lo, "source": "enc"},
                "tippecanoe": {"minzoom": lo, "maxzoom": hi},
            })
    return feats


def _lines(geom) -> list:
    """The LineString parts of an intersection result; points and empty parts are dropped."""
    if hasattr(geom, "geoms"):
        return [line for part in geom.geoms for line in _lines(part)]
    return [geom] if geom.geom_type == "LineString" and not geom.is_empty and geom.length > 0 else []


def append_features(features: list[dict], path: Path) -> None:
    """Add features to a GeoJSONSeq layer file (created on first use), so a build can stream block by block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for feature in features:
            f.write(json.dumps(feature) + "\n")


def _missing_error(name: str, layers: list[str]) -> RuntimeError:
    return RuntimeError(f"{name} has no features in layer(s): {', '.join(layers)}")


def _has_features(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def tile_bathy(
    work: Path, out: Path, *, region: Region, crm_request: str, zooms: tuple[int, int] = (MINZOOM, MAXZOOM),
    coarse: bool = False, cudem_tiles: Sequence[CudemTile] = (),
) -> Path:
    """Tile the layer files work/<layer>.geojsonseq into out at zooms (min, max).

    With no features in any layer the file is written with its metadata and no tiles (the overview's
    fine file, a region with no CRM-only water). Otherwise every layer needs features, except that the
    coarse file may lack contour and band (COARSE_OPTIONAL_LAYERS) when it has coverage. crm_request
    records the CRM requests the build made.
    """
    out, work = Path(out), Path(work)
    out.parent.mkdir(parents=True, exist_ok=True)
    name = out.name
    files = {layer: work / f"{layer}.geojsonseq" for layer in BATHY_LAYERS}
    empty = [layer for layer, path in files.items() if not _has_features(path)]
    required = [layer for layer in BATHY_LAYERS if not (coarse and layer in COARSE_OPTIONAL_LAYERS)]
    if len(empty) == len(files):
        with MBTiles.create(out, fmt="pbf"):
            pass
    elif missing := [layer for layer in empty if layer in required]:
        raise _missing_error(name, missing)
    else:
        zoom_args = ["-Z", str(zooms[0]), "-z", str(zooms[1])]
        parts = []
        for part, names, extra in (("lines", ("contour", "coverage"), []), ("bands", ("band",), _BAND_ONLY)):
            names = [layer for layer in names if layer not in empty]
            if not names:
                continue
            path = work / f"{part}.mbtiles"
            cmd = ["tippecanoe", "-o", str(path), *zoom_args, *_COMMON, *extra]
            cmd += [f"-L{layer}:{files[layer]}" for layer in names]
            run(cmd)
            parts.append(str(path))
        run(["tile-join", "-o", str(out), "-pk", "-pC", "--force", *parts])

    with MBTiles.open(out) as m:
        if len(empty) < len(files):
            built = {l["id"] for l in json.loads(m.metadata()["json"])["vector_layers"]}
            missing = [layer for layer in BATHY_LAYERS if layer not in built and layer not in empty]
            if missing:
                raise _missing_error(name, missing)
        sources = {
            "cudem": [{"name": t.name, "url": t.url, "year": t.year, "version": t.version} for t in cudem_tiles],
            "crm": crm_request,
            "datum": datum_provenance(region.datum_file),
        }
        w, s, e, n = region.bbox
        m.set_metadata({
            "name": f"bathy-coarse-{region.name}" if coarse else f"bathy-{region.name}",
            "description": f"CheekyMarine bathy pack {region.name}" + (" (CRM only)" if coarse else ""),
            "format": "pbf",
            "bounds": f"{w},{s},{e},{n}",
            "minzoom": str(zooms[0]),
            "maxzoom": str(zooms[1]),
            "cheekymarine:schema": str(SCHEMA_VERSION),
            "cheekymarine:pack": "bathy",
            "cheekymarine:region": region.name,
            "cheekymarine:version": region.bathy_version,
            "cheekymarine:sources": json.dumps(sources),
            "cheekymarine:built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        m.delete_metadata(["generator_options"])  # holds the temp work paths
    return out
