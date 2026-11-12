"""Assemble the charts pack directory: enc.mbtiles, nav styles, sprites, glyphs, legend, README, NOTICE."""

import json
import re
import shutil
from importlib import resources
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape

from chartpack.grid import canada_side, tiles_area
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

# The CHS NONNA Licence notice (plan 8 spec 11), kept once in notices/chs.txt (package data).
CHS_NOTICE = resources.files("chartpack").joinpath("notices", "chs.txt").read_text(encoding="utf-8").rstrip()
# The Open Government Licence - British Columbia attribution (the Freshwater Atlas shoreline), notices/ogl-bc.txt.
OGL_BC_NOTICE = resources.files("chartpack").joinpath("notices", "ogl-bc.txt").read_text(encoding="utf-8").rstrip()
_NONNA = frozenset({"nonna10", "nonna100"})
_DATUM_SENTENCE = ("Canadian depths are on Canadian chart datum and US depths on MLLW; the two differ slightly at the"
                   " border.")

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
    return _NOTICE_HEAD.format(name=name, version=version, cells=cells) + _derived_notice(metadata) + survey + fonts


def _derived_notice(metadata: dict[str, str]) -> str:
    """The NOTICE block of a charts pack's derived inputs (cheekymarine:depth_sources, plan 8 spec 11): the NONNA
    assets with the datum sentence and the CHS notice, the shoreline with its credit; empty for a pack with none."""
    depth = {d["source"]: d for d in json.loads(metadata.get("cheekymarine:depth_sources", "[]"))}
    nonna = "".join(
        f"  CHS {label} bathymetry, Canadian Hydrographic Service, Fisheries and Oceans Canada,\n"
        "  under the CHS NONNA Licence and the Open Government Licence, Canada (the CHS notice below).\n"
        f"  Asset: {depth[product]['asset']} (sha256 {depth[product]['sha256']})\n"
        for product, label in (("nonna10", "NONNA-10"), ("nonna100", "NONNA-100")) if product in depth)
    shore = "" if "fwa" not in depth else (
        "  Land and shoreline from the BC Freshwater Atlas coastline, Province of British Columbia.\n"
        f"  Asset: {depth['fwa']['asset']} (sha256 {depth['fwa']['sha256']})\n{OGL_BC_NOTICE}\n")
    if not (nonna or shore):
        return ""
    chs = f"{_DATUM_SENTENCE}\n\n{CHS_NOTICE}\n\n" if nonna else ""
    return ("Inside the Canada polygon no NOAA chart content is shown; depth and shoreline there are derived:\n"
            f"{nonna}{shore}\n{chs}")


def charts_notice_areas(content: set[tuple[int, int]] | None, canada: shapely.Geometry | None) -> dict:
    """cheekymarine:notice_areas of a charts pack (plan 8 spec 7.3): its owned tiles (for the overview, every owned
    tile of the grid) cut to the Canada polygon, land included, as one feature of kind bc, not simplified, so a
    narrow channel is never lost. No feature when they do not meet it."""
    area = _polygons(tiles_area(content).intersection(canada)) if content and canada is not None else shapely.Polygon()
    features = [] if area.is_empty else [{"type": "Feature", "properties": {"kind": "bc"}, "geometry": mapping(area)}]
    return {"type": "FeatureCollection", "features": features}


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


def assemble_charts_pack(region: Region, enc_mbtiles: Path, out_dir: Path,
                         content: set[tuple[int, int]] | None = None, canada: shapely.Geometry | None = None) -> Path:
    """The charts pack directory. enc.mbtiles gets cheekymarine:notice_areas (charts_notice_areas of content, the
    pack's owned tiles or the overview's content tiles, and canada) and, when its depth_sources hold NONNA,
    cheekymarine:data_notice (the CHS notice)."""
    root = Path(out_dir) / f"charts-{region.name}-{region.charts_version}"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(enc_mbtiles, root / "enc.mbtiles")
    with MBTiles.open(enc_mbtiles) as m:
        metadata = m.metadata()
    notice = {"cheekymarine:notice_areas": json.dumps(charts_notice_areas(content, canada))}
    if _NONNA & {d["source"] for d in json.loads(metadata.get("cheekymarine:depth_sources", "[]"))}:
        notice["cheekymarine:data_notice"] = CHS_NOTICE
    with MBTiles.open(root / "enc.mbtiles") as m:
        m.set_metadata(notice)
    safety_contour = _safety_contour_m(metadata)

    write_styles(root, "charts", safety_contour)

    _sprites_glyphs_readme(root, "nav", f"charts-{region.name}-{region.charts_version}")
    legend = build_legend(json.loads(metadata["cheekymarine:seabed"]))
    (root / "legend.json").write_text(json.dumps(legend, indent=2) + "\n")
    (root / "NOTICE").write_text(_notice(metadata, region.name, region.charts_version, region.cmecs_blocks))
    return root


def _etopo_citation(licences: str) -> str:
    """The ETOPO 2022 citation and its fixed shift line from the project NOTICE, indented as a Bathymetry entry."""
    m = re.search(r"^ETOPO 2022 15 Arc-Second.*?no tide station data is used\.$", licences, re.M | re.S)
    if m is None:
        raise RuntimeError(f"{PROJECT / 'NOTICE'} has no ETOPO 2022 citation")
    return "".join(f"  {line}\n" for line in m.group(0).replace(" (bathy/etopo.py)", "").splitlines())


def _bathy_notice(metadata: dict[str, str], name: str, version: str, chs: bool = False,
                  coverage: frozenset[str] = frozenset()) -> str:
    """The bathy pack NOTICE; chs adds the datum sentence and the CHS notice (the pack holds NONNA depth).
    coverage (the sources the coverage layers hold) adds the NONNA assets and the ETOPO citation the pack draws."""
    sources = json.loads(metadata["cheekymarine:sources"])
    licences = (PROJECT / "NOTICE").read_text()
    nonna = "".join(
        f"  CHS {label} bathymetry, Canadian Hydrographic Service, Fisheries and Oceans Canada,\n"
        "  under the CHS NONNA Licence and the Open Government Licence, Canada (the CHS notice below).\n"
        f"  Asset: {sources[product]['name']} (sha256 {sources[product]['sha256']})\n"
        for product, label in (("nonna10", "NONNA-10"), ("nonna100", "NONNA-100"))
        if product in coverage and product in sources)
    etopo = "" if "etopo" not in coverage else _etopo_citation(licences) + "".join(
        f"  ETOPO tile used: {tile['name']} ({tile['file']})\n" for tile in sources.get("etopo", []))
    cudem = "" if "cudem" not in sources else (
        "  NOAA NCEI Continuously Updated Digital Elevation Model (CUDEM) 1/9 arc-second tiles,\n"
        "  DOI 10.25921/ds9v-ky35, a US Government work.\n  CUDEM tiles used:\n"
        + "".join(f"  {t['name']} ({t['year']} v{t['version']})\n" for t in sources["cudem"]))
    crm = "" if "crm" not in sources else (
        "  NOAA NCEI Coastal Relief Model (CRM) volume 8, 2025, a US Government work.\n"
        f"  Request: {sources['crm']}\n")
    geoid = "" if "crm" not in sources else (
        "  CRM heights (EGM2008) go through NAVD88 with the NGA EGM2008 and NOAA GEOID18 geoid grids\n"
        "  (public domain, from cdn.proj.org) and PROJ.\n")
    # ENC contours fill only water a CUDEM region's sources leave uncovered (a CRM-only build draws none).
    fallback = "" if "cudem" not in sources else "\n{} the water, contours come from NOAA ENC.\n".format(
        "Where neither CUDEM nor CRM covers" if "crm" in sources else "Where CUDEM does not cover")
    datum = sources["datum"]
    lakes = "" if "lakes_file" not in datum else (
        "  In Lake Union and Lake Washington depths are below the lakes' managed low level\n"
        "  (US Army Corps of Engineers, a US Government work), inside polygons from NOAA ENC\n"
        "  (a US Government work) in "
        f"{datum['lakes_file']} (sha256 {datum['lakes_sha256']}).\n")
    fonts = _fonts_notice(licences)
    chs_text = f"{_DATUM_SENTENCE}\n\n{CHS_NOTICE}\n\n" if chs else ""
    return f"""CheekyMarine bathy pack {name} {version}

This pack is a derived product. It is not an official chart.
It is not certified for navigation. Do not rely on it as the only means of navigation.
Depths are survey depths converted to approximate MLLW.

Bathymetry:
{cudem}{crm}{nonna}{etopo}
Boundaries: NOAA maritime boundaries (the water clip), a US Government work.

Datum: elevations are converted to MLLW with offsets interpolated between NOAA CO-OPS tide
  stations (a US Government work), listed in {datum["file"]} (sha256 {datum["sha256"]}).
{lakes}{geoid}{fallback}
""" + chs_text + fonts + "\nSymbols are drawn in-house after US Chart No. 1 (public domain).\n"


def _polygons(geom: shapely.Geometry) -> shapely.Geometry:
    """The polygonal part of a union (a tile only touching the clip adds an edge, not area)."""
    parts = [g for g in shapely.get_parts(geom) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def notice_areas(region: Region, owned: set[tuple[int, int]] | None) -> dict:
    """cheekymarine:notice_areas of a bathy pack (plan 8 spec 7.3): the Canadian column (spec 6) of its owned tiles,
    canada_side by the pack itself, as one feature of kind bc, not simplified. No feature when there is none: a US
    pack with no clip or with every tile on the US side, and the overview (owned None), which is clipped to US
    water."""
    parts = []
    if owned and (region.charts_kind != "enc" or region.clip is not None):
        clip = None
        if region.charts_kind == "enc":
            data = json.loads(region.clip.read_text())
            clip = shape(data.get("geometry", data))
        parts = [canada_side(clip, tile, region) for tile in sorted(owned)]
    area = _polygons(shapely.union_all(parts)) if parts else shapely.Polygon()
    features = [] if area.is_empty else [{"type": "Feature", "properties": {"kind": "bc"}, "geometry": mapping(area)}]
    return {"type": "FeatureCollection", "features": features}


def assemble_bathy_pack(region: Region, files: dict[str, Path], out_dir: Path,
                        owned: set[tuple[int, int]] | None = None) -> Path:
    """The bathy pack directory from the four built files, keyed by their BATHY_FILES names, each given the
    notice metadata: cheekymarine:notice_areas (notice_areas over the owned tiles) and, when a coverage layer holds
    NONNA, cheekymarine:data_notice (the CHS notice)."""
    root = Path(out_dir) / f"bathy-{region.name}-{region.bathy_version}"
    root.mkdir(parents=True, exist_ok=True)
    for name in BATHY_FILES:
        shutil.copyfile(files[name], root / name)
    with MBTiles.open(root / "bathy.mbtiles") as m:
        metadata = m.metadata()
    with MBTiles.open(root / "bathy-coarse.mbtiles") as m:
        coverage = json.loads(metadata.get("cheekymarine:coverage", "[]"))
        coverage += json.loads(m.metadata().get("cheekymarine:coverage", "[]"))
    chs = bool(_NONNA & set(coverage))
    notice = {"cheekymarine:notice_areas": json.dumps(notice_areas(region, owned))}
    if chs:
        notice["cheekymarine:data_notice"] = CHS_NOTICE
    for name in BATHY_FILES:
        with MBTiles.open(root / name) as m:
            m.set_metadata(notice)

    write_styles(root, "bathy")

    _sprites_glyphs_readme(root, "fish", f"bathy-{region.name}-{region.bathy_version}")
    (root / "NOTICE").write_text(_bathy_notice(metadata, region.name, region.bathy_version, chs, frozenset(coverage)))
    return root
