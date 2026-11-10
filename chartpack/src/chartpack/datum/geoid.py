"""CRM's EGM2008 heights to NAVD88 heights with PROJ geoid grids (plan 7, #88).

The PROJ pipeline runs from ITRF2014 2D + EGM2008 height (CRM's WGS 84 heights are realized in ITRF2014) to
NAD83(2011) + NAVD88 height at epoch 2010.0: the NGA EGM2008 grid to ellipsoid height, the ITRF2014 to
NAD83(2011) frame change (about 0.3 m of ellipsoid height at Seattle), then the NOAA GEOID18 grid to NAVD88.
Never EPSG:4326 as the source: PROJ may pick a ballpark (no shift) step from the WGS 84 ensemble.
"""

import functools
import os
from pathlib import Path

import numpy as np
import pyproj
from pyproj.transformer import TransformerGroup

from chartpack.cache import download
from chartpack.datum import node_axes, resample

SOURCE_CRS = "EPSG:9000+3855"  # ITRF2014 (geographic 2D) + EGM2008 height
TARGET_CRS = "EPSG:6318+5703"  # NAD83(2011) (geographic 2D) + NAVD88 height
EPOCH = 2010.0
CDN = "https://cdn.proj.org/"
# The grids the pipeline uses, with their sizes from https://cdn.proj.org/files.geojson (2026-11-09).
# Both are public domain (PROJ-data us_nga/us_nga_README.txt and us_noaa/us_noaa_README.txt).
GRIDS = {"us_nga_egm08_25.tif": 80585622, "us_noaa_g2018u0.tif": 16742155}


class GeoidError(Exception):
    pass


def fetch_grids(cache: Path) -> None:
    """The geoid grids in cache, downloaded from the PROJ CDN when absent or the wrong size."""
    for name, size in GRIDS.items():
        path = Path(cache) / name
        if not path.exists() or path.stat().st_size != size:
            download(CDN + name, path, expected_size=size)


def check_pipeline(transformer) -> None:
    """Fail the build unless the pipeline uses real grids: no ballpark step, a known accuracy."""
    accuracy = transformer.accuracy
    if "Ballpark" in transformer.description or accuracy is None or accuracy < 0:
        raise GeoidError(f"EGM2008 to NAVD88 has no grid pipeline: {transformer.description} (accuracy {accuracy})")


@functools.cache
def _transformer(cache: str) -> pyproj.Transformer:
    if cache not in pyproj.datadir.get_data_dir().split(os.pathsep):
        pyproj.datadir.append_data_dir(cache)
    group = TransformerGroup(SOURCE_CRS, TARGET_CRS, always_xy=True)
    if not group.best_available or not group.transformers:
        raise GeoidError(f"EGM2008 to NAVD88: the best pipeline needs grids missing from {cache}")
    transformer = group.transformers[0]
    check_pipeline(transformer)
    return transformer


def egm2008_to_navd88_m(transform, shape: tuple[int, int], cache: Path) -> np.ndarray:
    """NAVD88 height minus EGM2008 height at each cell of the grid (float32, meters): add it to a CRM height
    for the NAVD88 height. The grids are fetched into cache when missing."""
    cache = Path(cache).resolve()
    fetch_grids(cache)
    transformer = _transformer(str(cache))
    lons, lats = node_axes(transform, shape)
    lon, lat = (a.ravel() for a in np.meshgrid(lons, lats))
    _, _, height, _ = transformer.transform(lon, lat, np.zeros_like(lon), np.full_like(lon, EPOCH))
    nodes = np.asarray(height).reshape(len(lats), len(lons))
    if not np.isfinite(nodes).all():
        raise GeoidError(f"EGM2008 to NAVD88 is undefined in part of {transform} {shape} (outside GEOID18)")
    return resample(nodes, lons, lats, transform, shape)
