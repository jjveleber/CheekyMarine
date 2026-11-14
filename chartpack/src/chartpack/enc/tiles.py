"""Build enc.mbtiles: quilted features -> tippecanoe (safety and thinned groups) -> tile-join."""

import json
import shutil
import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape

from chartpack.bathy.contours import BANDS
from chartpack.enc.bc import DERIVED_SRC, apply_rules
from chartpack.enc.gridsnap import snap_derived
from chartpack.enc.quilt import _parts, quilt
from chartpack.enc.reader import CellMeta, Feature
from chartpack.enc.schema import DERIVED_LAYERS, LAYERS, OPTIONAL_LAYERS, SAFETY_LAYERS, SCHEMA_VERSION
from chartpack.mbtiles import MBTiles
from chartpack.region import Region

ENC_METADATA_KEYS = (
    "cheekymarine:schema",
    "cheekymarine:pack",
    "cheekymarine:region",
    "cheekymarine:version",
    "cheekymarine:sources",
    "cheekymarine:valdco",
    "cheekymarine:seabed",
    "cheekymarine:built",
)

REGION_ZOOMS = (10, 16)
OVERVIEW_ZOOMS = (6, 9)

_COMMON = ["-r1", "--no-feature-limit", "--no-tile-size-limit",
           "--no-tiny-polygon-reduction", "--no-simplification-of-shared-nodes",
           "--extend-zooms-if-still-dropping", "-P", "--force"]
_SAFETY_ONLY = ["--detect-shared-borders"]
# The layers tiled with _SAFETY_ONLY: the no-survey areas share their edges with the depth areas, so they are
# simplified together.
_SAFETY_GROUP = SAFETY_LAYERS + ("nosurvey",)
# The snapped derived areas and contours (enc/gridsnap.py) are tiled on their own with no simplification: their
# vertices are on the tile grid of their band's minzoom, so tippecanoe draws them exactly at every zoom of the band.
# tile-join merges them with the layers of the same name from the other runs.
_DERIVED_ONLY = ["-ps"]
_DERIVED_GROUP = ("depare", "depcnt", "lndare", "nosurvey")
_SEABED_KEYS = ("src", "class", "NATSUR", "NATQUA", "CATWED", "folk", "substrate")


def _is_derived(feature: Feature) -> bool:
    """A derived feature (enc/derived.py): nosurvey, or a src of the derived sources."""
    return feature.layer == "nosurvey" or feature.props.get("src") in DERIVED_SRC


def run(cmd: list[str]) -> None:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"{cmd[0]} not found on PATH: run scripts/install-tippecanoe.sh")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed with exit {proc.returncode}:\n{proc.stderr}")


def _write_geojsonseq(features: list[Feature], path: Path) -> None:
    with path.open("w") as f:
        for feature in features:
            props = dict(feature.props)
            tip = props.pop("tippecanoe")
            f.write(json.dumps({
                "type": "Feature",
                "tippecanoe": {"minzoom": tip["minzoom"], "maxzoom": tip["maxzoom"]},
                "geometry": feature.geometry,
                "properties": props,
            }) + "\n")


def _crop(features: list[Feature], area) -> list[Feature]:
    """The features cut to `area` (a prepared geometry): points outside it are dropped, lines and polygons are
    cut, and the cut keeps only parts of the feature's own dimension."""
    out = []
    for feature in features:
        geom = shape(feature.geometry)
        if shapely.covers(area, geom):
            out.append(feature)
        elif geom.geom_type != "Point" and shapely.intersects(area, geom):
            dim = shapely.get_dimensions(geom)
            out += [Feature(feature.layer, mapping(part), feature.props)
                    for part in _parts(geom.intersection(area)) if shapely.get_dimensions(part) == dim]
    return out


def _tippecanoe(out: Path, layer_files: list[tuple[str, Path]], extra: list[str], zooms: tuple[int, int]) -> None:
    cmd = ["tippecanoe", "-o", str(out), "-Z", str(zooms[0]), "-z", str(zooms[1]), *_COMMON, *extra]
    cmd += [f"-L{name}:{path}" for name, path in layer_files]
    run(cmd)


def build_enc_mbtiles(
    cells: list[tuple[CellMeta, list[Feature]]], out: Path, *, region: Region, work: Path,
    seabed: Sequence[Feature] = (), zooms: tuple[int, int], area: shapely.Geometry | None = None,
    canada: shapely.Geometry | None = None, derived: Sequence[Feature] = (), depth_sources: Sequence[dict] = (),
    bands=BANDS,
) -> Path:
    """`seabed`: USGS survey features (seabed/usseabed.py, seabed/cmecs.py) that already carry their
    tippecanoe zooms; they join the seabed layer as they are, not quilted (spec 6.10).
    `zooms`: (minzoom, maxzoom) of the tippecanoe run, REGION_ZOOMS or OVERVIEW_ZOOMS.
    `area`: where the quilt output is kept (the owned tiles plus a margin; the overview: every owned tile), so a
    cell spanning far past the region does not fill tippecanoe's top zooms over its whole extent; None keeps it
    all.
    `canada`: the Canada polygon when the pack's tiles meet it (plan 8 spec 7.2): the quilt output and `seabed`
    are cut at it and `derived` (enc/derived.py features, made for the charts side) is added, by apply_rules.
    `depth_sources`: the derived inputs ({"source", "asset", "sha256"}); those whose source is a src of the
    built features (or "nosurvey", when the nosurvey layer holds any) go to cheekymarine:depth_sources.
    `bands`: the derived features' zoom bands (BANDS, or OVERVIEW_BANDS for the overview): after apply_rules they
    are snapped per block core and band (snap_derived), and their depare, depcnt, lndare and nosurvey are tiled in
    a run of their own without simplification. A derived list is consumed (emptied) so its unsnapped features are
    not held beside the snapped ones at the memory peak.
    A charts kind other than enc (DERIVED_LAYERS) needs its derived layers only, not every schema layer."""
    out, work = Path(out), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    by_layer: dict[str, list[Feature]] = {spec.name: [] for spec in LAYERS}
    features = quilt(cells)
    if area is not None:
        shapely.prepare(area)
        features = _crop(features, area)
    if canada is not None:
        ruled = apply_rules(features + list(seabed), list(derived), canada)
        if isinstance(derived, list):
            derived.clear()  # consumed: the caller's list does not hold the unsnapped features while they snap
        features, seabed = snap_derived(ruled, bands), ()  # snap_derived empties ruled as it goes
    snapped: dict[str, list[Feature]] = {name: [] for name in _DERIVED_GROUP}
    for feature in features:
        if feature.layer in _DERIVED_GROUP and _is_derived(feature):
            snapped[feature.layer].append(feature)
        else:
            by_layer[feature.layer].append(feature)
    by_layer["seabed"].extend(seabed)

    groups: dict[str, list[tuple[str, Path]]] = {"safety": [], "thinned": [], "derived": []}
    for spec in LAYERS:
        if by_layer[spec.name]:  # none in any group: reported by name after the build, below
            path = work / f"{spec.name}.geojsonseq"
            _write_geojsonseq(by_layer[spec.name], path)
            groups["safety" if spec.name in _SAFETY_GROUP else "thinned"].append((spec.name, path))
        if snapped.get(spec.name):
            path = work / f"derived-{spec.name}.geojsonseq"
            _write_geojsonseq(snapped[spec.name], path)
            groups["derived"].append((spec.name, path))
    for name, feats in snapped.items():
        by_layer[name].extend(feats)  # for the metadata below

    parts = []
    for group, extra in (("safety", _SAFETY_ONLY), ("thinned", []), ("derived", _DERIVED_ONLY)):
        if groups[group]:
            part = work / f"{group}.mbtiles"
            _tippecanoe(part, groups[group], extra, zooms)
            parts.append(str(part))
    run(["tile-join", "-o", str(out), "-pk", "-pC", "--force", *parts])

    with MBTiles.open(out) as m:
        built_layers = {l["id"] for l in json.loads(m.metadata()["json"])["vector_layers"]}
        required = DERIVED_LAYERS.get(region.charts_kind) or [spec.name for spec in LAYERS]
        missing = [name for name in required if name not in built_layers | OPTIONAL_LAYERS]
        if missing:
            raise RuntimeError(f"enc.mbtiles has no features in layer(s): {', '.join(missing)}")
        sources = [
            {"cell": meta.name, "edtn": meta.edtn, "updn": meta.updn, "isdt": meta.isdt}
            for meta, _ in sorted(cells, key=lambda c: c[0].name)
        ]
        valdco = sorted({f.props["VALDCO"] for f in by_layer["depcnt"] if "VALDCO" in f.props}, key=float)
        # the distinct seabed codes in the tiles, for legend.json (seabed/legend.py)
        seabed = sorted({json.dumps({k: f.props[k] for k in _SEABED_KEYS if k in f.props}, sort_keys=True)
                         for f in by_layer["seabed"]})
        srcs = {f.props.get("src") for layer in by_layer.values() for f in layer} | (
            {"nosurvey"} if by_layer["nosurvey"] else set())
        recorded = [source for source in depth_sources if source["source"] in srcs]
        w, s, e, n = region.bbox
        m.set_metadata({
            "name": f"charts-{region.name}",
            "description": f"CheekyMarine charts pack {region.name}",
            "format": "pbf",
            "bounds": f"{w},{s},{e},{n}",
            "minzoom": str(zooms[0]),
            "maxzoom": str(zooms[1]),
            "cheekymarine:schema": str(SCHEMA_VERSION),
            "cheekymarine:pack": "charts",
            "cheekymarine:region": region.name,
            "cheekymarine:version": region.charts_version,
            "cheekymarine:sources": json.dumps(sources),
            "cheekymarine:valdco": json.dumps(valdco),
            "cheekymarine:seabed": json.dumps([json.loads(row) for row in seabed]),
            "cheekymarine:built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **({"cheekymarine:depth_sources": json.dumps(recorded)} if recorded else {}),
        })
        m.delete_metadata(["generator_options"])  # holds the temp work paths
    return out
