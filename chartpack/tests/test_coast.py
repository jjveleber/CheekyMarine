import gzip
import json
import math
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


def test_coordinates_far_past_the_box_are_kept(tmp_path):
    """A line meeting the box can run far past it (a long mainland piece); any position in the source's range
    is accepted."""
    session = PagingSession(total=1, coords=((-131.5, 54.0), (-124.4, 50.5)))
    assert coast.fetch_coastline(BOX, tmp_path / "c.geojson.gz", session, count=2) == 1


@pytest.mark.parametrize("coords", [((0.0, 0.0), (-124.4, 50.5)), ((-124.4, 50.5), (-100.0, 50.0))])
def test_position_outside_the_source_range_fails(tmp_path, coords):
    with pytest.raises(DownloadError, match="outside the expected range") as info:
        coast.fetch_coastline(BOX, tmp_path / "c.geojson.gz", PagingSession(total=1, coords=coords), count=2)
    assert "axis order" not in str(info.value)
    assert list(tmp_path.iterdir()) == []


# Land polygons (plan 8 Task 9). A 0.1 by 0.1 degree box inside Canada; DY is 1 m of latitude.
LAND_BOX = (-124.0, 49.5, -123.9, 49.6)
CANADA = __import__("shapely").geometry.box(-125.0, 49.0, -123.0, 50.0)
DY = 1 / 111320


def _water_points(area, land):
    """A 41 by 41 grid of points over LAND_BOX (off every line of these tests), kept where they are in area and
    not in land."""
    import numpy as np
    import shapely

    w, s, e, n = LAND_BOX
    x, y = np.meshgrid(np.linspace(w + 1.7e-3, e - 1.3e-3, 41), np.linspace(s + 1.7e-3, n - 1.3e-3, 41))
    keep = shapely.contains_xy(area, x, y) & ~shapely.contains_xy(land, x, y)
    return shapely.MultiPoint(np.column_stack([x[keep], y[keep]]))


def _close(a, b, km2=0.001):
    from chartpack.enc.bc import area_km2

    return area_km2(a.symmetric_difference(b)) < km2


def _land(lines, land, *, canada=CANADA, wet=None, water=None):
    from shapely.geometry import Polygon, box

    area = box(*LAND_BOX).intersection(canada)
    return coast.land_polygons(lines, LAND_BOX, canada, _water_points(area, land) if water is None else water,
                               Polygon() if wet is None else wet)


L_COAST = [(-124.01, 49.53), (-123.95, 49.53), (-123.95, 49.61)]
L_LAND = __import__("shapely").geometry.box(-124.0, 49.53, -123.95, 49.6)


def test_land_closes_at_box_edge():
    from shapely.geometry import LineString

    land, flipped = _land([LineString(L_COAST)], L_LAND)
    assert land.geom_type == "MultiPolygon" and len(land.geoms) == 1
    assert _close(land, L_LAND) and flipped == []


def test_coast_ending_at_canada_border_closes_along_it():
    from shapely.geometry import LineString, box

    canada = box(-125.0, 49.55, -123.0, 50.0)
    line = LineString([(-124.01, 49.58), (-123.95, 49.58), (-123.95, 49.55 + 30 * DY)])
    expected = box(-124.0, 49.55, -123.95, 49.58)
    land, _ = _land([line], expected, canada=canada)
    assert _close(land, expected)
    assert land.difference(canada).area == 0


def test_unclosable_ring_fails():
    from shapely.geometry import LineString, box

    canada = box(-125.0, 49.55, -123.0, 50.0)
    end = (-124.0 + 500 * DY / math.cos(math.radians(49.55)), 49.55 + 500 * DY)
    line = LineString([(-123.99, 49.61), end])
    with pytest.raises(coast.CoastError, match=f"{end[0]:.5f}, {end[1]:.5f}"):
        _land([line], box(-124.0, 49.55, -123.99, 49.6), canada=canada)


def test_land_side_ignores_line_direction():
    from shapely.geometry import LineString

    forward, _ = _land([LineString(L_COAST)], L_LAND)
    backward, _ = _land([LineString(L_COAST[::-1])], L_LAND)
    split, _ = _land([LineString(L_COAST[:2]), LineString(L_COAST[1:][::-1])], L_LAND)
    assert _close(forward, backward, 1e-6) and _close(forward, split, 1e-6)


def test_island_ring_is_land():
    from shapely.geometry import box

    island = box(-123.96, 49.54, -123.94, 49.56)
    for ring in (island.exterior, island.exterior.reverse()):
        land, _ = _land([ring], island)
        assert _close(land, island)


# A coast along 49.55 N with land north, a construction line (EDGE_TYPE 150) across a river mouth from -123.97 to
# -123.93, and an island in the sea. The face north of the line is 60% river: wet but shallower than 2 m.
RIVER_COAST = [[(-124.01, 49.55), (-123.97, 49.55)], [(-123.93, 49.55), (-123.89, 49.55)]]
RIVER_MOUTH = [(-123.97, 49.55), (-123.93, 49.55)]
RIVER_WET = __import__("shapely").geometry.box(-123.98, 49.55, -123.92, 49.6)
SEA_ISLAND = __import__("shapely").geometry.box(-123.99, 49.51, -123.98, 49.52)


def _river_case():
    from shapely.geometry import LineString, box

    lines = [LineString(c) for c in RIVER_COAST] + [LineString(RIVER_MOUTH), SEA_ISLAND.exterior]
    north = box(-124.0, 49.55, -123.9, 49.6)
    sea = box(-124.0, 49.5, -123.9, 49.55).difference(SEA_ISLAND)
    return lines, north, sea


def test_river_mouth_face_with_nonna_is_water():
    from chartpack.enc.bc import area_km2

    lines, north, sea = _river_case()
    land, flipped = _land(lines, north.union(SEA_ISLAND), wet=sea.union(RIVER_WET))
    assert _close(land, SEA_ISLAND)
    assert len(flipped) == 1
    face = flipped[0]
    assert set(face) == {"id", "area_km2", "wet_share"}
    assert face["area_km2"] == pytest.approx(area_km2(north), rel=1e-3)
    assert face["wet_share"] == pytest.approx(0.6, abs=0.01)


def test_small_closed_islet_never_flips():
    from shapely.geometry import box

    dx = 100 * DY / math.cos(math.radians(49.55))
    islet = box(-123.95, 49.55, -123.95 + dx, 49.55 + 100 * DY)  # 0.01 km2
    sea = box(*LAND_BOX).difference(islet)
    fringe = box(-123.95, 49.55, -123.95 + 0.4 * dx, 49.55 + 100 * DY)  # 40% of the islet
    land, flipped = _land([islet.exterior], islet, wet=sea.union(fringe))
    assert _close(land, islet, 1e-6) and flipped == []


def test_land_never_over_wet_nonna_cells():
    from shapely.geometry import LineString, box

    river = box(-123.99, 49.53, -123.985, 49.6)  # surveyed water the atlas draws inside the land (10% of it)
    land, flipped = _land([LineString(L_COAST)], L_LAND, wet=river)
    assert flipped == [] and land.intersection(river).area == 0
    assert _close(land, L_LAND.difference(river))


def test_water_vote_on_land_fails():
    from shapely.geometry import LineString, box

    area = box(*LAND_BOX)
    water = _water_points(area, area.difference(L_LAND))  # deep cells all over the true land
    water = water.union(_water_points(area, area.difference(box(-123.95, 49.5, -123.9, 49.53))))
    with pytest.raises(coast.CoastError, match="1%"):
        _land([LineString(L_COAST)], L_LAND, water=water)


def test_no_coastline_is_all_water():
    land, flipped = _land([], __import__("shapely").geometry.Polygon())
    assert land.is_empty and land.geom_type == "MultiPolygon" and flipped == []


@pytest.mark.parametrize("cap", [None, 500])
def test_derive_stats_lists_water_faces(tmp_path, regions_dir, monkeypatch, cap):
    """derive-sources over a river mouth: the face behind the construction line is a third river (wet, 1 m deep,
    NONNA-10 only), so it turns to water and derive-stats lists it; no land is left, and the land beside the
    river, which no grid covers, is the no-survey mask. A vote sampled down to 500 points gives the same."""
    if cap is not None:
        monkeypatch.setattr("chartpack.enc.nosurvey.MAX_VOTE_POINTS", cap)
    import hashlib
    import shutil

    import numpy as np
    from make_nonna import NODATA
    from test_bathy_blocks import _write_nonna_over

    from chartpack.cli import main
    from chartpack.grid import fetch_extent
    from chartpack.region import load_region

    shutil.copytree(regions_dir / "clip", tmp_path / "clip")
    region = tmp_path / "rv.toml"
    region.write_text('name = "rv"\ncharts_version = "0.1.0"\nbathy_version = "0.1.0"\n'
                      'bbox = [-123.96, 49.54, -123.94, 49.56]\n\n[enc]\n\n[bathy]\nsources = ["nonna10", "nonna100"]\n'
                      'dem_maxzoom = 14\n\n[datum]\nfile = "datum/wa-stations.toml"\n\n[charts]\nkind = "derived-inshore"\n')
    extent = fetch_extent(load_region(region), tmp_path)
    folder = tmp_path / "cache" / "sources-bc-1"
    folder.mkdir(parents=True)
    river = (-123.96, -123.94)  # a third of the face behind the mouth line (-123.955 to -123.945)

    def n10(lon, lat):
        return np.where(lat < 49.55, -10.0, np.where((lon > river[0]) & (lon < river[1]), -1.0, NODATA))

    _write_nonna_over(folder / "nonna10-rv.tif", "nonna10", extent, n10)
    _write_nonna_over(folder / "nonna100-rv.tif", "nonna100", extent,
                      lambda lon, lat: np.where(lat < 49.55, -10.0, NODATA))
    lines = [[(-124.1, 49.55), (-123.955, 49.55)], [(-123.955, 49.55), (-123.945, 49.55)],
             [(-123.945, 49.55), (-123.8, 49.55)]]
    rows = [json.dumps({"type": "Feature", "properties": {"EDGE_TYPE": 150 if i == 1 else 1000},
                        "geometry": {"type": "LineString", "coordinates": c}}) for i, c in enumerate(lines)]
    (folder / "coast-rv.geojson.gz").write_bytes(gzip.compress(("\n".join(rows) + "\n").encode()))
    files = {name: {"sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()}
             for name in ("nonna10-rv.tif", "nonna100-rv.tif", "coast-rv.geojson.gz")}
    (folder / "fetch-stats-rv.json").write_text(json.dumps({"extent": [round(v, 9) for v in extent], "files": files}))

    out = tmp_path / "out"
    assert main(["derive-sources", "--region", str(region), "--cache", str(tmp_path / "cache"), "--out", str(out)]) == 0
    stats = json.loads((out / "derive-stats-rv.json").read_text())
    assert len(stats["water_faces"]) == 1
    assert stats["water_faces"][0]["wet_share"] == pytest.approx(1 / 3, abs=0.02)
    assert stats["land_polygons"] == 0 and stats["nosurvey_polygons"] == 2
    assert stats["missing_in_100_km2"] > 0
    with gzip.open(out / "land-rv.geojson.gz", "rt") as f:
        assert json.load(f)["features"] == []
    with gzip.open(out / "nosurvey-rv.geojson.gz", "rt") as f:
        assert len(json.load(f)["features"]) == 2
