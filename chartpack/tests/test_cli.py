import shutil
from pathlib import Path

import pytest

from chartpack import __version__
from chartpack.cli import main
from chartpack.datum import geoid


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"chartpack {__version__}"


def test_cells_and_fetch_enc(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import shutil

    from chartpack import cli

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = fixtures_dir / ("ENCProdCat_excerpt.xml" if url.endswith(".xml") else "US4WA1HK.zip")
        shutil.copy(src, dest)
        return dest

    monkeypatch.setattr(cli, "download", fake_download)
    region = str(_grid_region(tmp_path, regions_dir))  # cells reads the grid beside the region file
    assert main(["cells", region, "--band", "4", "--cache", str(tmp_path)]) == 0
    assert "US4WA1HK" in capsys.readouterr().out.split()
    assert main(["fetch-enc", region, "--cache", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "US4WA1HK 1.3 2026-09-09\n"


def _fixture_catalog(monkeypatch, fixtures_dir):
    """cli.download serves the catalog excerpt for the catalog url."""
    from chartpack import cli

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        assert url.endswith(".xml"), url
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "ENCProdCat_excerpt.xml", dest)
        return dest

    monkeypatch.setattr(cli, "download", fake_download)


def test_cells_selects_over_the_owned_tiles(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    """A region box that is a sliver of its owned zoom-10 tile column: cells lists the cells meeting the owned tiles,
    not only the box."""
    _fixture_catalog(monkeypatch, fixtures_dir)
    region = _grid_region(tmp_path, regions_dir)
    region.write_text(region.read_text().replace("bbox = [-122.4, 47.7, -122.1, 48.0]", "bbox = [-122.4, 47.7, -122.39, 47.71]"))
    assert main(["cells", str(region), "--band", "5", "--cache", str(tmp_path / "cache")]) == 0
    assert "US5SEAEH" in capsys.readouterr().out.split()  # in the owned tile (163, 357), south of the box


def test_cells_reproduces_the_wave1_lists(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    """The documented refresh (chartpack cells per region and band) gives the committed lists, the overview's over
    every owned tile. The fixture holds every cell the regions name, so this holds against it."""
    from chartpack.region import load_region

    from chartpack.grid import load_grid

    _fixture_catalog(monkeypatch, fixtures_dir)
    for name in load_grid(regions_dir / "grid.toml") + ["overview"]:
        path = regions_dir / f"{name}.toml"
        for band, names in load_region(path).cells.items():
            assert main(["cells", str(path), "--band", str(band), "--cache", str(tmp_path / "cache")]) == 0
            assert capsys.readouterr().out.split() == names, (name, band)


def _grid_region(tmp_path, regions_dir):
    """A copy of test-cell.toml next to a grid.toml that lists it: build-enc reads the grid beside the region file."""
    import shutil

    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "grid.toml").write_text('zoom = 10\norder = ["test-cell"]\n')
    shutil.copytree(regions_dir / "clip", tmp_path / "regions" / "clip")  # build-enc loads the Canada polygon
    return Path(shutil.copy(regions_dir / "test-cell.toml", tmp_path / "regions"))


@pytest.mark.parametrize("overview, zooms", [(False, ("10", "16")), (True, ("6", "9"))])
def test_build_enc_zoom_range_reaches_tippecanoe(tmp_path, fixtures_dir, regions_dir, monkeypatch, overview, zooms):
    import shutil

    from chartpack.enc import tiles

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    region = _grid_region(tmp_path, regions_dir)
    if overview:  # beside the grid's one region pack, whose owned tiles crop it
        region = region.with_name("ov.toml")
        region.write_text("overview = true\n" + (tmp_path / "regions" / "test-cell.toml").read_text()
                          .replace('name = "test-cell"', 'name = "ov"').replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    cmds = []
    monkeypatch.setattr(tiles, "run", cmds.append)
    with pytest.raises(Exception):  # the patched run writes no mbtiles: only the commands matter
        main(["build-enc", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    tippecanoe = [c for c in cmds if c[0] == "tippecanoe"]
    assert tippecanoe
    for c in tippecanoe:
        assert (c[c.index("-Z") + 1], c[c.index("-z") + 1]) == zooms


def test_build_enc_records_the_overview_content_tiles(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """The overview's enc.mbtiles keeps owned null and records every owned tile of the grid as its content (#85)."""
    import shutil

    from chartpack import cli
    from chartpack.grid import owned_tiles
    from chartpack.region import load_region

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    pack = _grid_region(tmp_path, regions_dir)
    region = pack.with_name("ov.toml")
    region.write_text("overview = true\n" + pack.read_text()
                      .replace('name = "test-cell"', 'name = "ov"').replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    calls = []

    def keep(path, owned, **kw):
        calls.append((owned, kw))
        raise RuntimeError("stop")

    monkeypatch.setattr(cli, "build_enc_mbtiles", lambda *a, **kw: tmp_path / "enc.mbtiles")
    monkeypatch.setattr(cli, "keep_tiles", keep)
    with pytest.raises(RuntimeError, match="stop"):
        main(["build-enc", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    assert calls == [(None, {"minzoom": 6, "maxzoom": 9, "content": owned_tiles(load_region(pack), pack.parent)})]


def test_build_enc_crops_band1_to_the_owned_tiles(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """A band 1 cell spans far past the region: the quilt output reaching tippecanoe is cut to the owned
    zoom-10 tiles plus BLOCK_MARGIN_DEG, so a feature across an owned edge still renders over the seam."""
    import json

    from chartpack import cli
    from chartpack.bathy.blocks import BLOCK_MARGIN_DEG
    from chartpack.enc import tiles
    from chartpack.enc.reader import CellMeta, Feature
    from chartpack.grid import GRID_ZOOM, owned_tiles, tile_bounds
    from chartpack.region import load_region
    from shapely.geometry import Polygon, box, mapping, shape

    # The margin covers tippecanoe's default tile buffer (5 of 256 px) at the region's lowest zoom.
    assert BLOCK_MARGIN_DEG >= 5 / 256 * 360 / 2**tiles.REGION_ZOOMS[0]
    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    (tmp_path / "cache" / "enc" / "US1AAAAA-1.0.zip").touch()
    region = _grid_region(tmp_path, regions_dir)
    region.write_text(region.read_text().replace('[enc]\n', '[enc]\nband1 = ["US1AAAAA"]\n'))
    owned = owned_tiles(load_region(region), region.parent)
    x, y = min(owned)  # the west column: nothing owned past its west edge
    w, s, e, n = tile_bounds(GRID_ZOOM, x, y)
    points = {"inside": ((w + e) / 2, (s + n) / 2), "edge": (w - BLOCK_MARGIN_DEG / 2, (s + n) / 2),
              "far": (-140.0, 30.0)}
    band1 = (CellMeta("US1AAAAA", 1, 1, 0, "2026-01-01", mapping(box(-170, 10, -100, 60))),
             [Feature("hazard", {"type": "Point", "coordinates": list(p)},
                      {"cell": "US1AAAAA", "band": 1, "class": "OBSTRN", "OBJNAM": name})
              for name, p in points.items()]
             + [Feature("depare", mapping(box(w - 5, s, e, n)),  # reaches 5 degrees west of the owned tiles
                        {"cell": "US1AAAAA", "band": 1, "class": "DEPARE", "DRVAL1": "0.0", "DRVAL2": "5.5"})])
    read_cell, read_notes, read_canadian_area = cli.read_cell, cli.read_notes, cli.read_canadian_area
    monkeypatch.setattr(cli, "read_cell", lambda path: band1 if path.name.startswith("US1") else read_cell(path))
    monkeypatch.setattr(cli, "read_notes", lambda path: [] if path.name.startswith("US1") else read_notes(path))
    monkeypatch.setattr(cli, "read_canadian_area",
                        lambda path: Polygon() if path.name.startswith("US1") else read_canadian_area(path))
    monkeypatch.setattr(tiles, "run", lambda cmd: None)
    with pytest.raises(Exception):  # the patched run writes no mbtiles: only the tippecanoe input matters
        main(["build-enc", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    hazards = [json.loads(line) for line in (tmp_path / "work" / "tippecanoe" / "hazard.geojsonseq").read_text().splitlines()]
    assert {f["properties"]["OBJNAM"] for f in hazards if f["properties"].get("cell") == "US1AAAAA"} == {"inside", "edge"}
    depare = [shape(json.loads(line)["geometry"]) for line in
              (tmp_path / "work" / "tippecanoe" / "depare.geojsonseq").read_text().splitlines()
              if json.loads(line)["properties"]["cell"] == "US1AAAAA"]
    assert depare and all(g.bounds[0] >= w - BLOCK_MARGIN_DEG - 1e-9 for g in depare)


def test_build_enc_crops_the_overview_to_every_owned_tile(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """The overview owns no zoom-10 tile, but its quilt output is cut to the union of every owned tile plus
    BLOCK_MARGIN_DEG: a band 1 feature in Alaska does not reach tippecanoe."""
    import json

    from chartpack import cli
    from chartpack.enc import tiles
    from chartpack.enc.reader import CellMeta, Feature
    from chartpack.grid import GRID_ZOOM, owned_tiles, tile_bounds
    from chartpack.region import load_region
    from shapely.geometry import Polygon, box, mapping

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    (tmp_path / "cache" / "enc" / "US1AAAAA-1.0.zip").touch()
    pack = _grid_region(tmp_path, regions_dir)
    overview = tmp_path / "regions" / "ov.toml"
    overview.write_text("overview = true\n" + pack.read_text().replace('name = "test-cell"', 'name = "ov"')
                        .replace('sources = ["cudem", "crm"]', 'sources = ["crm"]')
                        .replace('band4 = ["US4WA1HK"]', 'band1 = ["US1AAAAA"]'))
    w, s, e, n = tile_bounds(GRID_ZOOM, *min(owned_tiles(load_region(pack), pack.parent)))
    points = {"inside": ((w + e) / 2, (s + n) / 2), "alaska": (-150.0, 61.0)}
    band1 = (CellMeta("US1AAAAA", 1, 1, 0, "2026-01-01", mapping(box(-170, 10, -100, 65))),
             [Feature("hazard", {"type": "Point", "coordinates": list(p)},
                      {"cell": "US1AAAAA", "band": 1, "class": "OBSTRN", "OBJNAM": name}) for name, p in points.items()])
    monkeypatch.setattr(cli, "read_cell", lambda path: band1)
    monkeypatch.setattr(cli, "read_notes", lambda path: [])
    monkeypatch.setattr(cli, "read_canadian_area", lambda path: Polygon())
    monkeypatch.setattr(tiles, "run", lambda cmd: None)
    with pytest.raises(Exception):  # the patched run writes no mbtiles: only the tippecanoe input matters
        main(["build-enc", str(overview), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    hazards = [json.loads(line) for line in (tmp_path / "work" / "tippecanoe" / "hazard.geojsonseq").read_text().splitlines()]
    assert {f["properties"]["OBJNAM"] for f in hazards} == {"inside"}


def test_build_enc_uses_cached_zip(tmp_path, fixtures_dir, regions_dir):
    import json
    import shutil

    from chartpack.mbtiles import MBTiles

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    args = ["build-enc", str(_grid_region(tmp_path, regions_dir)), str(tmp_path / "out"),
            "--cache", str(tmp_path / "cache"), "--work", str(tmp_path / "work")]
    assert main(args) == 0
    root = tmp_path / "out" / "charts-test-cell-0.1.0"
    with MBTiles.open(root / "enc.mbtiles") as m:
        md = m.metadata()
        assert md["cheekymarine:region"] == "test-cell" and (md["minzoom"], md["maxzoom"]) == ("10", "16")
        # away from the Canada polygon: none of the plan 8 metadata keys, so the old keys exactly
        assert not {"cheekymarine:notice_areas", "cheekymarine:data_notice", "cheekymarine:depth_sources"} & set(md)
        owned = json.loads(md["cheekymarine:owned"])
        assert owned and all(isinstance(t, list) and len(t) == 2 for t in owned)
        assert {z for z in range(17) if any(True for _ in m.tiles_at(z))} <= set(range(10, 17))
    assert (root / "manifest.json").exists() and (root / "styles" / "nav-day.json").exists()
    assert main(["check", str(root), "--enc-cache", str(tmp_path / "cache")]) == 0
    (tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip").unlink()
    with pytest.raises(SystemExit):
        main(args)


def test_fetch_bathy_prints_tiles_and_crm(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import shutil

    from chartpack import cli
    from chartpack.bathy.blocks import iter_blocks
    from chartpack.grid import owned_tiles
    from chartpack.region import load_region

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "cudem_urllist_excerpt.txt", dest)
        return dest

    fetched = []

    def fake_fetch_crm(bbox, cache_dir):
        fetched.append(bbox)
        return cache_dir / "crm" / f"crm_{len(fetched)}.tif"

    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "fetch_crm", fake_fetch_crm)
    grids = []
    monkeypatch.setattr(geoid, "fetch_grids", grids.append)
    region = _grid_region(tmp_path, regions_dir)
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path)]) == 0
    assert grids == [tmp_path / "proj"]  # every build converts CRM from EGM2008
    lines = capsys.readouterr().out.splitlines()
    assert (tmp_path / "cudem" / "urllist8483.txt").exists()
    assert "ncei19_n48x00_w122x50_2023v1" in lines
    owned = owned_tiles(load_region(region), region.parent)
    assert fetched == [read for _, _, read in iter_blocks(owned)]  # one CRM request per owned tile
    assert lines[-1] == str(tmp_path / "crm" / f"crm_{len(fetched)}.tif")


def test_crm_only_region_fetches_no_cudem(tmp_path, regions_dir, monkeypatch, capsys):
    from chartpack import cli

    monkeypatch.setattr(cli, "download", lambda *a, **k: pytest.fail("a CRM-only region needs no CUDEM list"))
    fetched = []
    monkeypatch.setattr(cli, "fetch_crm", lambda bbox, cache: fetched.append(bbox) or cache)
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)
    region = _grid_region(tmp_path, regions_dir)
    region.write_text(region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path)]) == 0
    capsys.readouterr()
    assert fetched


def test_cudem_only_region_fetches_no_crm(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import shutil

    from chartpack import cli

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "cudem_urllist_excerpt.txt", dest)
        return dest

    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "fetch_crm", lambda *a, **k: pytest.fail("a CUDEM-only region needs no CRM"))
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)
    region = _grid_region(tmp_path, regions_dir)
    region.write_text('coarse_fallback = "enc"\n' + region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["cudem"]'))
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path)]) == 0
    assert "ncei19_n48x00_w122x50_2023v1" in capsys.readouterr().out.splitlines()


def test_fetch_bathy_overview_reads_crm_once(tmp_path, regions_dir, monkeypatch, capsys):
    from chartpack import cli
    from chartpack.bathy.blocks import overview_bounds

    fetched = []
    monkeypatch.setattr(cli, "download", lambda *a, **k: pytest.fail("the overview needs no CUDEM list"))
    monkeypatch.setattr(cli, "fetch_crm", lambda bbox, cache: fetched.append(bbox) or cache)
    grids = []
    monkeypatch.setattr(geoid, "fetch_grids", grids.append)
    region = _grid_region(tmp_path, regions_dir)
    region.write_text("overview = true\n" + region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path)]) == 0
    assert grids == [tmp_path / "proj"]
    capsys.readouterr()
    assert fetched == [overview_bounds((-122.4, 47.7, -122.1, 48.0))]  # native: the WCS ignores width/height


def _bathy_region(tmp_path, regions_dir):
    toml = (regions_dir / "test-cell.toml").read_text().replace(
        "bbox = [-122.4, 47.7, -122.1, 48.0]", "bbox = [-122.3846, 47.8954, -122.3754, 47.9046]"
    ).replace("dem_maxzoom = 14", "dem_maxzoom = 12")
    (tmp_path / "regions").mkdir()
    shutil.copytree(regions_dir / "datum", tmp_path / "regions" / "datum")
    shutil.copytree(regions_dir / "clip", tmp_path / "regions" / "clip")  # the builds load the Canada polygon
    (tmp_path / "regions" / "grid.toml").write_text('zoom = 10\norder = ["test-cell"]\n')
    path = tmp_path / "regions" / "bathy-test.toml"
    path.write_text(toml)
    return path


def _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, urls):
    """A fetch-bathy cache for the region: the possession bar fixture as CRM for every owned block. The grids are
    patched to 1 and 3 arc-seconds so a whole zoom-10 block stays small."""
    import shutil

    from chartpack.bathy import blocks
    from chartpack.bathy.crm import crm_path
    from chartpack.grid import owned_tiles
    from chartpack.region import load_region

    monkeypatch.setattr(blocks, "FINE_RES_DEG", 1 / 3600)
    monkeypatch.setattr(blocks, "COARSE_RES_DEG", 1 / 1200)
    cache = tmp_path / "cache"
    (cache / "enc").mkdir(parents=True)
    (cache / "cudem").mkdir()
    shutil.copy(fixtures_dir / "US4WA1HK.zip", cache / "enc" / "US4WA1HK-1.3.zip")
    for _, _, read in blocks.iter_blocks(owned_tiles(load_region(region), region.parent)):
        dest = crm_path(read, cache)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "cudem_possession_bar.tif", dest)
    (cache / "cudem" / "urllist8483.txt").write_text("".join(u + "\n" for u in urls))
    return cache


def _fixture_window(fixtures_dir, bbox):
    """The possession bar fixture over bbox cut to the fixture's own extent (the fakes serve it for any source)."""
    from chartpack.bathy.cudem import read_window

    fw, fs, fe, fn = -122.3846, 47.8954, -122.3754, 47.9046
    w, s, e, n = bbox
    return read_window(str(fixtures_dir / "cudem_possession_bar.tif"), (max(w, fw), max(s, fs), min(e, fe), min(n, fn)))


def _assert_bathy_sources(root, listed):
    """The pack's bathy metadata, manifest and NOTICE record only the listed bathy sources."""
    import json

    from chartpack.mbtiles import MBTiles

    for name in ("bathy.mbtiles", "bathy-coarse.mbtiles"):
        with MBTiles.open(root / name) as m:
            assert set(json.loads(m.metadata()["cheekymarine:sources"])) == set(listed) | {"datum"}, name
    manifest = {s["source"] for s in json.loads((root / "manifest.json").read_text())["sources"]}
    assert manifest <= set(listed) | {"datum"} and "datum" in manifest
    assert ("crm" in manifest) == ("crm" in listed)
    notice = (root / "NOTICE").read_text()
    assert ("Coastal Relief Model" in notice) == ("crm" in listed)
    assert ("CRM" in notice) == ("crm" in listed)
    assert ("CUDEM" in notice) == ("cudem" in listed)


def test_build_bathy_needs_fetch_bathy_first(tmp_path, regions_dir):
    args = ["build-bathy", str(_bathy_region(tmp_path, regions_dir)), str(tmp_path / "out"),
            "--cache", str(tmp_path / "cache"), "--work", str(tmp_path / "work")]
    with pytest.raises(SystemExit, match="fetch-bathy"):
        main(args)


def test_build_bathy_needs_the_geoid_grids(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """CRM, CUDEM list and ENC cached, but no geoid grids: build-bathy stops before reading anything."""
    region = _bathy_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, ["https://example.test/ncei19_n48x00_w122x50_2023v1.tif"])
    monkeypatch.setattr(geoid, "download", lambda *a, **k: pytest.fail("build-bathy must not download"))
    with pytest.raises(SystemExit, match="us_nga_egm08_25.tif .*run fetch-bathy first"):
        main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")])


def test_build_bathy_end_to_end(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys, zero_geoid):
    import json

    from chartpack.bathy import blocks
    from chartpack.mbtiles import MBTiles

    region = _bathy_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [
        "https://example.test/ncei19_n48x00_w122x50_2023v1.tif", "https://example.test/ncei19_n48x00_w122x50_2017v1.tif"])
    opened = []

    def fake_read_window(src, bbox):
        opened.append(src)
        return _fixture_window(fixtures_dir, bbox)

    monkeypatch.setattr(blocks, "read_window", fake_read_window)
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")]) == 0
    root = tmp_path / "out" / "bathy-test-cell-0.1.0"
    assert capsys.readouterr().out.strip() == str(root)
    assert opened[0] == "/vsicurl/https://example.test/ncei19_n48x00_w122x50_2023v1.tif" and len(opened) == 2  # tile, then CRM
    assert (root / "styles" / "fish-day.json").exists() and (root / "dem.mbtiles").exists()
    assert json.loads((root / "manifest.json").read_text())["charts_schema"] == 2
    assert main(["check", str(root)]) == 0
    with MBTiles.open(root / "bathy.mbtiles") as m:
        md = m.metadata()
        assert [t["year"] for t in json.loads(md["cheekymarine:sources"])["cudem"]] == [2023]
        assert any(True for _ in m.tiles_at(12))
    _assert_bathy_sources(root, ["cudem", "crm"])
    from chartpack.pack.assemble import BATHY_FILES

    for name in BATHY_FILES:  # a US pack with no Canadian water: no CHS notice, no notice area
        with MBTiles.open(root / name) as m:
            md = m.metadata()
        assert "cheekymarine:data_notice" not in md and json.loads(md["cheekymarine:notice_areas"])["features"] == []
    assert "Canadian" not in (root / "NOTICE").read_text()


def test_build_bathy_enc_fallback_drops_crm_contours(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys,
                                                     zero_geoid):
    """coarse_fallback = "enc" on a CUDEM-only region: where CUDEM is absent the ENC lines are the only contours."""
    import json

    from shapely.geometry import box, shape

    from chartpack.bathy import blocks

    region = _bathy_region(tmp_path, regions_dir)
    region.write_text('coarse_fallback = "enc"\n' + region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["cudem"]'))
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, ["https://example.test/ncei19_n48x00_w122x50_2023v1.tif"])
    shutil.rmtree(cache / "crm")  # a CUDEM-only region needs no CRM files

    def fake_read_window(src, bbox):
        assert src.startswith("/vsicurl/"), src  # CRM is never read
        grid = _fixture_window(fixtures_dir, bbox)
        if src.startswith("/vsicurl/"):  # the CUDEM tile covers only the east half
            grid.data[:, : grid.data.shape[1] // 2] = grid.nodata
        return grid

    monkeypatch.setattr(blocks, "read_window", fake_read_window)
    work = tmp_path / "work"
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(work)]) == 0
    capsys.readouterr()
    contours = [json.loads(line) for line in (work / "tippecanoe" / "contour.geojsonseq").read_text().splitlines()]
    sources = {f["properties"]["source"] for f in contours}
    assert "crm" not in sources and {"cudem", "enc"} <= sources
    west = box(-122.3846, 47.8954, -122.382, 47.9046)  # well inside the CRM-only half
    assert any(shape(f["geometry"]).intersects(west) for f in contours if f["properties"]["source"] == "enc")
    assert not (work / "tippecanoe-coarse" / "contour.geojsonseq").exists()  # no coarse layers on the ENC path
    _assert_bathy_sources(tmp_path / "out" / "bathy-test-cell-0.1.0", ["cudem"])


def test_build_bathy_enc_fallback_leaves_out_the_clip(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys,
                                                      zero_geoid):
    """A region clip over part of the ENC-fallback half (#16): no ENC fallback contour reaches into the clip."""
    import json

    from shapely.geometry import box, mapping, shape

    from chartpack.bathy import blocks

    region = _bathy_region(tmp_path, regions_dir)
    clip = box(-122.45, 47.85, -122.383, 47.95)  # the west edge of the CUDEM-free half and the water past it
    (tmp_path / "regions" / "clip.geojson").write_text(json.dumps({"type": "Feature", "properties": {},
                                                                   "geometry": mapping(clip)}))
    region.write_text('coarse_fallback = "enc"\nclip = "clip.geojson"\n'
                      + region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["cudem"]'))
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, ["https://example.test/ncei19_n48x00_w122x50_2023v1.tif"])
    shutil.rmtree(cache / "crm")

    def fake_read_window(src, bbox):
        grid = _fixture_window(fixtures_dir, bbox)
        grid.data[:, : grid.data.shape[1] // 2] = grid.nodata  # the CUDEM tile covers only the east half
        return grid

    monkeypatch.setattr(blocks, "read_window", fake_read_window)
    work = tmp_path / "work"
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(work)]) == 0
    capsys.readouterr()
    contours = [json.loads(line) for line in (work / "tippecanoe" / "contour.geojsonseq").read_text().splitlines()]
    enc = [shape(f["geometry"]) for f in contours if f["properties"]["source"] == "enc"]
    assert enc  # ENC lines still fall outside the clip
    assert all(line.intersection(clip).length < 1e-9 for line in enc)


def _mask_lake(region, lake):
    """Make the lake mask file of the region's datum file (a copy of regions/datum) hold the polygon `lake` alone."""
    import json
    import tomllib

    from shapely.geometry import mapping

    datum = region.parent / "datum" / "wa-stations.toml"
    with datum.open("rb") as f:
        mask = datum.parent / tomllib.load(f)["lake_mask_file"]
    mask.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Test Lake"}, "geometry": mapping(lake)}]}))


@pytest.mark.parametrize("work_dir", ["tippecanoe", "tippecanoe-coarse"])
def test_build_bathy_masks_lakes_without_a_datum_rule(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys,
                                                      zero_geoid, work_dir):
    """A contour crossing a lake of the datum file's lake mask keeps only the part outside it, in the fine and the
    coarse layers, and no band reaches inside. The coarse case has no CUDEM, so CRM draws the lake. (Coverage is
    polygonized at COVERAGE_CELL_DEG, wider than this lake, so it follows the mask only to that size, as in
    test_lake_mask_removes_water_in_block.)"""
    import json

    from shapely.geometry import box, shape

    from chartpack.bathy import blocks

    lake = box(-122.382, 47.898, -122.378, 47.902)  # the middle of the fixture
    region = _bathy_region(tmp_path, regions_dir)
    fine = work_dir == "tippecanoe"
    if not fine:
        region.write_text(region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch,
                         ["https://example.test/ncei19_n48x00_w122x50_2023v1.tif"] if fine else [])
    monkeypatch.setattr(blocks, "read_window", lambda src, bbox: _fixture_window(fixtures_dir, bbox))

    def build(work):
        assert main(["build-bathy", str(region), str(tmp_path / work), "--cache", str(cache), "--work",
                     str(tmp_path / work / "work")]) == 0
        capsys.readouterr()
        return {layer: [shape(json.loads(line)["geometry"]) for line in
                        (tmp_path / work / "work" / work_dir / f"{layer}.geojsonseq").read_text().splitlines()]
                for layer in ("contour", "band")}

    before = build("before")
    assert any(g.intersection(lake).length > 0 for g in before["contour"])  # the lake has contours unmasked
    _mask_lake(region, lake)
    after = build("after")
    inner = lake.buffer(-0.0005)  # a cell or two in from the edge, past the grids' cell placement
    assert after["contour"] and any(g.intersects(lake.buffer(0.0005)) for g in after["contour"])
    for layer, geoms in after.items():
        assert all(g.intersection(inner).is_empty for g in geoms), layer


def test_build_bathy_masks_lakes_in_the_overview(tmp_path, regions_dir, monkeypatch, zero_geoid):
    """The overview's coarse read is cut by the same lake mask as the region packs."""
    from shapely.geometry import box

    from chartpack import cli
    from chartpack.bathy.blocks import overview_bounds
    from chartpack.bathy.crm import crm_path

    region = _bathy_region(tmp_path, regions_dir)
    shutil.copy(region, region.with_name("test-cell.toml"))  # the grid's region pack; the overview is in no grid
    text = region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]')
    region.write_text("overview = true\n" + text.replace('name = "test-cell"', 'name = "ov"'))
    lake = box(-122.382, 47.898, -122.378, 47.902)
    _mask_lake(region, lake)
    path = crm_path(overview_bounds((-122.3846, 47.8954, -122.3754, 47.9046)), tmp_path / "cache")
    path.parent.mkdir(parents=True)
    path.touch()
    clips = []

    def fake_overview(bbox, sources, datum, canada, nosurvey, *, lake_mask=None):
        clips.append(lake_mask)
        raise RuntimeError("stop")

    monkeypatch.setattr(cli, "build_overview", fake_overview)
    with pytest.raises(RuntimeError, match="stop"):
        main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    assert clips[0] is not None and clips[0].covers(lake)


def test_build_bathy_overview_draws_no_depth_outside_owned_tiles(tmp_path, regions_dir, monkeypatch, zero_geoid):
    """The overview bbox reaches past the owned tiles (an unowned tile east of the grid's one tile): the mask handed
    to build_overview covers everything in its read outside the owned tiles and nothing inside them, so no depth is
    drawn where no pack owns a tile (and so no BC notice area could be missing there)."""
    from shapely.geometry import box

    from chartpack import cli
    from chartpack.bathy.blocks import overview_bounds
    from chartpack.bathy.crm import crm_path
    from chartpack.grid import owned_tiles, tile_bounds, tiles_area
    from chartpack.region import load_region

    region = _bathy_region(tmp_path, regions_dir)
    pack = Path(shutil.copy(region, region.with_name("test-cell.toml")))
    bbox = "bbox = [-122.3846, 47.8954, -122.2, 47.9046]"  # east into the next zoom-10 column
    text = region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]')
    region.write_text("overview = true\n" + text.replace('name = "test-cell"', 'name = "ov"')
                      .replace("bbox = [-122.3846, 47.8954, -122.3754, 47.9046]", bbox))
    _mask_lake(region, box(-122.30, 47.70, -122.29, 47.71))  # one lake, away from the owned tile
    path = crm_path(overview_bounds(load_region(region).bbox), tmp_path / "cache")
    path.parent.mkdir(parents=True)
    path.touch()
    masks = []

    def fake_overview(bbox, sources, datum, canada, nosurvey, *, lake_mask=None):
        masks.append(lake_mask)
        raise RuntimeError("stop")

    monkeypatch.setattr(cli, "build_overview", fake_overview)
    with pytest.raises(RuntimeError, match="stop"):
        main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    owned = tiles_area(owned_tiles(load_region(pack), pack.parent))
    read = box(*overview_bounds(load_region(region).bbox))
    (mask,) = masks
    assert mask.covers(read.difference(owned)) and mask.intersection(owned).area < 1e-12
    unowned = box(*tile_bounds(10, 164, 356)).intersection(read)
    assert unowned.area > 0 and mask.covers(unowned)


def test_build_bathy_tile_outside_crm_has_no_coarse_layer(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys,
                                                           zero_geoid):
    """A tile wholly outside CRM's coverage: fetch-bathy asks nothing for it and build-bathy draws its CUDEM fine
    layers, with no coarse layer instead of an error."""
    import json

    from chartpack import cli
    from chartpack.bathy import blocks, crm

    region = _bathy_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, ["https://example.test/ncei19_n48x00_w122x50_2023v1.tif"])
    shutil.rmtree(cache / "crm")
    monkeypatch.setattr(crm, "CRM_BOUNDS", (-127.0, 44.0, -126.0, 45.0))  # far from the test tile
    monkeypatch.setattr(crm, "download", lambda *a, **k: pytest.fail("nothing is asked of CRM"))
    monkeypatch.setattr(cli, "download", lambda url, dest, **k: dest)  # the cached CUDEM list
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)
    assert main(["fetch-bathy", str(region), "--cache", str(cache)]) == 0
    monkeypatch.setattr(blocks, "read_window", lambda src, bbox: (
        _fixture_window(fixtures_dir, bbox) if src.startswith("/vsicurl/") else pytest.fail(f"CRM read: {src}")))
    work = tmp_path / "work"
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(work)]) == 0
    capsys.readouterr()
    assert (work / "tippecanoe" / "contour.geojsonseq").stat().st_size > 0
    coarse = work / "tippecanoe-coarse" / "contour.geojsonseq"
    assert not coarse.exists() or not [json.loads(line) for line in coarse.read_text().splitlines()]


def test_build_bathy_crm_only_writes_no_fine_layers(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys,
                                                    zero_geoid):
    """sources = ["crm"], no CUDEM list in the cache: the fine layer files stay absent, all four bathy files exist."""
    from chartpack.bathy import blocks

    region = _bathy_region(tmp_path, regions_dir)
    region.write_text(region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    (cache / "cudem" / "urllist8483.txt").unlink()
    monkeypatch.setattr(blocks, "read_window", lambda src, bbox: (
        pytest.fail(f"CUDEM read: {src}") if src.startswith("/vsicurl/") else _fixture_window(fixtures_dir, bbox)))
    work, out = tmp_path / "work", tmp_path / "out"
    assert main(["build-bathy", str(region), str(out), "--cache", str(cache), "--work", str(work)]) == 0
    capsys.readouterr()
    for layer in ("contour", "band", "coverage"):
        fine = work / "tippecanoe" / f"{layer}.geojsonseq"
        assert not fine.exists() or fine.stat().st_size == 0, layer
    assert (work / "tippecanoe-coarse" / "contour.geojsonseq").stat().st_size > 0
    for name in ("bathy.mbtiles", "bathy-coarse.mbtiles", "dem.mbtiles", "dem-coarse.mbtiles"):
        assert (work / name).is_file(), name
    _assert_bathy_sources(out / "bathy-test-cell-0.1.0", ["crm"])


def test_manifest_and_archive_commands(charts_pack_root_copy, regions_dir, tmp_path, capsys):
    (charts_pack_root_copy / "manifest.json").unlink()
    assert main(["check", str(charts_pack_root_copy)]) == 1
    assert "manifest" in capsys.readouterr().out
    assert main(["manifest", str(charts_pack_root_copy), "--region", str(regions_dir / "test-cell.toml")]) == 0
    assert main(["check", str(charts_pack_root_copy)]) == 0
    capsys.readouterr()
    assert main(["archive", str(charts_pack_root_copy), str(tmp_path / "dist")]) == 0
    assert capsys.readouterr().out.split() == [str(tmp_path / "dist" / "charts-test-cell-0.1.0.tar"), str(tmp_path / "dist" / "SHA256SUMS")]


def test_check_reports_problems_as_errors_not_tracebacks(charts_pack_root_copy, tmp_path, capsys):
    assert main(["check", str(charts_pack_root_copy), "--enc-cache", str(tmp_path / "empty")]) == 1
    assert "US4WA1HK-1.3.zip" in capsys.readouterr().out
    (charts_pack_root_copy / "manifest.json").unlink()
    assert main(["check", str(charts_pack_root_copy), "--enc-cache", str(tmp_path / "empty")]) == 1
    assert "manifest.json" in capsys.readouterr().out


def _seabed_region(tmp_path, regions_dir):
    path = tmp_path / "seabed-test.toml"
    path.write_text((regions_dir / "test-cell.toml").read_text()
                    + '\n[seabed]\nsources = ["enc", "usseabed", "usgs-cmecs"]\ncmecs_blocks = ["seattle", "admiralty-inlet"]\n')
    return path


def test_fetch_seabed(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys):
    import shutil

    from chartpack.seabed import cmecs, usseabed

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_dir / "seabed" / dest.name, dest)
        return dest

    def size(name):
        return (fixtures_dir / "seabed" / name).stat().st_size

    monkeypatch.setattr("chartpack.cache.download", fake_download)
    monkeypatch.setattr(usseabed, "FILES", {n: (u, size(n), m) for n, (u, _, m) in usseabed.FILES.items()})
    monkeypatch.setattr(cmecs, "BLOCKS", {b: k._replace(size=size(f"{k.name}.zip")) for b, k in cmecs.BLOCKS.items()})
    assert main(["fetch-seabed", str(_seabed_region(tmp_path, regions_dir)), "--cache", str(tmp_path / "cache")]) == 0
    seabed = tmp_path / "cache" / "seabed"
    assert capsys.readouterr().out.splitlines() == [
        str(seabed / "pac_ext.zip"), str(seabed / "pac_prs.zip"),
        str(seabed / "CMECS_OffshoreSeattle.zip"), str(seabed / "CMECS_AdmiraltyInlet.zip")]
    # a region with the ENC source only fetches nothing
    assert main(["fetch-seabed", str(regions_dir / "test-cell.toml"), "--cache", str(tmp_path / "c2")]) == 0
    assert capsys.readouterr().out == "" and not (tmp_path / "c2").exists()


def test_build_enc_merges_usgs_seabed(tmp_path, fixtures_dir, regions_dir):
    import json
    import shutil

    from chartpack.mbtiles import MBTiles, decode_pbf

    region = _seabed_region(tmp_path, regions_dir)
    (tmp_path / "grid.toml").write_text('zoom = 10\norder = ["test-cell"]\n')
    shutil.copytree(regions_dir / "clip", tmp_path / "clip")
    cache = tmp_path / "cache"
    (cache / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", cache / "enc" / "US4WA1HK-1.3.zip")
    args = ["build-enc", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")]
    with pytest.raises(SystemExit, match="fetch-seabed"):
        main(args)
    shutil.copytree(fixtures_dir / "seabed", cache / "seabed")
    assert main(args) == 0
    root = tmp_path / "out" / "charts-test-cell-0.1.0"
    srcs = set()
    with MBTiles.open(root / "enc.mbtiles") as m:
        for _, _, data in m.tiles_at(16):
            srcs |= {f["properties"]["src"] for f in decode_pbf(data).get("seabed", [])}
    assert srcs == {"enc", "usseabed", "usgs-cmecs"}
    legend = json.loads((root / "legend.json").read_text())
    assert {s for e in legend["entries"] for s in e["sources"]} == {"enc", "usseabed", "usgs-cmecs"}
    assert main(["check", str(root), "--enc-cache", str(cache)]) == 0


def test_build_enc_reads_usgs_seabed_over_the_owned_tiles(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """A region owns whole zoom-10 tiles that reach past its bbox (sound-south owns 47.45 to 47.5172 N): USGS seabed
    features in that strip must reach the pack input, or they land in no pack."""
    import shutil

    from chartpack import cli
    from chartpack.grid import GRID_ZOOM, owned_tiles, tile_bounds
    from chartpack.region import load_region
    from shapely import union_all
    from shapely.geometry import box, shape

    path = _grid_region(tmp_path, regions_dir)
    narrow = "bbox = [-122.4, 47.7, -122.39, 48.0]"  # a sliver of the west tile column (-122.695 to -122.344 W)
    path.write_text(path.read_text().replace("bbox = [-122.4, 47.7, -122.1, 48.0]", narrow)
                    + '\n[seabed]\nsources = ["enc", "usseabed", "usgs-cmecs"]\ncmecs_blocks = ["seattle"]\n')
    region = load_region(path)
    owned = union_all([box(*tile_bounds(GRID_ZOOM, *t)) for t in owned_tiles(region, path.parent)])
    cache = tmp_path / "cache"
    (cache / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", cache / "enc" / "US4WA1HK-1.3.zip")
    shutil.copytree(fixtures_dir / "seabed", cache / "seabed")
    got = []

    def fake_build(cells, out, *, seabed, **kw):
        got.extend(seabed)
        raise RuntimeError("stop after the seabed read")

    monkeypatch.setattr(cli, "build_enc_mbtiles", fake_build)
    with pytest.raises(RuntimeError, match="seabed read"):
        main(["build-enc", str(path), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")])
    strip = [f for f in got if shape(f.geometry).intersects(owned) and not shape(f.geometry).intersects(box(*region.bbox))]
    assert {f.props["src"] for f in strip} == {"usseabed", "usgs-cmecs"}


# Canadian source assets from the release sources-bc-1 (plan 8 Task 6): no pack build calls a Canadian host.

SOURCES_BASE = "https://github.com/jjveleber/CheekyMarine/releases/download/sources-bc-1/"


def _nonna_region(tmp_path, regions_dir):
    """The bathy test region as a BC inshore pack (its whole tile is the Canadian column), assets named toba."""
    path = _bathy_region(tmp_path, regions_dir)
    path.write_text(path.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["nonna10", "nonna100", "crm"]')
                    + '\n[charts]\nkind = "derived-inshore"\n\n[sources]\nassets = "toba"\n')
    return path


def _write_assets(folder, region, *, shrink=0.0):
    """Fixture assets for the region in folder: NONNA-10 (a slope) and NONNA-100 patches around Possession Bar, a
    coastline file, and fetch-stats-toba.json whose extent is the region's fetch extent with its west edge moved
    east by shrink degrees. Returns {file name: bytes}."""
    import gzip
    import hashlib
    import json

    import numpy as np
    from make_nonna import NODATA as NONNA_NODATA
    from test_bathy_blocks import _const, _write_nonna_over

    from chartpack.grid import fetch_extent
    from chartpack.region import load_region

    folder.mkdir(parents=True, exist_ok=True)
    near = (-122.384, 47.896, -122.376, 47.904)
    _write_nonna_over(folder / "nonna10-toba.tif", "nonna10", near,  # a slope from 5 m to 29 m deep, west to east
                      lambda lon, lat: np.where(_const(1.0, near)(lon, lat) == 1.0, -(5.0 + 3000 * (lon - near[0])),
                                                NONNA_NODATA))
    wide = (-122.40, 47.88, -122.36, 47.92)
    _write_nonna_over(folder / "nonna100-toba.tif", "nonna100", wide, _const(-15.0, wide))
    (folder / "coast-toba.geojson.gz").write_bytes(gzip.compress(b'{"type": "FeatureCollection", "features": []}'))
    w, s, e, n = fetch_extent(load_region(region), region.parent)
    files = {}
    for name in ("nonna10-toba.tif", "nonna100-toba.tif", "coast-toba.geojson.gz"):
        files[name] = {"chunks": 1, "bytes": (folder / name).stat().st_size, "seconds": 0.1,
                       "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()}
    stats = {"extent": [round(v, 9) for v in (w + shrink, s, e, n)], "files": files}
    (folder / "fetch-stats-toba.json").write_text(json.dumps(stats, indent=2) + "\n")
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def _no_network(monkeypatch):
    import socket
    import urllib.request

    def refuse(*a, **k):
        raise AssertionError(f"network request: {a[:1]}")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_fetch_bathy_downloads_the_region_assets(tmp_path, regions_dir, monkeypatch, capsys):
    """fetch-bathy of a region listing NONNA downloads its assets from sources-bc-1 into the cache, checks each
    against the sha256 in the fetch stats, and asks again only for the stats on a second run."""
    from chartpack import cli

    region = _nonna_region(tmp_path, regions_dir)
    served = _write_assets(tmp_path / "release", region)
    urls = []

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        urls.append(url)
        assert url.startswith(SOURCES_BASE), url
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(served[url.removeprefix(SOURCES_BASE)])
        return dest

    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "fetch_crm", lambda bbox, cache: None)
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)
    cache = tmp_path / "cache"
    assert main(["fetch-bathy", str(region), "--cache", str(cache)]) == 0
    names = ["fetch-stats-toba.json", "nonna10-toba.tif", "nonna100-toba.tif"]  # a bathy build reads no coastline
    assert urls == [SOURCES_BASE + name for name in names]
    for name in names:
        assert (cache / "sources-bc-1" / name).read_bytes() == served[name]
    urls.clear()
    assert main(["fetch-bathy", str(region), "--cache", str(cache)]) == 0
    assert urls == [SOURCES_BASE + "fetch-stats-toba.json"]  # the assets are cached
    capsys.readouterr()


def test_fetch_bathy_rejects_an_asset_that_does_not_match_its_stats(tmp_path, regions_dir, monkeypatch, capsys):
    from chartpack import cli

    region = _nonna_region(tmp_path, regions_dir)
    served = _write_assets(tmp_path / "release", region)
    served["nonna100-toba.tif"] = served["nonna100-toba.tif"] + b"x"

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(served[url.removeprefix(SOURCES_BASE)])
        return dest

    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "fetch_crm", lambda bbox, cache: None)
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)
    with pytest.raises(SystemExit, match=r"nonna100-toba\.tif.*sha256.*chartpack-sources\.yml"):
        main(["fetch-bathy", str(region), "--cache", str(tmp_path / "cache")])
    assert not (tmp_path / "cache" / "sources-bc-1" / "nonna100-toba.tif").exists()


def test_build_bathy_reads_assets_not_wcs(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys, zero_geoid):
    """build-bathy of a region listing NONNA reads the cached assets and makes no network request; its fine layers
    are NONNA-10 water. A missing asset stops the build naming the file and the fetch workflow."""
    import json

    from chartpack.bathy import blocks

    region = _nonna_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    _write_assets(cache / "sources-bc-1", region)
    monkeypatch.setattr(blocks, "read_window", lambda src, bbox: _fixture_window(fixtures_dir, bbox))
    _no_network(monkeypatch)
    work = tmp_path / "work"
    assert main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(work)]) == 0
    capsys.readouterr()
    fine = [json.loads(line)["properties"]
            for line in (work / "tippecanoe" / "coverage.geojsonseq").read_text().splitlines()]
    assert {(p["source"], p["grade"]) for p in fine} == {("nonna10", "survey")}
    coarse = [json.loads(line)["properties"]
              for line in (work / "tippecanoe-coarse" / "coverage.geojsonseq").read_text().splitlines()]
    assert ("nonna100", "coarse-survey") in {(p["source"], p["grade"]) for p in coarse}
    # a BC pack: the CHS notice and its owned tiles as the notice area, on all four files
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from chartpack.grid import owned_tiles, tiles_area
    from chartpack.mbtiles import MBTiles
    from chartpack.pack.assemble import BATHY_FILES, CHS_NOTICE
    from chartpack.region import load_region

    root = tmp_path / "out" / "bathy-test-cell-0.1.0"
    assert "Canadian Hydrographic Service" in (root / "NOTICE").read_text()
    import hashlib

    for asset in ("nonna10-toba.tif", "nonna100-toba.tif"):  # F1: the assets read, by name and sha256
        sha = hashlib.sha256((cache / "sources-bc-1" / asset).read_bytes()).hexdigest()
        assert f"{asset} (sha256 {sha})" in (root / "NOTICE").read_text()
    owned = tiles_area(owned_tiles(load_region(region), region.parent))
    for name in BATHY_FILES:
        with MBTiles.open(root / name) as m:
            md = m.metadata()
        assert md["cheekymarine:data_notice"] == CHS_NOTICE
        areas = json.loads(md["cheekymarine:notice_areas"])["features"]
        assert [f["properties"] for f in areas] == [{"kind": "bc"}]
        assert unary_union([shape(f["geometry"]) for f in areas]).symmetric_difference(owned).area < 1e-12
    (cache / "sources-bc-1" / "nonna100-toba.tif").unlink()
    with pytest.raises(SystemExit, match=r"nonna100-toba\.tif.*chartpack-sources\.yml"):
        main(["build-bathy", str(region), str(tmp_path / "out2"), "--cache", str(cache), "--work", str(work)])


@pytest.mark.parametrize("command, asset", [("build-bathy", "nonna10-toba.tif"),
                                            ("build-enc", "nonna10-toba.tif")])
def test_block_outside_asset_extent_is_error(tmp_path, fixtures_dir, regions_dir, monkeypatch, zero_geoid, command,
                                             asset):
    """A read box past the extent the fetch workflow pulled (fetch-stats-toba.json) fails the build, naming the
    region, the asset and the fetch workflow, before anything is built. build-enc reads the assets when its tiles
    meet the Canada polygon (here a stand-in over the region)."""
    from shapely.geometry import box

    from chartpack import cli

    monkeypatch.setattr(cli, "load_canada", lambda regions: box(-123.0, 47.5, -122.0, 48.5))
    region = _nonna_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    _write_assets(cache / "sources-bc-1", region, shrink=0.01)
    monkeypatch.setattr(cli, "build_block", lambda *a, **k: pytest.fail("built past the asset extent"))
    monkeypatch.setattr(cli, "build_enc_mbtiles", lambda *a, **k: pytest.fail("built past the asset extent"))
    with pytest.raises(SystemExit, match=rf"test-cell.*{asset.replace('.', '[.]')}.*chartpack-sources\.yml"):
        main([command, str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")])


def test_fetch_bathy_fetches_etopo_only_when_listed(tmp_path, regions_dir, monkeypatch, capsys):
    from chartpack import cli

    fetched = []
    monkeypatch.setattr(cli, "fetch_etopo", lambda extent, cache: fetched.append((extent, cache)) or [cache / "etopo" / "e.tif"])
    monkeypatch.setattr(cli, "fetch_crm", lambda bbox, cache: None)
    monkeypatch.setattr(cli, "download", lambda *a, **k: pytest.fail("no CUDEM list needed"))
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)
    region = _grid_region(tmp_path, regions_dir)
    region.write_text(region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path)]) == 0
    assert fetched == []
    region.write_text(region.read_text().replace('sources = ["crm"]', 'sources = ["crm", "etopo"]'))
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path)]) == 0
    assert len(fetched) == 1 and fetched[0][1] == tmp_path  # given the region's fetch extent
    assert capsys.readouterr().out.splitlines()[-1] == str(tmp_path / "etopo" / "e.tif")


def test_build_bathy_passes_the_etopo_path_only_when_listed(tmp_path, fixtures_dir, regions_dir, monkeypatch, zero_geoid):
    import shutil

    from chartpack import cli
    from chartpack.bathy.etopo import etopo_paths

    seen = []

    class Stop(Exception):
        pass

    def spy(core, read, sources, *a, **k):
        seen.append(sources.etopo)
        raise Stop

    monkeypatch.setattr(cli, "build_block", spy)
    region = _bathy_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    args = ["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "work")]
    with pytest.raises(Stop):
        main(args)
    assert seen == [None]  # the region does not list etopo
    region.write_text(region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["cudem", "crm", "etopo"]'))
    with pytest.raises(SystemExit, match="run fetch-bathy first"):  # the tile is not cached yet
        main(args)
    from chartpack.grid import fetch_extent
    from chartpack.region import load_region

    tiles = etopo_paths(fetch_extent(load_region(region), region.parent), cache)
    tiles[0].parent.mkdir(parents=True)
    for tile in tiles:
        shutil.copy(fixtures_dir / "cudem_possession_bar.tif", tile)
    with pytest.raises(Stop):
        main(args)
    assert seen[-1] == tiles


# PR #122 review F5 and F6: the asset checks name the file and the fetch workflow, never a traceback.

def _fetch_with(monkeypatch, served):
    """cli.download serves `served` (file name -> bytes) from the release; a missing file fails like a 404."""
    from chartpack import cli
    from chartpack.cache import DownloadError

    def fake_download(url, dest, *, expected_size=None, timeout=120):
        name = url.removeprefix(SOURCES_BASE)
        if name not in served:
            raise DownloadError(f"{url}: HTTP Error 404: Not Found")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(served[name])
        return dest

    monkeypatch.setattr(cli, "download", fake_download)
    monkeypatch.setattr(cli, "fetch_crm", lambda bbox, cache: None)
    monkeypatch.setattr(geoid, "fetch_grids", lambda p: None)


def test_fetch_bathy_needs_no_coastline(tmp_path, regions_dir, monkeypatch, capsys):
    """F6: stats from a NONNA-only fetch (no coastline entry, no coastline asset): fetch-bathy downloads the NONNA
    grids and asks nothing about the coastline."""
    import json

    region = _nonna_region(tmp_path, regions_dir)
    served = _write_assets(tmp_path / "release", region)
    del served["coast-toba.geojson.gz"]
    stats = json.loads(served["fetch-stats-toba.json"])
    del stats["files"]["coast-toba.geojson.gz"]
    served["fetch-stats-toba.json"] = json.dumps(stats).encode()
    _fetch_with(monkeypatch, served)
    assert main(["fetch-bathy", str(region), "--cache", str(tmp_path / "cache")]) == 0
    assert (tmp_path / "cache" / "sources-bc-1" / "nonna100-toba.tif").is_file()
    capsys.readouterr()


@pytest.mark.parametrize("case, match", [
    ("no stats", r"fetch-stats-toba\.json.*chartpack-sources\.yml"),
    ("no files key", r"fetch-stats-toba\.json.*chartpack-sources\.yml"),
    ("no entry", r"nonna100-toba\.tif.*fetch-stats-toba\.json.*chartpack-sources\.yml"),
])
def test_fetch_bathy_stats_problems_are_clean_errors(tmp_path, regions_dir, monkeypatch, capsys, case, match):
    """F6: a release without the stats file, a stats file without `files`, or one without a needed NONNA entry
    stops fetch-bathy with a message naming the file and the fetch workflow."""
    import json

    region = _nonna_region(tmp_path, regions_dir)
    served = _write_assets(tmp_path / "release", region)
    stats = json.loads(served["fetch-stats-toba.json"])
    if case == "no stats":
        del served["fetch-stats-toba.json"]
    elif case == "no files key":
        del stats["files"]
    else:
        del stats["files"]["nonna100-toba.tif"]
    if case != "no stats":
        served["fetch-stats-toba.json"] = json.dumps(stats).encode()
    _fetch_with(monkeypatch, served)
    with pytest.raises(SystemExit, match=match):
        main(["fetch-bathy", str(region), "--cache", str(tmp_path / "cache")])


@pytest.mark.parametrize("case", ["stale mosaic", "no entry", "no files key"])
def test_build_bathy_checks_the_assets_against_the_stats(tmp_path, fixtures_dir, regions_dir, monkeypatch,
                                                         zero_geoid, case):
    """F5: new stats beside a stale mosaic (or stats that do not list the asset) fail the build before any block,
    naming the file and the fetch workflow."""
    import json

    from chartpack import cli

    region = _nonna_region(tmp_path, regions_dir)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    folder = cache / "sources-bc-1"
    _write_assets(folder, region)
    stats_path = folder / "fetch-stats-toba.json"
    stats = json.loads(stats_path.read_text())
    if case == "stale mosaic":
        stats["files"]["nonna10-toba.tif"]["sha256"] = "0" * 64  # the stats of a newer fetch
    elif case == "no entry":
        del stats["files"]["nonna10-toba.tif"]
    else:
        del stats["files"]
    stats_path.write_text(json.dumps(stats))
    monkeypatch.setattr(cli, "build_block", lambda *a, **k: pytest.fail("built from an unchecked asset"))
    with pytest.raises(SystemExit, match=r"nonna10-toba\.tif.*chartpack-sources\.yml|fetch-stats-toba\.json.*"
                                         r"chartpack-sources\.yml"):
        main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "w")])


# ---- plan 8 Task 11: the charts build at the Canada polygon (spec 7.1, 7.2)

def test_enc_region_without_canada_builds_as_before(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """A region none of whose owned tiles meets the Canada polygon: the guards run on its cells, and the layer files
    reaching tippecanoe are the old path's (build_enc_mbtiles with no polygon and nothing derived)."""
    from chartpack import cli
    from chartpack.bathy.blocks import BLOCK_MARGIN_DEG
    from chartpack.enc import tiles
    from chartpack.enc.reader import read_cell
    from chartpack.grid import owned_tiles, tiles_area
    from chartpack.region import load_region

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    region = _grid_region(tmp_path, regions_dir)
    guards = []
    check_notices, check_canadian_areas = cli.check_notices, cli.check_canadian_areas
    monkeypatch.setattr(cli, "check_notices", lambda cells, canada: guards.append(
        ("notices", [name for name, _ in cells])) or check_notices(cells, canada))
    monkeypatch.setattr(cli, "check_canadian_areas", lambda cells, canada, owned: guards.append(
        ("areas", [c[0] for c in cells])) or check_canadian_areas(cells, canada, owned))
    monkeypatch.setattr(cli, "build_block", lambda *a, **k: pytest.fail("no block is derived"))
    monkeypatch.setattr(tiles, "run", lambda cmd: None)
    with pytest.raises(Exception):  # the patched run writes no mbtiles: only the tippecanoe input matters
        main(["build-enc", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "new")])
    assert guards == [("notices", ["US4WA1HK"]), ("areas", ["US4WA1HK"])]
    loaded = load_region(region)
    with pytest.raises(Exception):
        tiles.build_enc_mbtiles([read_cell(fixtures_dir / "US4WA1HK.zip")], tmp_path / "old" / "enc.mbtiles",
                                region=loaded, work=tmp_path / "old", zooms=tiles.REGION_ZOOMS,
                                area=tiles_area(owned_tiles(loaded, region.parent), BLOCK_MARGIN_DEG))
    new = sorted(p.name for p in (tmp_path / "new" / "tippecanoe").glob("*.geojsonseq"))
    assert new and new == sorted(p.name for p in (tmp_path / "old").glob("*.geojsonseq"))
    for name in new:
        assert (tmp_path / "new" / "tippecanoe" / name).read_text() == (tmp_path / "old" / name).read_text(), name


def _levels(regions_dir):
    import tomllib

    return tomllib.loads((regions_dir / "bc-valdco.toml").read_text())["levels_m"]


NORTH, SOUTH = (163, 356), (163, 357)  # two zoom-10 tiles stacked north-south near Kingston
EAST = (164, 356)  # east of NORTH: their shared edge (x = 164, not a multiple of 3) is not on a 96 px cell edge
_UNIT16 = 360 / 2**16 / 4096  # one tile unit at zoom 16, in degrees of longitude


@pytest.fixture
def small_blocks(monkeypatch, zero_geoid):
    """The block grids at 0.0004 and 0.0012 degree (as test_bathy_blocks), so a whole zoom-10 block stays small."""
    from chartpack.bathy import blocks

    monkeypatch.setattr(blocks, "FINE_RES_DEG", 0.0004)
    monkeypatch.setattr(blocks, "COARSE_RES_DEG", 0.0012)


def _slope_nonna(tmp_path, tiles):
    """A NONNA-100 mosaic over the read boxes of tiles: depth from 2 m in the north to about 90 m in the south, with
    a wiggle across, so every band of the derived features has many depth areas."""
    import numpy as np
    from test_bathy_blocks import _write_nonna_over

    from chartpack.bathy.blocks import iter_blocks

    reads = [read for _, _, read in iter_blocks(set(tiles))]
    area = (min(r[0] for r in reads) - 0.01, min(r[1] for r in reads) - 0.01, max(r[2] for r in reads) + 0.01,
            max(r[3] for r in reads) + 0.01)
    return _write_nonna_over(tmp_path / "n100.tif", "nonna100", area, lambda lon, lat: -(
        2.0 + 160.0 * (area[3] - lat) + 3.0 * np.sin(lon * 300.0)))


def _region(regions_dir, kind):
    import dataclasses

    from chartpack.region import load_region

    return dataclasses.replace(load_region(regions_dir / "test-cell.toml"), charts_kind=kind)


def _derive_tile(tile, region, owners, canada, nonna100, regions_dir, *, etopo=None, land=None, outline=None):
    from shapely.geometry import Polygon

    from chartpack import cli
    from chartpack.bathy.blocks import BlockSources, area_datum, iter_blocks

    _, core, read = next(iter_blocks({tile}))
    land = Polygon() if land is None else land
    return core, cli._derived_block(tile, core, read, BlockSources([], None, None, nonna100, etopo),
                                    area_datum(region, Path("unused")), region, owners, canada,
                                    levels_m=_levels(regions_dir), land=land, nosurvey=Polygon(),
                                    outline=canada.boundary if outline is None else outline)


def _band_areas(features, lo, **match):
    from shapely import union_all
    from shapely.geometry import shape

    return union_all([shape(f.geometry) for f in features if f.layer == "depare" and f.props["tippecanoe"]["minzoom"]
                      == lo and all(f.props.get(k) == v for k, v in match.items())])


def _thin(geom):
    """No part of geom is wider than one zoom-16 tile unit."""
    return geom.is_empty or geom.buffer(-_UNIT16 / 2).is_empty


def test_noaa_and_derived_meet_on_one_line(tmp_path, regions_dir, small_blocks):
    """A US-owned tile across the polygon: the NOAA depare cut at the polygon and the derived depare made for the
    charts side leave no gap and no overlap wider than one tile unit, at every band."""
    from shapely.geometry import box, mapping

    from chartpack.bathy.contours import BANDS
    from chartpack.enc.bc import apply_rules
    from chartpack.enc.reader import Feature
    from chartpack.grid import tile_bounds

    region = _region(regions_dir, "enc")
    nonna100 = _slope_nonna(tmp_path, [NORTH])
    w, s, e, n = tile_bounds(10, *NORTH)
    mid = (s + n) / 2 + 0.00013
    canada = box(w - 1, mid, e + 1, n + 1).union(box(w + 0.1, s + 0.05, w + 0.15, mid))  # a notch into the US part
    core, derived = _derive_tile(NORTH, region, {NORTH: region}, canada, nonna100, regions_dir)
    noaa = Feature("depare", mapping(box(*core)), {"cell": "US4AAAAA", "band": 4, "class": "DEPARE", "DRVAL1": "0",
                                                   "DRVAL2": "5", "tippecanoe": {"minzoom": 10, "maxzoom": 16}})
    out = apply_rules([noaa], derived, canada)
    kept = _band_areas(out, 10, cell="US4AAAAA")
    assert kept.equals(box(*core).difference(canada))
    for lo, _, _ in BANDS:
        mine = _band_areas(out, lo, src="nonna100")
        assert not mine.is_empty, lo
        assert _thin(mine.intersection(kept)), lo
        assert _thin(box(*core).difference(mine.union(kept))), lo


def test_adjacent_blocks_depare_meet_at_every_band(tmp_path, regions_dir, small_blocks):
    """Two adjacent BC-owned blocks, each derived from its own read box: no gap and no overlap in depare along their
    shared core edge, at every band (nav_depth reaches past the core, so the core edge is inside both grids)."""
    from shapely.geometry import box

    from chartpack.bathy.contours import BANDS

    region = _region(regions_dir, "derived-inshore")
    owners = {NORTH: region, SOUTH: region}
    canada = box(-130, 40, -110, 55)
    nonna100 = _slope_nonna(tmp_path, [NORTH, SOUTH])
    north, a = _derive_tile(NORTH, region, owners, canada, nonna100, regions_dir)
    south, b = _derive_tile(SOUTH, region, owners, canada, nonna100, regions_dir)
    assert north[1] == south[3]
    both = box(*north).union(box(*south))
    for lo, _, _ in BANDS:
        da, db = _band_areas(a, lo), _band_areas(b, lo)
        assert box(*north).covers(da) and box(*south).covers(db), lo
        assert _thin(da.intersection(db)), lo
        assert _thin(both.difference(da.union(db))), lo


def test_adjacent_blocks_one_sounding_per_cell(tmp_path, regions_dir, small_blocks):
    """A 96 px sounding cell across the shared core edge of two blocks gets one sounding at each zoom, from the block
    holding its center. A zoom-10 tile edge is on a sounding cell edge only when its index is a multiple of 3
    (256 px tiles, 96 px cells), so NORTH and EAST, meeting at x = 164, share straddling cells at every zoom."""
    import math
    from collections import Counter

    from shapely.geometry import box

    from chartpack.enc.derived import SOUNDING_PX
    from chartpack.grid import tile_bounds

    region = _region(regions_dir, "derived-inshore")
    owners = {NORTH: region, EAST: region}
    nonna100 = _slope_nonna(tmp_path, [NORTH, EAST])
    canada = box(-130, 40, -110, 55)
    edge = tile_bounds(10, *EAST)[0]
    cells = Counter()
    for tile in (NORTH, EAST):
        _, feats = _derive_tile(tile, region, owners, canada, nonna100, regions_dir)
        for f in feats:
            if f.layer == "soundg":
                z = f.props["tippecanoe"]["minzoom"]
                lon, lat = f.geometry["coordinates"]
                world = 256 * 2**z
                kx = math.floor((lon + 180) / 360 * world / SOUNDING_PX)
                ky = math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * world / SOUNDING_PX)
                cells[(z, kx, ky)] += 1
    assert cells and max(cells.values()) == 1, [k for k, v in cells.items() if v > 1][:5]
    for z in range(10, 17):  # the column of cells across the edge keeps its soundings at every zoom
        straddling = math.floor((edge + 180) / 360 * 256 * 2**z / SOUNDING_PX)
        assert (edge + 180) / 360 * 256 * 2**z / SOUNDING_PX % 1 > 0, z
        assert any(k[0] == z and k[1] == straddling for k in cells), z


def test_derived_coalne_not_on_polygon_or_box_edge(tmp_path, regions_dir, small_blocks):
    """The land asset is cut to its box and to the Canada polygon by the derive stage: no derived coalne is drawn
    along either cut (the 49th parallel on land is not a coastline); the real coast is kept."""
    from shapely import union_all
    from shapely.geometry import LineString, box, shape

    from chartpack.enc.bc import apply_rules
    from chartpack.grid import tile_bounds

    w, s, e, n = tile_bounds(10, *NORTH)
    region = _region(regions_dir, "derived-inshore")
    canada = box(w - 1, s + 0.1, e + 1, n + 1)  # its south edge crosses the tile on land
    extent = (w - 1, s - 1, w + 0.2, n + 1)  # the land asset's box edge at w + 0.2, inside the tile
    land = box(w + 0.05, s + 0.05, w + 0.3, s + 0.15).intersection(canada).intersection(box(*extent))
    outline = canada.boundary.union(box(*extent).boundary)
    nonna100 = _slope_nonna(tmp_path, [NORTH])
    _, feats = _derive_tile(NORTH, region, {NORTH: region}, canada, nonna100, regions_dir, land=land,
                            outline=outline)
    real = union_all([shape(f.geometry) for f in apply_rules([], feats, canada) if f.layer == "coalne"])
    assert real.intersection(outline.buffer(1e-9)).length == 0
    expected = LineString([(w + 0.05, s + 0.1), (w + 0.05, s + 0.15), (w + 0.2, s + 0.15)])
    assert real.length == pytest.approx(expected.length, rel=1e-6)
    assert real.buffer(1e-7).covers(expected.difference(outline.buffer(2e-7)))


def test_offshore_inside_polygon_from_nonna100_then_coarse(tmp_path, regions_dir, small_blocks):
    """An offshore BC tile inside the polygon: derived depare with src nonna100 where NONNA-100 has data, etopo
    elsewhere, at every band; no NOAA depare is left there."""
    import numpy as np
    from shapely.geometry import Point, box, mapping, shape
    from test_bathy_blocks import _write_grid, _write_nonna_over

    from chartpack.bathy.contours import BANDS
    from chartpack.enc.bc import apply_rules
    from chartpack.enc.reader import Feature
    from chartpack.grid import tile_bounds

    w, s, e, n = tile_bounds(10, *NORTH)
    cx, cy = (w + e) / 2, (s + n) / 2
    patch = (cx - 0.05, cy - 0.05, cx + 0.05, cy + 0.05)
    nonna100 = _write_nonna_over(tmp_path / "n100.tif", "nonna100", patch, lambda lon, lat: -(  # a seamount
        21.0 + 1000.0 * np.hypot(lon - cx, lat - cy)))
    etopo = _write_grid(tmp_path / "etopo.tif", -300.0, (-123.0, 47.25, -122.0, 48.25))
    region = _region(regions_dir, "derived-offshore")
    canada = box(-130, 40, -110, 55)
    core, derived = _derive_tile(NORTH, region, {NORTH: region}, canada, nonna100, regions_dir, etopo=etopo)
    noaa = Feature("depare", mapping(box(*core)), {"cell": "US1AAAAA", "band": 1, "class": "DEPARE",
                                                   "DRVAL1": "0", "DRVAL2": "5000",
                                                   "tippecanoe": {"minzoom": 10, "maxzoom": 16}})
    out = apply_rules([noaa], derived, canada)
    assert not [f for f in out if f.layer == "depare" and "src" not in f.props]
    for lo, _, _ in BANDS:
        at = {name: [f.props["src"] for f in out if f.layer == "depare" and f.props["tippecanoe"]["minzoom"] == lo
                     and shape(f.geometry).contains(p)]
              for name, p in (("seamount", Point(cx, cy)), ("deep", Point(w + 0.02, n - 0.02)))}
        assert at == {"seamount": ["nonna100"], "deep": ["etopo"]}, lo


def test_no_enc_fallback_contour_inside_canada(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys, zero_geoid):
    """The ENC fallback contours of a bathy pack are cut at the Canada polygon (the Juan de Fuca strip is inside it
    though canada-wa.geojson, the depth side, calls it US): a contour across it keeps only its outside part, one
    wholly inside is dropped."""
    import json

    from shapely import union_all
    from shapely.geometry import box, shape

    from chartpack import cli
    from chartpack.bathy import blocks

    region = _bathy_region(tmp_path, regions_dir)
    region.write_text('coarse_fallback = "enc"\n' + region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["cudem"]'))
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, ["https://example.test/ncei19_n48x00_w122x50_2023v1.tif"])
    shutil.rmtree(cache / "crm")

    def fake_read_window(src, bbox):
        grid = _fixture_window(fixtures_dir, bbox)
        grid.data[:, : grid.data.shape[1] // 2] = grid.nodata  # the CUDEM tile covers only the east half
        return grid

    monkeypatch.setattr(blocks, "read_window", fake_read_window)

    def enc_lines(work):
        assert main(["build-bathy", str(region), str(tmp_path / work), "--cache", str(cache), "--work",
                     str(tmp_path / work / "w")]) == 0
        capsys.readouterr()
        rows = [json.loads(line) for line in (tmp_path / work / "w" / "tippecanoe" / "contour.geojsonseq").read_text()
                .splitlines()]
        return [shape(f["geometry"]) for f in rows if f["properties"]["source"] == "enc"]

    before = enc_lines("before")  # the Canada polygon far away
    strip = box(-122.45, 47.85, -122.383, 47.95)  # over the west part of the ENC-fallback half
    assert any(strip.contains(line) for line in before) and any(line.crosses(strip.boundary) for line in before)
    monkeypatch.setattr(cli, "load_canada", lambda regions: strip)
    after = enc_lines("after")
    assert after and union_all(after).intersection(strip).length < 1e-12
    assert union_all(after).symmetric_difference(union_all(before).difference(strip)).length < 1e-9


def test_check_passes_the_repo_canada_polygon(charts_pack_root_copy, regions_dir, monkeypatch, capsys):
    from chartpack import cli
    from chartpack.enc.bc import load_canada

    got = []
    monkeypatch.setattr(cli, "check_pack", lambda root, *, enc_zips=None, canada=None: got.append(canada) or [])
    assert main(["check", str(charts_pack_root_copy)]) == 0
    assert len(got) == 1 and got[0].equals(load_canada(regions_dir))


def test_build_enc_derived_region_end_to_end(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys, zero_geoid):
    """build-enc of a BC inshore region across the Canada polygon (a stand-in with a diagonal edge through the tile,
    densified as load_canada does): no NOAA feature is left inside it, the derived depth and land are, the inputs
    and the notices are recorded, and the pack passes the check with that polygon. The no-survey asset is a
    triangle over the NONNA data, so both of the check's tolerances meet edges tippecanoe moved."""
    import gzip
    import json

    import shapely
    from shapely.geometry import Polygon, box, mapping, shape

    from chartpack.enc.bc import SEGMENT_DEG

    from chartpack import cli
    from chartpack.grid import fetch_extent, owned_tiles, tiles_area
    from chartpack.mbtiles import MBTiles
    from chartpack.pack.assemble import CHS_NOTICE, OGL_BC_NOTICE
    from chartpack.pack.check import check_pack
    from chartpack.region import load_region

    canada = shapely.segmentize(Polygon([(-122.6, 47.5), (-122.0, 47.5), (-122.0, 48.5), (-122.3, 48.5),
                                         (-122.41, 47.95), (-122.42, 47.86)]), SEGMENT_DEG)
    monkeypatch.setattr(cli, "load_canada", lambda regions: canada)
    region = _nonna_region(tmp_path, regions_dir)
    shutil.copy(regions_dir / "bc-valdco.toml", region.parent)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    folder = cache / "sources-bc-1"
    _write_assets(folder, region)
    extent = fetch_extent(load_region(region), region.parent)
    nosurvey = Polygon([(-122.399, 47.881), (-122.37, 47.919), (-122.361, 47.885)])
    land = box(-122.395, 47.885, -122.390, 47.890).difference(nosurvey)
    for name, geoms in (("land-toba.geojson.gz", [land]), ("nosurvey-toba.geojson.gz", [nosurvey])):
        features = [{"type": "Feature", "properties": {}, "geometry": mapping(g)} for g in geoms]
        (folder / name).write_bytes(gzip.compress(json.dumps({"type": "FeatureCollection",
                                                              "features": features}).encode()))
    _write_derive_stats(folder, extent)
    _no_network(monkeypatch)
    assert main(["build-enc", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work",
                 str(tmp_path / "work")]) == 0
    capsys.readouterr()
    root = tmp_path / "out" / "charts-test-cell-0.1.0"
    with MBTiles.open(root / "enc.mbtiles") as m:
        md = m.metadata()
    assert [d["source"] for d in json.loads(md["cheekymarine:depth_sources"])] == ["nonna10", "nonna100", "fwa",
                                                                                 "nosurvey"]
    assert md["cheekymarine:data_notice"] == f"{CHS_NOTICE}\n\n{OGL_BC_NOTICE}"
    areas = json.loads(md["cheekymarine:notice_areas"])["features"]
    owned = tiles_area(owned_tiles(load_region(region), region.parent))
    assert len(areas) == 1 and shape(areas[0]["geometry"]).symmetric_difference(owned.intersection(canada)).area < 1e-12
    notice = (root / "NOTICE").read_text()
    assert CHS_NOTICE in notice and OGL_BC_NOTICE in notice
    assert json.loads((root / "manifest.json").read_text())["charts"] == {"kind": "derived-inshore"}
    assert check_pack(root, canada=canada) == []


def test_build_enc_canadian_tiles_without_nonna_fail(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """A region whose owned tiles meet the Canada polygon but which lists no NONNA source would draw blank Canadian
    water (the NOAA cut, nothing derived): the build stops naming the region, before anything is tiled."""
    from shapely.geometry import box

    from chartpack import cli

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    region = _grid_region(tmp_path, regions_dir)
    monkeypatch.setattr(cli, "load_canada", lambda regions: box(-123.0, 47.5, -122.0, 48.5))
    monkeypatch.setattr(cli, "build_enc_mbtiles", lambda *a, **k: pytest.fail("built with blank Canadian water"))
    with pytest.raises(SystemExit, match=r"region test-cell: .*Canada polygon.*NONNA"):
        main(["build-enc", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])


def _overview_over_bc(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """A grid of one BC inshore region (the bathy test region as test-cell, assets toba, with its fetched and derived
    assets in the cache) and an overview ov over it reading NONNA-100 and CRM. Returns (overview path, cache)."""
    import gzip
    import json

    from shapely.geometry import box, mapping

    from chartpack.bathy.blocks import overview_bounds
    from chartpack.bathy.crm import crm_path
    from chartpack.grid import fetch_extent
    from chartpack.region import load_region

    region = _nonna_region(tmp_path, regions_dir)
    region = region.rename(region.with_name("test-cell.toml"))
    shutil.copy(regions_dir / "bc-valdco.toml", region.parent)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    folder = cache / "sources-bc-1"
    _write_assets(folder, region)
    land = box(-122.395, 47.885, -122.390, 47.890)
    for name, geom in (("land-toba.geojson.gz", land), ("nosurvey-toba.geojson.gz", box(-122.37, 47.915, -122.365,
                                                                                          47.918))):
        features = [{"type": "Feature", "properties": {}, "geometry": mapping(geom)}]
        (folder / name).write_bytes(gzip.compress(json.dumps({"type": "FeatureCollection",
                                                              "features": features}).encode()))
    _write_derive_stats(folder, fetch_extent(load_region(region), region.parent))
    overview = region.with_name("ov.toml")
    overview.write_text("overview = true\n" + (regions_dir / "test-cell.toml").read_text()
                        .replace('name = "test-cell"', 'name = "ov"')
                        .replace('sources = ["cudem", "crm"]', 'sources = ["nonna100", "crm"]'))
    path = crm_path(overview_bounds(load_region(overview).bbox), cache)
    shutil.copy(fixtures_dir / "cudem_possession_bar.tif", path)
    return overview, cache


def test_overview_charts_never_open_nonna10(tmp_path, fixtures_dir, regions_dir, monkeypatch, capsys, zero_geoid):
    """The overview's charts build draws its Canadian water from the stored land and no-survey assets of every BC
    region and the coarse depth (NONNA-100 through one VRT): a spy on every way the build opens a file or a raster
    sees the NONNA-100 asset and never a NONNA-10 one. build-enc hands the derived depth and land and their inputs
    to the tiling, at the overview's zooms."""
    import argparse

    from osgeo import gdal
    from shapely.geometry import box

    from chartpack import cli
    from chartpack.bathy import blocks
    from chartpack.grid import content_tiles
    from chartpack.region import load_region

    overview, cache = _overview_over_bc(tmp_path, fixtures_dir, regions_dir, monkeypatch)
    canada = box(-123.0, 47.5, -122.385, 48.5)  # the west part of the tile: the NOAA cell keeps its east part
    monkeypatch.setattr(cli, "load_canada", lambda regions: canada)
    seen = []

    def spy(module, name):
        real = getattr(module, name)

        def wrapper(*args, **kwargs):
            for value in list(args) + list(kwargs.values()):
                for item in value if isinstance(value, (list, tuple)) else [value]:
                    seen.append(str(item))
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, wrapper)

    for name in ("Open", "OpenEx", "Warp", "Translate", "BuildVRT"):
        spy(gdal, name)
    spy(cli, "_sha256")
    spy(cli, "_read_polygons")
    spy(blocks, "read_nonna")
    _no_network(monkeypatch)
    ov = load_region(overview)
    args = argparse.Namespace(region=overview, cache=cache, work=tmp_path / "work")
    features, depth_sources = cli._overview_derived(args, ov, content_tiles(ov, overview.parent), canada)
    assert not [p for p in seen if "nonna10-" in p]
    assert [p for p in seen if p.endswith("nonna100-toba.tif")]
    assert "nonna10-" not in (tmp_path / "work" / "nonna100.vrt").read_text()
    assets = {d["asset"] for d in depth_sources}  # the build keeps those its features come from
    assert {"nonna100-toba.tif", "land-toba.geojson.gz", "nosurvey-toba.geojson.gz"} <= assets
    assert not [a for a in assets if a.startswith("nonna10-")]
    srcs = {(f.layer, f.props.get("src")) for f in features}
    assert ("depare", "nonna100") in srcs and ("lndare", "fwa") in srcs
    assert not [f for f in features if f.props.get("src") in ("nonna10", "crm", "etopo")]  # inshore: NONNA only
    assert all(f.props["tippecanoe"]["minzoom"] >= 6 and f.props["tippecanoe"]["maxzoom"] <= 9 for f in features)
    assert not [f for f in features if f.layer == "soundg"]

    seen.clear()
    built = []

    def stop(*args, **kwargs):  # tippecanoe of the overview cell is not the point: what reaches it is
        built.append(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr(cli, "build_enc_mbtiles", stop)
    with pytest.raises(RuntimeError, match="stop"):
        main(["build-enc", str(overview), str(tmp_path / "out"), "--cache", str(cache), "--work",
              str(tmp_path / "work")])
    assert not [p for p in seen if "nonna10-" in p]
    (kwargs,) = built
    assert kwargs["canada"] is canada and kwargs["zooms"] == (6, 9)
    assert {(f.layer, f.props.get("src")) for f in kwargs["derived"]} == srcs
    assert kwargs["depth_sources"] == depth_sources


def test_build_enc_overview_without_nonna100_meeting_canada_stops(tmp_path, fixtures_dir, regions_dir, monkeypatch):
    """An overview whose content tiles meet the Canada polygon but which lists no NONNA-100 would leave its Canadian
    water blank after the NOAA cut: the build stops naming the region, before anything is tiled."""
    from shapely.geometry import box

    from chartpack import cli

    (tmp_path / "cache" / "enc").mkdir(parents=True)
    shutil.copy(fixtures_dir / "US4WA1HK.zip", tmp_path / "cache" / "enc" / "US4WA1HK-1.3.zip")
    pack = _grid_region(tmp_path, regions_dir)
    overview = pack.with_name("ov.toml")
    overview.write_text("overview = true\n" + pack.read_text().replace('name = "test-cell"', 'name = "ov"')
                        .replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    monkeypatch.setattr(cli, "load_canada", lambda regions: box(-123.0, 47.5, -122.0, 48.5))
    monkeypatch.setattr(cli, "build_enc_mbtiles", lambda *a, **k: pytest.fail("built with blank Canadian water"))
    with pytest.raises(SystemExit, match=r"region ov: .*Canada polygon.*NONNA-100"):
        main(["build-enc", str(overview), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])


def test_derived_coalne_drop_on_real_land_asset_geometry():
    """The same drop on land as coast.land_polygons makes it (faces in BC Albers meters, back to lon/lat, cut to the
    box and to a densified polygon with a long diagonal edge): its cut edges lie on the outline to float noise
    (measured 3e-14 degree, far under _OUTLINE_TOL_DEG), no coalne is left on the box edge or the polygon's
    boundary, and the real coast is kept whole."""
    from types import SimpleNamespace

    import numpy as np
    import shapely
    from shapely.geometry import LineString, Polygon, box, shape
    from test_coast import LAND_BOX, _water_points

    from chartpack import cli
    from chartpack.bathy.cudem import Grid
    from chartpack.coast import land_polygons
    from chartpack.enc.bc import SEGMENT_DEG

    canada = shapely.segmentize(Polygon([(-125.0, 49.52), (-123.0, 49.56), (-123.0, 50.0), (-125.0, 50.0)]),
                                SEGMENT_DEG)
    coast = LineString([(-123.95, 49.49), (-123.95, 49.61)])  # land to the west, cut by the diagonal edge
    area = box(*LAND_BOX).intersection(canada)
    expected_land = area.intersection(box(-124.0, 49.4, -123.95, 49.7))
    land, *_ = land_polygons([coast], LAND_BOX, canada, _water_points(area, expected_land), Polygon(), cell_m=10.0)
    assert land.symmetric_difference(expected_land).area < 1e-9
    outline = canada.boundary.union(box(*LAND_BOX).boundary)
    cut_edges = [p for p in shapely.points(shapely.get_coordinates(land.boundary)) if coast.distance(p) > 1e-6]
    assert max(outline.distance(p) for p in cut_edges) < cli._OUTLINE_TOL_DEG / 1000
    core = (-124.05, 49.45, -123.85, 49.65)
    nav = Grid(np.full((4, 4), np.nan, np.float32), np.nan, (core[0], 0.05, 0.0, core[3], 0.0, -0.05), "")
    r = SimpleNamespace(nav_depth=nav, nav_src=np.zeros((4, 4), np.int8), coarse_grid=None, coarse_source=None)
    feats = cli._tile_derived(r, "derived-inshore", core, box(*core), levels_m=[0, 5], land=land,
                              nosurvey=Polygon(), outline=outline)
    real = shapely.union_all([shape(f.geometry) for f in feats if f.layer == "coalne"])
    expected = LineString([(-123.95, 49.52 + 0.04 * 1.05 / 2), (-123.95, 49.6)])
    assert real.intersection(outline.buffer(1e-9)).length == 0
    assert abs(real.length - expected.length) < 1e-6 and real.hausdorff_distance(expected) < 1e-6


def _write_derive_stats(folder, extent, inputs=None):
    """derive-stats-toba.json over extent, derived from the inputs (default: the files fetch-stats-toba.json lists
    now, as derive-sources records them)."""
    import json

    if inputs is None:
        files = json.loads((folder / "fetch-stats-toba.json").read_text())["files"]
        inputs = {name: entry["sha256"] for name, entry in files.items()}
    stats = {"extent": [round(v, 9) for v in extent], **({} if inputs is False else {"inputs": inputs})}
    (folder / "derive-stats-toba.json").write_text(json.dumps(stats))


@pytest.mark.parametrize("case", ["match", "new fetch", "old stats"])
def test_build_enc_checks_the_derive_inputs(tmp_path, fixtures_dir, regions_dir, monkeypatch, zero_geoid, case):
    """The land and no-survey assets must come from the NONNA and coastline files of the current fetch: derive-stats
    records their sha256 and the build compares them with fetch-stats. A fetch run again without stage derive, or
    derive-stats from before the hashes, stops the build telling the owner to run stage derive again."""
    import gzip
    import json

    from shapely.geometry import box

    from chartpack import cli
    from chartpack.grid import fetch_extent
    from chartpack.region import load_region

    monkeypatch.setattr(cli, "load_canada", lambda regions: box(-123.0, 47.5, -122.0, 48.5))
    region = _nonna_region(tmp_path, regions_dir)
    shutil.copy(regions_dir / "bc-valdco.toml", region.parent)
    cache = _bathy_cache(tmp_path, fixtures_dir, region, monkeypatch, [])
    folder = cache / "sources-bc-1"
    _write_assets(folder, region)
    for name in ("land-toba.geojson.gz", "nosurvey-toba.geojson.gz"):
        (folder / name).write_bytes(gzip.compress(b'{"type": "FeatureCollection", "features": []}'))
    extent = fetch_extent(load_region(region), region.parent)
    if case == "match":
        _write_derive_stats(folder, extent)
    elif case == "new fetch":
        files = json.loads((folder / "fetch-stats-toba.json").read_text())["files"]
        _write_derive_stats(folder, extent,
                            {**{n: e["sha256"] for n, e in files.items()}, "nonna10-toba.tif": "0" * 64})
    else:
        _write_derive_stats(folder, extent, False)
    monkeypatch.setattr(cli, "build_block", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("past the check")))
    args = ["build-enc", str(region), str(tmp_path / "out"), "--cache", str(cache), "--work", str(tmp_path / "w")]
    if case == "match":
        with pytest.raises(RuntimeError, match="past the check"):
            main(args)
    else:
        with pytest.raises(SystemExit, match=r"region test-cell: derive-stats-toba\.json .*stage derive .*again"):
            main(args)
