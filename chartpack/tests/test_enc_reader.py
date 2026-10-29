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


def test_every_hazard_present_with_attributes(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    h = [f for f in feats if f.layer == "hazard"]
    assert Counter(f.props["class"] for f in h) == ogr_class_counts(fixtures_dir / "US4WA1HK.zip", ["UWTROC", "WRECKS", "OBSTRN"])
    assert all("WATLEV" in f.props or f.props["class"] == "OBSTRN" for f in h)
    rock_without_depth = next(f for f in h if f.props["class"] == "UWTROC" and "VALSOU" not in f.props)
    assert "VALSOU" not in rock_without_depth.props


def test_soundings_are_split_points_with_depth(fixtures_dir):
    _, feats = read_cell(fixtures_dir / "US4WA1HK.zip")
    s = [f for f in feats if f.layer == "soundg"]
    assert all(f.geometry["type"] == "Point" and "depth" in f.props for f in s)
    assert len(s) == ogr_sounding_point_count(fixtures_dir / "US4WA1HK.zip")


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
