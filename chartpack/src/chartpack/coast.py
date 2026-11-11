"""BC Freshwater Atlas coastline (WHSE_BASEMAPPING.FWA_COASTLINES_SP) from the BC Government WFS (plan 8).

Only the source-data fetch workflow calls the WFS, through a PoliteSession. Values recorded in plan 8 Task 1
(2026-11-11): WFS 2.0.0 with GeoJSON output, a lon/lat bbox with the EPSG:4326 suffix, at most 10000 features
per request, paging with count and startIndex sorted by OBJECTID (paging is not transaction safe without a
sort). License: Open Government Licence - British Columbia (see NOTICE).
"""

import gzip
import json
from pathlib import Path

from chartpack.cache import DownloadError

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.FWA_COASTLINES_SP/ows"
LAYER = "pub:WHSE_BASEMAPPING.FWA_COASTLINES_SP"
PAGE_SIZE = 10000  # the server's CountDefault, its most features per request
AXIS_MARGIN_DEG = 1.0  # how far past the requested bbox a coordinate may lie (lines run past the box they meet)


def page_url(bbox, start: int, count: int) -> str:
    w, s, e, n = bbox
    return (
        f"{WFS_BASE}?service=WFS&version=2.0.0&request=GetFeature&typeNames={LAYER}"
        f"&outputFormat=application/json&srsName=EPSG:4326&sortBy=OBJECTID"
        f"&count={count}&startIndex={start}&bbox={w},{s},{e},{n},EPSG:4326"
    )


def _page(body: bytes) -> dict:
    """The parsed page; DownloadError unless it is a GeoJSON FeatureCollection (a WFS exception, XML or JSON,
    is not an empty page)."""
    try:
        page = json.loads(body)
    except ValueError:
        page = None
    if not (isinstance(page, dict) and page.get("type") == "FeatureCollection" and isinstance(page.get("features"), list)):
        snippet = " ".join(body[:500].decode("utf-8", "replace").split())
        raise DownloadError(f"coastline: the response is not a GeoJSON FeatureCollection: {snippet}")
    return page


def _positions(coords):
    if coords and isinstance(coords[0], (int, float)):
        yield coords
    else:
        for c in coords or ():
            yield from _positions(c)


def _check_axes(feature: dict, bbox) -> None:
    """DownloadError unless every position lies in bbox grown by AXIS_MARGIN_DEG with x as longitude."""
    w, s, e, n = bbox
    m = AXIS_MARGIN_DEG
    for x, y, *_ in _positions((feature.get("geometry") or {}).get("coordinates")):
        if not (w - m <= x <= e + m and s - m <= y <= n + m):
            raise DownloadError(f"coastline: position ({x}, {y}) lies outside the box {bbox} grown by {m} degree: "
                                "the axis order looks swapped (lat, lon), expected lon, lat")


def fetch_coastline(bbox, out: Path, session, count: int = PAGE_SIZE) -> int:
    """Every coastline feature meeting bbox (W, S, E, N, degrees), paged until a page comes back short, written
    to out as gzip GeoJSONSeq (one feature per line). Returns the feature count.

    Nothing is written at out unless every page is a FeatureCollection, no OBJECTID repeats, every position is
    lon, lat near bbox, and the total equals the first page's numberMatched when the server gives a number."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    total = 0
    matched = None
    seen = set()
    try:
        with gzip.open(part, "wt", encoding="utf-8") as f:
            while True:
                page = _page(session.get(page_url(bbox, total, count)))
                if total == 0 and isinstance(page.get("numberMatched"), int):
                    matched = page["numberMatched"]
                features = page["features"]
                for feature in features:
                    oid = (feature.get("properties") or {}).get("OBJECTID")
                    if oid is not None:
                        if oid in seen:
                            raise DownloadError(f"coastline: OBJECTID {oid} came twice (pages shifted while paging)")
                        seen.add(oid)
                    _check_axes(feature, bbox)
                    f.write(json.dumps(feature, separators=(",", ":")) + "\n")
                total += len(features)
                if len(features) < count:
                    break
        if matched is not None and total != matched:
            raise DownloadError(f"coastline: got {total} features, the server matched {matched}")
        part.rename(out)
    finally:
        part.unlink(missing_ok=True)  # no-op after a successful rename
    return total
