"""Build bathy.mbtiles: contour, band and coverage layers through tippecanoe and tile-join."""

import json
from datetime import datetime, timezone
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape

from chartpack.bathy.contours import M_TO_FT
from chartpack.bathy.crm import crm_wcs_url
from chartpack.bathy.cudem import CudemTile
from chartpack.enc.reader import CellMeta, Feature
from chartpack.enc.schema import SCHEMA_VERSION
from chartpack.enc.tiles import _run
from chartpack.mbtiles import MBTiles
from chartpack.region import Region

BATHY_LAYERS = ("contour", "band", "coverage")
MINZOOM, MAXZOOM = 10, 16

_COMMON = ["-Z", str(MINZOOM), "-z", str(MAXZOOM), "-r1", "--no-feature-limit", "--no-tile-size-limit", "-P", "--force"]
_BAND_ONLY = ["--detect-shared-borders", "--no-tiny-polygon-reduction"]


def enc_fallback_contours(enc_cells: list[tuple[CellMeta, list[Feature]]], uncovered: shapely.Geometry) -> list[dict]:
    """ENC depcnt lines clipped to `uncovered`, as contour Features (one per simple line)."""
    feats = []
    for _, features in enc_cells:
        for feature in features:
            if feature.layer != "depcnt" or "VALDCO" not in feature.props:
                continue
            depth_ft = round(float(feature.props["VALDCO"]) * M_TO_FT)
            clipped = shape(feature.geometry).intersection(uncovered)
            for line in _lines(clipped):
                feats.append({
                    "type": "Feature",
                    "geometry": mapping(line),
                    "properties": {"depth_ft": depth_ft, "major": False, "minzoom": MINZOOM, "source": "enc"},
                    "tippecanoe": {"minzoom": MINZOOM, "maxzoom": MAXZOOM},
                })
    return feats


def _lines(geom) -> list:
    """The LineString parts of an intersection result; points and empty parts are dropped."""
    if hasattr(geom, "geoms"):
        return [line for part in geom.geoms for line in _lines(part)]
    return [geom] if geom.geom_type == "LineString" and not geom.is_empty and geom.length > 0 else []


def _write(features: list[dict], path: Path) -> None:
    with path.open("w") as f:
        for feature in features:
            f.write(json.dumps(feature) + "\n")


def _missing_error(names: list[str]) -> RuntimeError:
    return RuntimeError(f"bathy.mbtiles has no features in layer(s): {', '.join(names)}")


def build_bathy_mbtiles(
    contours: list[dict], bands: list[dict], coverage: list[dict], out: Path, *, region: Region, work: Path,
    cudem_tiles: list[CudemTile] = (),
) -> Path:
    out, work = Path(out), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    layers = dict(zip(BATHY_LAYERS, (contours, bands, coverage)))
    empty = [name for name, feats in layers.items() if not feats]
    if empty:
        raise _missing_error(empty)

    for name, feats in layers.items():
        _write(feats, work / f"{name}.geojsonseq")
    parts = []
    for part, names, extra in (("lines", ("contour", "coverage"), []), ("bands", ("band",), _BAND_ONLY)):
        path = work / f"{part}.mbtiles"
        cmd = ["tippecanoe", "-o", str(path), *_COMMON, *extra]
        cmd += [f"-L{name}:{work / f'{name}.geojsonseq'}" for name in names]
        _run(cmd)
        parts.append(str(path))
    _run(["tile-join", "-o", str(out), "-pk", "-pC", "--force", *parts])

    with MBTiles.open(out) as m:
        built = {l["id"] for l in json.loads(m.metadata()["json"])["vector_layers"]}
        missing = [name for name in BATHY_LAYERS if name not in built]
        if missing:
            raise _missing_error(missing)
        sources = {
            "cudem": [{"name": t.name, "url": t.url, "year": t.year, "version": t.version} for t in cudem_tiles],
            "crm": crm_wcs_url(region.bbox),
            "datum": {
                "station": region.datum_station,
                "navd88_to_mllw_m": region.navd88_to_mllw_m,
                "msl_to_mllw_m": region.msl_to_mllw_m,
            },
        }
        w, s, e, n = region.bbox
        m.set_metadata({
            "name": f"bathy-{region.name}",
            "description": f"CheekyMarine bathy pack {region.name}",
            "format": "pbf",
            "bounds": f"{w},{s},{e},{n}",
            "minzoom": str(MINZOOM),
            "maxzoom": str(MAXZOOM),
            "cheekymarine:schema": str(SCHEMA_VERSION),
            "cheekymarine:pack": "bathy",
            "cheekymarine:region": region.name,
            "cheekymarine:version": region.bathy_version,
            "cheekymarine:sources": json.dumps(sources),
            "cheekymarine:built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        m.delete_metadata(["generator_options"])  # holds the temp work paths
    return out
