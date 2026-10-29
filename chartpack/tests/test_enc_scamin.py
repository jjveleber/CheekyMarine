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
    assert minzoom_for_scamin(scamin, band) == expected


@pytest.mark.parametrize("scamin,band,expected", [(259999, 3, 9), (59999, 4, 12), (29999, 5, 13), (17999, 5, 13)])
def test_puget_north_scamins(scamin, band, expected):
    """R44: band 4 soundings (59999) show from z12, band 5 soundings (17999, 29999) from z13."""
    assert minzoom_for_scamin(scamin, band) == expected


def test_non_positive_scamin_gives_band_low_zoom():
    assert minzoom_for_scamin(0, 5) == BAND_ZOOMS[5][0]
    assert minzoom_for_scamin(-3, 4) == BAND_ZOOMS[4][0]


def test_huge_scamin_clamped_up_to_band_low_zoom():
    assert minzoom_for_scamin(10**9, 5) == 13


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
