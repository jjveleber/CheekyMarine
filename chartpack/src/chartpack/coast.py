"""BC Freshwater Atlas coastline (WHSE_BASEMAPPING.FWA_COASTLINES_SP) from the BC Government WFS (plan 8).

Only the source-data fetch workflow calls the WFS, through a PoliteSession. Values recorded in plan 8 Task 1
(2026-11-11): WFS 2.0.0 with GeoJSON output, a lon/lat bbox with the EPSG:4326 suffix, at most 10000 features
per request, paging with count and startIndex sorted by OBJECTID (paging is not transaction safe without a
sort). Licence: Open Government Licence - British Columbia (see NOTICE).
"""

import gzip
import json
from pathlib import Path

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.FWA_COASTLINES_SP/ows"
LAYER = "pub:WHSE_BASEMAPPING.FWA_COASTLINES_SP"
PAGE_SIZE = 10000  # the server's CountDefault, its most features per request


def page_url(bbox, start: int, count: int) -> str:
    w, s, e, n = bbox
    return (
        f"{WFS_BASE}?service=WFS&version=2.0.0&request=GetFeature&typeNames={LAYER}"
        f"&outputFormat=application/json&srsName=EPSG:4326&sortBy=OBJECTID"
        f"&count={count}&startIndex={start}&bbox={w},{s},{e},{n},EPSG:4326"
    )


def fetch_coastline(bbox, out: Path, session, count: int = PAGE_SIZE) -> int:
    """Every coastline feature meeting bbox (W, S, E, N, degrees), paged until a page comes back short, written
    to out as gzip GeoJSONSeq (one feature per line). Returns the feature count."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    total = 0
    try:
        with gzip.open(part, "wt", encoding="utf-8") as f:
            while True:
                features = json.loads(session.get(page_url(bbox, total, count)))["features"]
                for feature in features:
                    f.write(json.dumps(feature, separators=(",", ":")) + "\n")
                total += len(features)
                if len(features) < count:
                    break
        part.rename(out)
    finally:
        part.unlink(missing_ok=True)  # no-op after a successful rename
    return total
