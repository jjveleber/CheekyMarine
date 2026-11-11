"""Polite HTTP fetching for the Canadian source hosts (plan 8): only the source-data fetch workflow uses it.

Manners: one request at a time, a pause after each response, a User-Agent that names the project, robots.txt
read before the first request to a host (a missing robots.txt, HTTP 404 or another 4xx, allows every path; one
that cannot be read, 5xx or a timeout after the retry, allows none), one retry after 60 s on a 5xx or a timeout,
and a stop for good on HTTP 403 or 429.
"""

import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlsplit

from chartpack import __version__

USER_AGENT = f"CheekyMarine-pack-builder/{__version__} (+https://github.com/jjveleber/CheekyMarine)"
BACKOFF_S = 60
TIMEOUT_S = 300


class FetchStopped(Exception):
    pass


def _is_timeout(e: Exception) -> bool:
    return isinstance(e, TimeoutError) or (isinstance(e, urllib.error.URLError) and isinstance(e.reason, TimeoutError))


class PoliteSession:
    def __init__(self, user_agent: str, pause_s: float = 2.0, opener=urllib.request.urlopen, sleep=time.sleep):
        self.user_agent = user_agent
        self.pause_s = pause_s
        self._opener = opener
        self._sleep = sleep
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}  # None: every path allowed
        self._stopped: str | None = None

    def _once(self, url: str) -> tuple[int, bytes]:
        """(status, body) of one request; a timeout gives status 0. Pauses after a response."""
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with self._opener(request, timeout=TIMEOUT_S) as response:
                status, body = getattr(response, "status", 200), response.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except (TimeoutError, urllib.error.URLError) as e:
            if not _is_timeout(e):
                raise
            return 0, b""
        self._sleep(self.pause_s)
        return status, body

    def _request(self, url: str) -> tuple[int, bytes]:
        """(status, body), retried once after BACKOFF_S on a 5xx or a timeout; FetchStopped on 403, 429 or a
        second failure."""
        if self._stopped:
            raise FetchStopped(f"stopped earlier: {self._stopped}")
        status, body = self._once(url)
        if status == 0 or status >= 500:
            self._sleep(BACKOFF_S)
            status, body = self._once(url)
            if status == 0 or status >= 500:
                raise FetchStopped(f"{url}: {'timeout' if status == 0 else f'HTTP {status}'} twice")
        if status in (403, 429):
            self._stopped = f"{url}: HTTP {status}"
            raise FetchStopped(self._stopped)
        return status, body

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            try:
                status, body = self._request(f"{root}/robots.txt")
            except FetchStopped as e:
                raise FetchStopped(f"robots.txt of {root} could not be read: {e}") from e
            if status == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(body.decode("utf-8", "replace").splitlines())
                self._robots[root] = parser
            else:  # 404 and other 4xx: no robots.txt
                self._robots[root] = None
        parser = self._robots[root]
        return parser is None or parser.can_fetch(self.user_agent, url)

    def get(self, url: str) -> bytes:
        if not self._allowed(url):
            raise FetchStopped(f"{url}: disallowed by robots.txt")
        status, body = self._request(url)
        if status != 200:
            raise FetchStopped(f"{url}: HTTP {status}: {body[:300]!r}")
        return body
