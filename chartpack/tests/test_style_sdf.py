import numpy as np

from chartpack.style.sdf import bitmap_to_sdf


def test_sdf_of_filled_square():
    a = np.zeros((20, 20), np.uint8)
    a[5:15, 5:15] = 255
    s = bitmap_to_sdf(a)
    assert s.shape == (26, 26) and s[13, 13] > 200 and s[0, 0] < 30 and 100 < s[8, 13] < 200  # inside high, far outside low, edge mid
