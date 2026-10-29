"""Read one ENC cell zip (with its updates applied) into tile-schema features."""

import json
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from osgeo import gdal
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from chartpack.enc.schema import LAYERS

gdal.UseExceptions()

# Depths are kept as exact decimal strings, never floats.
DEPTH_FIELDS = ("DRVAL1", "DRVAL2", "VALDCO", "VALSOU", "DEPTH")
_POLYGONS = ("POLYGON", "MULTIPOLYGON")
_LINES = ("LINESTRING", "MULTILINESTRING")


@dataclass
class Feature:
    layer: str
    geometry: dict
    props: dict


@dataclass
class CellMeta:
    name: str
    band: int
    edtn: int
    updn: int
    isdt: str
    covr: dict
    skipped_no_geometry: int = 0  # features GDAL gave without a geometry


def _accepts(geometry: str, geom_name: str) -> bool:
    if geometry == "any":
        return True
    if geometry == "polygon":
        return geom_name in _POLYGONS
    if geometry == "line":
        return geom_name in _LINES
    return geom_name in ("POINT", "MULTIPOINT")


def _route(cls: str, geom_name: str):
    """The layer a feature of this class and geometry goes to. Geometry never causes a drop:
    when no candidate accepts the geometry, the first candidate takes it (pinned by a test)."""
    candidates = [spec for spec in LAYERS if cls in spec.classes]
    for spec in candidates:
        if _accepts(spec.geometry, geom_name):
            return spec
    return candidates[0]


def _value(feature, field: str):
    """The field value, or None when unset or null."""
    if feature.GetFieldIndex(field) < 0 or not feature.IsFieldSetAndNotNull(field):
        return None
    value = feature.GetField(field)
    if field in DEPTH_FIELDS:
        return format(value, ".15g")
    return value


def _props(feature, cls: str, attributes, cell: str, band: int) -> dict:
    props = {"cell": cell, "band": band, "class": cls}
    for attr in attributes:
        value = _value(feature, "DEPTH" if attr == "depth" else attr)
        if value is not None:
            props[attr] = value
    return props


def _geometry(feature) -> dict | None:
    geom = feature.GetGeometryRef()
    if geom is None:
        return None
    geom = geom.Clone()
    geom.FlattenTo2D()  # GDAL gives SOUNDG points a Z; the tiles are 2D
    return json.loads(geom.ExportToJson())


def read_cell(zip_path: Path, *, apply_updates: bool = True) -> tuple[CellMeta, list[Feature]]:
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path) as zf:
        base000 = next(n for n in zf.namelist() if n.endswith(".000"))
        name = Path(base000).stem
        for n in zf.namelist():
            if not n.endswith("/") and Path(n).name.startswith(name + "."):
                (Path(tmp) / Path(n).name).write_bytes(zf.read(n))
        band = int(name[2])
        ds = gdal.OpenEx(
            str(Path(tmp) / f"{name}.000"),
            gdal.OF_VECTOR,
            open_options=[
                "SPLIT_MULTIPOINT=ON",
                "ADD_SOUNDG_DEPTH=ON",
                "LNAM_REFS=ON",
                "RECODE_BY_DSSI=ON",
                "LIST_AS_STRING=ON",
                f"UPDATES={'APPLY' if apply_updates else 'IGNORE'}",
            ],
        )
        try:
            dsid = ds.GetLayerByName("DSID").GetNextFeature()
            isdt = datetime.strptime(dsid.GetField("DSID_ISDT"), "%Y%m%d").date().isoformat()
            edtn, updn = int(dsid.GetField("DSID_EDTN")), int(dsid.GetField("DSID_UPDN"))
            features: list[Feature] = []
            covr_parts = []
            skipped = 0
            classes = [c for spec in LAYERS for c in spec.classes]
            for cls in dict.fromkeys(classes):
                layer = ds.GetLayerByName(cls)
                if layer is None:
                    continue
                for feature in layer:
                    if cls == "M_COVR" and _value(feature, "CATCOV") != 1:
                        continue
                    geometry = _geometry(feature)
                    if geometry is None:
                        skipped += 1
                        continue
                    spec = _route(cls, geometry["type"].upper())
                    props = _props(feature, cls, spec.attributes, name, band)
                    if cls == "M_COVR":
                        covr_parts.append(shape(geometry))
                    features.append(Feature(spec.name, geometry, props))
        finally:
            layer = feature = dsid = ds = None  # release the files before the temp dir goes
    if not covr_parts:
        raise ValueError(f"{name}: no M_COVR feature with CATCOV=1")
    covr = mapping(unary_union(covr_parts))
    return CellMeta(name, band, edtn, updn, isdt, covr, skipped), features
