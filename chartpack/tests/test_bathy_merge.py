import json

import numpy as np
import pytest
from make_ridge import BBOX, NODATA, ORIGIN, PIXEL_DEG
from osgeo import osr
from shapely.geometry import LineString, Point, mapping, shape

from chartpack.bathy.cudem import Grid
from chartpack.bathy.merge import (
    clip_mask,
    coverage_polygons,
    fill_land,
    merge_to_mllw,
    tag_source,
    to_mllw_depth,
    uncovered_area,
)

RES = PIXEL_DEG


def _wkt(epsg: int) -> str:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    return srs.ExportToWkt()


@pytest.fixture
def ridge_grid(fixtures_dir):
    data = np.load(fixtures_dir / "ridge.npy")
    return Grid(data, NODATA, (ORIGIN[0], PIXEL_DEG, 0.0, ORIGIN[1], 0.0, -PIXEL_DEG), _wkt(4269))


@pytest.fixture
def flat_fallback():
    """-50 m everywhere, 0.01 degree cells, a little larger than BBOX."""
    data = np.full((24, 24), -50.0, np.float32)
    return Grid(data, -9999.0, (-122.51, 0.01, 0.0, 48.01, 0.0, -0.01), _wkt(4326))


@pytest.fixture
def merged(ridge_grid, flat_fallback):
    grid, src = merge_to_mllw([(ridge_grid, "cudem")], flat_fallback, 2.02, 0.715, BBOX, res_deg=RES)
    return grid.data, src


TRANSFORM = (BBOX[0], RES, 0.0, BBOX[3], 0.0, -RES)
HOLE = (slice(50, 60), slice(50, 60))


def xy(row: float, col: float) -> tuple[float, float]:
    return (BBOX[0] + col * RES, BBOX[3] - row * RES)


def test_to_mllw_depth_navd88():
    assert to_mllw_depth(np.array([-10.0], np.float32), -9999.0, 0.715)[0] == pytest.approx(9.285, abs=1e-4)
    assert np.isnan(to_mllw_depth(np.array([-9999.0], np.float32), -9999.0, 0.715)[0])
    assert np.isnan(to_mllw_depth(np.array([np.nan], np.float32), float("nan"), 0.715)[0])


def test_nodata_hole_filled_from_fallback(merged):
    depth, src = merged
    hole = np.zeros(src.shape, bool)
    hole[HOLE] = True
    water = np.ones(src.shape, bool)
    water[:, 190:] = False
    assert depth.shape == (200, 200) and src.dtype == np.uint8
    assert not np.isnan(depth[hole]).any() and (src[hole] == 2).all()
    assert (src[~hole & water] == 1).all()
    assert abs(depth[hole].mean() - (50 - 2.02)) < 0.01
    assert depth[100, 100] == pytest.approx(20.0 - 0.715, abs=0.01)


def test_merged_grid_is_wgs84_with_nan_nodata(ridge_grid, flat_fallback):
    out = merge_to_mllw([(ridge_grid, "cudem")], flat_fallback, 2.02, 0.715, BBOX, res_deg=RES)
    grid, src = out
    assert isinstance(grid, Grid) and np.isnan(grid.nodata) and grid.data.dtype == np.float32
    assert grid.transform == pytest.approx(TRANSFORM)
    srs = osr.SpatialReference(wkt=grid.crs)
    assert srs.GetAuthorityCode(None) == "4326"
    assert src.shape == grid.data.shape


def test_fallback_only_where_primary_missing(ridge_grid, flat_fallback):
    # primary covers only the west half: the east half comes from the fallback
    half = Grid(ridge_grid.data[:, :100].copy(), NODATA, ridge_grid.transform, ridge_grid.crs)
    _, src = merge_to_mllw([(half, "cudem")], flat_fallback, 2.02, 0.715, BBOX, res_deg=RES)
    assert (src[:, :50] == 1).all() and (src[100:, :100] == 1).all()
    assert (src[:, 100:] == 2).all()


def test_no_coverage_is_zero(ridge_grid):
    far = Grid(np.full((4, 4), -50.0, np.float32), -9999.0, (-100.0, 0.01, 0.0, 40.0, 0.0, -0.01), _wkt(4326))
    grid, src = merge_to_mllw([(ridge_grid, "cudem")], far, 2.02, 0.715, BBOX, res_deg=RES)
    assert np.isnan(grid.data[HOLE]).all() and (src[HOLE] == 0).all()


def test_fill_land_closes_lines(merged):
    depth, _ = merged
    assert (depth[:, 195] < -0.3).all()  # land is above water by more than 0.3 m before
    filled = fill_land(depth)
    assert not (filled[np.isfinite(filled)] < -0.3).any()
    assert (filled[:, 190:] == np.float32(-0.3)).all()
    assert np.isnan(fill_land(np.array([np.nan, -2.0, 4.0], np.float32))[0])
    assert fill_land(np.array([np.nan, -2.0, 4.0], np.float32))[1:].tolist() == pytest.approx([-0.3, 4.0])


LABELS = {
    1: {"source": "cudem", "resolution_m": 3, "date": "2023"},
    2: {"source": "crm", "resolution_m": 30, "date": "2025"},
}


def test_coverage_polygons(merged):
    _, src = merged
    feats = coverage_polygons(src, TRANSFORM, LABELS)
    assert {f["properties"]["source"] for f in feats} == {"cudem", "crm"}
    assert all(f["type"] == "Feature" and f["geometry"]["type"] == "Polygon" for f in feats)
    cudem = next(f for f in feats if f["properties"]["source"] == "cudem")
    assert cudem["properties"] == LABELS[1] and cudem["properties"] is not LABELS[1]
    assert shape(cudem["geometry"]).contains(Point(*xy(150, 150)))
    crm = next(f for f in feats if f["properties"]["source"] == "crm")
    assert shape(crm["geometry"]).contains(Point(*xy(55, 55)))


def line_over(r0, r1, c0, c1):
    return {"type": "Feature", "geometry": mapping(LineString([xy(r0, c0), xy(r1, c1)])), "properties": {}}


def test_tag_source_and_uncovered(merged):
    _, src = merged
    feats = [line_over(54, 55, 54, 55), line_over(140, 160, 100, 100)]
    tagged = tag_source(feats, src, TRANSFORM, {1: "cudem", 2: "crm"})
    assert [f["properties"]["source"] for f in tagged] == ["crm", "cudem"]
    assert feats[0]["properties"] == {}  # input not mutated
    assert uncovered_area(src, TRANSFORM, treat_fallback_as_uncovered=False).is_empty
    assert uncovered_area(src, TRANSFORM, treat_fallback_as_uncovered=True).contains(Point(*xy(55, 55)))


def test_tag_source_drops_uncovered_features():
    src = np.zeros((10, 10), np.uint8)
    src[:, 5:] = 1
    t = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    feats = [
        {"type": "Feature", "geometry": mapping(LineString([(1.5, 5.5), (2.5, 5.5)])), "properties": {"a": 1}},
        {"type": "Feature", "geometry": mapping(LineString([(6.5, 5.5), (7.5, 5.5)])), "properties": {"a": 2}},
    ]
    tagged = tag_source(feats, src, t, {1: "cudem", 2: "crm"})
    assert [f["properties"] for f in tagged] == [{"a": 2, "source": "cudem"}]


def test_uncovered_area_zero_cells():
    src = np.ones((240, 240), np.uint8)
    src[:120, :120] = 0
    t = (0.0, 1 / 120, 0.0, 2.0, 0.0, -1 / 120)
    area = uncovered_area(src, t, treat_fallback_as_uncovered=False)
    assert area.contains(Point(0.5, 1.5)) and not area.contains(Point(1.5, 0.5))


def test_clip_removes_canadian_side(regions_dir):
    clip = json.loads((regions_dir / "clip/canada-wa.geojson").read_text())
    bbox = (-123.5, 48.0, -122.5, 48.9)
    t = (bbox[0], 0.01, 0.0, bbox[3], 0.0, -0.01)

    def cell_at(lat, lon):
        return int((bbox[3] - lat) / 0.01), int((lon - bbox[0]) / 0.01)

    m = clip_mask(t, (90, 100), clip)
    assert m.dtype == bool and m.shape == (90, 100)
    assert m[cell_at(48.75, -123.3)] and not m[cell_at(48.05, -122.6)]  # Gulf Islands side removed, Possession Bar kept
