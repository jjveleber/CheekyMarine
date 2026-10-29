"""Local HTTP server that lets MapLibre in a headless browser read a pack directory."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from chartpack.mbtiles import MBTiles

HERE = Path(__file__).resolve().parent
_TYPES = {
    ".json": "application/json", ".png": "image/png", ".pbf": "application/x-protobuf",
    ".css": "text/css", ".mjs": "text/javascript", ".html": "text/html",
}
_TILE = re.compile(r"/tiles/([^/]+)/(\d+)/(\d+)/(\d+)\.(pbf|png)")


class PackServer:
    def __init__(self, pack_dirs: list[Path]):
        self.pack_dirs = [Path(p) for p in pack_dirs]
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def style_url(self, style_name: str) -> str:
        return f"{self.base}/styles/{style_name}.json"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()

    def _find(self, *parts: str) -> Path | None:
        for pack in self.pack_dirs:
            path = pack.joinpath(*parts)
            if path.is_file() and pack.resolve() in path.resolve().parents:
                return path
        return None

    def _tile_source(self, name: str) -> Path | None:
        return self._find(f"{name}.mbtiles")

    def _style(self, name: str) -> dict | None:
        path = self._find("styles", f"{name}.json")
        if path is None:
            return None
        style = json.loads(path.read_text())
        for name, source in style["sources"].items():
            tiles = self._tile_source(name)
            if tiles is None:
                continue
            with MBTiles.open(tiles) as m:
                md = m.metadata()
            ext = "png" if source["type"] == "raster-dem" else "pbf"
            source.pop("url", None)
            source["tiles"] = [f"{self.base}/tiles/{name}/{{z}}/{{x}}/{{y}}.{ext}"]
            if "minzoom" in md and "maxzoom" in md:
                source["minzoom"], source["maxzoom"] = int(md["minzoom"]), int(md["maxzoom"])
        sprite = style["sprite"].rsplit("/", 1)[-1]
        style["sprite"] = f"{self.base}/sprites/{sprite}"
        style["glyphs"] = f"{self.base}/glyphs/{{fontstack}}/{{range}}.pbf"
        return style

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code: int, body: bytes = b"", ctype: str | None = None, gzip: bool = False):
                self.send_response(code)
                if ctype:
                    self.send_header("Content-Type", ctype)
                if gzip:
                    self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the browser abandoned the request

            def _file(self, path: Path | None):
                if path is None:
                    return self._send(404)
                self._send(200, path.read_bytes(), _TYPES.get(path.suffix, "application/octet-stream"))

            def do_GET(self):
                path = unquote(urlsplit(self.path).path)
                if m := re.fullmatch(r"/styles/([^/]+)\.json", path):
                    style = server._style(m[1])
                    if style is None:
                        return self._send(404)
                    return self._send(200, json.dumps(style).encode(), "application/json")
                if m := _TILE.fullmatch(path):
                    tiles = server._tile_source(m[1])
                    if tiles is None:
                        return self._send(404)
                    z, x, y = int(m[2]), int(m[3]), int(m[4])
                    with MBTiles.open(tiles) as db:
                        data = db.get_tile(z, x, y)
                    if data is None:
                        return self._send(204)
                    ctype = "application/x-protobuf" if m[5] == "pbf" else "image/png"
                    return self._send(200, data, ctype, gzip=data[:2] == b"\x1f\x8b")
                if m := re.fullmatch(r"/sprites/([^/]+)", path):
                    return self._file(server._find("sprites", m[1]))
                if m := re.fullmatch(r"/glyphs/([^/]+)/([^/]+\.pbf)", path):
                    return self._file(server._find("glyphs", m[1], m[2]))
                if path == "/page.html":
                    return self._file(HERE / "page.html")
                if m := re.fullmatch(r"/vendor/(maplibre-gl(?:-worker)?\.(?:mjs|css))", path):
                    return self._file(HERE / "vendor" / m[1])
                self._send(404)

        return Handler
