"""NAVD88 to MLLW offsets per area from NOAA CO-OPS stations (plan 7, Task 13, #88)."""

import dataclasses
import hashlib
import datetime
import json
import math
import tomllib

import numpy as np
import shapely
import pytest
from osgeo import gdal, osr
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from chartpack.bathy.blocks import area_datum, build_overview, overview_bounds
from chartpack.datum import geoid
from chartpack.datum.offsets import Station, datum_provenance, load_datum, navd88_to_mllw_grid

KM_PER_DEG_LAT = 6371.0088 * math.pi / 180


def _around(lon: float, lat: float, res: float = 1 / 3600, n: int = 3) -> tuple[tuple, tuple[int, int]]:
    """An n by n grid of res cells whose middle cell is centered on (lon, lat)."""
    half = n * res / 2
    return (lon - half, res, 0.0, lat + half, 0.0, -res), (n, n)


def _at(stations, lon: float, lat: float) -> float:
    transform, shape = _around(lon, lat)
    return float(navd88_to_mllw_grid(stations, transform, shape)[1, 1])


@pytest.fixture
def wa(regions_dir):
    return load_datum(regions_dir / "datum" / "wa-stations.toml")


def test_offset_equals_station_at_station(wa):
    for s in wa.stations:
        assert _at(wa.stations, s.lon, s.lat) == pytest.approx(s.navd88_to_mllw_m, abs=0.01), s.name


def test_offset_between_two_stations_is_between():
    a = Station("1", "a", 48.0, -124.0, 0.2)
    b = Station("2", "b", 48.0, -123.0, 0.9)
    mid = _at([a, b], -123.5, 48.0)
    assert 0.2 < mid < 0.9


def test_far_offshore_close_to_nearest():
    """Inverse distance weighting is continuous, not the nearest station of spec 8: 50 km west of the nearest
    station, with the next one 50 km along the coast and 0.3 m off, the offset stays within 0.15 m of the nearest."""
    near = Station("1", "near", 48.0, -124.6, 0.3)
    along = Station("2", "along", 48.0 + 50 / KM_PER_DEG_LAT, -124.6, 0.6)
    west = -124.6 - 50 / (KM_PER_DEG_LAT * math.cos(math.radians(48.0)))
    assert _at([near, along], west, 48.0) == pytest.approx(0.3, abs=0.15)


def test_seattle_offset_matches_today(wa):
    """The constant every region used before #88: Seattle 9447130, NAVD88 0.715 m above MLLW."""
    assert _at(wa.stations, -122.3393, 47.60264) == pytest.approx(0.715, abs=0.01)


def test_stations_file_has_sources(regions_dir):
    with (regions_dir / "datum" / "wa-stations.toml").open("rb") as f:
        stations = tomllib.load(f)["stations"]
    assert stations
    for s in stations:
        assert s["source"] == (
            f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{s['id']}/datums.json?units=metric"
        ), s["id"]
        assert isinstance(s["retrieved"], datetime.date), s["id"]


def test_lake_file_names_match(wa, regions_dir):
    """Every polygon of lakes.geojson has a [[lakes]] entry of the datum file, and the reverse."""
    with (regions_dir / "datum" / "lakes.geojson").open() as f:
        polygons = {feat["properties"]["name"] for feat in json.load(f)["features"]}
    assert polygons == {lake.name for lake in wa.lakes} == {"Lake Union", "Lake Washington"}
    assert set(wa.lake_areas) == polygons
    for lake in wa.lakes:
        assert lake.source and 4.0 < lake.low_level_navd88_m < 7.0, lake.name


def _lake_region(test_region, tmp_path, lake: dict):
    """test_region with a datum file of one station (0.7 m) far west and one lake "Pond" (low level 6.0 m NAVD88)
    whose polygon is the lake geometry given."""
    (tmp_path / "pond.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Pond"}, "geometry": lake}]}))
    (tmp_path / "datum.toml").write_text(
        'lakes_file = "pond.geojson"\n\n'
        '[[stations]]\nid = "1"\nname = "a"\nlat = 47.6\nlon = -122.5\nnavd88_to_mllw_m = 0.7\n\n'
        '[[lakes]]\nname = "Pond"\nlow_level_navd88_m = 6.0\nsource = "test"\n')
    return dataclasses.replace(test_region, datum_file=tmp_path / "datum.toml")


@pytest.mark.parametrize("polygons, listed", [(["Pond", "Other"], ["Pond"]), (["Pond"], ["Pond", "Other"])])
def test_lake_names_must_match(polygons, listed, tmp_path):
    """A polygon with no [[lakes]] entry, or a [[lakes]] entry with no polygon, is an error."""
    square = mapping(box(-122.3, 47.6, -122.29, 47.61))
    (tmp_path / "pond.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": name}, "geometry": square} for name in polygons]}))
    lakes = "".join(f'[[lakes]]\nname = "{name}"\nlow_level_navd88_m = 6.0\nsource = "test"\n\n' for name in listed)
    (tmp_path / "datum.toml").write_text(
        'lakes_file = "pond.geojson"\n\n'
        '[[stations]]\nid = "1"\nname = "a"\nlat = 47.6\nlon = -122.5\nnavd88_to_mllw_m = 0.7\n\n' + lakes)
    with pytest.raises(ValueError, match="do not match"):
        load_datum(tmp_path / "datum.toml")


def test_provenance_changes_with_the_lakes_file_alone(test_region, tmp_path):
    """The pack records both files: an edit to the lake polygons alone changes the recorded lakes hash."""
    region = _lake_region(test_region, tmp_path, mapping(box(-122.3, 47.6, -122.29, 47.61)))
    before = datum_provenance(region.datum_file)
    assert set(before) == {"file", "sha256", "lakes_file", "lakes_sha256"}
    assert (before["file"], before["lakes_file"]) == ("datum.toml", "pond.geojson")
    _lake_region(test_region, tmp_path, mapping(box(-122.3, 47.6, -122.28, 47.61)))
    after = datum_provenance(region.datum_file)
    assert after["sha256"] == before["sha256"] and after["lakes_sha256"] != before["lakes_sha256"]


def test_provenance_without_lakes(tmp_path):
    (tmp_path / "datum.toml").write_text(
        '[[stations]]\nid = "1"\nname = "a"\nlat = 47.6\nlon = -122.5\nnavd88_to_mllw_m = 0.7\n')
    assert set(datum_provenance(tmp_path / "datum.toml")) == {"file", "sha256"}


@pytest.mark.parametrize("source, change", [("cudem", 0.0), ("crm", 1.0)])
def test_lake_depth_from_low_level(source, change, test_region, tmp_path, monkeypatch):
    """A flat bottom at NAVD88 0 m under a lake whose low level is 6.0 m NAVD88 reads 6.0 m deep inside the lake
    polygon (cells decided by their centers) and the station path outside. CRM is EGM2008: with NAVD88 zero 1.0 m
    below EGM2008 zero, NAVD88 0 m is an EGM2008 height of -1.0 m."""
    monkeypatch.setattr(geoid, "egm2008_to_navd88_nodes",
                        lambda lons, lats, cache: np.full((len(lats), len(lons)), change))
    res = 1 / 3600
    west, north = -122.31, 47.61
    lake = mapping(box(west, north - 20 * res, west + 10 * res, north))  # the west half of the grid below
    region = _lake_region(test_region, tmp_path, lake)
    transform, shape = (west, res, 0.0, north, 0.0, -res), (20, 20)
    offset = area_datum(region, tmp_path)(source, transform, shape)
    depth = -np.full(shape, -change, np.float32) - offset
    np.testing.assert_allclose(depth[:, :10], 6.0, atol=1e-5)
    station = navd88_to_mllw_grid(load_datum(region.datum_file).stations, transform, shape)
    np.testing.assert_allclose(depth[:, 10:], -station[:, 10:], atol=1e-5)


def test_overview_applies_lake_rule(test_region, tmp_path, zero_geoid):
    """The overview path over a synthetic lake draws the lake depth, not the station path (the 0 to 60 ft band
    fills the lake, the land around it has none), while its DEM grid keeps the station path everywhere: the
    lake rule is a depth datum, not terrain (#88 review)."""
    bbox = (-122.4, 47.5, -122.2, 47.7)
    read = overview_bounds(bbox)
    cell = 1 / 3600  # native CRM, as the WCS serves it; the overview block-means it to OVERVIEW_RES_DEG
    rows, cols = round((read[3] - read[1]) / cell), round((read[2] - read[0]) / cell)
    crm = tmp_path / "crm.tif"
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds = gdal.GetDriverByName("GTiff").Create(str(crm), cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((read[0], cell, 0.0, read[3], 0.0, -cell))
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(-9999.0)
    ds.GetRasterBand(1).WriteArray(np.zeros((rows, cols), np.float32))  # flat bottom at 0 m
    ds = None
    lake = box(-122.35, 47.55, -122.25, 47.65)
    region = _lake_region(test_region, tmp_path, mapping(lake))
    result = build_overview(bbox, crm, area_datum(region, tmp_path), None)
    grid = result.coarse_grid
    station = navd88_to_mllw_grid(load_datum(region.datum_file).stations, grid.transform, grid.data.shape)
    np.testing.assert_allclose(grid.data, -station, atol=1e-5)
    water = unary_union([shape(f["geometry"]) for f in result.coarse_bands if f["properties"]["depth_min_ft"] == 0])
    assert water.symmetric_difference(lake).area < 0.05 * lake.area


def test_grid_is_window_independent(wa):
    """Every window samples the same global 0.05 degree grid, so two blocks agree on the cells they share."""
    res = 1 / 1200
    big = (-122.6, res, 0.0, 48.0, 0.0, -res)
    whole = navd88_to_mllw_grid(wa.stations, big, (240, 360))
    part = navd88_to_mllw_grid(wa.stations, (-122.6 + 100 * res, res, 0.0, 48.0 - 50 * res, 0.0, -res), (40, 70))
    np.testing.assert_array_equal(part, whole[50:90, 100:170])
    assert whole.dtype == np.float32


def test_provenance_records_the_lake_mask(test_region, tmp_path):
    """The lake mask changes depths too (none drawn there): the pack records its name and hash."""
    region = _lake_region(test_region, tmp_path, mapping(box(-122.3, 47.6, -122.29, 47.61)))
    text = region.datum_file.read_text()
    region.datum_file.write_text('lake_mask_file = "mask.geojson"\n' + text)
    (tmp_path / "mask.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Other"}, "geometry": mapping(box(-122.2, 47.6, -122.19, 47.61))}]}))
    got = datum_provenance(region.datum_file)
    assert got["lake_mask_file"] == "mask.geojson"
    assert got["lake_mask_sha256"] == hashlib.sha256((tmp_path / "mask.geojson").read_bytes()).hexdigest()
    assert [shape(g) for g in load_datum(region.datum_file).lake_mask] == [box(-122.2, 47.6, -122.19, 47.61)]


def test_wave1_lake_mask(wa, regions_dir):
    """The shipped lake mask: polygons inside the owned tiles, outside the Canada clip, apart from the lakes that
    keep a datum rule (lakes.geojson)."""
    from chartpack.grid import load_grid, owned_tiles, tiles_area
    from chartpack.region import load_region

    assert wa.lake_mask
    mask = shapely.union_all([shape(g) for g in wa.lake_mask])
    datum_lakes = shapely.union_all([shape(g) for g in wa.lake_areas.values()])
    clip = json.loads((regions_dir / "clip" / "canada-wa.geojson").read_text())
    owned = set().union(*(owned_tiles(load_region(regions_dir / f"{n}.toml"), regions_dir)
                          for n in load_grid(regions_dir / "grid.toml")))
    assert not mask.intersects(datum_lakes)
    assert tiles_area(owned).buffer(1e-6).covers(mask)
    assert mask.intersection(shape(clip["geometry"])).area < 1e-8  # about 100 m2: float noise along the border


MASKED = {"Lake Sammamish": (-122.09, 47.59), "Lake Whatcom": (-122.308, 48.719), "Lake Crescent": (-123.783, 48.072),
          "Ozette Lake": (-124.63, 48.10), "Lake Quinault": (-123.86, 47.47)}
TIDAL = {"Crescent Harbor": (-122.614, 48.302), "Port Angeles lagoon": (-123.469, 48.133),
         "Crockett Lake": (-122.662, 48.1667), "Blind Slough": (-122.501, 48.448), "Old Channel": (-122.5079, 48.448),
         "Joe Leary Slough": (-122.474, 48.518), "Alder Creek": (-123.927, 46.181), "Tansy Creek": (-123.926, 46.186),
         "Jetty Lagoon": (-123.987, 46.214), "Keyport Lagoon": (-122.6206, 47.6959),
         "Little Clam Bay": (-122.5477, 47.5638), "Whiteman Cove": (-122.8039, 47.2202)}


def test_wave1_lake_mask_holds_the_inland_lakes_not_tidal_water(wa):
    """The review's inland lakes are masked; tidal water charted or ruled as such (PR #105) is not."""
    from shapely.geometry import Point

    mask = shapely.union_all([shape(g) for g in wa.lake_mask])
    for name, (lon, lat) in MASKED.items():
        assert mask.contains(Point(lon, lat)), name
    for name, (lon, lat) in TIDAL.items():
        assert not mask.intersects(Point(lon, lat).buffer(0.0005)), name
