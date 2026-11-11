import gzip
import hashlib
import http.client
import io
import json
import urllib.error
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import pytest

from chartpack import __version__, cli
from chartpack.cache import DownloadError
from chartpack.fetching import USER_AGENT, FetchStopped, PoliteSession
from make_nonna import index_zip, write_request_chunk

HOST = "https://nonna-geoserver.data.chs-shc.ca"
ROBOTS = f"{HOST}/robots.txt"
DATA = f"{HOST}/geoserver/wcs?service=WCS&request=GetCoverage"


@dataclass
class Redirect:
    """A response that urlopen reached by following redirects to final_url."""

    final_url: str
    body: bytes


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, url: str):
        super().__init__(body)
        self.url = url
        self.status = 200

    def geturl(self):
        return self.url


class FakeOpener:
    """urlopen stand-in: each url maps to a list of results served in order. A result is the body (bytes), a
    Redirect, an HTTP status to raise (int) or an exception to raise."""

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
        if isinstance(result, Redirect):
            return FakeResponse(result.body, result.final_url)
        return FakeResponse(result, url)


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


@pytest.mark.parametrize("robots", [500, TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out")),
                                    urllib.error.URLError(ConnectionResetError("reset"))])
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


TRANSPORT = [TimeoutError("timed out"), urllib.error.URLError(TimeoutError("timed out")),
             urllib.error.URLError(ConnectionResetError("reset")), http.client.RemoteDisconnected("closed"),
             http.client.IncompleteRead(b"cut"), ConnectionResetError("reset")]


@pytest.mark.parametrize("failure", [503] + TRANSPORT)
def test_5xx_retries_once_after_60s(failure):
    session, opener, sleeps = _session({ROBOTS: [404], DATA: [failure, b"ok"]})
    assert session.get(DATA) == b"ok"
    assert [url for url, _, _ in opener.calls] == [ROBOTS, DATA, DATA]
    assert sleeps[-2:] == [60, 2.0]  # the back-off, then the pause after the answer
    assert sleeps.count(60) == 1


@pytest.mark.parametrize("failure", [502] + TRANSPORT)
def test_failure_twice_raises_naming_the_url(failure):
    session, opener, _ = _session({ROBOTS: [404], DATA: [failure, failure, b"never served"]})
    with pytest.raises(DownloadError, match="geoserver/wcs"):
        session.get(DATA)
    assert len(opener.calls) == 3


@pytest.mark.parametrize("failure", [503, ConnectionResetError("reset")])
def test_get_without_retry_fails_at_once(failure):
    session, opener, sleeps = _session({ROBOTS: [404], DATA: [failure, b"never served"]})
    with pytest.raises(DownloadError, match="geoserver/wcs"):
        session.get(DATA, retry=False)
    assert len(opener.calls) == 2 and 60 not in sleeps


@pytest.mark.parametrize("status", [403, 429])
def test_get_without_retry_still_stops_for_good(status):
    session, _, _ = _session({ROBOTS: [404], DATA: [status]})
    with pytest.raises(FetchStopped):
        session.get(DATA, retry=False)


def test_redirect_to_another_host_stops():
    session, opener, _ = _session({ROBOTS: [404], DATA: [Redirect("https://elsewhere.example/wcs", b"data")]})
    with pytest.raises(FetchStopped, match="elsewhere.example"):
        session.get(DATA)


def test_robots_redirect_to_another_host_stops():
    session, opener, _ = _session({ROBOTS: [Redirect("https://elsewhere.example/page.html", b"<html></html>")]})
    with pytest.raises(FetchStopped, match="elsewhere.example"):
        session.get(DATA)
    assert [url for url, _, _ in opener.calls] == [ROBOTS]


def test_redirect_on_the_same_host_is_followed():
    session, _, _ = _session({ROBOTS: [404], DATA: [Redirect(f"{HOST}/geoserver/other", b"data")]})
    assert session.get(DATA) == b"data"


def test_robots_401_stops():
    session, opener, _ = _session({ROBOTS: [401]})
    with pytest.raises(FetchStopped, match="401"):
        session.get(DATA)
    assert [url for url, _, _ in opener.calls] == [ROBOTS]


def test_robots_200_allowing_the_path_lets_it_through():
    session, opener, _ = _session({ROBOTS: [b"User-agent: *\nDisallow: /private/\n"], DATA: [b"data"]})
    assert session.get(DATA) == b"data"
    assert [url for url, _, _ in opener.calls] == [ROBOTS, DATA]


def test_robots_200_that_is_not_robots_syntax_allows():
    """RFC 9309: lines that are not rules are ignored, so an HTML page served as robots.txt disallows nothing."""
    session, _, _ = _session({ROBOTS: [b"<html><body>Welcome</body></html>"], DATA: [b"data"]})
    assert session.get(DATA) == b"data"


@pytest.mark.parametrize("rule", ["/*/wcs", "/geoserver/*?", "/geoserver/wcs$", "/geo*"])
@pytest.mark.parametrize("agent", ["*", "CheekyMarine-pack-builder"])
def test_robots_wildcard_rule_refuses_when_its_prefix_matches(rule, agent):
    """urllib.robotparser reads * and $ literally; a wildcard rule whose literal prefix matches the path refuses it."""
    session, opener, _ = _session({ROBOTS: [f"User-agent: {agent}\nDisallow: {rule}\n".encode()]})
    with pytest.raises(FetchStopped, match="robots.txt"):
        session.get(DATA)
    assert [url for url, _, _ in opener.calls] == [ROBOTS]


def test_robots_wildcard_rule_elsewhere_allows():
    session, _, _ = _session({ROBOTS: [b"User-agent: *\nDisallow: /other/*.tif\n"], DATA: [b"data"]})
    assert session.get(DATA) == b"data"


@pytest.mark.parametrize("delay, pause", [("10", 10.0), ("1", 2.0)])
def test_crawl_delay_longer_than_the_pause_is_honored(delay, pause):
    session, _, sleeps = _session({ROBOTS: [f"User-agent: *\nCrawl-delay: {delay}\n".encode()], DATA: [b"a", b"b"]})
    session.get(DATA)
    session.get(DATA)
    assert sleeps == [2.0, pause, pause]  # robots.txt is read at the plain pause


class FakeSession:
    """Serves the NONNA index zips, WCS chunks and coastline pages of the CLI test by url."""

    def __init__(self, user_agent, tmp_path, index_boxes):
        self.user_agent = user_agent
        self.urls = []
        self.tmp_path = tmp_path
        self.index = index_zip(tmp_path, "NONNA100", index_boxes)

    def get(self, url, retry=True):
        self.urls.append(url)
        if url.endswith("/NONNA100.zip"):
            return self.index
        if "/geoserver/wcs?" in url:  # a chunk covering exactly the requested subset
            q = parse_qs(urlsplit(url).query)
            x = [float(v) for v in q["subset"][0][2:-1].split(",")]
            y = [float(v) for v in q["subset"][1][2:-1].split(",")]
            path = self.tmp_path / f"chunk-{len(self.urls)}.tif"
            return write_request_chunk(path, "nonna100", (x[0], y[0], x[1], y[1])).read_bytes()
        if "FWA_COASTLINES_SP" in url:
            features = [{"type": "Feature", "properties": {"OBJECTID": i}, "geometry": None} for i in range(3)]
            return json.dumps({"type": "FeatureCollection", "features": features}).encode()
        raise AssertionError(f"unexpected url {url}")


SMALL_TILE = (-124.61, 50.29, -124.6, 50.3)  # a stand-in index tile inside the fetch extent, a few NONNA-100 cells

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
    boxes = [("small", SMALL_TILE), ("outside", (-125.0, 51.0, -124.0, 52.0))]
    sessions = []

    def make_session(user_agent):
        sessions.append(FakeSession(user_agent, tmp_path / "work", boxes))
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
        assert entry["sha256"] == hashlib.sha256((out / name).read_bytes()).hexdigest()
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
    sessions = []

    def make_session(user_agent):
        sessions.append(FakeSession(user_agent, tmp_path / "work", [("small", SMALL_TILE)]))
        return sessions[-1]

    monkeypatch.setattr(cli, "PoliteSession", make_session)
    out = tmp_path / "out"
    return cli.main(["fetch-sources", "--region", str(region), "--out", str(out), "--only", only]), out, sessions


EXTENT = [-124.62, 50.28, -124.18, 50.62]
KEPT = {"coast-toba.geojson.gz": {"chunks": 7, "features": 60001, "bytes": 123, "sha256": "ab" * 32, "seconds": 9.5}}


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
    tif = out / "nonna100-toba.tif"
    assert stats["files"]["nonna100-toba.tif"]["sha256"] == hashlib.sha256(tif.read_bytes()).hexdigest()


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
