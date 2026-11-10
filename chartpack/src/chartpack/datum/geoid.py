"""CRM's EGM2008 heights to NAVD88 heights with PROJ geoid grids (plan 7, #88).

The PROJ pipeline runs from ITRF2014 2D + EGM2008 height (CRM's WGS 84 heights are realized in ITRF2014) to
NAD83(2011) + NAVD88 height at epoch 2010.0: the NGA EGM2008 grid to ellipsoid height, the ITRF2014 to
NAD83(2011) frame change (about 0.3 m of ellipsoid height at Seattle), then the NOAA GEOID18 grid to NAVD88.
Never EPSG:4326 as the source: PROJ may pick a ballpark (no shift) step from the WGS 84 ensemble.
"""

import functools
import hashlib
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
# The grids the pipeline uses: (size, sha256) from https://cdn.proj.org/files.geojson (2026-11-09).
# Both are public domain (PROJ-data us_nga/us_nga_README.txt and us_noaa/us_noaa_README.txt).
GRIDS = {
    "us_nga_egm08_25.tif": (80585622, "4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a"),
    "us_noaa_g2018u0.tif": (16742155, "fa9a407ac7ee3f5a3694008e4bcd09ce9cc250452f0c3b11700a4960340abce2"),
}


class GeoidError(Exception):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _good(path: Path, size: int, sha256: str) -> bool:
    return path.exists() and path.stat().st_size == size and _sha256(path) == sha256


def missing_grids(cache: Path) -> list[Path]:
    """The grid paths in cache that are absent or do not match their published size and sha256."""
    return [Path(cache) / name for name, (size, sha256) in GRIDS.items() if not _good(Path(cache) / name, size, sha256)]


def fetch_grids(cache: Path) -> None:
    """The geoid grids in cache (fetch-bathy): a grid that is absent or damaged is downloaded from the PROJ CDN,
    and a download whose sha256 is not the published one is removed and fails."""
    for path in missing_grids(cache):
        size, sha256 = GRIDS[path.name]
        download(CDN + path.name, path, expected_size=size)
        if _sha256(path) != sha256:
            path.unlink()
            raise GeoidError(f"{CDN + path.name}: sha256 is not the published {sha256}")


def check_pipeline(transformer) -> None:
    """Fail the build unless the pipeline uses real grids: no ballpark step, a known accuracy, both GRIDS."""
    accuracy = transformer.accuracy
    if "Ballpark" in transformer.description or accuracy is None or accuracy < 0:
        raise GeoidError(f"EGM2008 to NAVD88 has no grid pipeline: {transformer.description} (accuracy {accuracy})")
    if unused := [name for name in GRIDS if name not in transformer.definition]:
        raise GeoidError(f"EGM2008 to NAVD88 pipeline does not use {', '.join(unused)}: {transformer.definition}")


@functools.cache
def _transformer(cache: str) -> pyproj.Transformer:
    """The checked pipeline over the grids in cache, verified once per cache."""
    if missing := missing_grids(Path(cache)):
        raise GeoidError(f"{missing[0]} missing or damaged; run fetch-bathy first")
    if cache not in pyproj.datadir.get_data_dir().split(os.pathsep):
        pyproj.datadir.append_data_dir(cache)
    group = TransformerGroup(SOURCE_CRS, TARGET_CRS, always_xy=True)
    if not group.best_available or not group.transformers:
        raise GeoidError(f"EGM2008 to NAVD88: the best pipeline needs grids missing from {cache}")
    transformer = group.transformers[0]
    check_pipeline(transformer)
    return transformer


def egm2008_to_navd88_nodes(lons: np.ndarray, lats: np.ndarray, cache: Path) -> np.ndarray:
    """NAVD88 height minus EGM2008 height at the global grid nodes (lats by lons, from node_axes), from the grids
    fetch_grids put in cache."""
    transformer = _transformer(str(Path(cache).resolve()))
    lon, lat = (a.ravel() for a in np.meshgrid(lons, lats))
    _, _, height, _ = transformer.transform(lon, lat, np.zeros_like(lon), np.full_like(lon, EPOCH))
    nodes = np.asarray(height).reshape(len(lats), len(lons))
    if not np.isfinite(nodes).all():
        raise GeoidError(f"EGM2008 to NAVD88 is undefined at some of lon {lons[[0, -1]]}, lat {lats[[0, -1]]} "
                         "(outside GEOID18)")
    return nodes


def egm2008_to_navd88_m(transform, shape: tuple[int, int], cache: Path) -> np.ndarray:
    """NAVD88 height minus EGM2008 height at each cell of the grid (float32, meters): add it to a CRM height
    for the NAVD88 height."""
    lons, lats = node_axes(transform, shape)
    return resample(egm2008_to_navd88_nodes(lons, lats, cache), lons, lats, transform, shape)
