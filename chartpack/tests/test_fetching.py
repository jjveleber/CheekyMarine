import gzip
import io
import json
import urllib.error

import pytest

from chartpack import __version__, cli
from chartpack.fetching import USER_AGENT, FetchStopped, PoliteSession
from make_nonna import A_COL, A_ROW, chunk_values, index_zip, write_nonna

HOST = "https://nonna-geoserver.data.chs-shc.ca"
ROBOTS = f"{HOST}/robots.txt"
DATA = f"{HOST}/geoserver/wcs?service=WCS&request=GetCoverage"


class FakeOpener:
    """urlopen stand-in: each url maps to a list of results served in order. A result is the body (bytes), an
    HTTP status to raise (int) or an exception to raise."""

    def __init__(self, routes: dict):
        self.routes = {url: list(results) for url, results in routes.items()}
        self.calls = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.calls.append((url, request.get_header("User-agent"), timeout))
        result = self.routes[url].pop(0)
        if isinstance(result, int):
            raise urllib.error.HTTPError(url, result, "status", {}, io.BytesIO(b""))
        if isinstance(result, BaseException):
            raise result
        return io.BytesIO(result)


def _session(routes):
    opener, sleeps = FakeOpener(routes), []
    return PoliteSession("CheekyMarine-pack-builder/9.9.9 (+test)", opener=opener, sleep=sleeps.append), opener, sleeps


def test_user_agent_names_the_project_and_version():
    assert USER_AGENT == f"CheekyMarine-pack-builder/{__version__} (+https://github.com/jjveleber/CheekyMarine)"


def test_robots_disallow_stops():
    session, opener, _ = _session({ROBOTS: [b"User-agent: *\nDisallow: /geoserver/\n"]})
    with pytest.raises(FetchStopped, match="robots.txt"):
        session.get(DATA)
    assert [url for url, _, _ in opener.calls] == [ROBOTS]  # no data request


@pytest.mark.parametrize("robots", [500, TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out"))])
def test_unreadable_robots_stops(robots):
    """A robots.txt that cannot be read (5xx or timeout, after the one retry) does not count as allowed."""
    session, opener, sleeps = _session({ROBOTS: [robots, robots]})
    with pytest.raises(FetchStopped, match="robots.txt"):
        session.get(DATA)
    assert [url for url, _, _ in opener.calls] == [ROBOTS, ROBOTS]
    assert 60 in sleeps


def test_pause_after_each_response():
    """A missing robots.txt (404) allows every path; robots.txt is read once per host; every response,
    robots.txt included, is followed by one 2 s pause."""
    session, opener, sleeps = _session({ROBOTS: [404], DATA: [b"one", b"two"]})
    assert session.get(DATA) == b"one"
    assert session.get(DATA) == b"two"
    assert [url for url, _, _ in opener.calls] == [ROBOTS, DATA, DATA]
    assert sleeps == [2.0, 2.0, 2.0]
    assert {ua for _, ua, _ in opener.calls} == {"CheekyMarine-pack-builder/9.9.9 (+test)"}


@pytest.mark.parametrize("status", [403, 429])
def test_403_and_429_stop_for_good(status):
    session, opener, _ = _session({ROBOTS: [404], DATA: [status, b"never served"]})
    with pytest.raises(FetchStopped, match=str(status)):
        session.get(DATA)
    with pytest.raises(FetchStopped):
        session.get(DATA)
    assert [url for url, _, _ in opener.calls] == [ROBOTS, DATA]  # nothing asked after the stop


@pytest.mark.parametrize("failure", [503, TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out"))])
def test_5xx_retries_once_after_60s(failure):
    session, opener, sleeps = _session({ROBOTS: [404], DATA: [failure, b"ok"]})
    assert session.get(DATA) == b"ok"
    assert [url for url, _, _ in opener.calls] == [ROBOTS, DATA, DATA]
    assert sleeps[-2:] == [60, 2.0]  # the back-off, then the pause after the answer
    assert sleeps.count(60) == 1


def test_5xx_twice_stops():
    session, opener, _ = _session({ROBOTS: [404], DATA: [502, 502, b"never served"]})
    with pytest.raises(FetchStopped, match="502"):
        session.get(DATA)
    assert len(opener.calls) == 3


class FakeSession:
    """Serves the NONNA index zips, WCS chunks and coastline pages of the CLI test by url."""

    def __init__(self, user_agent, tmp_path, index_boxes, chunk: bytes):
        self.user_agent = user_agent
        self.urls = []
        self.index = index_zip(tmp_path, "NONNA100", index_boxes)
        self.chunk = chunk

    def get(self, url):
        self.urls.append(url)
        if url.endswith("/NONNA100.zip"):
            return self.index
        if "/geoserver/wcs?" in url:
            return self.chunk
        if "FWA_COASTLINES_SP" in url:
            features = [{"type": "Feature", "properties": {"OBJECTID": i}, "geometry": None} for i in range(3)]
            return json.dumps({"type": "FeatureCollection", "features": features}).encode()
        raise AssertionError(f"unexpected url {url}")


REGION = """name = "toba-part"
charts_version = "0.1.0"
bathy_version = "0.1.0"
bbox = [-124.6, 50.3, -124.2, 50.6]

[sources]
assets = "toba"

[enc]

[bathy]
sources = ["nonna100"]
dem_maxzoom = 14

[datum]
file = "datum/wa-stations.toml"
"""


@pytest.mark.parametrize("only", ["both", "coast", "nonna"])
def test_fetch_sources_cli_writes_stats(tmp_path, monkeypatch, only):
    """Files are named by [sources] assets; a region without nonna10 in its sources skips that file; the stats
    record the requested extent (the box grown by 0.02 degree) and chunks, bytes and seconds per file."""
    region = tmp_path / "toba-part.toml"
    region.write_text(REGION)
    (tmp_path / "work").mkdir()
    chunk_path = write_nonna(tmp_path / "chunk.tif", chunk_values("a")[:8, :8], "nonna100", A_COL // 8, A_ROW // 8)
    boxes = [("NONNA100_5000N12500W", (-125.0, 50.0, -124.0, 51.0)), ("NONNA100_5100N12500W", (-125.0, 51.0, -124.0, 52.0))]
    sessions = []

    def make_session(user_agent):
        sessions.append(FakeSession(user_agent, tmp_path / "work", boxes, chunk_path.read_bytes()))
        return sessions[-1]

    monkeypatch.setattr(cli, "PoliteSession", make_session)
    out = tmp_path / "out"
    assert cli.main(["fetch-sources", "--region", str(region), "--out", str(out), "--only", only]) == 0

    (session,) = sessions
    assert session.user_agent == USER_AGENT
    stats = json.loads((out / "fetch-stats-toba.json").read_text())
    assert stats["extent"] == pytest.approx([-124.62, 50.28, -124.18, 50.62], abs=1e-9)
    names = {"coast": ["coast-toba.geojson.gz"], "nonna": ["nonna100-toba.tif"]}
    expected = names["coast"] + names["nonna"] if only == "both" else names[only]
    assert sorted(p.name for p in out.iterdir()) == sorted(expected + ["fetch-stats-toba.json"])
    assert sorted(stats["files"]) == sorted(expected)
    for name, entry in stats["files"].items():
        assert entry["bytes"] == (out / name).stat().st_size
        assert entry["seconds"] >= 0
    if only != "coast":
        assert stats["files"]["nonna100-toba.tif"]["chunks"] == 1  # one index tile meets the extent
        assert not any("NONNA10.zip" in u or "NONNA%2010%20" in u for u in session.urls)
    if only != "nonna":
        assert stats["files"]["coast-toba.geojson.gz"] == {**stats["files"]["coast-toba.geojson.gz"], "chunks": 1,
                                                          "features": 3}
        with gzip.open(out / "coast-toba.geojson.gz", "rt") as f:
            assert len(f.read().splitlines()) == 3


def test_backoff_sleeps_60s():
    session, opener, sleeps = _session({})
    session.backoff()
    assert sleeps == [60] and opener.calls == []


def _run_cli(tmp_path, monkeypatch, only, region_text=REGION):
    region = tmp_path / "toba-part.toml"
    region.write_text(region_text)
    (tmp_path / "work").mkdir(exist_ok=True)
    chunk_path = write_nonna(tmp_path / "chunk.tif", chunk_values("a")[:8, :8], "nonna100", A_COL // 8, A_ROW // 8)
    boxes = [("NONNA100_5000N12500W", (-125.0, 50.0, -124.0, 51.0))]
    sessions = []

    def make_session(user_agent):
        sessions.append(FakeSession(user_agent, tmp_path / "work", boxes, chunk_path.read_bytes()))
        return sessions[-1]

    monkeypatch.setattr(cli, "PoliteSession", make_session)
    out = tmp_path / "out"
    return cli.main(["fetch-sources", "--region", str(region), "--out", str(out), "--only", only]), out, sessions


EXTENT = [-124.62, 50.28, -124.18, 50.62]
KEPT = {"coast-toba.geojson.gz": {"chunks": 7, "features": 60001, "bytes": 123, "seconds": 9.5}}


def test_partial_run_keeps_the_other_kinds_stats(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "fetch-stats-toba.json").write_text(json.dumps({"extent": EXTENT, "files": KEPT}))
    rc, out, _ = _run_cli(tmp_path, monkeypatch, "nonna")
    assert rc == 0
    stats = json.loads((out / "fetch-stats-toba.json").read_text())
    assert stats["extent"] == EXTENT
    assert sorted(stats["files"]) == ["coast-toba.geojson.gz", "nonna100-toba.tif"]
    assert stats["files"]["coast-toba.geojson.gz"] == KEPT["coast-toba.geojson.gz"]


def test_partial_run_with_another_extent_fails(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    out.mkdir()
    old = {"extent": [-124.7, 50.28, -124.18, 50.62], "files": KEPT}
    (out / "fetch-stats-toba.json").write_text(json.dumps(old))
    rc, out, sessions = _run_cli(tmp_path, monkeypatch, "coast")
    assert rc == 1 and sessions == []  # nothing fetched
    assert "--only both" in capsys.readouterr().err
    assert json.loads((out / "fetch-stats-toba.json").read_text()) == old


def test_full_run_writes_fresh_stats(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "fetch-stats-toba.json").write_text(json.dumps({"extent": [0, 0, 1, 1], "files": {"old.tif": {}}}))
    rc, out, _ = _run_cli(tmp_path, monkeypatch, "both")
    assert rc == 0
    stats = json.loads((out / "fetch-stats-toba.json").read_text())
    assert stats["extent"] == EXTENT
    assert sorted(stats["files"]) == ["coast-toba.geojson.gz", "nonna100-toba.tif"]


@pytest.mark.parametrize("assets", ["Toba", "../toba", "toba_1", ""])
def test_assets_name_must_be_safe(tmp_path, monkeypatch, capsys, assets):
    rc, out, sessions = _run_cli(tmp_path, monkeypatch, "both", REGION.replace('assets = "toba"', f'assets = "{assets}"'))
    assert rc == 1 and sessions == [] and not out.exists()
    assert "[a-z0-9-]+" in capsys.readouterr().err
