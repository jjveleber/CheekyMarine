"""NAVD88 to MLLW offsets per area from NOAA CO-OPS stations (plan 7, Task 13, #88)."""

import dataclasses
import datetime
import json
import math
import tomllib

import numpy as np
import pytest
from osgeo import gdal, osr
from shapely.geometry import box, mapping

from chartpack.bathy.blocks import OVERVIEW_RES_DEG, area_datum, build_overview, overview_bounds
from chartpack.datum import geoid
from chartpack.datum.offsets import Station, load_datum, navd88_to_mllw_grid

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
    """The overview path over a synthetic lake gives the lake depth, not the station path."""
    bbox = (-122.4, 47.5, -122.2, 47.7)
    read = overview_bounds(bbox)
    cell = OVERVIEW_RES_DEG
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
    grid = build_overview(bbox, crm, area_datum(region, tmp_path), None).coarse_grid
    x0, dx, _, y0, _, dy = grid.transform
    lon = x0 + (np.arange(grid.data.shape[1]) + 0.5) * dx
    lat = y0 + (np.arange(grid.data.shape[0]) + 0.5) * dy
    inside = ((lon > -122.35) & (lon < -122.25))[None, :] & ((lat > 47.55) & (lat < 47.65))[:, None]
    assert inside.sum() > 100 and (~inside).sum() > 100
    np.testing.assert_allclose(grid.data[inside], 6.0, atol=1e-5)
    station = navd88_to_mllw_grid(load_datum(region.datum_file).stations, grid.transform, grid.data.shape)
    np.testing.assert_allclose(grid.data[~inside], -station[~inside], atol=1e-5)


def test_grid_is_window_independent(wa):
    """Every window samples the same global 0.05 degree grid, so two blocks agree on the cells they share."""
    res = 1 / 1200
    big = (-122.6, res, 0.0, 48.0, 0.0, -res)
    whole = navd88_to_mllw_grid(wa.stations, big, (240, 360))
    part = navd88_to_mllw_grid(wa.stations, (-122.6 + 100 * res, res, 0.0, 48.0 - 50 * res, 0.0, -res), (40, 70))
    np.testing.assert_array_equal(part, whole[50:90, 100:170])
    assert whole.dtype == np.float32
