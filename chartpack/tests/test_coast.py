import gzip
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from chartpack import coast
from chartpack.cache import DownloadError

BOX = (-124.6, 50.3, -124.2, 50.6)


class PagingSession:
    """Serves numbered features from a pool of `total`, honoring count and startIndex."""

    def __init__(self, total: int, matched=None, ids=None, coords=((-124.5, 50.4), (-124.4, 50.5))):
        self.total = total
        self.matched = total if matched is None else matched  # numberMatched; "absent" leaves it out
        self.ids = ids  # OBJECTIDs in order; default 0..total-1
        self.coords = [list(c) for c in coords]
        self.queries = []

    def get(self, url):
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.queries.append(q)
        start, count = int(q["startIndex"]), int(q["count"])
        ids = (self.ids or range(self.total))[start:min(start + count, self.total)]
        features = [{"type": "Feature", "properties": {"OBJECTID": i},
                     "geometry": {"type": "LineString", "coordinates": self.coords}} for i in ids]
        page = {"type": "FeatureCollection", "numberReturned": len(features), "features": features}
        if self.matched != "absent":
            page["numberMatched"] = self.matched
        return json.dumps(page).encode()


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


def test_short_page_with_more_matched_fails(tmp_path):
    """A page cut short by a server or proxy cap must not end the fetch as if the coastline were whole."""
    out = tmp_path / "c.geojson.gz"
    with pytest.raises(DownloadError, match="56204"):
        coast.fetch_coastline(BOX, out, PagingSession(total=5, matched=56204), count=10)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("matched", ["absent", "unknown"])
def test_no_matched_number_falls_back_to_the_short_page(tmp_path, matched):
    assert coast.fetch_coastline(BOX, tmp_path / "c.geojson.gz", PagingSession(total=3, matched=matched), count=2) == 3


def test_repeated_objectid_fails(tmp_path):
    out = tmp_path / "c.geojson.gz"
    with pytest.raises(DownloadError, match="OBJECTID 1"):
        coast.fetch_coastline(BOX, out, PagingSession(total=3, ids=[0, 1, 1]), count=2)
    assert list(tmp_path.iterdir()) == []


class BodySession:
    def __init__(self, body: bytes):
        self.body = body

    def get(self, url):
        return self.body


@pytest.mark.parametrize("body", [
    b'<?xml version="1.0"?><ows:ExceptionReport><ows:Exception exceptionCode="InvalidParameterValue"/></ows:ExceptionReport>',
    b'{"exceptions": [{"code": "InvalidParameterValue", "text": "bad bbox"}]}',
    b'{"type": "Feature", "properties": {}}',
])
def test_body_that_is_not_a_feature_collection_fails(tmp_path, body):
    with pytest.raises(DownloadError, match="FeatureCollection"):
        coast.fetch_coastline(BOX, tmp_path / "c.geojson.gz", BodySession(body), count=2)
    assert list(tmp_path.iterdir()) == []


def test_swapped_axis_order_fails(tmp_path):
    session = PagingSession(total=1, coords=((50.4, -124.5), (50.5, -124.4)))  # lat, lon
    with pytest.raises(DownloadError, match="axis order"):
        coast.fetch_coastline(BOX, tmp_path / "c.geojson.gz", session, count=2)
    assert list(tmp_path.iterdir()) == []


def test_coordinates_just_past_the_box_are_kept(tmp_path):
    """Lines run past the bbox they meet; the guard allows 1 degree around it."""
    session = PagingSession(total=1, coords=((-125.5, 50.4), (-124.4, 51.5)))
    assert coast.fetch_coastline(BOX, tmp_path / "c.geojson.gz", session, count=2) == 1
