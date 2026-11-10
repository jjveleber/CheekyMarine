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
    # 44999 -> zoom 12 (R44, 512 px world): absent at z11, present from z12 (band 4 ends at 12, then band 5)
    assert [_range(f) for f in out] == [(12, 12), (13, 16)]


def test_thinned_feature_dropped_when_minzoom_exceeds_range():
    area = Feature(
        "area",
        mapping(box(0, 0, 1, 1)),
        {"cell": "US3AAAAA", "band": 3, "class": "SEAARE", "SCAMIN": 5999},
    )
    out = quilt([(_cell("US3AAAAA", 3, (0, 0, 1, 1)), [area])])
    assert [_range(f) for f in out] == [(15, 16)]  # 5999 -> zoom 15, past band 3's top zoom 10


def test_seabed_area_minzoom_is_the_larger_of_scamin_and_size():
    """R37: a seabed area shows from the zoom where it is about 48 px across, or its SCAMIN zoom if later."""
    small = box(-122.5, 48.0, -122.499, 48.001)  # about 75 by 110 m: 48 px across at z15 (R44)
    big = box(-122.5, 48.0, -122.45, 48.05)  # about 3.7 by 5.6 km: 48 px across at z10, so band 4's z11
    feats = [Feature("seabed", mapping(g), {"cell": "US4AAAAA", "band": 4, "class": "SBDARE", "SCAMIN": scamin,
                                            "extent": extent_z0(mapping(g))})
             for g, scamin in ((small, 179999), (big, 179999), (big, 44999))]
    out = quilt([(_cell("US4AAAAA", 4, (-123, 47, -122, 49)), feats)])
    ranges = [[_range(f) for f in out if f.props["SCAMIN"] == s and f.geometry == mapping(g)] for g, s in
              ((small, 179999), (big, 179999), (big, 44999))]
    assert ranges == [[(15, 16)], [(11, 12), (13, 16)], [(12, 12), (13, 16)]]


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


def test_band2_clipped_by_band3():
    c2 = _cell("US2AAAAA", 2, (0, 0, 2, 1))
    c3 = _cell("US3AAAAA", 3, (0, 0, 1, 1))
    out = quilt([(c2, [_depare(2, "US2AAAAA", (0, 0, 2, 1))]), (c3, [])])
    low = _in(out, "depare", 2, (6, 10))
    assert len(low) == 1 and shape(low[0].geometry).equals(box(1, 0, 2, 1))
    mid = _in(out, "depare", 2, (11, 12))
    assert len(mid) == 1 and shape(mid[0].geometry).equals(box(1, 0, 2, 1))


def test_band1_clipped_by_band2_and_3():
    c1 = _cell("US1AAAAA", 1, (0, 0, 3, 1))
    c2 = _cell("US2AAAAA", 2, (0, 0, 1, 1))
    c3 = _cell("US3AAAAA", 3, (1, 0, 2, 1))
    out = quilt([(c1, [_depare(1, "US1AAAAA", (0, 0, 3, 1))]), (c2, []), (c3, [])])
    low = _in(out, "depare", 1, (6, 10))
    assert len(low) == 1 and shape(low[0].geometry).equals(box(2, 0, 3, 1))
    # with band 2 coverage alone, band 1 is still clipped by it
    only2 = quilt([(c1, [_depare(1, "US1AAAAA", (0, 0, 3, 1))]), (c2, [])])
    (f,) = _in(only2, "depare", 1, (6, 10))
    assert shape(f.geometry).equals(box(1, 0, 3, 1))


def _synthetic_cells():
    def cell(name, band, covr):
        return _cell(name, band, covr)

    def area(band, name, bounds, scamin=None):
        props = {"cell": name, "band": band, "class": "SEAARE"}
        if scamin is not None:
            props["SCAMIN"] = scamin
        return Feature("area", mapping(box(*bounds)), props)

    def depare(band, name, bounds):
        return _depare(band, name, bounds)

    def sound(band, name, x, scamin):
        props = {"cell": name, "band": band, "class": "SOUNDG", "depth": "3.2", "SCAMIN": scamin}
        return Feature("soundg", {"type": "Point", "coordinates": [x, 0.5]}, props)

    def wreck(band, name, x):
        return Feature("hazard", {"type": "Point", "coordinates": [x, 0.5]}, {"cell": name, "band": band, "class": "WRECKS"})

    return [
        (
            cell("US3AAAAA", 3, (0, 0, 4, 2)),
            [
                area(3, "US3AAAAA", (0, 0, 4, 2), 1000000),
                depare(3, "US3AAAAA", (0, 0, 4, 2)),
                sound(3, "US3AAAAA", 0.5, 400000),
                sound(3, "US3AAAAA", 3.5, 90000),
                wreck(3, "US3AAAAA", 0.5),
                wreck(3, "US3AAAAA", 3.5),
            ],
        ),
        (
            cell("US4AAAAA", 4, (1, 0, 3, 2)),
            [
                area(4, "US4AAAAA", (1, 0, 3, 2), 180000),
                depare(4, "US4AAAAA", (1, 0, 3, 2)),
                sound(4, "US4AAAAA", 2.0, 44999),
                wreck(4, "US4AAAAA", 2.0),
            ],
        ),
        (
            cell("US5AAAAA", 5, (1.5, 0.5, 2.5, 1.5)),
            [
                area(5, "US5AAAAA", (1.5, 0.5, 2.5, 1.5), 22000),
                depare(5, "US5AAAAA", (1.5, 0.5, 2.5, 1.5)),
                sound(5, "US5AAAAA", 2.0, 22000),
                wreck(5, "US5AAAAA", 2.0),
            ],
        ),
    ]


def _canon(out):
    return [(f.layer, f.geometry, {k: f.props[k] for k in sorted(f.props)}) for f in out]


EXPECTED_BANDS_3_TO_5 = [('area',
  {'coordinates': (((4.0, 0.0), (4.0, 2.0), (0.0, 2.0), (0.0, 0.0), (4.0, 0.0)),), 'type': 'Polygon'},
  {'SCAMIN': 1000000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 10, 'minzoom': 8}}),
 ('depare',
  {'coordinates': (((4.0, 0.0), (4.0, 2.0), (0.0, 2.0), (0.0, 0.0), (4.0, 0.0)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 10, 'minzoom': 6}}),
 ('soundg',
  {'coordinates': [0.5, 0.5], 'type': 'Point'},
  {'SCAMIN': 400000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 10, 'minzoom': 9}}),
 ('hazard',
  {'coordinates': [0.5, 0.5], 'type': 'Point'},
  {'band': 3, 'cell': 'US3AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 10, 'minzoom': 6}}),
 ('hazard',
  {'coordinates': [3.5, 0.5], 'type': 'Point'},
  {'band': 3, 'cell': 'US3AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 10, 'minzoom': 6}}),
 ('area',
  {'coordinates': (((4.0, 2.0), (4.0, 0.0), (3.0, 0.0), (3.0, 2.0), (4.0, 2.0)),), 'type': 'Polygon'},
  {'SCAMIN': 1000000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('area',
  {'coordinates': (((0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (1.0, 0.0), (0.0, 0.0)),), 'type': 'Polygon'},
  {'SCAMIN': 1000000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('depare',
  {'coordinates': (((4.0, 2.0), (4.0, 0.0), (3.0, 0.0), (3.0, 2.0), (4.0, 2.0)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('depare',
  {'coordinates': (((0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (1.0, 0.0), (0.0, 0.0)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('soundg',
  {'coordinates': [0.5, 0.5], 'type': 'Point'},
  {'SCAMIN': 400000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('soundg',
  {'coordinates': [3.5, 0.5], 'type': 'Point'},
  {'SCAMIN': 90000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('hazard',
  {'coordinates': [0.5, 0.5], 'type': 'Point'},
  {'band': 3, 'cell': 'US3AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('hazard',
  {'coordinates': [3.5, 0.5], 'type': 'Point'},
  {'band': 3, 'cell': 'US3AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('area',
  {'coordinates': (((3.0, 0.0), (3.0, 2.0), (1.0, 2.0), (1.0, 0.0), (3.0, 0.0)),), 'type': 'Polygon'},
  {'SCAMIN': 180000,
   'band': 4,
   'cell': 'US4AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('depare',
  {'coordinates': (((3.0, 0.0), (3.0, 2.0), (1.0, 2.0), (1.0, 0.0), (3.0, 0.0)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 4,
   'cell': 'US4AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('soundg',
  {'coordinates': [2.0, 0.5], 'type': 'Point'},
  {'SCAMIN': 44999,
   'band': 4,
   'cell': 'US4AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 12, 'minzoom': 12}}),
 ('hazard',
  {'coordinates': [2.0, 0.5], 'type': 'Point'},
  {'band': 4, 'cell': 'US4AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 12, 'minzoom': 11}}),
 ('area',
  {'coordinates': (((4.0, 2.0), (4.0, 0.0), (3.0, 0.0), (3.0, 2.0), (4.0, 2.0)),), 'type': 'Polygon'},
  {'SCAMIN': 1000000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('area',
  {'coordinates': (((0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (1.0, 0.0), (0.0, 0.0)),), 'type': 'Polygon'},
  {'SCAMIN': 1000000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('depare',
  {'coordinates': (((4.0, 2.0), (4.0, 0.0), (3.0, 0.0), (3.0, 2.0), (4.0, 2.0)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('depare',
  {'coordinates': (((0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (1.0, 0.0), (0.0, 0.0)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('soundg',
  {'coordinates': [0.5, 0.5], 'type': 'Point'},
  {'SCAMIN': 400000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('soundg',
  {'coordinates': [3.5, 0.5], 'type': 'Point'},
  {'SCAMIN': 90000,
   'band': 3,
   'cell': 'US3AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('hazard',
  {'coordinates': [0.5, 0.5], 'type': 'Point'},
  {'band': 3, 'cell': 'US3AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('hazard',
  {'coordinates': [3.5, 0.5], 'type': 'Point'},
  {'band': 3, 'cell': 'US3AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('area',
  {'coordinates': (((1.0, 0.0), (1.0, 2.0), (3.0, 2.0), (3.0, 0.0), (1.0, 0.0)),
                   ((2.5, 1.5), (1.5, 1.5), (1.5, 0.5), (2.5, 0.5), (2.5, 1.5))),
   'type': 'Polygon'},
  {'SCAMIN': 180000,
   'band': 4,
   'cell': 'US4AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('depare',
  {'coordinates': (((1.0, 0.0), (1.0, 2.0), (3.0, 2.0), (3.0, 0.0), (1.0, 0.0)),
                   ((2.5, 1.5), (1.5, 1.5), (1.5, 0.5), (2.5, 0.5), (2.5, 1.5))),
   'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 4,
   'cell': 'US4AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('soundg',
  {'coordinates': [2.0, 0.5], 'type': 'Point'},
  {'SCAMIN': 44999,
   'band': 4,
   'cell': 'US4AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('hazard',
  {'coordinates': [2.0, 0.5], 'type': 'Point'},
  {'band': 4, 'cell': 'US4AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('area',
  {'coordinates': (((2.5, 0.5), (2.5, 1.5), (1.5, 1.5), (1.5, 0.5), (2.5, 0.5)),), 'type': 'Polygon'},
  {'SCAMIN': 22000,
   'band': 5,
   'cell': 'US5AAAAA',
   'class': 'SEAARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('depare',
  {'coordinates': (((2.5, 0.5), (2.5, 1.5), (1.5, 1.5), (1.5, 0.5), (2.5, 0.5)),), 'type': 'Polygon'},
  {'DRVAL1': '0.0',
   'DRVAL2': '5.5',
   'band': 5,
   'cell': 'US5AAAAA',
   'class': 'DEPARE',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('soundg',
  {'coordinates': [2.0, 0.5], 'type': 'Point'},
  {'SCAMIN': 22000,
   'band': 5,
   'cell': 'US5AAAAA',
   'class': 'SOUNDG',
   'depth': '3.2',
   'tippecanoe': {'maxzoom': 16, 'minzoom': 13}}),
 ('hazard',
  {'coordinates': [2.0, 0.5], 'type': 'Point'},
  {'band': 5, 'cell': 'US5AAAAA', 'class': 'WRECKS', 'tippecanoe': {'maxzoom': 16, 'minzoom': 13}})]


def test_bands_3_to_5_unchanged():
    # EXPECTED_BANDS_3_TO_5 was captured from quilt() at commit 9fec335, before bands 1 and 2 were quilted.
    assert _canon(quilt(_synthetic_cells())) == EXPECTED_BANDS_3_TO_5
