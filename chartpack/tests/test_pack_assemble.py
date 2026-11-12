import dataclasses
import json

import pytest
import shapely

from chartpack.mbtiles import MBTiles
from chartpack.pack.assemble import PROJECT, assemble_charts_pack
from chartpack.style.validate import check_style_sprites_glyphs


def test_charts_pack_layout(test_region, enc_pack_path, tmp_path):
    root = assemble_charts_pack(test_region, enc_pack_path, tmp_path)
    assert root == tmp_path / "charts-test-cell-0.1.0"
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert "enc.mbtiles" in names and "styles/nav-night.json" in names and "sprites/nav@2x.json" in names
    assert "styles/nav-day.json" in names and "styles/nav-dusk.json" in names and "sprites/nav.png" in names
    assert "glyphs/Noto Sans Regular/0-255.pbf" in names and "glyphs/Noto Sans Bold/256-511.pbf" in names
    assert "README.md" in names and "NOTICE" in names and "legend.json" in names
    assert "OFL.txt" in names


def test_legend_from_enc_metadata(charts_pack_root):
    from chartpack.seabed.legend import build_legend

    with MBTiles.open(charts_pack_root / "enc.mbtiles") as m:
        features = json.loads(m.metadata()["cheekymarine:seabed"])
    assert json.loads((charts_pack_root / "legend.json").read_text()) == build_legend(features)


def test_shipped_style_matches_sprite_and_glyphs(charts_pack_root):
    fonts = {p.name for p in (charts_pack_root / "glyphs").iterdir()}
    sprite = json.loads((charts_pack_root / "sprites" / "nav.json").read_text())
    styles = sorted((charts_pack_root / "styles").glob("*.json"))
    assert len(styles) == 3
    for path in styles:
        assert check_style_sprites_glyphs(json.loads(path.read_text()), sprite, fonts) == []


def test_safety_contour_is_a_charted_value(charts_pack_root):
    for path in (charts_pack_root / "styles").glob("*.json"):
        value = json.loads(path.read_text())["metadata"]["cheekymarine"]["safety_contour_m"]
        assert isinstance(value, float) and value >= 3.048


def test_notice_and_readme(charts_pack_root):
    notice = (charts_pack_root / "NOTICE").read_text()
    assert "NOAA ENC" in notice and "not certified for navigation" in notice and "US4WA1HK" in notice
    assert "SIL Open Font License" in notice and "(OFL.txt)" in notice
    assert (charts_pack_root / "OFL.txt").read_text() == (PROJECT / "fonts" / "OFL.txt").read_text()
    assert "Pack contract" in (charts_pack_root / "README.md").read_text()
    # the USGS releases ask to be recognized as the source in derived products
    assert "U.S. Geological Survey" in notice and "doi:10.3133/ds182" in notice


def test_notice_credits_only_the_cmecs_blocks_present(test_region, enc_pack_path, tmp_path):
    region = dataclasses.replace(test_region, cmecs_blocks=("seattle",))
    notice = (assemble_charts_pack(region, enc_pack_path, tmp_path / "out") / "NOTICE").read_text()
    assert "doi:10.5066/P9GVRZ3M" in notice
    assert "P9KA6GH2" not in notice and "P96T1B44" not in notice and "ofr20151073" not in notice


def test_notice_without_usgs_seabed(test_region, enc_pack_path, tmp_path):
    from chartpack.mbtiles import MBTiles
    from chartpack.pack.assemble import assemble_charts_pack

    enc = tmp_path / "enc.mbtiles"
    enc.write_bytes(enc_pack_path.read_bytes())
    with MBTiles.open(enc) as m:
        rows = [r for r in json.loads(m.metadata()["cheekymarine:seabed"]) if r["src"] == "enc"]
        m.set_metadata({"cheekymarine:seabed": json.dumps(rows)})
    notice = (assemble_charts_pack(test_region, enc, tmp_path / "out") / "NOTICE").read_text()
    assert "NOAA ENC" in notice and "Geological Survey" not in notice


def test_bathy_pack_layout(test_region, tmp_path):
    import numpy as np

    import shutil

    from chartpack.bathy.dem import build_dem_mbtiles
    from chartpack.pack.assemble import BATHY_FILES, assemble_bathy_pack

    with MBTiles.create(tmp_path / "bathy.mbtiles", fmt="pbf") as m:
        m.set_metadata({"cheekymarine:sources": json.dumps({
            "cudem": [{"name": "t1", "url": "u", "year": 2023, "version": 1}], "crm": "https://crm.test",
            "datum": {"file": "wa-stations.toml", "sha256": "ab12", "lakes_file": "lakes.geojson",
                      "lakes_sha256": "cd34"}})})
    shutil.copy(tmp_path / "bathy.mbtiles", tmp_path / "bathy-coarse.mbtiles")
    for name in ("dem.mbtiles", "dem-coarse.mbtiles"):
        build_dem_mbtiles(np.full((40, 40), 20.0, np.float32), (-122.3, 0.001, 0, 47.9, 0, -0.001), tmp_path / name,
                          maxzoom=11)
    files = {name: tmp_path / name for name in BATHY_FILES}
    root = assemble_bathy_pack(test_region, files, tmp_path / "out")
    assert root == tmp_path / "out" / "bathy-test-cell-0.1.0"
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    for name in BATHY_FILES:  # the built files, plus the notice metadata
        with MBTiles.open(root / name) as copy, MBTiles.open(files[name]) as built:
            assert list(copy.tiles_at(11)) == list(built.tiles_at(11))
            md = copy.metadata()
            assert md.pop("cheekymarine:notice_areas") and md == built.metadata()
    for want in ("bathy.mbtiles", "dem.mbtiles", "styles/fish-day.json", "styles/fish-dusk.json", "styles/fish-night.json",
                 "sprites/fish.json", "sprites/fish.png", "sprites/fish@2x.json", "sprites/fish@2x.png",
                 "glyphs/Noto Sans Bold/0-255.pbf", "README.md", "NOTICE", "OFL.txt"):
        assert want in names
    assert not any(n.startswith("styles/nav") for n in names)
    fonts = {p.name for p in (root / "glyphs").iterdir()}
    sprite = json.loads((root / "sprites" / "fish.json").read_text())
    for palette in ("day", "dusk", "night"):
        style = json.loads((root / "styles" / f"fish-{palette}.json").read_text())
        assert check_style_sprites_glyphs(style, sprite, fonts) == []
    notice = (root / "NOTICE").read_text()
    assert "10.25921/ds9v-ky35" in notice and "Coastal Relief Model" in notice and "SIL Open Font License" in notice
    assert "lakes.geojson (sha256 cd34)" in notice and "US Army Corps of Engineers" in notice
    assert "wa-stations.toml (sha256 ab12)" in notice and "GEOID18" in notice and "approximate MLLW" in notice
    assert "Pack contract" in (root / "README.md").read_text()


# Plan 8 spec 11, verbatim (the maker filled in as the CheekyMarine project).
CHS_PARAGRAPHS = (
    "This product was made by the CheekyMarine project and contains intellectual property of the Canadian Hydrographic"
    " Service (CHS) of the Department of Fisheries and Oceans.",
    "This product does not meet the requirements of the Navigation Safety Regulations, 2020 under the Canada Shipping"
    " Act, 2001. Charts and publications issued by or on the authority of CHS must be used to meet the requirements of"
    " those regulations.",
    "The copyright in the data are and remain the property of His Majesty the King in Right of Canada and shall not be"
    " sold, licensed, leased, assigned or given to a third party.",
    "The incorporation of CHS data in this product does not constitute an endorsement or an approval of this product by"
    " the Canadian Hydrographic Service, the Department of Fisheries and Oceans or His Majesty the King in Right of"
    " Canada.",
)
OGL_CANADA = ("Contains information licensed under the Open Government Licence – Canada.\n"
              "https://open.canada.ca/en/open-government-licence-canada")
DATUM_SENTENCE = ("Canadian depths are on Canadian chart datum and US depths on MLLW; the two differ slightly at the"
                  " border.")


def _bathy_files(tmp_path, coverage: dict[str, list[str] | None]) -> dict:
    """The four bathy files with test metadata; coverage gives each vector file's cheekymarine:coverage list
    (None: no key, as in a wave 1 file)."""
    import numpy as np

    from chartpack.bathy.dem import build_dem_mbtiles
    from chartpack.pack.assemble import BATHY_FILES

    tmp_path.mkdir(parents=True, exist_ok=True)
    for name in ("bathy.mbtiles", "bathy-coarse.mbtiles"):
        with MBTiles.create(tmp_path / name, fmt="pbf") as m:
            m.set_metadata({"cheekymarine:sources": json.dumps({
                "crm": "https://crm.test", "datum": {"file": "wa-stations.toml", "sha256": "ab12"}})})
            if coverage.get(name) is not None:
                m.set_metadata({"cheekymarine:coverage": json.dumps(coverage[name])})
    for name in ("dem.mbtiles", "dem-coarse.mbtiles"):
        build_dem_mbtiles(np.full((40, 40), 20.0, np.float32), (-122.3, 0.001, 0, 47.9, 0, -0.001), tmp_path / name,
                          maxzoom=11)
    return {name: tmp_path / name for name in BATHY_FILES}


def test_chs_notice_is_the_packaged_text():
    """CHS_NOTICE is notices/chs.txt read through the package (one copy of the text), and the file ships in a
    non-editable install (package data)."""
    import tomllib
    from importlib import resources

    from chartpack.pack.assemble import CHS_NOTICE

    assert CHS_NOTICE == resources.files("chartpack").joinpath("notices", "chs.txt").read_text(encoding="utf-8").rstrip()
    assert CHS_NOTICE == "\n\n".join(CHS_PARAGRAPHS) + "\n\n" + OGL_CANADA
    data = tomllib.loads((PROJECT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
    assert "notices/*.txt" in data["chartpack"]


@pytest.mark.parametrize("coverage, chs", [
    ({"bathy.mbtiles": ["nonna10"], "bathy-coarse.mbtiles": ["crm", "etopo"]}, True),
    ({"bathy.mbtiles": [], "bathy-coarse.mbtiles": ["nonna100"]}, True),
    ({"bathy.mbtiles": ["cudem"], "bathy-coarse.mbtiles": ["crm", "etopo"]}, False),
    ({}, False),  # wave 1 files: no coverage list
])
def test_bathy_notice_has_chs_text_only_with_nonna(test_region, tmp_path, coverage, chs):
    from chartpack.pack.assemble import BATHY_FILES, CHS_NOTICE, assemble_bathy_pack

    root = assemble_bathy_pack(test_region, _bathy_files(tmp_path / "in", coverage), tmp_path / "out")
    notice = (root / "NOTICE").read_text()
    for text in CHS_PARAGRAPHS + (OGL_CANADA, DATUM_SENTENCE):
        assert (text in notice) is chs, text
    assert ("Canadian Hydrographic" in notice) is chs
    assert "British Columbia" not in notice  # the shoreline credit is for charts packs only
    assert "approximate MLLW" in notice and "SIL Open Font License" in notice
    for name in BATHY_FILES:
        with MBTiles.open(root / name) as m:
            etopo = "etopo" in {c for v in coverage.values() for c in (v or [])}
            expected = "\n\n".join(([CHS_NOTICE] if chs else []) + ([ETOPO_PARAGRAPH] if etopo else []))
            assert m.metadata().get("cheekymarine:data_notice") == (expected or None), name


def _tiles_union(tiles):
    from shapely.geometry import box
    from shapely.ops import unary_union

    from chartpack.grid import GRID_ZOOM, tile_bounds

    return unary_union([box(*tile_bounds(GRID_ZOOM, *t)) for t in tiles])


def test_notice_areas_metadata_is_geojson(test_region, tmp_path):
    """cheekymarine:notice_areas on all four bathy files: a FeatureCollection of kind bc, the Canadian column of the
    pack's owned tiles (whole tiles for a BC pack, the clip side for a US pack), not simplified; empty when the
    pack has none (a US pack with no clip, or tiles wholly on the US side, or no owned tiles)."""
    import dataclasses

    from shapely.geometry import shape

    from chartpack.pack.assemble import BATHY_FILES, assemble_bathy_pack

    tiles = {(163, 356), (164, 356)}  # two neighbors at Possession Bar
    w, s, e, n = _tiles_union(tiles).bounds
    # a clip with a notch, cutting the west tile only: the cut keeps every vertex
    notch = [(w - 1, (s + n) / 2), ((w + e) / 2 - 0.01, (s + n) / 2), ((w + e) / 2 - 0.02, n - 0.01),
             ((w + e) / 2 - 0.03, (s + n) / 2 + 1e-4), ((w + e) / 2 - 0.03, n + 1), (w - 1, n + 1)]
    clip_path = tmp_path / "clip.geojson"
    clip = {"type": "Polygon", "coordinates": [[*notch, notch[0]]]}
    clip_path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": clip}))
    cases = [
        (dataclasses.replace(test_region, charts_kind="derived-inshore"), tiles, _tiles_union(tiles)),
        (dataclasses.replace(test_region, clip=clip_path), tiles, _tiles_union(tiles).intersection(shape(clip))),
        (test_region, tiles, None),  # a US pack with no clip
        (dataclasses.replace(test_region, clip=clip_path), {(164, 357)}, None),  # wholly on the US side
        (dataclasses.replace(test_region, charts_kind="derived-inshore"), None, None),  # no owned tiles given
    ]
    for i, (region, owned, want) in enumerate(cases):
        root = assemble_bathy_pack(region, _bathy_files(tmp_path / f"in{i}", {}), tmp_path / f"out{i}", owned=owned)
        for name in BATHY_FILES:
            with MBTiles.open(root / name) as m:
                areas = json.loads(m.metadata()["cheekymarine:notice_areas"])
            assert areas["type"] == "FeatureCollection", (i, name)
            if want is None:
                assert areas["features"] == [], (i, name)
                continue
            [feature] = areas["features"]
            assert feature["type"] == "Feature" and feature["properties"] == {"kind": "bc"}
            got = shape(feature["geometry"])
            assert got.is_valid and got.symmetric_difference(want).area < 1e-12, (i, name)
            assert shapely.get_num_coordinates(got) == shapely.get_num_coordinates(want)  # not simplified


# PR #122 review F1: the pack NOTICE and source metadata name every depth source the pack holds.

def _sourced_files(tmp_path, sources: dict, coverage: list[str]) -> dict:
    """The four bathy files with the given cheekymarine:sources (the datum added) and the coverage list on both
    vector files."""
    files = _bathy_files(tmp_path, {"bathy.mbtiles": coverage, "bathy-coarse.mbtiles": coverage})
    for name in ("bathy.mbtiles", "bathy-coarse.mbtiles"):
        with MBTiles.open(files[name]) as m:
            m.set_metadata({"cheekymarine:pack": "bathy", "cheekymarine:sources": json.dumps(
                {**sources, "datum": {"file": "wa-stations.toml", "sha256": "ab12"}})})
    return files


NONNA_SOURCES = {"nonna10": {"name": "nonna10-toba.tif", "sha256": "aa11"},
                 "nonna100": {"name": "nonna100-toba.tif", "sha256": "bb22"}}
ETOPO_SOURCES = {"etopo": [{"name": "N60W135", "file": "ETOPO_2022_v1_15s_N60W135_surface.tif"}]}
ETOPO_PARAGRAPH = (
    "ETOPO 2022 15 Arc-Second Global Relief Model: NOAA National Centers for Environmental\n"
    "Information. 2022: ETOPO 2022 15 Arc-Second Global Relief Model. NOAA National Centers for Environmental\n"
    "Information. https://doi.org/10.25921/fd45-gt74. CC0 1.0 public domain dedication.\n"
    "ETOPO depths are shifted by a fixed 4 m toward chart datum; no tide station data is used.")
ETOPO_LINE = "ETOPO depths are shifted by a fixed 4 m toward chart datum; no tide station data is used."


def test_bathy_notice_names_nonna(test_region, tmp_path):
    from chartpack.pack.assemble import assemble_bathy_pack

    root = assemble_bathy_pack(test_region, _sourced_files(tmp_path / "in", NONNA_SOURCES, ["nonna10", "nonna100"]),
                               tmp_path / "out")
    notice = (root / "NOTICE").read_text()
    bathy = notice[notice.index("Bathymetry:"):notice.index("Boundaries:")]
    assert "NONNA-10" in bathy and "nonna10-toba.tif (sha256 aa11)" in bathy
    assert "NONNA-100" in bathy and "nonna100-toba.tif (sha256 bb22)" in bathy
    assert "CHS NONNA Licence" in bathy and "Open Government Licence" in bathy
    assert "ETOPO" not in notice and "Coastal Relief Model" not in notice
    from chartpack.pack.manifest import describe_pack

    _, sources, _ = describe_pack(root)
    assert {"source": "nonna10", "name": "nonna10-toba.tif", "sha256": "aa11"} in sources
    assert {"source": "nonna100", "name": "nonna100-toba.tif", "sha256": "bb22"} in sources


def test_bathy_notice_names_etopo(test_region, tmp_path):
    from chartpack.pack.assemble import assemble_bathy_pack

    root = assemble_bathy_pack(test_region, _sourced_files(tmp_path / "in", ETOPO_SOURCES, ["etopo"]), tmp_path / "out")
    notice = (root / "NOTICE").read_text()
    bathy = notice[notice.index("Bathymetry:"):notice.index("Boundaries:")]
    assert "ETOPO 2022 15 Arc-Second Global Relief Model" in bathy and "https://doi.org/10.25921/fd45-gt74" in bathy
    assert "CC0 1.0" in bathy and ETOPO_LINE in bathy and "N60W135" in bathy
    assert "bathy/etopo.py" not in notice and "NONNA" not in notice
    from chartpack.pack.manifest import describe_pack

    _, sources, _ = describe_pack(root)
    assert {"source": "etopo", "name": "N60W135", "file": "ETOPO_2022_v1_15s_N60W135_surface.tif"} in sources


def test_bathy_notice_etopo_listed_but_not_drawn(test_region, tmp_path):
    """A region that lists ETOPO whose coverage holds none (CRM filled the water): no ETOPO credit."""
    from chartpack.pack.assemble import assemble_bathy_pack

    files = _sourced_files(tmp_path / "in", {"crm": "https://crm.test", **ETOPO_SOURCES}, ["crm"])
    notice = (assemble_bathy_pack(test_region, files, tmp_path / "out") / "NOTICE").read_text()
    assert "ETOPO" not in notice and "Coastal Relief Model" in notice


def test_bathy_notice_wave1_unchanged(test_region, tmp_path):
    """A wave 1 style pack (CUDEM and CRM, no coverage list): the Bathymetry block is the plan 7 text."""
    from chartpack.pack.assemble import assemble_bathy_pack

    cudem = [{"name": "t1", "url": "u", "year": 2023, "version": 1}]
    files = _sourced_files(tmp_path / "in", {"cudem": cudem, "crm": "https://crm.test"}, ["cudem", "crm"])
    notice = (assemble_bathy_pack(test_region, files, tmp_path / "out") / "NOTICE").read_text()
    assert ("Bathymetry:\n"
            "  NOAA NCEI Continuously Updated Digital Elevation Model (CUDEM) 1/9 arc-second tiles,\n"
            "  DOI 10.25921/ds9v-ky35, a US Government work.\n  CUDEM tiles used:\n  t1 (2023 v1)\n"
            "  NOAA NCEI Coastal Relief Model (CRM) volume 8, 2025, a US Government work.\n"
            "  Request: https://crm.test\n\nBoundaries:") in notice
    assert "NONNA" not in notice and "ETOPO" not in notice


# ---- plan 8 Task 11: the charts pack's BC notice metadata and NOTICE (spec 7.3, 11)

def _with_depth_sources(enc_pack_path, tmp_path, sources):
    """A copy of the session enc.mbtiles whose cheekymarine:depth_sources is sources."""
    import shutil

    path = tmp_path / "enc.mbtiles"
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(enc_pack_path, path)
    with MBTiles.open(path) as m:
        m.set_metadata({"cheekymarine:depth_sources": json.dumps(sources)})
    return path


DEPTH_SOURCES = [{"source": "nonna100", "asset": "nonna100-toba.tif", "sha256": "a" * 64},
                 {"source": "fwa", "asset": "land-toba.geojson.gz", "sha256": "b" * 64},
                 {"source": "nosurvey", "asset": "nosurvey-toba.geojson.gz", "sha256": "c" * 64}]


def test_notice_areas_are_owned_tiles_inside_polygon(test_region, enc_pack_path, tmp_path):
    """One feature of kind bc: the owned tiles cut to the Canada polygon, land included, not simplified; the
    Alaskan water of a BC-owned tile (outside the polygon) is not in it. A pack whose tiles miss it: no key."""
    from shapely.geometry import box, shape

    from chartpack.grid import tile_bounds

    tiles = {(163, 356), (164, 356)}
    w, s, e, n = tile_bounds(10, 163, 356)
    canada = box(w + 0.1, s - 1, e + 1, n + 1).union(box(w + 0.01, s + 0.1, w + 0.0101, s + 0.2))  # a 7 m channel
    region = dataclasses.replace(test_region, charts_kind="derived-inshore")
    root = assemble_charts_pack(region, enc_pack_path, tmp_path / "a", content=tiles, canada=canada)
    with MBTiles.open(root / "enc.mbtiles") as m:
        areas = json.loads(m.metadata()["cheekymarine:notice_areas"])["features"]
    assert [f["properties"] for f in areas] == [{"kind": "bc"}]
    got = shape(areas[0]["geometry"])
    owned = box(w, s, *tile_bounds(10, 164, 356)[2:])
    assert got.symmetric_difference(owned.intersection(canada)).area < 1e-14
    assert not got.intersects(box(w, s, w + 0.009, n))  # Alaskan water of the tile
    assert got.intersects(box(w + 0.0100001, s + 0.15, w + 0.01009, s + 0.15001))  # the channel is kept
    far = assemble_charts_pack(region, enc_pack_path, tmp_path / "b", content=tiles, canada=box(0, 0, 1, 1))
    with MBTiles.open(far / "enc.mbtiles") as m:  # no area: the key is not written, the old keys stay as they were
        assert "cheekymarine:notice_areas" not in m.metadata()


def test_charts_notice_has_chs_and_bc_credit(test_region, enc_pack_path, tmp_path):
    from chartpack.pack.assemble import CHS_NOTICE, OGL_BC_NOTICE

    root = assemble_charts_pack(test_region, _with_depth_sources(enc_pack_path, tmp_path, DEPTH_SOURCES),
                                tmp_path / "bc")
    notice = (root / "NOTICE").read_text()
    assert CHS_NOTICE in notice and OGL_BC_NOTICE in notice
    assert f"nonna100-toba.tif (sha256 {'a' * 64})" in notice and f"land-toba.geojson.gz (sha256 {'b' * 64})" in notice
    with MBTiles.open(root / "enc.mbtiles") as m:
        assert m.metadata()["cheekymarine:data_notice"] == f"{CHS_NOTICE}\n\n{OGL_BC_NOTICE}"
    land_only = assemble_charts_pack(
        test_region, _with_depth_sources(enc_pack_path, tmp_path / "f", DEPTH_SOURCES[1:2]), tmp_path / "land")
    notice = (land_only / "NOTICE").read_text()
    assert OGL_BC_NOTICE in notice and "Canadian Hydrographic" not in notice
    with MBTiles.open(land_only / "enc.mbtiles") as m:
        assert m.metadata()["cheekymarine:data_notice"] == OGL_BC_NOTICE  # the credit only, no CHS text
    wave1 = (assemble_charts_pack(test_region, enc_pack_path, tmp_path / "us") / "NOTICE").read_text()
    assert "Canadian Hydrographic" not in wave1 and "British Columbia" not in wave1


def test_valdco_gains_no_value_from_derived(test_region, tmp_path):
    """A derived pack's cheekymarine:valdco is a subset of regions/bc-valdco.toml, and cheekymarine:depth_sources
    keeps only the inputs its features come from."""
    import tomllib

    import numpy as np
    from shapely.geometry import box

    from chartpack.bathy.blocks import SOURCE_NAMES
    from chartpack.enc.derived import derived_features
    from chartpack.enc.tiles import build_enc_mbtiles

    levels = tomllib.loads((PROJECT / "regions" / "bc-valdco.toml").read_text())["levels_m"]
    d, x0, y0, size = 0.0002, -124.0, 49.0, 120
    rows, cols = np.mgrid[0:size, 0:size]
    depth = (-1.0 + 140.0 * rows / size + 2.0 * np.sin(cols / 7.0)).astype(np.float32)
    core = (x0, y0 - size * d, x0 + size * d, y0)
    src = np.full(depth.shape, SOURCE_NAMES.index("nonna10"), np.int8)
    land = box(x0, y0 - 10 * d, x0 + 10 * d, y0)
    feats = derived_features(depth, src, (x0, d, 0.0, y0, 0.0, -d), core=core, levels_m=levels,
                             nosurvey=shapely.Polygon(), land=land, lat=48.99)
    region = dataclasses.replace(test_region, charts_kind="derived-inshore")
    inputs = [{"source": "nonna10", "asset": "nonna10-x.tif", "sha256": "a" * 64},
              {"source": "nonna100", "asset": "nonna100-x.tif", "sha256": "b" * 64},
              {"source": "fwa", "asset": "land-x.geojson.gz", "sha256": "c" * 64},
              {"source": "nosurvey", "asset": "nosurvey-x.geojson.gz", "sha256": "d" * 64}]
    out = build_enc_mbtiles([], tmp_path / "enc.mbtiles", region=region, work=tmp_path / "work", zooms=(10, 16),
                            canada=box(-125, 48, -123, 50), derived=feats, depth_sources=inputs)
    with MBTiles.open(out) as m:
        metadata = m.metadata()
    valdco = [float(v) for v in json.loads(metadata["cheekymarine:valdco"])]
    assert valdco and set(valdco) <= {float(v) for v in levels}
    assert json.loads(metadata["cheekymarine:depth_sources"]) == [inputs[0], inputs[2]]
