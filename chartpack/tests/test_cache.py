import io
import http.server
import threading

import pytest

from chartpack.cache import DownloadError, download


@pytest.fixture
def http_server_that_truncates():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2000")
            self.end_headers()
            self.wfile.write(b"x" * 1000)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/f.bin"
    server.shutdown()
    server.server_close()


def test_partial_download_is_rejected(tmp_path, http_server_that_truncates):
    dest = tmp_path / "f.bin"
    with pytest.raises(DownloadError):
        download(http_server_that_truncates, dest, expected_size=2000)
    assert not dest.exists() and not (tmp_path / "f.bin.part").exists()


def test_fetch_zip_refetches_same_size_zip_with_corrupt_deflate(tmp_path, fixtures_dir, monkeypatch):
    """Review Focus 5: a cached zip of the right size whose member's deflate stream is damaged (zlib.error,
    which zipfile.testzip does not turn into a CRC result) is rejected and fetched again."""
    import shutil

    from chartpack import cache
    from zipdamage import flip_to_zlib_error

    src = fixtures_dir / "seabed" / "CMECS_OffshoreSeattle.zip"
    calls = []

    def fake(url, dest, *, expected_size=None, timeout=120):
        calls.append(url)
        shutil.copy(src, dest)
        return dest

    monkeypatch.setattr(cache, "download", fake)
    dest = tmp_path / "CMECS_OffshoreSeattle.zip"
    shutil.copy(src, dest)
    flip_to_zlib_error(dest, "CMECS_OffshoreSeattle.shp")
    assert dest.stat().st_size == src.stat().st_size
    cache.fetch_zip("u", dest, size=src.stat().st_size, member="CMECS_OffshoreSeattle.shp")
    assert calls == ["u"] and dest.read_bytes() == src.read_bytes()


def test_truncation_is_rejected_without_expected_size(tmp_path, http_server_that_truncates):
    dest = tmp_path / "f.bin"
    with pytest.raises(DownloadError):
        download(http_server_that_truncates, dest)
    assert not dest.exists() and not (tmp_path / "f.bin.part").exists()


def _fake_urlopen(monkeypatch, body, headers):
    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(body)
            self.headers = headers

        def __enter__(self):
            return self

    monkeypatch.setattr("chartpack.cache.urllib.request.urlopen", lambda request, timeout=None: Response())


def test_download_size_difference_is_a_size_mismatch(tmp_path, monkeypatch):
    from chartpack.cache import SizeMismatch

    _fake_urlopen(monkeypatch, b"x" * 10, {"Content-Length": "10"})
    with pytest.raises(SizeMismatch):
        download("http://h/f.zip", tmp_path / "f.zip", expected_size=12)
    assert not list(tmp_path.iterdir())


def test_download_with_modified_returns_the_header(tmp_path, monkeypatch):
    from chartpack.cache import download_with_modified

    _fake_urlopen(monkeypatch, b"x" * 10, {"Content-Length": "10", "Last-Modified": "Sat, 14 Nov 2026 05:50:17 GMT"})
    assert download_with_modified("http://h/f.zip", tmp_path / "a.zip") == "Sat, 14 Nov 2026 05:50:17 GMT"
    assert (tmp_path / "a.zip").read_bytes() == b"x" * 10
    _fake_urlopen(monkeypatch, b"x", {})
    assert download_with_modified("http://h/f.zip", tmp_path / "b.zip") is None
