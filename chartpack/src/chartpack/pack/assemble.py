"""Assemble the charts pack directory: enc.mbtiles, nav styles, sprites, glyphs, legend, README, NOTICE."""

import json
import re
import shutil
from pathlib import Path

from chartpack.mbtiles import MBTiles
from chartpack.region import Region
from chartpack.seabed import cmecs, usseabed
from chartpack.seabed.legend import build_legend
from chartpack.style.fish import fish_style
from chartpack.style.glyphs import build_glyphs
from chartpack.style.nav import Depths, nav_style
from chartpack.style.palette import PALETTES
from chartpack.style.sprites import build_sprites

# symbols/, fonts/ and README.md live beside src/ in the chartpack project (editable install).
PROJECT = Path(__file__).resolve().parents[3]
FONTS = {"Noto Sans Regular": "NotoSans-Regular.ttf", "Noto Sans Bold": "NotoSans-Bold.ttf"}

# Python twin of kBathyFiles in plotter/src/core/PackCatalog.h (same order).
BATHY_FILES = ("bathy.mbtiles", "dem.mbtiles", "bathy-coarse.mbtiles", "dem-coarse.mbtiles")

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


def _fonts_notice(licences: str) -> str:
    """The project NOTICE font block, pointing at the OFL.txt that sits in the pack root."""
    return licences[licences.index("Bundled fonts"):].replace("(fonts/OFL.txt)", "(OFL.txt)")


def _notice(metadata: dict[str, str], name: str, version: str, cmecs_blocks: tuple[str, ...]) -> str:
    cells = "\n".join(
        f"  {s['cell']} {s['edtn']}.{s['updn']} {s['isdt']}" for s in json.loads(metadata["cheekymarine:sources"])
    )
    licences = (PROJECT / "NOTICE").read_text()
    fonts = _fonts_notice(licences)
    srcs = {row["src"] for row in json.loads(metadata["cheekymarine:seabed"])}
    usgs = [text for src, text in (("usseabed", usseabed.NOTICE), ("usgs-cmecs", cmecs.notice(cmecs_blocks))) if src in srcs]
    survey = ("Bottom composition also from the U.S. Geological Survey (public domain; the USGS is the source):\n"
              + "\n".join(usgs) + "\n\n") if usgs else ""
    return _NOTICE_HEAD.format(name=name, version=version, cells=cells) + survey + fonts


def write_styles(root: Path, pack: str, safety_contour_m: float | None = None, night: dict | None = None) -> None:
    """Write every palette's style file of a pack (nav-*.json for charts, fish-*.json for bathy).
    night replaces the night palette's colors (a night_palette variant)."""
    (root / "styles").mkdir(exist_ok=True)
    for palette in PALETTES:
        colors = night if palette == "night" else None
        if pack == "charts":
            style, name = nav_style(palette, safety_contour_m=safety_contour_m, colors=colors), f"nav-{palette}.json"
        else:
            style, name = fish_style(palette, colors=colors), f"fish-{palette}.json"
        (root / "styles" / name).write_text(json.dumps(style, indent=2) + "\n")


def _sprites_glyphs_readme(root: Path, sprite_name: str, title: str) -> None:
    build_sprites(PROJECT / "symbols", root / "sprites", sprite_name)
    for fontstack, filename in FONTS.items():
        build_glyphs(PROJECT / "fonts" / filename, fontstack, root / "glyphs")
    shutil.copyfile(PROJECT / "fonts" / "OFL.txt", root / "OFL.txt")
    (root / "README.md").write_text(f"# {title}\n\n{_contract_section()}")


def assemble_charts_pack(region: Region, enc_mbtiles: Path, out_dir: Path) -> Path:
    root = Path(out_dir) / f"charts-{region.name}-{region.charts_version}"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(enc_mbtiles, root / "enc.mbtiles")
    with MBTiles.open(enc_mbtiles) as m:
        metadata = m.metadata()
    safety_contour = _safety_contour_m(metadata)

    write_styles(root, "charts", safety_contour)

    _sprites_glyphs_readme(root, "nav", f"charts-{region.name}-{region.charts_version}")
    legend = build_legend(json.loads(metadata["cheekymarine:seabed"]))
    (root / "legend.json").write_text(json.dumps(legend, indent=2) + "\n")
    (root / "NOTICE").write_text(_notice(metadata, region.name, region.charts_version, region.cmecs_blocks))
    return root


def _bathy_notice(metadata: dict[str, str], name: str, version: str) -> str:
    sources = json.loads(metadata["cheekymarine:sources"])
    tiles = "\n".join(f"  {t['name']} ({t['year']} v{t['version']})" for t in sources["cudem"])
    datum = sources["datum"]
    licences = (PROJECT / "NOTICE").read_text()
    fonts = _fonts_notice(licences)
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

Datum: elevations are converted to MLLW with offsets interpolated between NOAA CO-OPS tide
  stations (a US Government work), listed in {datum["file"]} (sha256 {datum["sha256"]}).
  CRM heights (EGM2008) go through NAVD88 with the NGA EGM2008 and NOAA GEOID18 geoid grids
  (public domain, from cdn.proj.org) and PROJ.

Where neither CUDEM nor CRM covers the water, contours come from NOAA ENC.

""" + fonts + "\nSymbols are drawn in-house after US Chart No. 1 (public domain).\n"


def assemble_bathy_pack(region: Region, files: dict[str, Path], out_dir: Path) -> Path:
    """The bathy pack directory from the four built files, keyed by their BATHY_FILES names."""
    root = Path(out_dir) / f"bathy-{region.name}-{region.bathy_version}"
    root.mkdir(parents=True, exist_ok=True)
    for name in BATHY_FILES:
        shutil.copyfile(files[name], root / name)
    with MBTiles.open(root / "bathy.mbtiles") as m:
        metadata = m.metadata()

    write_styles(root, "bathy")

    _sprites_glyphs_readme(root, "fish", f"bathy-{region.name}-{region.bathy_version}")
    (root / "NOTICE").write_text(_bathy_notice(metadata, region.name, region.bathy_version))
    return root
