import gzip
import json
from urllib.parse import parse_qs, urlsplit

from chartpack import coast


class PagingSession:
    """Serves numbered features from a pool of `total`, honoring count and startIndex."""

    def __init__(self, total: int):
        self.total = total
        self.queries = []

    def get(self, url):
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.queries.append(q)
        start, count = int(q["startIndex"]), int(q["count"])
        ids = range(start, min(start + count, self.total))
        features = [{"type": "Feature", "properties": {"OBJECTID": i},
                     "geometry": {"type": "LineString", "coordinates": [[-124.5, 50.4], [-124.4, 50.5]]}} for i in ids]
        return json.dumps({"type": "FeatureCollection", "numberReturned": len(features),
                           "features": features}).encode()


def test_coastline_pages_until_short_page(tmp_path):
    session = PagingSession(total=5)
    out = tmp_path / "coast-x.geojson.gz"
    assert coast.fetch_coastline((-124.6, 50.3, -124.2, 50.6), out, session, count=2) == 5
    assert [q["startIndex"] for q in session.queries] == ["0", "2", "4"]
    for q in session.queries:
        assert q["service"] == "WFS" and q["version"] == "2.0.0" and q["request"] == "GetFeature"
        assert q["typeNames"] == "pub:WHSE_BASEMAPPING.FWA_COASTLINES_SP"
        assert q["outputFormat"] == "application/json" and q["srsName"] == "EPSG:4326"
        assert q["sortBy"] == "OBJECTID" and q["count"] == "2"
        assert q["bbox"] == "-124.6,50.3,-124.2,50.6,EPSG:4326"
    with gzip.open(out, "rt") as f:
        lines = f.read().splitlines()
    assert [json.loads(line)["properties"]["OBJECTID"] for line in lines] == [0, 1, 2, 3, 4]
    assert not list(tmp_path.glob("*.part"))


def test_coastline_full_last_page_needs_an_empty_one(tmp_path):
    session = PagingSession(total=4)
    assert coast.fetch_coastline((-124.6, 50.3, -124.2, 50.6), tmp_path / "c.geojson.gz", session, count=2) == 4
    assert [q["startIndex"] for q in session.queries] == ["0", "2", "4"]


def test_coastline_url_base():
    assert coast.WFS_BASE == "https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.FWA_COASTLINES_SP/ows"
    assert coast.PAGE_SIZE == 10000
