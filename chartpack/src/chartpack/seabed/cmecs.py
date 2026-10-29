"""USGS Southern Salish Sea habitat map CMECS substrate polygons (Data Series 935) as seabed areas.

Each block is one published zip holding one shapefile in NAD83 / UTM zone 10N, reprojected here to
lon/lat (NAD83 is used as WGS84, under 2 m apart here). The blocks name their substrate fields
differently; each polygon's substrate is the first filled field from finest to coarsest: subgroup,
group, the block's own symbolization field ("substrate", where it has one), subclass, class. A polygon
with no substrate, or "na" (land), is left out. Polygons are made valid and cut to the region bbox.
"""

from pathlib import Path
from typing import NamedTuple

import shapely
from osgeo import ogr, osr
from shapely import wkb
from shapely.geometry import box, mapping

from chartpack.cache import fetch_zip
from chartpack.enc.reader import Feature
from chartpack.enc.scamin import BAND_ZOOMS, extent_z0, minzoom_for_extent
from chartpack.seabed.codes import cmecs_label

ogr.UseExceptions()
osr.UseExceptions()


class Block(NamedTuple):
    url: str
    size: int  # published zip size in bytes
    name: str  # shapefile name inside the zip, and the cache file stem
    fields: tuple[str, ...]  # substrate fields, finest first


_CMGDS = "https://cmgds.marine.usgs.gov/data-releases/media/"
BLOCKS: dict[str, Block] = {
    # OFR 2015-1073, doi:10.3133/ofr20151073
    "admiralty-inlet": Block("https://pubs.usgs.gov/ds/935/downloads/AdmiraltyInlet/data/CMECS_AdmiraltyInlet.zip",
                             2320963, "CMECS_AdmiraltyInlet",
                             ("substrat_2", "substrat_1", "substrate1", "substrate_")),
    # doi:10.5066/P9GVRZ3M
    "seattle": Block(_CMGDS + "2022/10.5066-P9GVRZ3M/6835756e96aa4c36a4821c86eaf4b118/CMECS_OffshoreSeattle.zip",
                     1940569, "CMECS_OffshoreSeattle",
                     ("substr_sgr", "substr_grp", "substrate", "sbstr_scls", "sbstr_clas")),
    # doi:10.5066/P9KA6GH2
    "tacoma": Block(_CMGDS + "2022/10.5066-P9KA6GH2/498920c2c2154934bb8f68af617e3bd4/CMECS_OffshoreTacoma.zip",
                    4436048, "CMECS_OffshoreTacoma",
                    ("substr_sgr", "substr_grp", "substrate", "sbstr_scls", "substr_cls")),
    # doi:10.5066/P96T1B44
    "burien": Block(_CMGDS + "2021/10.5066-P96T1B44/8a1b2dae3c6f4b36bcc068c90c29912a/CMECS_OffshoreBurien.zip",
                    2757084, "CMECS_OffshoreBurien",
                    ("substr_sgr", "substr_grp", "substrate", "sbstr_scls")),
}

# For the pack NOTICE: the releases ask that the USGS be acknowledged in derived products.
NOTICE = (
    "  Southern Salish Sea Habitat Map Series, USGS Data Series 935, CMECS substrate polygons:\n"
    "    Admiralty Inlet, Open-File Report 2015-1073, doi:10.3133/ofr20151073\n"
    "    offshore Seattle, doi:10.5066/P9GVRZ3M\n"
    "    offshore Tacoma, doi:10.5066/P9KA6GH2\n"
    "    offshore Burien, doi:10.5066/P96T1B44"
)

# Substrate outlines and labels show from zoom 13, with the samples and the ENC bottom marks: at zoom 12 the
# Admiralty Inlet polygons crowd the chart (renders, Task 14b report). A smaller polygon waits until it is
# about 48 px across (R37).
MINZOOM = 13
MAXZOOM = BAND_ZOOMS[5][1]


def fetch_cmecs(blocks: list[str], cache_dir: Path) -> list[Path]:
    paths = []
    for block in blocks:
        b = BLOCKS[block]
        paths.append(fetch_zip(b.url, Path(cache_dir) / "seabed" / f"{b.name}.zip", size=b.size, member=f"{b.name}.shp"))
    return paths


def _substrate(feature, fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = feature.GetField(field)
        if value not in (None, ""):
            return None if value == "na" else value
    return None


def _polygons(geom):
    """The polygonal part of a shapely geometry (make_valid and clipping can add lines and points)."""
    if geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
    return shapely.union_all(parts) if parts else None


def read_cmecs(zip_path: Path, block: str, bbox) -> list[Feature]:
    """Substrate polygons of one block inside bbox (W, S, E, N), each with src, class CMECS, its
    substrate name as the source gives it, and label."""
    b = BLOCKS[block]
    area = box(*bbox)
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds = ogr.Open(f"/vsizip/{zip_path}/{b.name}.shp")
    try:
        layer = ds.GetLayer(0)
        src = layer.GetSpatialRef()
        src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transform = osr.CoordinateTransformation(src, wgs84)
        out = []
        for feature in layer:
            substrate = _substrate(feature, b.fields)
            if substrate is None:
                continue
            geom = feature.GetGeometryRef().Clone()
            geom.Transform(transform)
            shp = wkb.loads(bytes(geom.ExportToWkb()))
            if not shp.intersects(area):
                continue
            shp = _polygons(shapely.make_valid(shp).intersection(area))
            if shp is None:
                continue
            props = {"src": "usgs-cmecs", "class": "CMECS", "substrate": substrate}
            text = cmecs_label(substrate)
            if text is not None:
                props["label"] = text
            props["extent"] = extent_z0(mapping(shp))
            props["tippecanoe"] = {"minzoom": max(MINZOOM, minzoom_for_extent(props["extent"])), "maxzoom": MAXZOOM}
            out.append(Feature("seabed", mapping(shp), props))
    finally:
        feature = layer = ds = None
    return out
