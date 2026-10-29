import hashlib
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import pytest
from osgeo import gdal
from shapely.geometry import shape

from chartpack.enc.reader import read_cell
from chartpack.enc.scamin import extent_z0

gdal.UseExceptions()


def _open(zip_path):
    """Open the cell with GDAL directly, independently of read_cell. Returns (ds, tmpdir)."""
    tmp = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp.name)
    name = Path(zip_path).stem
    ds = gdal.OpenEx(
        f"{tmp.name}/ENC_ROOT/{name}/{name}.000",
        gdal.OF_VECTOR,
        open_options=["SPLIT_MULTIPOINT=ON", "ADD_SOUNDG_DEPTH=ON"],
    )
    return ds, tmp


def ogr_depare_pairs(zip_path):
    ds, tmp = _open(zip_path)
    with tmp:
        pairs = {
            tuple(format(f.GetField(a), ".15g") for a in ("DRVAL1", "DRVAL2"))
            for cls in ("DEPARE", "DRGARE")
            for f in (ds.GetLayerByName(cls) or [])
        }
        ds = None
    return pairs


def ogr_class_counts(zip_path, classes):
    ds, tmp = _open(zip_path)
    with tmp:
        counts = Counter({c: ds.GetLayerByName(c).GetFeatureCount() for c in classes})
        ds = None
    return counts


def ogr_sounding_point_count(zip_path):
    ds, tmp = _open(zip_path)
    with tmp:
        n = ds.GetLayerByName("SOUNDG").GetFeatureCount()
        ds = None
    return n


def features_digest(feats):
    rows = sorted(json.dumps([f.layer, f.geometry, f.props], sort_keys=True) for f in feats)
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def test_layer_counts_match_golden(fixtures_dir, golden):
    meta, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    counts = Counter(f.layer for f in feats)
    assert counts == golden("US4WA1HK_layers.json")  # --update-golden rewrites


def test_depare_values_are_exact_strings(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    d = [f for f in feats if f.layer == "depare"]
    assert d and all(isinstance(f.props["DRVAL1"], str) for f in d)
    assert {(f.props["DRVAL1"], f.props["DRVAL2"]) for f in d} == ogr_depare_pairs(fixtures_dir / "US4WA1HK.zip")


def ogr_hazards(zip_path):
    """Sorted (class, minx, miny, VALSOU-or-None) for every UWTROC, WRECKS and OBSTRN, read via GDAL."""
    ds, tmp = _open(zip_path)
    with tmp:
        rows = []
        for cls in ("UWTROC", "WRECKS", "OBSTRN"):
            for f in ds.GetLayerByName(cls):
                g = f.GetGeometryRef().Clone()
                g.FlattenTo2D()
                minx, _, miny, _ = g.GetEnvelope()
                v = f.GetField("VALSOU") if f.IsFieldSetAndNotNull("VALSOU") else None
                rows.append((cls, minx, miny, None if v is None else format(v, ".15g")))
        ds = None
    return sorted(rows, key=repr)


def test_every_hazard_present_with_attributes(fixtures_dir):
    zip_path = fixtures_dir / "US4WA1HK.zip"
    _, feats = read_cell(zip_path)
    h = [f for f in feats if f.layer == "hazard"]
    assert Counter(f.props["class"] for f in h) == ogr_class_counts(zip_path, ["UWTROC", "WRECKS", "OBSTRN"])
    assert all("WATLEV" in f.props or f.props["class"] == "OBSTRN" for f in h)
    ours = sorted(
        ((f.props["class"],) + shape(f.geometry).bounds[:2] + (f.props.get("VALSOU"),) for f in h),
        key=repr,
    )
    theirs = ogr_hazards(zip_path)
    assert ours == theirs  # VALSOU present exactly where OGR has it, with the same exact string
    values = {r[3] for r in theirs}
    assert None in values and "0" in values and any(v and v.startswith("-") for v in values)
    assert sum(r[3] is None for r in theirs if r[0] == "UWTROC") > 0


def test_soundings_are_split_points_with_depth(fixtures_dir):
    zip_path = fixtures_dir / "US4WA1HK.zip"
    _, feats = read_cell(zip_path)
    s = [f for f in feats if f.layer == "soundg"]
    assert all(f.geometry["type"] == "Point" and "depth" in f.props for f in s)
    ours = sorted((*f.geometry["coordinates"], f.props["depth"], f.props.get("SCAMIN")) for f in s)
    ds, tmp = _open(zip_path)
    with tmp:
        theirs = sorted(
            (
                f.GetGeometryRef().GetX(),
                f.GetGeometryRef().GetY(),
                format(f.GetField("DEPTH"), ".15g"),
                f.GetField("SCAMIN") if f.IsFieldSetAndNotNull("SCAMIN") else None,
            )
            for f in ds.GetLayerByName("SOUNDG")
        )
        ds = None
    assert ours == theirs


def test_geometry_mismatched_features_are_kept_and_counted(fixtures_dir):
    """A feature whose geometry its layer does not list is kept in its class's first layer.
    The exact counts are pinned so any routing change is noticed."""
    meta, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    accepts = {"polygon": ("Polygon", "MultiPolygon"), "line": ("LineString", "MultiLineString"),
               "point": ("Point", "MultiPoint")}
    from chartpack.enc.schema import LAYERS

    geometry = {spec.name: spec.geometry for spec in LAYERS}
    mismatched = Counter(
        f.layer for f in feats
        if geometry[f.layer] != "any" and f.geometry["type"] not in accepts[geometry[f.layer]]
    )
    assert mismatched == {"area": 4, "coalne": 1}
    assert meta.skipped_no_geometry == 0


def test_zip_with_000_at_the_root(fixtures_dir, tmp_path):
    src = fixtures_dir / "US5SEAKL.zip"
    flat = tmp_path / "US5SEAKL.zip"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(flat, "w") as zout:
        for n in zin.namelist():
            if not n.endswith("/") and Path(n).name.startswith("US5SEAKL."):
                zout.writestr(Path(n).name, zin.read(n))
    meta, feats = read_cell(flat)
    assert meta.updn == 1 and feats


def test_cell_without_coverage_is_an_error(fixtures_dir, monkeypatch):
    import chartpack.enc.reader as reader

    # without the meta layer M_COVR is never read, as for a cell with no CATCOV=1 polygon
    monkeypatch.setattr(reader, "LAYERS", tuple(s for s in reader.LAYERS if s.name != "meta"))
    with pytest.raises(ValueError, match="US4WA1HK"):
        read_cell(fixtures_dir / "US4WA1HK.zip")


def test_lists_are_comma_joined(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    n = next(f for f in feats if f.layer == "navaid" and "," in f.props.get("COLOUR", ""))
    assert all(part.isdigit() for part in n.props["COLOUR"].split(","))


def test_update_changes_output(fixtures_dir):
    with_u = read_cell(fixtures_dir / "US5SEAKL.zip")
    without = read_cell(fixtures_dir / "US5SEAKL.zip", apply_updates=False)
    assert with_u[0].updn == 1 and without[0].updn == 0
    assert features_digest(with_u[1]) != features_digest(without[1])


def test_cell_meta_and_covr(fixtures_dir):
    meta, _ = read_cell(fixtures_dir / "US4WA1HK.zip")
    assert (meta.name, meta.band) == ("US4WA1HK", 4)
    assert shape(meta.covr).is_valid and shape(meta.covr).bounds == pytest.approx((-122.4, 47.7, -122.1, 48.0), abs=0.01)


def ogr_seabed(zip_path):
    """Sorted (class, minx, miny, NATSUR, NATQUA, CATWED) for every SBDARE and WEDKLP, read via GDAL
    without LIST_AS_STRING, so the lists are joined here independently of the reader."""
    ds, tmp = _open(zip_path)
    with tmp:
        rows = []
        for cls in ("SBDARE", "WEDKLP"):
            for f in ds.GetLayerByName(cls) or []:
                g = f.GetGeometryRef().Clone()
                g.FlattenTo2D()
                minx, _, miny, _ = g.GetEnvelope()

                def value(field, f=f):
                    if f.GetFieldIndex(field) < 0 or not f.IsFieldSetAndNotNull(field):
                        return None
                    if field == "CATWED":
                        return f.GetField(field)
                    return ",".join(f.GetFieldAsStringList(f.GetFieldIndex(field)))

                rows.append((cls, minx, miny, value("NATSUR"), value("NATQUA"), value("CATWED")))
        ds = None
    return sorted(rows, key=repr)


@pytest.mark.parametrize("cell", ["US4WA1HK", "US5SEAKL"])
def test_reader_extracts_seabed(fixtures_dir, cell):
    zip_path = fixtures_dir / f"{cell}.zip"
    _, feats = read_cell(zip_path)
    s = [f for f in feats if f.layer == "seabed"]
    assert Counter(f.props["class"] for f in s) == ogr_class_counts(zip_path, ["SBDARE", "WEDKLP"])
    ours = sorted(
        ((f.props["class"],) + shape(f.geometry).bounds[:2]
         + (f.props.get("NATSUR"), f.props.get("NATQUA"), f.props.get("CATWED")) for f in s),
        key=repr,
    )
    assert ours == ogr_seabed(zip_path)
    assert all(f.props["src"] == "enc" and f.props["label"] and "SCAMIN" in f.props for f in s)
    # R37: areas and lines carry their size for the zoom thinning and the label order; points do not
    for f in s:
        if f.geometry["type"] == "Point":
            assert "extent" not in f.props
        else:
            assert f.props["extent"] == pytest.approx(extent_z0(f.geometry), rel=1e-5) and f.props["extent"] > 0


def test_seabed_labels_in_test_cell(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    s = [f.props for f in feats if f.layer == "seabed"]
    assert any(p.get("NATSUR") == "4,1" for p in s)  # NATSUR kept as the comma string
    by = {(p.get("NATSUR"), p.get("NATQUA")): p["label"] for p in s if p["class"] == "SBDARE"}
    assert by[("4,1", None)] == "S.M" and by[("4", "1")] == "fS" and by[(None, "10")] == "h"
    assert by[("2,1,17", None)] == "Cy.M.Sh" and by[("9", None)] == "Rk"
    weed = {p.get("CATWED"): p["label"] for p in s if p["class"] == "WEDKLP"}
    assert weed == {1: "Kelp", 3: "Sg", None: "Wd"}
