"""NOAA ENC product catalog (ENCProdCat.xml) parsing and bbox selection."""

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

from shapely.geometry import Polygon, box

CATALOG_URL = "https://charts.noaa.gov/ENCs/ENCProdCat.xml"


@dataclass(frozen=True)
class CellInfo:
    name: str
    band: int
    status: str
    edtn: int
    updn: int
    isdt: date
    zip_url: str
    zip_size: int
    polygon: list[tuple[float, float]]  # (lat, lon) vertices of the first coverage panel
    other_panels: tuple[tuple[tuple[float, float], ...], ...] = ()  # further panels


def _panels(cell: ET.Element) -> list[list[tuple[float, float]]]:
    panels = []
    for panel in cell.findall("cov/panel"):
        if panel.findtext("type") != "E":
            continue
        panels.append(
            [(float(v.findtext("lat")), float(v.findtext("long"))) for v in panel.findall("vertex")]
        )
    return panels


def parse_catalog(xml_bytes: bytes) -> dict[str, CellInfo]:
    catalog: dict[str, CellInfo] = {}
    for _, el in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if el.tag != "cell":
            continue
        name = el.findtext("name")
        panels = _panels(el)
        # The catalog lists www.charts.noaa.gov; the bare host serves the same files.
        url = el.findtext("zipfile_location").replace("://www.charts.", "://charts.")
        catalog[name] = CellInfo(
            name=name,
            band=int(name[2]),
            status=el.findtext("status"),
            edtn=int(el.findtext("edtn")),
            updn=int(el.findtext("updn")),
            isdt=date.fromisoformat(el.findtext("isdt")),
            zip_url=url,
            zip_size=int(el.findtext("zipfile_size")),
            polygon=panels[0] if panels else [],
            other_panels=tuple(tuple(p) for p in panels[1:]),
        )
        el.clear()
    return catalog


def _intersects(cell: CellInfo, window) -> bool:
    for ring in [cell.polygon, *cell.other_panels]:
        if len(ring) >= 3 and Polygon([(lon, lat) for lat, lon in ring]).intersects(window):
            return True
    return False


def cells_in_bbox(catalog: dict[str, CellInfo], bbox, band: int) -> list[str]:
    window = box(*bbox)  # W, S, E, N
    return sorted(
        c.name
        for c in catalog.values()
        if c.band == band and c.status == "Active" and _intersects(c, window)
    )
