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

from chartpack.enc.bc import DERIVED_SRC
from chartpack.enc.reader import read_cell
from chartpack.enc.scamin import BAND_ZOOMS
from chartpack.enc.schema import (
    BATHY_LAYER_SPECS,
    COARSE_OPTIONAL_LAYERS,
    DERIVED_LAYERS,
    LAYERS,
    OPTIONAL_LAYERS,
    SAFETY_LAYERS,
    SCHEMA_VERSION,
)
from chartpack.enc.tiles import ENC_METADATA_KEYS
from chartpack.grid import GRID_ZOOM, tile_bounds
from chartpack.mbtiles import MBTiles, decode_pbf
from chartpack.pack.assemble import BATHY_FILES
from chartpack.pack.manifest import MANIFEST, sha256_of
from chartpack.style.validate import check_style_against_schema, check_style_sprites_glyphs

_COMMON_KEYS = ("name", "format", "bounds", "minzoom", "maxzoom", "cheekymarine:schema", "cheekymarine:pack",
                "cheekymarine:region", "cheekymarine:version", "cheekymarine:sources", "cheekymarine:built")
_DEM_KEYS = ("name", "minzoom", "maxzoom", "bounds", "cheekymarine:encoding", "cheekymarine:pack",
             "cheekymarine:schema")
_METADATA_KEYS = {
    "enc.mbtiles": ENC_METADATA_KEYS + ("name", "format", "bounds", "minzoom", "maxzoom"),
    "bathy.mbtiles": _COMMON_KEYS,
    "dem.mbtiles": _DEM_KEYS,
    "bathy-coarse.mbtiles": _COMMON_KEYS,
    "dem-coarse.mbtiles": _DEM_KEYS,
}
PACK_CAP_BYTES = 1_500_000_000
_MANIFEST_KEYS = ("pack", "region", "version", "schema", "built", "files", "sources", "notice")
_EXTENT = 4096
_COVERAGE_MIN = 0.9999
# The Canada polygon is shrunk by this many tile units before the "nothing NOAA inside" rules (plan 8 spec 7.2):
# tippecanoe, as the packs are built, keeps a line or polygon within 1 unit of its place and rounds to half a unit,
# so a correctly cut feature stays at least 2.5 units clear (about 400 m at zoom 6, 6 m at zoom 16).
CANADA_TOLERANCE_UNITS = 4
_NEAR_UNITS = 512  # the polygon is cut this far around a tile before it goes to tile units: past the tile buffer


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


def _check_vector_layers(name: str, metadata: dict, specs, optional: frozenset[str] = OPTIONAL_LAYERS) -> list[str]:
    try:
        built = {layer["id"] for layer in json.loads(metadata["json"])["vector_layers"]}
    except (KeyError, ValueError):
        return [f"{name}: metadata json has no vector_layers"]
    expected = {spec.name for spec in specs}
    errors = [f"{name}: schema layer {layer} missing" for layer in sorted(expected - optional - built)]
    errors += [f"{name}: layer {layer} is not in the schema" for layer in sorted(built - expected)]
    return errors


def _layer_ids(metadata: dict) -> set[str]:
    try:
        return {layer["id"] for layer in json.loads(metadata["json"])["vector_layers"]}
    except (KeyError, ValueError):
        return set()


def _band_zooms(metadata: dict) -> set[int]:
    """Zooms inside the band range of any source cell (band is the third character of the cell name),
    limited to the file's own minzoom..maxzoom so a region pack is not asked for the overview's zooms."""
    zooms = set()
    for source in json.loads(metadata["cheekymarine:sources"]):
        band = min(max(int(source["cell"][2]), 3), 5)  # bands 1 and 2 share band 3's zoom range (BAND_ZOOMS)
        zooms.update(range(BAND_ZOOMS[band][0], BAND_ZOOMS[band][1] + 1))
    return {z for z in zooms if int(metadata["minzoom"]) <= z <= int(metadata["maxzoom"])}


def _owned_area(metadata: dict):
    """The owned zoom-10 tiles as one polygon; for the overview (owned null) its content tiles; None for an
    overview with no content tiles recorded (an older pack: the whole cells)."""
    owned = json.loads(metadata.get("cheekymarine:owned", "null"))
    if owned is None:
        owned = json.loads(metadata.get("cheekymarine:content", "null"))
    if owned is None:
        return None
    return unary_union([box(*tile_bounds(GRID_ZOOM, x, y)) for x, y in owned])


def _has_tiles(path: Path) -> bool:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("select 1 from tiles limit 1").fetchone() is not None
    finally:
        conn.close()


def _check_safety_layers(m: MBTiles, metadata: dict) -> list[str]:
    # Pack-wide on purpose, not clipped to the owned tiles: it fails closed.
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


def _check_derived_layers(m: MBTiles, metadata: dict, kind: str) -> list[str]:
    """A derived charts pack (charts.kind) holds its DERIVED_LAYERS at every zoom from the file's minzoom to its
    maxzoom. Pack-wide, as _check_safety_layers."""
    errors = []
    for z in range(int(metadata["minzoom"]), int(metadata["maxzoom"]) + 1):
        missing = set(DERIVED_LAYERS[kind])
        for _, _, data in m.tiles_at(z):
            missing -= decode_pbf(data).keys()
            if not missing:
                break
        errors += [f"enc.mbtiles: derived layer {layer} has no features at zoom {z}"
                   for layer in DERIVED_LAYERS[kind] if layer in missing]
    return errors


def _zooms(metadata: dict) -> range:
    return range(int(metadata["minzoom"]), int(metadata["maxzoom"]) + 1)


def _check_no_depth_in_nosurvey(m: MBTiles) -> list[str]:
    """No derived depth (depare, depcnt or soundg with a src) meets a nosurvey polygon of the same tile shrunk by
    CANADA_TOLERANCE_UNITS (plan 8 spec 7.1). The depth is cut exactly at the mask edge before tiling, but
    tippecanoe simplifies and rounds both sides, so on a diagonal or curved edge a depth edge lands up to about
    2.5 units inside the tiled mask (measured 2.16 at zoom 16, PR 123 review): the same allowance as the Canada
    rule. One error per feature, naming the tile."""
    errors = []
    for z in _zooms(m.metadata()):
        for x, y, data in m.tiles_at(z):
            layers = decode_pbf(data)
            if not layers.get("nosurvey"):
                continue
            mask = shapely.union_all([make_valid(shape(f["geometry"])) for f in layers["nosurvey"]]).buffer(
                -CANADA_TOLERANCE_UNITS)
            shapely.prepare(mask)
            for layer in ("depare", "depcnt", "soundg"):
                errors += [f"enc.mbtiles: {layer} depth inside a nosurvey area in tile {z}/{x}/{y}"
                           for f in layers.get(layer, []) if "src" in f["properties"]
                           and mask.intersects(make_valid(shape(f["geometry"])))]
    return errors


def _tile_units(z: int, x: int, y: int, geom: shapely.Geometry) -> shapely.Geometry:
    """A lon/lat geometry in the tile units of tile z/x/y (4,096 per tile, y down), the inverse of _lonlat."""
    n = 2**z

    def to_units(c):
        px = ((c[:, 0] + 180.0) / 360.0 * n - x) * _EXTENT
        py = ((1 - np.arcsinh(np.tan(np.radians(c[:, 1]))) / math.pi) / 2 * n - y) * _EXTENT
        return np.column_stack([px, py])

    return shapely.transform(geom, to_units)


def _canada_in_tiles(m: MBTiles, canada: shapely.Geometry):
    """(z, x, y, layers, shrunk) for every tile of every zoom of the file that meets canada: shrunk is canada in
    the tile's units shrunk by CANADA_TOLERANCE_UNITS (None: nothing of it is left there)."""
    shapely.prepare(canada)
    for z in _zooms(m.metadata()):
        for x, y, data in m.tiles_at(z):
            (w, n), (e, s) = _lonlat(z, x, y, np.array([[-_NEAR_UNITS, -_NEAR_UNITS],
                                                        [_EXTENT + _NEAR_UNITS, _EXTENT + _NEAR_UNITS]]))
            near = box(w, s, e, n)
            if not canada.intersects(near):
                continue
            shrunk = _tile_units(z, x, y, canada.intersection(near)).buffer(-CANADA_TOLERANCE_UNITS)
            if not shrunk.is_empty:
                shapely.prepare(shrunk)
                yield z, x, y, decode_pbf(data), shrunk


def _check_no_noaa_in_canada(m: MBTiles, canada: shapely.Geometry) -> list[str]:
    """No feature of any layer (seabed included) meets canada shrunk by CANADA_TOLERANCE_UNITS, in every tile at
    every zoom, unless it is a nosurvey area or its src is in DERIVED_SRC (plan 8 spec 7.2). True intersection, so
    a line across the polygon with no vertex inside is caught. One error per feature, naming the tile and layer."""
    errors = []
    for z, x, y, layers, shrunk in _canada_in_tiles(m, canada):
        for layer, feats in layers.items():
            if layer == "nosurvey":
                continue
            errors += [f"enc.mbtiles: {layer} feature inside the Canada polygon in tile {z}/{x}/{y}" for f in feats
                       if f["properties"].get("src") not in DERIVED_SRC
                       and shrunk.intersects(make_valid(shape(f["geometry"])))]
    return errors


def _check_no_enc_contour_in_canada(m: MBTiles, canada: shapely.Geometry) -> list[str]:
    """No contour with source enc (the ENC fallback lines) meets canada shrunk as in _check_no_noaa_in_canada."""
    return [f"contour feature with source enc inside the Canada polygon in tile {z}/{x}/{y}"
            for z, x, y, layers, shrunk in _canada_in_tiles(m, canada) for f in layers.get("contour", [])
            if f["properties"].get("source") == "enc" and shrunk.intersects(shape(f["geometry"]))]


def _check_against_sources(m: MBTiles, metadata: dict, enc_zips: list[Path],
                           canada: shapely.Geometry | None = None) -> list[str]:
    """Hazards and depth/land coverage at the top zoom against the source cells. nosurvey areas count as cover
    beside depare and lndare. A source hazard whose point lies inside canada (the Canada polygon, where every NOAA
    feature is cut) is not expected in the tiles."""
    z = int(metadata["maxzoom"])
    owned = _owned_area(metadata)
    tile_box = box(0, 0, _EXTENT, _EXTENT)
    hazards: dict[tuple, list] = {}
    area_polys = []
    for x, y, data in m.tiles_at(z):
        layers = decode_pbf(data)
        for feat in layers.get("hazard", []):
            geom = shapely.transform(shape(feat["geometry"]), lambda c, x=x, y=y: _lonlat(z, x, y, c))
            if owned is not None and not owned.intersects(geom.representative_point()):
                continue  # tippecanoe's tile buffer carries hazards from ground another pack owns
            hazards.setdefault(hazard_key(feat["properties"]), []).append(geom)
        for layer in ("depare", "lndare", "nosurvey"):
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
        # The union, as the quilt clips: a point on the seam of two finer cells is inside it, though in neither.
        finer = unary_union([shape(other.covr) for other, _ in cells if other.band > meta.band])
        for f in feats:
            if f.layer != "hazard":
                continue
            point = shape(f.geometry).representative_point()
            if owned is not None and not owned.intersects(point):
                continue  # another pack owns this ground
            if finer.contains(point):
                continue  # a finer band's cell takes this ground over in the quilt
            key = hazard_key(f.props)
            source_keys.add(key)
            if canada is not None and canada.contains(point):
                continue  # cut at the Canada polygon
            if not any(g.distance(point) <= tol for g in hazards.get(key, [])):
                errors.append(f"hazard {key} at {point.x:.6f},{point.y:.6f} from {meta.name} missing at zoom {z}")
    errors += [f"hazard {key} in the tiles at zoom {z} is not in the source cells" for key in sorted(set(hazards) - source_keys, key=str)]

    covr = unary_union([shape(meta.covr) for meta, _ in cells])
    if owned is not None:
        covr = covr.intersection(owned)
    if covr.area == 0:
        return errors
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


def check_pack(pack_root: Path, *, enc_zips: list[Path] | None = None,
               canada: shapely.Geometry | None = None) -> list[str]:
    """Every check of the pack. canada (the Canada polygon, enc.bc.load_canada) turns on the rules of plan 8 spec
    7.2: nothing but derived features inside it in a charts pack, no ENC contour inside it in a bathy pack."""
    root = Path(pack_root)
    try:
        manifest = json.loads((root / MANIFEST).read_text())
        absent = [k for k in _MANIFEST_KEYS if k not in manifest]
    except (OSError, ValueError) as exc:
        return [f"{MANIFEST}: missing or invalid ({exc})"]
    if absent:
        return [f"{MANIFEST}: missing keys {', '.join(absent)}"]
    errors = []
    kind = (manifest.get("charts") or {}).get("kind", "enc")
    if manifest["schema"] != SCHEMA_VERSION:
        errors.append(f"{MANIFEST}: schema {manifest['schema']!r} is not {SCHEMA_VERSION}")
    errors += _check_files(root, manifest)
    total = sum(entry["bytes"] for entry in manifest["files"])
    if total > PACK_CAP_BYTES:
        errors.append(f"pack is {total} bytes, over the 1.5 GB cap")
    if manifest["pack"] == "bathy":
        errors += [f"{name}: missing from the bathy pack" for name in BATHY_FILES if not (root / name).is_file()]
        present = [root / name for name in BATHY_FILES if (root / name).is_file()]
        if present and len(present) == len(BATHY_FILES) and not any(_has_tiles(p) for p in present):
            errors.append("bathy pack: all four bathy files hold no tiles")

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
                if name.startswith("dem") or missing or (name != "enc.mbtiles" and not _has_tiles(path)):
                    continue
                if name == "bathy-coarse.mbtiles":  # coverage alone is allowed (CRM-only cells all land)
                    errors += _check_vector_layers(name, metadata, BATHY_LAYER_SPECS, OPTIONAL_LAYERS | COARSE_OPTIONAL_LAYERS)
                elif name == "enc.mbtiles" and kind != "enc":  # a derived pack needs its derived layers only
                    optional = frozenset(spec.name for spec in LAYERS) - set(DERIVED_LAYERS[kind])
                    errors += _check_vector_layers(name, metadata, LAYERS, optional)
                else:
                    errors += _check_vector_layers(name, metadata, LAYERS if name == "enc.mbtiles" else BATHY_LAYER_SPECS)
                if name == "enc.mbtiles":
                    if kind == "enc":
                        errors += _check_safety_layers(m, metadata)
                    else:
                        errors += _check_derived_layers(m, metadata, kind)
                    if "nosurvey" in _layer_ids(metadata):
                        errors += _check_no_depth_in_nosurvey(m)
                    if canada is not None:
                        errors += _check_no_noaa_in_canada(m, canada)
                    if enc_zips:
                        errors += _check_against_sources(m, metadata, enc_zips, canada)
                elif canada is not None:
                    errors += [f"{name}: {e}" for e in _check_no_enc_contour_in_canada(m, canada)]
        except sqlite3.Error as exc:
            errors.append(f"{name}: not readable ({exc})")
    errors += _check_styles(root, manifest["pack"])
    return errors
