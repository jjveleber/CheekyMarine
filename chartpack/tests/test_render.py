import numpy as np
import pytest
from PIL import Image

from chartpack.render.render import render_views


@pytest.mark.render
def test_render_produces_nonblank_png(charts_pack_root, test_region, tmp_path):
    out = render_views([charts_pack_root], test_region.views, ["nav-day"], tmp_path)
    assert [p.name for p in out] == [f"possession-bar-z{z}-nav-day.png" for z in (11, 13, 15)]
    img = np.asarray(Image.open(out[0]).convert("L"))
    assert img.std() > 10  # not a flat colour
