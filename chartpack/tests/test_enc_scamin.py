import pytest

from chartpack.enc.scamin import BAND_ZOOMS, minzoom_for_scamin


# zoom = round(log2(559082264.028 * cos(48 deg) / scamin)); each factor of 2 in scale is one zoom.
# 44999 is about 4x finer than 179999, so it lands two zooms above it (13.02 -> 13), not one.
@pytest.mark.parametrize(
    "scamin,band,expected",
    [(None, 4, 11), (179999, 4, 11), (44999, 4, 13), (11999, 5, 15), (5999, 5, 16), (1, 5, 16)],
)
def test_minzoom_for_scamin(scamin, band, expected):
    assert minzoom_for_scamin(scamin, band) == expected


def test_non_positive_scamin_gives_band_low_zoom():
    assert minzoom_for_scamin(0, 5) == BAND_ZOOMS[5][0]
    assert minzoom_for_scamin(-3, 4) == BAND_ZOOMS[4][0]


def test_huge_scamin_clamped_up_to_band_low_zoom():
    assert minzoom_for_scamin(10**9, 5) == 13
