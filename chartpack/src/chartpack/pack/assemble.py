"""Assemble the charts pack directory: enc.mbtiles, nav styles, sprites, glyphs, README, NOTICE."""

import json
import re
import shutil
from pathlib import Path

from chartpack.mbtiles import MBTiles
from chartpack.region import Region
from chartpack.style.glyphs import build_glyphs
from chartpack.style.fish import fish_style
from chartpack.style.nav import Depths, nav_style
from chartpack.style.palette import PALETTES
from chartpack.style.sprites import build_sprites

# symbols/, fonts/ and README.md live beside src/ in the chartpack project (editable install).
PROJECT = Path(__file__).resolve().parents[3]
FONTS = {"Noto Sans Regular": "NotoSans-Regular.ttf", "Noto Sans Bold": "NotoSans-Bold.ttf"}

_NOTICE_HEAD = """CheekyMarine charts pack {name} {version}

Data source: NOAA ENC (Electronic Navigational Charts), a US Government work.
This pack is a derived product. It is not an official chart.
It is not certified for navigation. Do not rely on it as the only means of navigation.

ENC cells (edition.update, issue date):
{cells}

"""


def _safety_contour_m(metadata: dict[str, str]) -> float:
    """The smallest charted contour value at or deeper than the safety depth, else the safety depth."""
    safety = Depths().safety_m
    deeper = [float(v) for v in json.loads(metadata["cheekymarine:valdco"]) if float(v) >= safety]
    return min(deeper) if deeper else safety


def _contract_section() -> str:
    readme = (PROJECT / "README.md").read_text()
    m = re.search(r"^## Pack contract\n.*?(?=^## |\Z)", readme, re.M | re.S)
    if m is None:
        raise RuntimeError(f"{PROJECT / 'README.md'} has no 'Pack contract' section")
    return m.group(0).rstrip() + "\n"


def _notice(metadata: dict[str, str], name: str, version: str) -> str:
    cells = "\n".join(
        f"  {s['cell']} {s['edtn']}.{s['updn']} {s['isdt']}" for s in json.loads(metadata["cheekymarine:sources"])
    )
    licences = (PROJECT / "NOTICE").read_text()
    fonts = licences[licences.index("Bundled fonts"):]
    return _NOTICE_HEAD.format(name=name, version=version, cells=cells) + fonts


def _sprites_glyphs_readme(root: Path, sprite_name: str, title: str) -> None:
    build_sprites(PROJECT / "symbols", root / "sprites", sprite_name)
    for fontstack, filename in FONTS.items():
        build_glyphs(PROJECT / "fonts" / filename, fontstack, root / "glyphs")
    (root / "README.md").write_text(f"# {title}\n\n{_contract_section()}")


def assemble_charts_pack(region: Region, enc_mbtiles: Path, out_dir: Path) -> Path:
    root = Path(out_dir) / f"charts-{region.name}-{region.charts_version}"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(enc_mbtiles, root / "enc.mbtiles")
    with MBTiles.open(enc_mbtiles) as m:
        metadata = m.metadata()
    safety_contour = _safety_contour_m(metadata)

    (root / "styles").mkdir(exist_ok=True)
    for palette in PALETTES:
        style = nav_style(palette, safety_contour_m=safety_contour)
        (root / "styles" / f"nav-{palette}.json").write_text(json.dumps(style, indent=2) + "\n")

    _sprites_glyphs_readme(root, "nav", f"charts-{region.name}-{region.charts_version}")
    (root / "NOTICE").write_text(_notice(metadata, region.name, region.charts_version))
    return root


def _bathy_notice(metadata: dict[str, str], name: str, version: str) -> str:
    sources = json.loads(metadata["cheekymarine:sources"])
    tiles = "\n".join(f"  {t['name']} ({t['year']} v{t['version']})" for t in sources["cudem"])
    datum = sources["datum"]
    licences = (PROJECT / "NOTICE").read_text()
    fonts = licences[licences.index("Bundled fonts"):]
    return f"""CheekyMarine bathy pack {name} {version}

This pack is a derived product. It is not an official chart.
It is not certified for navigation. Do not rely on it as the only means of navigation.
Depths are survey depths converted to approximate MLLW.

Bathymetry:
  NOAA NCEI Continuously Updated Digital Elevation Model (CUDEM) 1/9 arc-second tiles,
  DOI 10.25921/ds9v-ky35, a US Government work.
  NOAA NCEI Coastal Relief Model (CRM) volume 8, 2025, a US Government work.
  Request: {sources["crm"]}
  CUDEM tiles used:
{tiles}

Boundaries: NOAA maritime boundaries (the water clip), a US Government work.

Datum: elevations are converted to MLLW with NOAA CO-OPS station {datum["station"]}
  (NAVD88 to MLLW {datum["navd88_to_mllw_m"]} m, MSL to MLLW {datum["msl_to_mllw_m"]} m).

Where neither CUDEM nor CRM covers the water, contours come from NOAA ENC.

""" + fonts + "\nSymbols are drawn in-house after US Chart No. 1 (public domain).\n"


def assemble_bathy_pack(region: Region, bathy_mbtiles: Path, dem_mbtiles: Path, out_dir: Path) -> Path:
    root = Path(out_dir) / f"bathy-{region.name}-{region.bathy_version}"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bathy_mbtiles, root / "bathy.mbtiles")
    shutil.copyfile(dem_mbtiles, root / "dem.mbtiles")
    with MBTiles.open(bathy_mbtiles) as m:
        metadata = m.metadata()

    (root / "styles").mkdir(exist_ok=True)
    for palette in PALETTES:
        (root / "styles" / f"fish-{palette}.json").write_text(json.dumps(fish_style(palette), indent=2) + "\n")

    _sprites_glyphs_readme(root, "fish", f"bathy-{region.name}-{region.bathy_version}")
    (root / "NOTICE").write_text(_bathy_notice(metadata, region.name, region.bathy_version))
    return root
