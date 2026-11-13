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


def _land(lines, land, *, canada=CANADA, wet=None, water=None, full=False):
    """(land, water faces), or with full also the count of inland water points."""
    from shapely.geometry import Polygon, box

    area = box(*LAND_BOX).intersection(canada)
    result = coast.land_polygons(lines, LAND_BOX, canada, _water_points(area, land) if water is None else water,
                                 Polygon() if wet is None else wet, skip_m=0.0)
    return result[:3] if full else result[:2]


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


def test_clip_follows_the_box_parallels():
    """A box 3.9 degrees wide at 52.5 N: in BC Albers the straight chord between its south corners lies up to 1.8 km
    north of the south parallel, past the 1 km clip margin. A coast crossing the south edge mid-box must not be cut
    inside the box (bc-north, 2026-11-12)."""
    import numpy as np
    import shapely
    from shapely.geometry import LineString, box

    wide = (-131.5, 52.46, -127.6, 52.9)
    line = LineString([(-129.55, 52.40), (-129.55, 52.95)])  # land to the west
    west = box(-131.5, 52.46, -129.55, 52.9)
    x, y = np.meshgrid(np.linspace(-131.47, -127.63, 60), np.linspace(52.47, 52.89, 20))
    near = np.column_stack([np.full(20, -129.548), np.linspace(52.47, 52.89, 20)])  # about 140 m east of the line
    water = shapely.MultiPoint(np.vstack([np.column_stack([x[x > -129.5], y[x > -129.5]]), near]))
    canada = box(-140.0, 45.0, -120.0, 60.0)
    land, *_ = coast.land_polygons([line], wide, canada, water, shapely.Polygon(), skip_m=0.0)
    assert _close(land, west, 0.01)


def _with_spike(coords, at, tip, retrace_offset):
    """coords with an out-and-back spike at vertex at: out to tip, back exactly, out again and back retrace_offset
    degrees off, as OBJECTID 32612852 of the atlas does (Seymour Inlet, 2026-11-12)."""
    x, y = coords[at]
    tx, ty = tip
    o = retrace_offset
    return coords[:at + 1] + [(tx, ty), (x, y), (tx + o, ty + o), (x + o, y + o)] + coords[at + 1:]


def test_retraced_segment_is_not_a_line_end():
    """A 20 m spike retraced three times (once exactly, once 2 cm off) is no line end: the land is as without it,
    and it is reported."""
    from shapely.geometry import LineString, Polygon, box

    coords = [(-124.01, 49.53), (-123.97, 49.53), (-123.95, 49.53), (-123.95, 49.61)]
    spiked = _with_spike(coords, 1, (-123.97, 49.53 - 20 * DY), 2e-7)
    plain, _ = _land([LineString(coords)], L_LAND)
    area = box(*LAND_BOX)
    land, _, _, retraced = coast.land_polygons([LineString(spiked)], LAND_BOX, CANADA, _water_points(area, L_LAND),
                                               Polygon(), skip_m=0.0)
    assert _close(land, plain, 1e-4)  # the 2 cm offset of the line after the spike leaves a 16 m2 sliver
    assert len(retraced) == 1 and set(retraced[0]) == {"lon", "lat", "length_m"}
    assert retraced[0]["length_m"] == pytest.approx(20, abs=0.5)
    assert retraced[0]["lat"] == pytest.approx(49.53 - 20 * DY, abs=1e-6)


def test_twice_digitized_gap_still_fails():
    """An island ring with a 290 m gap, digitized twice 0.5 m apart (PR 128 review): each copy covers the other's
    end, but both copies stop at the gap, so it is a real gap and the build stops."""
    from shapely.geometry import LineString, box

    island = box(-123.96, 49.54, -123.94, 49.56)
    ring = list(island.exterior.coords)
    a, b = ring[-2], ring[-1]
    open_ring = ring[:-1] + [(a[0] + (b[0] - a[0]) * 0.8, a[1] + (b[1] - a[1]) * 0.8)]
    dx = 0.5 * DY / math.cos(math.radians(49.55))
    copy = [(x + dx, y + 0.5 * DY) for x, y in open_ring]
    with pytest.raises(coast.CoastError, match="more than 50 m"):
        _land([LineString(open_ring), LineString(copy)], island)


def test_short_doubled_ends_at_a_gap_still_fail():
    """Both ends of a 290 m gap doubled over their last 40 m by a short feature that crosses the line and lies 0.5 m
    alongside it to the gap: each 40 m dangle is covered and under RETRACE_MAX_M, but the covering line ends at the
    same place, so neither is skipped."""
    from shapely.geometry import LineString, box

    island = box(-123.96, 49.54, -123.94, 49.56)
    ring = list(island.exterior.coords)
    a, b = ring[-2], ring[-1]
    open_ring = ring[:-1] + [(a[0] + (b[0] - a[0]) * 0.8, a[1] + (b[1] - a[1]) * 0.8)]
    dx = DY / math.cos(math.radians(49.55))

    def doubled(tip, toward):
        """A 40 m feature crossing the line 40 m before tip and running 0.5 m alongside it to tip."""
        ux, uy = (toward[0] - tip[0]) / dx, (toward[1] - tip[1]) / DY
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n  # unit vector from the tip back along the line, in meters
        mid = (tip[0] + 40 * ux * dx, tip[1] + 40 * uy * DY)
        side = (-uy, ux)  # 0.5 m to one side
        return LineString([(mid[0] - 0.5 * side[0] * dx, mid[1] - 0.5 * side[1] * DY),
                           (mid[0] + 0.5 * side[0] * dx, mid[1] + 0.5 * side[1] * DY),
                           (tip[0] + 0.5 * side[0] * dx, tip[1] + 0.5 * side[1] * DY)])

    lines = [LineString(open_ring), doubled(open_ring[0], open_ring[1]), doubled(open_ring[-1], open_ring[-2])]
    with pytest.raises(coast.CoastError, match="more than 50 m"):
        _land(lines, island)


def test_long_retraced_stub_still_fails():
    """A spike retraced as the atlas does it but 150 m long, over RETRACE_MAX_M: never skipped."""
    from shapely.geometry import LineString

    coords = [(-124.01, 49.53), (-123.97, 49.53), (-123.95, 49.53), (-123.95, 49.61)]
    spiked = _with_spike(coords, 1, (-123.97, 49.53 - 150 * DY), 2e-7)
    with pytest.raises(coast.CoastError, match="more than 50 m"):
        _land([LineString(spiked)], L_LAND)


def test_stub_into_open_water_still_fails():
    """A 20 m stub off the coast with nothing alongside it is a free line end, not a retraced segment."""
    from shapely.geometry import LineString

    stub = LineString([(-123.97, 49.53), (-123.97, 49.53 - 20 * DY)])
    with pytest.raises(coast.CoastError, match="more than 50 m"):
        _land([LineString(L_COAST), stub], L_LAND)


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


def test_wet_cells_along_a_long_parallel_stay_valid_in_meters():
    """Wet cells come as lon/lat polygons whose edges run along parallels for tens of km (strait, 2026-11-12: a
    29 km edge on 48.50 N). Projected by their vertices alone, such an edge becomes a chord that sags across a
    one-cell hole 13 m north of it, and the wet cells are invalid in meters (side location conflict)."""
    from shapely.geometry import LineString, box

    dx = DY / math.cos(math.radians(49.55))
    hole = box(-123.975, 49.55 + 10 * DY, -123.975 + 10 * dx, 49.55 + 40 * DY)
    wet = box(-124.2, 49.55, -123.75, 49.56).difference(hole)  # a 32 km south edge; 14% of the land face
    land, flipped = _land([LineString(L_COAST)], L_LAND, wet=wet)
    assert flipped == [] and land.intersection(wet).area == 0 and land.contains(hole.representative_point())
    assert _close(land, L_LAND.difference(wet))


def test_water_vote_on_land_fails():
    """A wrong land side: the vote takes the true land for water, so the deep points beside the line are on land."""
    from shapely.geometry import LineString, box

    area = box(*LAND_BOX)
    water = _water_points(area, area.difference(L_LAND))  # deep cells all over the true land
    water = water.union(_water_points(area, area.difference(box(-123.95, 49.5, -123.9, 49.53))))
    with pytest.raises(coast.CoastError, match="1%"):
        _land([LineString(L_COAST)], L_LAND, water=water)


def test_inland_lake_far_from_the_coastline_passes_and_is_counted():
    """Deep points of a lake over 1 km inside the land (about 5% of all points, over the old whole-region 1%)
    are not a coastline error: the guard counts only points near a line, and the inland ones are reported."""
    import numpy as np
    import shapely
    from shapely.geometry import LineString, box

    lake = box(-123.99, 49.55, -123.975, 49.58)  # 13% of the land face: under the river share, stays land
    area = box(*LAND_BOX)
    water = _water_points(area, L_LAND).union(_water_points(area, area.difference(lake)))
    in_lake = int(shapely.contains_xy(lake, *np.transpose(shapely.get_coordinates(water))).sum())
    assert in_lake > 0.01 * len(water.geoms)
    land, flipped, inland = _land([LineString(L_COAST)], L_LAND, water=water, wet=lake, full=True)
    assert inland == in_lake and flipped == []
    assert _close(land, L_LAND.difference(lake))


def test_coastline_shifted_seaward_fails():
    """The atlas line 300 m seaward of the true shore puts a strip of deep water next to it on land."""
    from shapely.geometry import LineString

    dy, dx = 300 * DY, 300 * DY / math.cos(math.radians(49.53))
    shifted = [(-124.01, 49.53 - dy), (-123.95 + dx, 49.53 - dy), (-123.95 + dx, 49.61)]
    with pytest.raises(coast.CoastError, match="within 500 m of the coastline"):
        _land([LineString(shifted)], L_LAND)  # water points from the true shore


def _strips(near_land: int, inland: int, straddle: int = 0, sea_m: float = 100):
    """A straight coast along 49.55 N (land north) and vote points in rows parallel to it: 990 in the sea sea_m
    south of the line, near_land on land 400 m north (inside GUARD_NEAR_M), inland on land 600 m north
    (outside it) and straddle on land 150 m north."""
    import numpy as np
    import shapely
    from shapely.geometry import LineString

    def row(n, metres):
        x = np.linspace(-123.995, -123.905, n) if n else np.zeros(0)
        return np.column_stack([x, np.full(n, 49.55 + metres * DY)])

    points = np.vstack([row(990, -sea_m), row(near_land, 400), row(inland, 600), row(straddle, 150)])
    return [LineString([(-124.01, 49.55), (-123.89, 49.55)])], shapely.MultiPoint(points)


def test_guard_limit_is_one_percent_of_the_points_within_500_m():
    """11 of 1,001 near points on land (1.10%) stop the build; 9 of 999 (0.90%) pass. The rows 400 m from the line
    pin the 500 m reach too: at a shorter reach they would not count."""
    from shapely.geometry import box

    north = box(-124.0, 49.55, -123.9, 49.6)
    lines, water = _strips(11, 0)
    with pytest.raises(coast.CoastError, match="11 of 1001 water points within 500 m"):
        _land(lines, north, water=water)
    lines, water = _strips(9, 0)
    _, _, inland = _land(lines, north, water=water, full=True)
    assert inland == 0


def test_points_beyond_500_m_are_inland_not_in_the_guard():
    """50 points 600 m inside the land (5% of all) count as inland only; the 9 at 400 m count in the guard only."""
    from shapely.geometry import box

    lines, water = _strips(9, 50)
    _, _, inland = _land(lines, box(-124.0, 49.55, -123.9, 49.6), water=water, full=True)
    assert inland == 50


def test_guard_leaves_out_points_within_two_cells_of_a_line():
    """On NONNA-100 (about 100 m cells) deep cells reach a cell or two past a right coastline: from NONNA-100 alone,
    5.37% of the near points of bc-south-georgia fall on land, against 0.20% from NONNA-10 (2026-11-12). With a
    200 m skip (two NONNA-100 cells) the 100 points 150 m inside the land (9%) are left out; the 11 at 400 m still
    stop the build. With no skip, as on NONNA-10, the same 100 points count, and so do points 20 m inside (two
    NONNA-10 cells)."""
    import numpy as np
    import shapely
    from shapely.geometry import Polygon, box

    north = box(-124.0, 49.55, -123.9, 49.6)
    lines, water = _strips(9, 0, straddle=100, sea_m=300)
    land, _ = coast.land_polygons(lines, LAND_BOX, CANADA, water, Polygon(), skip_m=200.0)[:2]
    assert _close(land, north, 0.01)  # the 8.6 km line, projected by its two ends, sags about 1 m
    with pytest.raises(coast.CoastError, match=r"109 of 1099 water points within 500 m of the coastline \("):
        coast.land_polygons(lines, LAND_BOX, CANADA, water, Polygon(), skip_m=0.0)
    lines, water = _strips(11, 0, straddle=100, sea_m=300)
    with pytest.raises(coast.CoastError, match="11 of 1001 water points within 500 m"):
        coast.land_polygons(lines, LAND_BOX, CANADA, water, Polygon(), skip_m=200.0)
    lines, water = _strips(0, 0, sea_m=300)
    inside = shapely.MultiPoint([(x, 49.55 + 20 * DY) for x in np.linspace(-123.995, -123.905, 11)])
    with pytest.raises(coast.CoastError, match=r"11 of 1001 water points within 500 m of the coastline \("):
        coast.land_polygons(lines, LAND_BOX, CANADA, water.union(inside), Polygon(), skip_m=0.0)


def test_guard_without_points_near_the_coastline_fails():
    """No water point within 500 m of a line: the guard cannot judge, so it fails rather than pass."""
    import shapely
    from shapely.geometry import LineString, box

    line = LineString(L_COAST)
    area = box(*LAND_BOX)
    water = _water_points(area, L_LAND)
    far = shapely.MultiPoint([p for p in water.geoms if p.distance(line) * 111320 * 0.65 > 600])
    assert 0 < len(far.geoms) < len(water.geoms)
    with pytest.raises(coast.CoastError, match="no water point lies within 500 m"):
        _land([line], L_LAND, water=far)


def test_no_coastline_is_all_water():
    land, flipped = _land([], __import__("shapely").geometry.Polygon())
    assert land.is_empty and land.geom_type == "MultiPolygon" and flipped == []


@pytest.mark.parametrize("cap", [None, 500])
def test_derive_stats_lists_water_faces(tmp_path, regions_dir, monkeypatch, cap):
    """derive-sources over a river mouth: the face behind the construction line is a third river (wet, 1 m deep,
    NONNA-10 only), so it turns to water and derive-stats lists it; no land is left, and the land beside the
    river, which no grid covers, is the no-survey mask. A vote sampled down to 500 points gives the same. The guard
    skips no point near a line on NONNA-10, and two cells (the EPSG:3857 cell width at mid-box) on NONNA-100 alone."""
    if cap is not None:
        monkeypatch.setattr("chartpack.enc.nosurvey.MAX_VOTE_POINTS", cap)
    import hashlib
    import shutil

    import numpy as np
    from make_nonna import NODATA
    from test_bathy_blocks import _write_nonna_over

    from osgeo import gdal

    from chartpack import cli
    from chartpack.cli import main
    from chartpack.grid import fetch_extent
    from chartpack.region import load_region

    skips = []

    def recorded(*args, **kwargs):
        skips.append(kwargs["skip_m"])
        return coast.land_polygons(*args, **kwargs)

    monkeypatch.setattr(cli, "land_polygons", recorded)
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
    assert stats["missing_in_100_km2"] > 0 and stats["inland_water_points"] == 0 and stats["retraced_ends"] == []
    assert stats["inputs"] == {name: entry["sha256"] for name, entry in files.items()}  # what it was derived from
    with gzip.open(out / "land-rv.geojson.gz", "rt") as f:
        assert json.load(f)["features"] == []
    with gzip.open(out / "nosurvey-rv.geojson.gz", "rt") as f:
        assert len(json.load(f)["features"]) == 2
    region.write_text(region.read_text().replace('["nonna10", "nonna100"]', '["nonna100"]'))
    assert main(["derive-sources", "--region", str(region), "--cache", str(tmp_path / "cache"),
                 "--out", str(tmp_path / "out100")]) == 0
    px = gdal.Open(str(folder / "nonna100-rv.tif")).GetGeoTransform()[1]
    mid = math.radians((extent[1] + extent[3]) / 2)
    assert skips == [0.0, pytest.approx(coast.GUARD_SKIP_CELLS * px * math.cos(mid), rel=1e-6)]
