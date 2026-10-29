import io
import math

import numpy as np
import pytest
from make_ridge import BBOX, NODATA, PIXEL_DEG
from PIL import Image

from chartpack.bathy.dem import build_dem_mbtiles, terrarium_decode, terrarium_encode
from chartpack.bathy.merge import to_mllw_depth
from chartpack.mbtiles import MBTiles

OFFSET = 2.02
TRANSFORM = (BBOX[0], PIXEL_DEG, 0.0, BBOX[3], 0.0, -PIXEL_DEG)


@pytest.fixture
def ridge_depth(fixtures_dir):
    return to_mllw_depth(np.load(fixtures_dir / "ridge.npy"), NODATA, OFFSET)


def _tile_rgb(m, z, x, y):
    return np.asarray(Image.open(io.BytesIO(m.get_tile(z, x, y))).convert("RGB"))


def _pixel_at(z, lon, lat):
    n = 2**z
    fx = (lon + 180) / 360 * n
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(fx), int(fy), int((fx % 1) * 256), int((fy % 1) * 256)


def test_terrarium_roundtrip():
    e = np.array([[-123.45, 0.0, 12.5, -0.3, 4000.75]], np.float32)
    assert np.allclose(terrarium_decode(terrarium_encode(e)), e, atol=1 / 256)


def test_terrarium_channels_and_offset():
    rgb = terrarium_encode(np.array([[0.0, -32768.0, 1.5]], np.float32))
    assert rgb[0, 0].tolist() == [128, 0, 0]  # 32768 = 128 * 256
    assert rgb[0, 1].tolist() == [0, 0, 0]
    assert rgb[0, 2].tolist() == [128, 1, 128]  # 32769.5


def test_dem_mbtiles_roundtrip(ridge_depth, tmp_path):
    p = build_dem_mbtiles(ridge_depth, TRANSFORM, tmp_path / "dem.mbtiles", minzoom=10, maxzoom=12)
    with MBTiles.open(p) as m:
        md = m.metadata()
        assert md["format"] == "png" and md["cheekymarine:encoding"] == "terrarium"
        assert md["maxzoom"] == "12" and md["minzoom"] == "10" and md["name"] == "dem"
        assert md["bounds"] == "-122.5,47.8,-122.3,48.0"
        assert md["cheekymarine:pack"] == "bathy" and md["cheekymarine:schema"] == "1"
        assert md["type"] == "baselayer"
        assert len(list(m.tiles_at(10))) >= 1
        x, y, data = next(m.tiles_at(12))
        rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
        assert rgb.shape == (256, 256, 3) and terrarium_decode(rgb).min() < -5

        # deep water near the west edge: elevation = -depth, tolerant of bilinear resampling
        lon, lat = -122.49, 47.9
        cols = BBOX[0] + (np.arange(200) + 0.5) * PIXEL_DEG
        tx, ty, px, py = _pixel_at(12, lon, lat)
        centre_lon = (tx + (px + 0.5) / 256) / 2**12 * 360 - 180  # sample where the pixel is centred
        expected = -np.interp(centre_lon, cols, ridge_depth[100])
        dec = terrarium_decode(_tile_rgb(m, 12, tx, ty))
        assert dec[py, px] == pytest.approx(expected, abs=0.1) and expected < -100

        # land plateau (flat): exact to the encoding precision
        lon = -122.305
        tx, ty, px, py = _pixel_at(12, lon, lat)
        dec = terrarium_decode(_tile_rgb(m, 12, tx, ty))
        assert dec[py, px] == pytest.approx(-ridge_depth[100, 195], abs=1 / 128)

        # no tile outside the grid bbox
        xs = [t[0] for t in m.tiles_at(12)]
        assert min(xs) == _pixel_at(12, BBOX[0], lat)[0] and max(xs) == _pixel_at(12, BBOX[2], lat)[0]


def test_nan_is_sea_level(tmp_path):
    depth = np.full((20, 20), np.nan, np.float32)
    p = build_dem_mbtiles(depth, (-122.5, 0.001, 0.0, 48.0, 0.0, -0.001), tmp_path / "d.mbtiles", minzoom=12, maxzoom=12)
    with MBTiles.open(p) as m:
        for _, _, data in m.tiles_at(12):
            dec = terrarium_decode(np.asarray(Image.open(io.BytesIO(data)).convert("RGB")))
            assert np.all(dec == 0)
