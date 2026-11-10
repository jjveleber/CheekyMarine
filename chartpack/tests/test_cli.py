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

    _fixture_catalog(monkeypatch, fixtures_dir)
    for name in ["sound-south", "sound-central", "north-sound", "strait", "wa-coast", "overview"]:
        path = regions_dir / f"{name}.toml"
        for band, names in load_region(path).cells.items():
            assert main(["cells", str(path), "--band", str(band), "--cache", str(tmp_path / "cache")]) == 0
            assert capsys.readouterr().out.split() == names, (name, band)


def _grid_region(tmp_path, regions_dir):
    """A copy of test-cell.toml next to a grid.toml that lists it: build-enc reads the grid beside the region file."""
    import shutil

    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "grid.toml").write_text('zoom = 10\norder = ["test-cell"]\n')
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
    from shapely.geometry import box, mapping, shape

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
    read_cell = cli.read_cell
    monkeypatch.setattr(cli, "read_cell", lambda path: band1 if path.name.startswith("US1") else read_cell(path))
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
    from shapely.geometry import box, mapping

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
    polygonized at COVERAGE_CELL_DEG, wider than this lake, so it follows the mask only to that size, as for the
    clip: test_clip_removes_water_in_block.)"""
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
    """The overview's one CRM read is cut by the same lake mask as the region packs."""
    from shapely.geometry import box

    from chartpack import cli
    from chartpack.bathy.blocks import overview_bounds
    from chartpack.bathy.crm import crm_path

    region = _bathy_region(tmp_path, regions_dir)
    region.write_text("overview = true\n" + region.read_text().replace('sources = ["cudem", "crm"]', 'sources = ["crm"]'))
    lake = box(-122.382, 47.898, -122.378, 47.902)
    _mask_lake(region, lake)
    path = crm_path(overview_bounds((-122.3846, 47.8954, -122.3754, 47.9046)), tmp_path / "cache")
    path.parent.mkdir(parents=True)
    path.touch()
    clips = []

    def fake_overview(bbox, crm, datum, clip):
        clips.append(clip)
        raise RuntimeError("stop")

    monkeypatch.setattr(cli, "build_overview", fake_overview)
    with pytest.raises(RuntimeError, match="stop"):
        main(["build-bathy", str(region), str(tmp_path / "out"), "--cache", str(tmp_path / "cache"),
              "--work", str(tmp_path / "work")])
    assert clips[0] is not None and clips[0].covers(lake)


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
