"""Structural checks of an assembled pack: manifest, hashes, metadata, layers, safety data, styles."""

import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon, box, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from chartpack.enc.reader import read_cell
from chartpack.enc.scamin import BAND_ZOOMS
from chartpack.enc.schema import BATHY_LAYER_SPECS, LAYERS, OPTIONAL_LAYERS, SAFETY_LAYERS, SCHEMA_VERSION
from chartpack.enc.tiles import ENC_METADATA_KEYS
from chartpack.mbtiles import MBTiles, decode_pbf
from chartpack.pack.manifest import MANIFEST, sha256_of
from chartpack.style.validate import check_style_against_schema, check_style_sprites_glyphs

_COMMON_KEYS = ("name", "format", "bounds", "minzoom", "maxzoom", "cheekymarine:schema", "cheekymarine:pack",
                "cheekymarine:region", "cheekymarine:version", "cheekymarine:sources", "cheekymarine:built")
_METADATA_KEYS = {
    "enc.mbtiles": ENC_METADATA_KEYS + ("name", "format", "bounds", "minzoom", "maxzoom"),
    "bathy.mbtiles": _COMMON_KEYS,
    "dem.mbtiles": ("name", "minzoom", "maxzoom", "bounds", "cheekymarine:encoding", "cheekymarine:pack",
                    "cheekymarine:schema"),
}
_MANIFEST_KEYS = ("pack", "region", "version", "schema", "built", "files", "sources", "notice")
_EXTENT = 4096
_COVERAGE_MIN = 0.9999


def _lonlat(z: int, x: int, y: int, coords: np.ndarray) -> np.ndarray:
    """Tile pixel coordinates (y down from the tile's north edge) to lon/lat."""
    n = 2**z
    lon = (x + coords[:, 0] / _EXTENT) / n * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (y + coords[:, 1] / _EXTENT) / n))))
    return np.column_stack([lon, lat])


def hazard_key(props: dict) -> tuple:
    """Class plus the charted attributes that tell hazards apart (the Task 5 presence tests use the same key)."""
    return (props["class"], props.get("VALSOU"), props.get("WATLEV"))


def _polygons(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in _polygons(g)]
    return [geom] if isinstance(geom, Polygon) else []


def _check_files(root: Path, manifest: dict) -> list[str]:
    errors = []
    listed = set()
    for entry in manifest["files"]:
        name = entry["name"]
        listed.add(name)
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: listed in the manifest but missing")
        elif path.stat().st_size != entry["bytes"]:
            errors.append(f"{name}: size {path.stat().st_size} != manifest {entry['bytes']}")
        elif sha256_of(path) != entry["sha256"]:
            errors.append(f"{name}: sha256 mismatch")
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_file() and name != MANIFEST and name not in listed:
            errors.append(f"{name}: not listed in the manifest")
    return errors


def _check_vector_layers(name: str, metadata: dict, specs) -> list[str]:
    try:
        built = {layer["id"] for layer in json.loads(metadata["json"])["vector_layers"]}
    except (KeyError, ValueError):
        return [f"{name}: metadata json has no vector_layers"]
    expected = {spec.name for spec in specs}
    errors = [f"{name}: schema layer {layer} missing" for layer in sorted(expected - OPTIONAL_LAYERS - built)]
    errors += [f"{name}: layer {layer} is not in the schema" for layer in sorted(built - expected)]
    return errors


def _band_zooms(metadata: dict) -> set[int]:
    """Zooms inside the band range of any source cell (band is the third character of the cell name)."""
    zooms = set()
    for source in json.loads(metadata["cheekymarine:sources"]):
        band = min(max(int(source["cell"][2]), 3), 5)  # as the quilt treats bands 1 to 3
        zooms.update(range(BAND_ZOOMS[band][0], BAND_ZOOMS[band][1] + 1))
    return zooms


def _check_safety_layers(m: MBTiles, metadata: dict) -> list[str]:
    errors = []
    for z in sorted(_band_zooms(metadata)):
        missing = set(SAFETY_LAYERS)
        for _, _, data in m.tiles_at(z):
            missing -= decode_pbf(data).keys()
            if not missing:
                break
        errors += [f"enc.mbtiles: safety layer {layer} has no features at zoom {z}"
                   for layer in SAFETY_LAYERS if layer in missing]
    return errors


def _check_against_sources(m: MBTiles, metadata: dict, enc_zips: list[Path]) -> list[str]:
    """Hazards and depth/land coverage at the top zoom against the source cells."""
    z = int(metadata["maxzoom"])
    tile_box = box(0, 0, _EXTENT, _EXTENT)
    hazards: dict[tuple, list] = {}
    area_polys = []
    for x, y, data in m.tiles_at(z):
        layers = decode_pbf(data)
        for feat in layers.get("hazard", []):
            geom = shapely.transform(shape(feat["geometry"]), lambda c, x=x, y=y: _lonlat(z, x, y, c))
            hazards.setdefault(hazard_key(feat["properties"]), []).append(geom)
        for layer in ("depare", "lndare"):
            for feat in layers.get(layer, []):
                for poly in _polygons(make_valid(shape(feat["geometry"])).intersection(tile_box)):
                    shell = _lonlat(z, x, y, np.array(poly.exterior.coords))
                    holes = [_lonlat(z, x, y, np.array(r.coords)) for r in poly.interiors]
                    area_polys.append(Polygon(shell, holes))

    cells = [read_cell(path) for path in enc_zips]
    tol = 1.5 * 360 / 2**z / _EXTENT  # tile coordinates are integers
    errors = []
    source_keys = set()
    for meta, feats in cells:
        finer = [shape(other.covr) for other, _ in cells if other.band > meta.band]
        for f in feats:
            if f.layer != "hazard":
                continue
            point = shape(f.geometry).representative_point()
            if any(covr.contains(point) for covr in finer):
                continue  # a finer band's cell takes this ground over in the quilt
            key = hazard_key(f.props)
            source_keys.add(key)
            if not any(g.distance(point) <= tol for g in hazards.get(key, [])):
                errors.append(f"hazard {key} at {point.x:.6f},{point.y:.6f} from {meta.name} missing at zoom {z}")
    errors += [f"hazard {key} in the tiles at zoom {z} is not in the source cells" for key in sorted(set(hazards) - source_keys, key=str)]

    covr = unary_union([shape(meta.covr) for meta, _ in cells])
    covered = unary_union(area_polys) if area_polys else Polygon()
    ratio = 1 - covr.difference(covered).area / covr.area
    if ratio < _COVERAGE_MIN:
        errors.append(f"depare and lndare cover {ratio:.6f} of the cell coverage at zoom {z}, need {_COVERAGE_MIN}")
    return errors


def _check_styles(root: Path, pack: str) -> list[str]:
    specs = LAYERS + BATHY_LAYER_SPECS if pack == "bathy" else LAYERS
    glyphs = root / "glyphs"
    fonts = {p.name for p in glyphs.iterdir()} if glyphs.is_dir() else set()
    errors = []
    for path in sorted((root / "styles").glob("*.json")):
        try:
            style = json.loads(path.read_text())
            sprite_path = root / "sprites" / f"{style['sprite'].rsplit('/', 1)[-1]}.json"
            sprite = json.loads(sprite_path.read_text())
            found = check_style_against_schema(style, specs) + check_style_sprites_glyphs(style, sprite, fonts)
        except (OSError, ValueError, KeyError) as exc:
            found = [f"cannot be checked ({exc!r})"]
        errors += [f"styles/{path.name}: {e}" for e in found]
    return errors


def check_pack(pack_root: Path, *, enc_zips: list[Path] | None = None) -> list[str]:
    root = Path(pack_root)
    try:
        manifest = json.loads((root / MANIFEST).read_text())
        absent = [k for k in _MANIFEST_KEYS if k not in manifest]
    except (OSError, ValueError) as exc:
        return [f"{MANIFEST}: missing or invalid ({exc})"]
    if absent:
        return [f"{MANIFEST}: missing keys {', '.join(absent)}"]
    errors = []
    if manifest["schema"] != SCHEMA_VERSION:
        errors.append(f"{MANIFEST}: schema {manifest['schema']!r} is not {SCHEMA_VERSION}")
    errors += _check_files(root, manifest)

    for name, keys in _METADATA_KEYS.items():
        path = root / name
        if not path.is_file():
            continue
        try:
            with MBTiles.open(path) as m:
                metadata = m.metadata()
                missing = [k for k in keys if k not in metadata]
                errors += [f"{name}: metadata key {k} missing" for k in missing]
                if metadata.get("cheekymarine:schema") not in (None, str(SCHEMA_VERSION)):
                    errors.append(f"{name}: schema {metadata['cheekymarine:schema']} is not {SCHEMA_VERSION}")
                if name == "dem.mbtiles" or missing:
                    continue
                errors += _check_vector_layers(name, metadata, LAYERS if name == "enc.mbtiles" else BATHY_LAYER_SPECS)
                if name == "enc.mbtiles":
                    errors += _check_safety_layers(m, metadata)
                    if enc_zips:
                        errors += _check_against_sources(m, metadata, enc_zips)
        except sqlite3.Error as exc:
            errors.append(f"{name}: not readable ({exc})")
    errors += _check_styles(root, manifest["pack"])
    return errors
