"""Assemble the charts pack directory: enc.mbtiles, nav styles, sprites, glyphs, README, NOTICE."""

import json
import re
import shutil
from pathlib import Path

from chartpack.mbtiles import MBTiles
from chartpack.region import Region
from chartpack.style.glyphs import build_glyphs
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

    build_sprites(PROJECT / "symbols", root / "sprites", "nav")
    for fontstack, filename in FONTS.items():
        build_glyphs(PROJECT / "fonts" / filename, fontstack, root / "glyphs")

    (root / "README.md").write_text(f"# charts-{region.name}-{region.charts_version}\n\n{_contract_section()}")
    (root / "NOTICE").write_text(_notice(metadata, region.name, region.charts_version))
    return root
