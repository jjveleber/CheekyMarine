"""NAVD88 to MLLW offsets per area from NOAA CO-OPS stations (plan 7, Task 13, #88)."""

import datetime
import math
import tomllib

import numpy as np
import pytest

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


def test_no_lakes_until_listed(wa):
    assert wa.lakes == []


def test_grid_is_window_independent(wa):
    """Every window samples the same global 0.05 degree grid, so two blocks agree on the cells they share."""
    res = 1 / 1200
    big = (-122.6, res, 0.0, 48.0, 0.0, -res)
    whole = navd88_to_mllw_grid(wa.stations, big, (240, 360))
    part = navd88_to_mllw_grid(wa.stations, (-122.6 + 100 * res, res, 0.0, 48.0 - 50 * res, 0.0, -res), (40, 70))
    np.testing.assert_array_equal(part, whole[50:90, 100:170])
    assert whole.dtype == np.float32
