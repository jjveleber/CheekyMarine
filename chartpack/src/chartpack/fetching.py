"""Polite HTTP fetching for the Canadian source hosts (plan 8): only the source-data fetch workflow uses it.

Manners: one request at a time, a pause after each response (the host's robots.txt Crawl-delay when that is
longer), a User-Agent that names the project, robots.txt read before the first request to a host, one retry after
60 s on a 5xx or a transport failure, and a stop for good on HTTP 403 or 429. A redirect to another host stops
the fetch: that host's robots.txt was never read.

robots.txt: HTTP 200 is parsed; a body that is not robots syntax (an HTML page) holds no rules and so allows
every path, as RFC 9309 reads it. 404 or another 4xx means no robots.txt: every path allowed. 401 and 403 stop.
One that cannot be read (5xx or a transport failure, after the retry) allows nothing. urllib.robotparser reads
`*` and `$` literally, so a Disallow rule with a wildcard is applied conservatively: the path is refused when the
rule's literal prefix (up to the first `*` or `$`) is a prefix of it.
"""

import http.client
import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import quote, unquote, urlparse, urlsplit, urlunparse

from chartpack import __version__
from chartpack.cache import DownloadError

USER_AGENT = f"CheekyMarine-pack-builder/{__version__} (+https://github.com/jjveleber/CheekyMarine)"
BACKOFF_S = 60
TIMEOUT_S = 300
# What a request can fail with before an HTTP status arrives (HTTPError is caught before these).
_TRANSPORT = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError)


class FetchStopped(Exception):
    pass


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _robots_path(url: str) -> str:
    """The path and query of url normalized as urllib.robotparser.can_fetch normalizes it."""
    parsed = urlparse(unquote(url))
    return quote(urlunparse(("", "", parsed.path, parsed.params, parsed.query, parsed.fragment))) or "/"


def _wildcard_refuses(parser: urllib.robotparser.RobotFileParser, user_agent: str, url: str) -> bool:
    """True when a Disallow rule with `*` or `$` in a group for this agent or for `*` has a literal prefix that
    starts the path. The parser keeps rule paths quoted, so `*` reads %2A and `$` reads %24."""
    path = _robots_path(url)
    entries = [e for e in parser.entries if e.applies_to(user_agent)]
    if parser.default_entry:
        entries.append(parser.default_entry)
    for entry in entries:
        for rule in entry.rulelines:
            cuts = [i for i in (rule.path.find("%2A"), rule.path.find("%24")) if i >= 0]
            if not rule.allowance and cuts and path.startswith(rule.path[: min(cuts)]):
                return True
    return False


class PoliteSession:
    def __init__(self, user_agent: str, pause_s: float = 2.0, opener=urllib.request.urlopen, sleep=time.sleep):
        self.user_agent = user_agent
        self.pause_s = pause_s
        self._opener = opener
        self._sleep = sleep
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}  # None: every path allowed
        self._pause: dict[str, float] = {}  # host: pause after a response, from its Crawl-delay
        self._stopped: str | None = None

    def _once(self, url: str) -> tuple[int, bytes, str]:
        """(status, body, failure) of one request; a transport failure gives status 0 and its description.
        Pauses after a response; FetchStopped when the response came from another host."""
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with self._opener(request, timeout=TIMEOUT_S) as response:
                status, body, final = getattr(response, "status", 200), response.read(), response.geturl()
        except urllib.error.HTTPError as e:
            status, body, final = e.code, e.read(), getattr(e, "url", None) or url
        except _TRANSPORT as e:
            return 0, b"", f"{type(e).__name__}: {e}"
        if _host(final) != _host(url):
            self._stopped = f"{url} was redirected to another host: {final}"
            raise FetchStopped(self._stopped)
        self._sleep(self._pause.get(_host(url), self.pause_s))
        return status, body, ""

    def _request(self, url: str, retry: bool = True) -> tuple[int, bytes]:
        """(status, body). A 5xx or a transport failure is retried once after BACKOFF_S when retry is set; a
        failure that remains raises DownloadError naming the url. FetchStopped on 403 or 429, for good."""
        if self._stopped:
            raise FetchStopped(f"stopped earlier: {self._stopped}")
        status, body, failure = self._once(url)
        if retry and (status == 0 or status >= 500):
            self._sleep(BACKOFF_S)
            status, body, failure = self._once(url)
        if status == 0 or status >= 500:
            raise DownloadError(f"{url}: {failure or f'HTTP {status}'}{' twice' if retry else ''}")
        if status in (403, 429):
            self._stopped = f"{url}: HTTP {status}"
            raise FetchStopped(self._stopped)
        return status, body

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            robots = f"{root}/robots.txt"
            try:
                status, body = self._request(robots)
            except DownloadError as e:
                raise FetchStopped(f"robots.txt of {root} could not be read: {e}") from e
            except FetchStopped as e:
                raise FetchStopped(f"robots.txt of {root}: {e}") from e
            if status == 401:
                raise FetchStopped(f"{robots}: HTTP 401")
            if status == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(body.decode("utf-8", "replace").splitlines())
                self._robots[root] = parser
                delay = parser.crawl_delay(self.user_agent)
                self._pause[_host(url)] = max(self.pause_s, float(delay or 0))
            else:  # 404 and other 4xx: no robots.txt
                self._robots[root] = None
        parser = self._robots[root]
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url) and not _wildcard_refuses(parser, self.user_agent, url)

    def backoff(self) -> None:
        """Wait BACKOFF_S before asking again for a response that came back unusable."""
        self._sleep(BACKOFF_S)

    def get(self, url: str, retry: bool = True) -> bytes:
        """The body of url. retry=False skips the one retry on a 5xx or a transport failure (for a caller that
        retries on its own, so one url is never asked for more than three times)."""
        if not self._allowed(url):
            raise FetchStopped(f"{url}: disallowed by robots.txt")
        status, body = self._request(url, retry)
        if status != 200:
            raise FetchStopped(f"{url}: HTTP {status}: {body[:300]!r}")
        return body
