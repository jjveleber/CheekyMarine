"""Region definition: which cells, bathymetry sources and datum file make a pack."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from chartpack.datum import SOURCE_VERTICAL
from chartpack.seabed.cmecs import BLOCKS

SEABED_SOURCES = ("enc", "usseabed", "usgs-cmecs")  # spec 6.10


class RegionError(Exception):
    pass


@dataclass(frozen=True)
class View:
    name: str
    lon: float
    lat: float
    zooms: tuple[int, ...]


@dataclass(frozen=True)
class Region:
    name: str
    charts_version: str
    bathy_version: str
    bbox: tuple[float, float, float, float]  # W, S, E, N
    cells: dict[int, list[str]]  # band -> cell names
    bathy_sources: list[str]
    coarse_fallback: str  # "crm": CRM contours where CUDEM is absent; "enc": ENC contours
    clip: Path | None  # polygon GeoJSON of water to remove
    dem_maxzoom: int
    datum_file: Path  # the MLLW offsets per area (chartpack.datum.offsets), from [datum] file
    views: list[View]
    seabed_sources: tuple[str, ...] = ("enc",)
    cmecs_blocks: tuple[str, ...] = ()  # keys of seabed.cmecs.BLOCKS
    overview: bool = False  # the zoom 6 to 9 overview pack: owns no zoom-10 tile


def _need(table: dict, key: str, where: str = ""):
    if key not in table:
        raise RegionError(f"missing key {where}{key}")
    return table[key]


def _overview(data: dict) -> bool:
    value = data.get("overview", False)
    if not isinstance(value, bool):
        raise RegionError("overview must be true or false")
    return value


def load_region(path: Path) -> Region:
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)

    name = _need(data, "name")
    charts_version = _need(data, "charts_version")
    bathy_version = _need(data, "bathy_version")
    bbox = tuple(float(v) for v in _need(data, "bbox"))
    if len(bbox) != 4:
        raise RegionError("bbox must have 4 values: W, S, E, N")

    enc = _need(data, "enc")
    cells: dict[int, list[str]] = {}
    for key, names in enc.items():
        m = re.fullmatch(r"band(\d+)", key)
        if not m:
            raise RegionError(f"unexpected key enc.{key}")
        cells[int(m.group(1))] = list(names)

    bathy = _need(data, "bathy")
    datum = _need(data, "datum")

    coarse_fallback = data.get("coarse_fallback", "crm")
    if coarse_fallback not in ("crm", "enc"):
        raise RegionError("coarse_fallback must be 'crm' or 'enc'")
    if coarse_fallback == "enc" and "crm" in bathy.get("sources", []):
        raise RegionError("coarse_fallback = 'enc' cannot be used with crm in bathy.sources (the coarse layers are CRM)")

    bathy_sources = list(_need(bathy, "sources", "bathy."))
    if not bathy_sources:
        raise RegionError("bathy.sources must list at least one source")
    for source in bathy_sources:
        if source not in SOURCE_VERTICAL:
            raise RegionError(f"unknown bathy source: {source}")

    if coarse_fallback == "crm" and "crm" not in bathy_sources:
        raise RegionError("coarse_fallback = 'crm' needs crm in bathy.sources (set coarse_fallback = 'enc' for CUDEM only)")
    overview = _overview(data)
    if overview and bathy_sources != ["crm"]:
        raise RegionError('an overview region needs bathy.sources = ["crm"]: it is built from one CRM read')

    seabed = data.get("seabed", {})
    seabed_sources = tuple(seabed.get("sources", ["enc"]))
    cmecs_blocks = tuple(seabed.get("cmecs_blocks", []))
    unknown = [s for s in seabed_sources if s not in SEABED_SOURCES] + [b for b in cmecs_blocks if b not in BLOCKS]
    if unknown:
        raise RegionError(f"unknown seabed source or CMECS block: {', '.join(unknown)}")
    if "enc" not in seabed_sources:
        raise RegionError("seabed.sources must include enc, the baseline bottom marks")
    if ("usgs-cmecs" in seabed_sources) != bool(cmecs_blocks):
        raise RegionError("seabed.cmecs_blocks must be listed exactly when seabed.sources has usgs-cmecs")

    clip = data.get("clip")
    views = [
        View(
            _need(v, "name", "render.views."),
            float(_need(v, "lon", "render.views.")),
            float(_need(v, "lat", "render.views.")),
            tuple(_need(v, "zooms", "render.views.")),
        )
        for v in data.get("render", {}).get("views", [])
    ]

    return Region(
        name=name,
        charts_version=charts_version,
        bathy_version=bathy_version,
        bbox=bbox,
        cells=cells,
        bathy_sources=bathy_sources,
        coarse_fallback=coarse_fallback,
        clip=path.parent / clip if clip else None,
        dem_maxzoom=int(_need(bathy, "dem_maxzoom", "bathy.")),
        datum_file=path.parent / _need(datum, "file", "datum."),
        views=views,
        seabed_sources=seabed_sources,
        cmecs_blocks=cmecs_blocks,
        overview=overview,
    )
