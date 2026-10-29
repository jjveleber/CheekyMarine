import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen as _urlopen

import pytest

from chartpack.mbtiles import MBTiles
from chartpack.render.server import PackServer


class _Response:
    def __init__(self, r):
        self.status, self.headers, self.body = r.status, r.headers, r.read()

    def read(self):
        return self.body


def urlopen(url):
    with _urlopen(url) as r:
        return _Response(r)


def a_tile_that_exists(path, z):
    with MBTiles.open(path) as m:
        x, y, _ = next(m.tiles_at(z))
    return z, x, y


@pytest.fixture
def server(charts_pack_root):
    s = PackServer([charts_pack_root])
    s.start()
    yield s
    s.stop()


def _base(server):
    return server.style_url("nav-day").split("/styles/")[0]


def test_server_serves_tile_and_rewritten_style(server, charts_pack_root):
    style = json.loads(urlopen(server.style_url("nav-day")).read())
    src = style["sources"]["enc"]
    assert src["tiles"][0].startswith("http://127.0.0.1:") and "url" not in src
    assert src["type"] == "vector" and src["minzoom"] == 6 and src["maxzoom"] == 16
    assert style["sprite"].startswith("http://127.0.0.1:")
    assert style["glyphs"].endswith("/glyphs/{fontstack}/{range}.pbf")
    z, x, y = a_tile_that_exists(charts_pack_root / "enc.mbtiles", 13)
    r = urlopen(f"{_base(server)}/tiles/enc/{z}/{x}/{y}.pbf")
    body = r.body
    # tile-join -pC stores the tiles uncompressed; the header is set only when the stored bytes are gzipped
    assert r.status == 200 and r.headers["Content-Encoding"] == ("gzip" if body[:2] == b"\x1f\x8b" else None)
    assert r.headers["Content-Type"] == "application/x-protobuf"


def test_missing_tile_is_204_and_unknown_is_404(server):
    assert urlopen(f"{_base(server)}/tiles/enc/0/0/0.pbf").status == 204
    with pytest.raises(HTTPError) as e:
        urlopen(f"{_base(server)}/tiles/nope/0/0/0.pbf")
    e.value.close()
    assert e.value.code == 404


def test_sprites_glyphs_and_page(server):
    base = _base(server)
    assert urlopen(f"{base}/sprites/nav.png").headers["Content-Type"] == "image/png"
    assert isinstance(json.loads(urlopen(f"{base}/sprites/nav@2x.json").read()), dict)
    assert len(urlopen(f"{base}/glyphs/{quote('Noto Sans Bold')}/0-255.pbf").read()) > 1000
    assert b"__rendered" in urlopen(f"{base}/page.html?style=x").read()
    for name in ("maplibre-gl.mjs", "maplibre-gl-worker.mjs"):
        assert urlopen(f"{base}/vendor/{name}").headers["Content-Type"].startswith("text/javascript")
