"""NAVD88 to MLLW offsets per area, interpolated between NOAA CO-OPS tide stations (plan 7, #88).

Inverse distance weighting (power 3) over every station, with no nearest-k cut, so the offset has no jump
where the nearest set would change. Far offshore the nearest coastal station dominates. Spec 8 asks for the
nearest station offshore; this is continuous instead (tests/test_datum_offsets.py bounds the difference).
"""

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from chartpack.datum import node_axes, resample

POWER = 3
EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    lat: float
    lon: float
    navd88_to_mllw_m: float  # how far NAVD88 zero lies above MLLW


@dataclass(frozen=True)
class Lake:
    name: str
    low_level_navd88_m: float
    source: str


@dataclass(frozen=True)
class Datum:
    stations: list[Station]
    lakes: list[Lake]
    lake_areas: dict[str, dict] = field(default_factory=dict)  # lake name -> GeoJSON geometry (lon/lat)


def load_datum(path: Path) -> Datum:
    """The stations and lakes of a datum file such as regions/datum/wa-stations.toml. The lake polygons come
    from the GeoJSON named by its lakes_file (relative to the datum file), one Feature per [[lakes]] name."""
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    stations = [Station(str(s["id"]), s["name"], float(s["lat"]), float(s["lon"]), float(s["navd88_to_mllw_m"]))
                for s in data["stations"]]
    lakes = [Lake(lake["name"], float(lake["low_level_navd88_m"]), lake["source"]) for lake in data.get("lakes", [])]
    areas = {}
    if "lakes_file" in data:
        with (path.parent / data["lakes_file"]).open() as f:
            areas = {feat["properties"]["name"]: feat["geometry"] for feat in json.load(f)["features"]}
    if set(areas) != {lake.name for lake in lakes}:
        names = sorted(lake.name for lake in lakes)
        raise ValueError(f"{path}: lake polygons {sorted(areas)} do not match [[lakes]] {names}")
    return Datum(stations, lakes, areas)


def datum_provenance(path: Path) -> dict:
    """The datum file's name and sha256, plus its lakes_file's name and sha256 when it has one, for the pack
    metadata: both files change depths."""
    path = Path(path)
    with path.open("rb") as f:
        lakes_file = tomllib.load(f).get("lakes_file")
    out = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if lakes_file is not None:
        lakes = path.parent / lakes_file
        out |= {"lakes_file": lakes.name, "lakes_sha256": hashlib.sha256(lakes.read_bytes()).hexdigest()}
    return out


def navd88_to_mllw_nodes(stations: list[Station], lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """The weighted offset at each node (lats by lons), by great-circle distance to every station."""
    lon, lat = (np.radians(a)[..., None] for a in np.meshgrid(lons, lats))
    s_lon = np.radians([s.lon for s in stations])
    s_lat = np.radians([s.lat for s in stations])
    h = np.sin((lat - s_lat) / 2) ** 2 + np.cos(lat) * np.cos(s_lat) * np.sin((lon - s_lon) / 2) ** 2
    distance = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(h))
    weight = 1 / np.maximum(distance, 1.0) ** POWER  # a node on a station takes its value
    return (weight * np.array([s.navd88_to_mllw_m for s in stations])).sum(-1) / weight.sum(-1)


def navd88_to_mllw_grid(stations: list[Station], transform, shape: tuple[int, int]) -> np.ndarray:
    """How far NAVD88 zero lies above MLLW at each cell of the grid (float32, meters)."""
    lons, lats = node_axes(transform, shape)
    return resample(navd88_to_mllw_nodes(stations, lons, lats), lons, lats, transform, shape)
