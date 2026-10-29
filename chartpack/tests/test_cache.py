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
