import math

import pytest
from shapely.geometry import LineString, box, mapping

from chartpack.enc.scamin import BAND_ZOOMS, extent_z0, minzoom_for_extent, minzoom_for_scamin


# zoom = round(log2(559082264.028 * cos(48 deg) / scamin) - 1): MapLibre's 512 px world (R44), one zoom
# earlier than 256 px tiles. 44999 is about 4x finer than 179999, so it lands two zooms above it (12.02 -> 12).
@pytest.mark.parametrize(
    "scamin,band,expected",
    [(None, 4, 11), (179999, 4, 11), (44999, 4, 12), (11999, 5, 14), (5999, 5, 15), (1, 5, 16)],
)
def test_minzoom_for_scamin(scamin, band, expected):
    assert minzoom_for_scamin(scamin, band, 48.0) == expected


@pytest.mark.parametrize("scamin,band,expected", [(259999, 3, 9), (59999, 4, 12), (29999, 5, 13), (17999, 5, 13)])
def test_puget_north_scamins(scamin, band, expected):
    """R44: band 4 soundings (59999) show from z12, band 5 soundings (17999, 29999) from z13."""
    assert minzoom_for_scamin(scamin, band, 48.0) == expected


def test_non_positive_scamin_gives_band_low_zoom():
    assert minzoom_for_scamin(0, 5, 48.0) == BAND_ZOOMS[5][0]
    assert minzoom_for_scamin(-3, 4, 48.0) == BAND_ZOOMS[4][0]


def test_huge_scamin_clamped_up_to_band_low_zoom():
    assert minzoom_for_scamin(10**9, 5, 48.0) == 13


def _mercator_px(lon, lat):
    """256 px Web Mercator pixel coordinates at zoom 0."""
    return (lon + 180) / 360 * 256, (1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2 * 256


def test_extent_of_a_polygon_is_sqrt_area_in_zoom0_pixels():
    """R37: a 0.01 by 0.01 degree box at 48 N (about 740 m by 1110 m)."""
    (x0, y0), (x1, y1) = _mercator_px(-122.5, 48.0), _mercator_px(-122.49, 48.01)
    want = math.sqrt(abs((x1 - x0) * (y1 - y0)))
    assert extent_z0(mapping(box(-122.5, 48.0, -122.49, 48.01))) == pytest.approx(want, rel=1e-4)


def test_extent_of_a_line_is_its_length_in_zoom0_pixels():
    (x0, y0), (x1, y1) = _mercator_px(-122.5, 48.0), _mercator_px(-122.48, 48.0)
    assert extent_z0(mapping(LineString([(-122.5, 48.0), (-122.48, 48.0)]))) == pytest.approx(x1 - x0, rel=1e-5)


def test_minzoom_for_extent_is_the_first_zoom_at_48_px():
    """R44: screen px in MapLibre's 512 px world, extent * 2**(z+1)."""
    extent = extent_z0(mapping(box(-122.5, 48.0, -122.49, 48.01)))
    assert extent * 2**12 < 48 <= extent * 2**13
    assert minzoom_for_extent(extent) == 12
    assert minzoom_for_extent(48 / 2**11) == 10  # exactly 48 px at z10
    assert minzoom_for_extent(1e-9) == 16  # clamped to the pack maxzoom
    assert minzoom_for_extent(10.0) == 2 and minzoom_for_extent(100.0) == 0


# minzoom_for_scamin(scamin, band) before #18 (hard-coded 48 N), captured from commit a1c4f0f.
_OLD_AT_48 = {
    (21999, 3): 13, (21999, 4): 13, (21999, 5): 13,
    (29999, 3): 13, (29999, 4): 13, (29999, 5): 13,
    (59999, 3): 12, (59999, 4): 12, (59999, 5): 13,
    (89999, 3): 11, (89999, 4): 11, (89999, 5): 13,
    (499999, 3): 9, (499999, 4): 11, (499999, 5): 13,
}


@pytest.mark.parametrize("scamin,band", sorted(_OLD_AT_48))
def test_scamin_zoom_matches_old_value_at_48(scamin, band):
    """#18: packs built at 48 N keep the zooms they had with the hard-coded latitude."""
    assert minzoom_for_scamin(scamin, band, 48.0) == _OLD_AT_48[scamin, band]


@pytest.mark.parametrize(
    "scamin,at_48,at_54", [(21999, 13, 13), (29999, 13, 12), (59999, 12, 11), (89999, 11, 11), (499999, 9, 8)]
)
def test_scamin_zoom_shifts_at_54(scamin, at_48, at_54):
    """#18: the ground under a SCAMIN is smaller farther north, so some features show one zoom earlier. Band 3
    starts at zoom 6, so none of these values is clamped."""
    assert minzoom_for_scamin(scamin, 3, 48.0) == at_48
    assert minzoom_for_scamin(scamin, 3, 54.0) == at_54


def test_scamin_latitude_rounded_to_quarter_degree():
    """Latitudes that round to the same 0.25 degree give the same zoom (both sides of a seam agree)."""
    assert minzoom_for_scamin(29999, 3, 53.88) == minzoom_for_scamin(29999, 3, 54.0)
    assert minzoom_for_scamin(29999, 3, 51.12) == minzoom_for_scamin(29999, 3, 51.0)
