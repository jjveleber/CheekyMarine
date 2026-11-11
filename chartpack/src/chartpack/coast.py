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
# Where every FWA coastline position lies (BC and its islands, with room to spare): a line meeting the requested
# box can run far past it, so positions are checked against the source's range, not the box.
LON_RANGE = (-140.0, -113.0)
LAT_RANGE = (47.0, 61.0)


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


def _inside(x: float, y: float) -> bool:
    return LON_RANGE[0] <= x <= LON_RANGE[1] and LAT_RANGE[0] <= y <= LAT_RANGE[1]


def _check_axes(feature: dict) -> None:
    """DownloadError unless every position is lon, lat inside LON_RANGE and LAT_RANGE. A position that would be
    inside with x and y exchanged is reported as a swapped axis order."""
    for x, y, *_ in _positions((feature.get("geometry") or {}).get("coordinates")):
        if _inside(x, y):
            continue
        if _inside(y, x):
            raise DownloadError(f"coastline: position ({x}, {y}) reads as lat, lon: the axis order looks swapped, "
                                "expected lon, lat")
        raise DownloadError(f"coastline: position ({x}, {y}) is outside the expected range for this source "
                            f"(longitude {LON_RANGE}, latitude {LAT_RANGE})")


def fetch_coastline(bbox, out: Path, session, count: int = PAGE_SIZE) -> int:
    """Every coastline feature meeting bbox (W, S, E, N, degrees), paged until a page comes back short, written
    to out as gzip GeoJSONSeq (one feature per line). Returns the feature count.

    Nothing is written at out unless every page is a FeatureCollection, no OBJECTID repeats, every position is
    lon, lat in the source's range, and the total equals the first page's numberMatched when the server gives a number."""
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
                    _check_axes(feature)
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
