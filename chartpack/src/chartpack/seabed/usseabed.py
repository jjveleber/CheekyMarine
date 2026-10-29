"""USGS usSEABED Pacific Coast sediment samples (Data Series 182, doi:10.3133/ds182) as seabed points.

The EXT (laboratory analyses) and PRS (parsed sample descriptions) files are read from the comma-delimited
text in each published zip. Coordinates are NAD83 decimal degrees (the DS 182 metadata; the shapefile .prj
says an assumed NAD27, which the metadata overrides) and are used as WGS84, under 2 m apart here. The
metadata warns that sources overlap, so exact duplicates by position and Folk class are dropped. A row
with no Folk class has no bottom type to show and is left out.
"""

import csv
import io
import zipfile
from pathlib import Path

from chartpack.cache import fetch_zip
from chartpack.enc.reader import Feature
from chartpack.enc.scamin import BAND_ZOOMS
from chartpack.seabed.codes import folk_label

_BASE = "https://pubs.usgs.gov/ds/2006/182/data/"
# cache file name -> (url, published size in bytes, text member)
FILES: dict[str, tuple[str, int, str]] = {
    "pac_ext.zip": (_BASE + "pac_ext.zip", 1087605, "PAC_EXT.txt"),
    "pac_prs.zip": (_BASE + "pac_prs.zip", 878875, "PAC_PRS.txt"),
}

# For the pack NOTICE: DS 182 asks that the USGS be recognized as the source.
NOTICE = "  usSEABED Pacific Coast offshore surficial-sediment data, USGS Data Series 182 (2006), doi:10.3133/ds182"

# Samples show from zoom 13, with the ENC bottom marks (SCAMIN 59999 in the test cell); chosen from the
# renders, where they read clean beside the soundings and lose collisions to them.
MINZOOM = 13
_TIPPECANOE = {"minzoom": MINZOOM, "maxzoom": BAND_ZOOMS[5][1]}


def fetch_usseabed(cache_dir: Path) -> list[Path]:
    return [fetch_zip(url, Path(cache_dir) / "seabed" / name, size=size, member=member)
            for name, (url, size, member) in FILES.items()]


def read_usseabed(zip_paths: list[Path], bbox) -> list[Feature]:
    """Sample points inside bbox (W, S, E, N), each with src, class SAMPLE, its Folk class and label."""
    w, s, e, n = bbox
    seen = set()
    out = []
    for path in zip_paths:
        with zipfile.ZipFile(path) as zf:
            text = zf.read(FILES[Path(path).name][2]).decode("latin1")
        for row in csv.DictReader(io.StringIO(text)):
            lon, lat, folk = float(row["Longitude"]), float(row["Latitude"]), row["FolkCode"].strip()
            if not folk or not (w <= lon <= e and s <= lat <= n) or (lon, lat, folk) in seen:
                continue
            seen.add((lon, lat, folk))
            props = {"src": "usseabed", "class": "SAMPLE", "folk": folk}
            text_label = folk_label(folk)
            if text_label is not None:
                props["label"] = text_label
            props["tippecanoe"] = dict(_TIPPECANOE)
            out.append(Feature("seabed", {"type": "Point", "coordinates": [lon, lat]}, props))
    return out
