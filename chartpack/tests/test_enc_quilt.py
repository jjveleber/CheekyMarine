import copy
from pathlib import Path

import pytest
from shapely.geometry import box, mapping, shape

from chartpack.enc.quilt import quilt
from chartpack.enc.scamin import extent_z0
from chartpack.enc.reader import CellMeta, Feature, read_cell


def _cell(name, band, covr_box):
    return CellMeta(name, band, 1, 0, "2026-01-01", mapping(box(*covr_box)))


def _depare(band, cell, bounds=(0, 0, 1, 1)):
    props = {"cell": cell, "band": band, "class": "DEPARE", "DRVAL1": "0.0", "DRVAL2": "5.5"}
    return Feature("depare", mapping(box(*bounds)), props)


def _range(f):
    t = f.props["tippecanoe"]
    return (t["minzoom"], t["maxzoom"])


def _in(out, layer, band, rng):
    return [f for f in out if f.layer == layer and f.props["band"] == band and _range(f) == rng]


def test_primary_band_fills_its_range():
    out = quilt([(_cell("US4AAAAA", 4, (0, 0, 1, 1)), [_depare(4, "US4AAAAA")])])
    assert sorted(_range(f) for f in out if f.props["band"] == 4) == [(11, 12), (13, 16)]


def test_lower_band_clipped_where_higher_exists():
    c3 = _cell("US3AAAAA", 3, (0, 0, 1, 1))
    c4 = _cell("US4AAAAA", 4, (0, 0, 0.5, 1))
    out = quilt([(c3, [_depare(3, "US3AAAAA")]), (c4, [_depare(4, "US4AAAAA", (0, 0, 0.5, 1))])])
    low = _in(out, "depare", 3, (6, 10))
    assert len(low) == 1 and shape(low[0].geometry).equals(box(0, 0, 1, 1))
    mid = _in(out, "depare", 3, (11, 12))
    assert len(mid) == 1 and shape(mid[0].geometry).equals(box(0.5, 0, 1, 1))
    assert mid[0].props["DRVAL2"] == "5.5"
    far = _in(out, "depare", 3, (13, 16))
    assert len(far) == 1 and shape(far[0].geometry).equals(box(0.5, 0, 1, 1))


def test_lower_band_fills_in_where_higher_absent():
    out = quilt([(_cell("US4AAAAA", 4, (0, 0, 1, 1)), [_depare(4, "US4AAAAA")])])
    (f,) = _in(out, "depare", 4, (13, 16))
    assert f.geometry == mapping(box(0, 0, 1, 1))


def test_higher_band_not_drawn_below_its_range():
    out = quilt([(_cell("US5AAAAA", 5, (0, 0, 1, 1)), [_depare(5, "US5AAAAA")])])
    assert out and all(f.props["tippecanoe"]["minzoom"] >= 13 for f in out)
    assert all(f.props["tippecanoe"]["maxzoom"] == 16 for f in out)


def test_soundings_use_scamin():
    pt = Feature(
        "soundg",
        {"type": "Point", "coordinates": [0.5, 0.5]},
        {"cell": "US4AAAAA", "band": 4, "class": "SOUNDG", "depth": "3.2", "SCAMIN": 44999},
    )
    out = quilt([(_cell("US4AAAAA", 4, (0, 0, 1, 1)), [pt])])
    # 44999 -> zoom 13: absent from (11,12), present from 13
    assert [_range(f) for f in out] == [(13, 16)]


def test_thinned_feature_dropped_when_minzoom_exceeds_range():
    area = Feature(
        "area",
        mapping(box(0, 0, 1, 1)),
        {"cell": "US3AAAAA", "band": 3, "class": "SEAARE", "SCAMIN": 5999},
    )
    out = quilt([(_cell("US3AAAAA", 3, (0, 0, 1, 1)), [area])])
    assert [_range(f) for f in out] == [(16, 16)]


def test_seabed_area_minzoom_is_the_larger_of_scamin_and_size():
    """R37: a seabed area shows from the zoom where it is about 48 px across, or its SCAMIN zoom if later."""
    small = box(-122.5, 48.0, -122.499, 48.001)  # about 75 by 110 m: 48 px across at z16
    big = box(-122.5, 48.0, -122.45, 48.05)  # about 3.7 by 5.6 km: 48 px across at z11
    feats = [Feature("seabed", mapping(g), {"cell": "US4AAAAA", "band": 4, "class": "SBDARE", "SCAMIN": scamin,
                                            "extent": extent_z0(mapping(g))})
             for g, scamin in ((small, 179999), (big, 179999), (big, 44999))]
    out = quilt([(_cell("US4AAAAA", 4, (-123, 47, -122, 49)), feats)])
    ranges = [[_range(f) for f in out if f.props["SCAMIN"] == s and f.geometry == mapping(g)] for g, s in
              ((small, 179999), (big, 179999), (big, 44999))]
    assert ranges == [[(16, 16)], [(11, 12), (13, 16)], [(13, 16)]]


def test_safety_layers_ignore_scamin():
    hz = Feature(
        "hazard",
        {"type": "Point", "coordinates": [0.5, 0.5]},
        {"cell": "US4AAAAA", "band": 4, "class": "WRECKS", "SCAMIN": 5999},
    )
    out = quilt([(_cell("US4AAAAA", 4, (0, 0, 1, 1)), [hz])])
    assert sorted(_range(f) for f in out) == [(11, 12), (13, 16)]


def test_points_inside_higher_coverage_are_dropped():
    pts = [
        Feature("hazard", {"type": "Point", "coordinates": [x, 0.5]}, {"cell": "US3AAAAA", "band": 3, "class": "WRECKS"})
        for x in (0.25, 0.75)
    ]
    c3 = _cell("US3AAAAA", 3, (0, 0, 1, 1))
    c4 = _cell("US4AAAAA", 4, (0, 0, 0.5, 1))
    out = quilt([(c3, pts), (c4, [])])
    mid = _in(out, "hazard", 3, (11, 12))
    assert [f.geometry["coordinates"][0] for f in mid] == [0.75]


def test_multi_results_split_into_simple_parts_with_same_props():
    c3 = _cell("US3AAAAA", 3, (0, 0, 3, 1))
    c4 = _cell("US4AAAAA", 4, (1, 0, 2, 1))
    out = quilt([(c3, [_depare(3, "US3AAAAA", (0, 0, 3, 1))]), (c4, [])])
    mid = _in(out, "depare", 3, (11, 12))
    assert len(mid) == 2 and all(f.geometry["type"] == "Polygon" for f in mid)
    assert all(f.props["DRVAL1"] == "0.0" for f in mid)


def test_input_features_not_mutated():
    feat = _depare(4, "US4AAAAA")
    before = copy.deepcopy(feat)
    out = quilt([(_cell("US4AAAAA", 4, (0, 0, 1, 1)), [feat])])
    assert feat == before and "tippecanoe" not in feat.props
    assert all(f is not feat for f in out)


@pytest.fixture(scope="module")
def real_cells():
    fx = Path(__file__).resolve().parent / "fixtures"
    return [read_cell(fx / "US4WA1HK.zip"), read_cell(fx / "US5SEAKL.zip")]


def test_quilt_on_real_cells(real_cells):
    out = quilt(real_cells)
    hole = shape(next(m for m, _ in real_cells if m.band == 5).covr)
    in_band4 = [f for m, fs in real_cells if m.band == 4 for f in fs if f.layer == "depare"]
    clipped = _in(out, "depare", 4, (13, 16))
    assert in_band4 and clipped
    assert any(shape(f.geometry).intersects(hole.envelope) for f in in_band4)  # the clip is exercised
    for f in clipped:
        assert shape(f.geometry).intersection(hole).area < 1e-12
    # on its own range the band-4 cell is emitted whole, attributes untouched
    own = _in(out, "depare", 4, (11, 12))
    assert [f.geometry for f in own] == [f.geometry for f in in_band4]
    assert [f.props["DRVAL1"] for f in own] == [f.props["DRVAL1"] for f in in_band4 if "DRVAL1" in f.props]
