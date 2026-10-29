import pytest
import shapely
from osgeo import ogr, osr
from shapely import wkb
from shapely.geometry import box, shape

from chartpack.enc.scamin import extent_z0, minzoom_for_extent
from chartpack.seabed import cmecs
from chartpack.seabed.cmecs import BLOCKS, MINZOOM, fetch_cmecs, read_cmecs
from chartpack.seabed.codes import cmecs_label

ogr.UseExceptions()

TEST_CELL = (-122.4, 47.7, -122.1, 48.0)
PUGET = (-123.0, 47.0, -122.0, 48.5)


def _path(fixtures_dir, block):
    return fixtures_dir / "seabed" / f"{BLOCKS[block].name}.zip"


def _ogr_polygons(path, name):
    """(raw fields, WGS84 shapely geometry) of each polygon, read and reprojected here independently."""
    ds = ogr.Open(f"/vsizip/{path}/{name}.shp")
    layer = ds.GetLayer(0)
    src = layer.GetSpatialRef()
    assert src.GetAuthorityCode(None) == "26910"  # NAD83 / UTM zone 10N
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, dst)
    out = []
    for f in layer:
        g = f.GetGeometryRef().Clone()
        g.Transform(ct)
        out.append((f.items(), shapely.make_valid(wkb.loads(bytes(g.ExportToWkb())))))
    return out


# block -> {substrate name: label} expected from the fixture polygons
EXPECTED = {
    "admiralty-inlet": {"cobble": "Cb", "gravelly sand": "S.G", "cobble mix": None, "gravel mix": None, "gravel": "G",
                        "mud": "M", "sand": "S", "sandy mud": "M.S", "coarse unconsolidated substrate": None,
                        "unconsolidated mineral substrate": None},
    "seattle": {"sand": "S", "mud": "M", "muddy sand": "S.M", "fine unconsolidated substrate": None,
                "unconsolidated mineral substrate": None},
    "tacoma": {"boulder": "Blds", "bedrock": "Rk", "anthropogenic rock rubble": None, "sandy cobble mix": None},
    "burien": {"mud": "M", "unconsolidated mineral substrate": None, "cobbley sandy mud": "M.S.Cb",
               "sandy cobble": "Cb.S", "bedrock": "Rk", "slightly cobbley sand": "S"},
}


@pytest.mark.parametrize("block", sorted(BLOCKS))
def test_cmecs_maps_to_labels(fixtures_dir, block):
    feats = read_cmecs(_path(fixtures_dir, block), block, PUGET)
    for f in feats:
        assert (f.layer, f.props["src"], f.props["class"]) == ("seabed", "usgs-cmecs", "CMECS")
        assert f.geometry["type"] in ("Polygon", "MultiPolygon")
        assert f.props.get("label") == cmecs_label(f.props["substrate"]) and "cell" not in f.props
        # R37: from the zoom where the polygon is about 48 px across, never before the CMECS floor
        assert f.props["extent"] == pytest.approx(extent_z0(f.geometry), rel=1e-5)
        want = max(MINZOOM, minzoom_for_extent(f.props["extent"]))
        assert f.props["tippecanoe"] == {"minzoom": want, "maxzoom": 16}
    assert {f.props["substrate"]: f.props.get("label") for f in feats} == EXPECTED[block]
    # every polygon with a substrate is kept, reprojected from UTM 10 NAD83 to WGS84 lon/lat
    source = [(items, g) for items, g in _ogr_polygons(_path(fixtures_dir, block), BLOCKS[block].name)
              if any(items.get(k) not in (None, "", "na") for k in BLOCKS[block].fields)]
    assert len(feats) == len(source)
    for (_, want), f in zip(source, feats):
        got = shape(f.geometry)
        assert got.symmetric_difference(want).area < 1e-12 and -123 < got.centroid.x < -122 and 47 < got.centroid.y < 48.4


def test_cmecs_substrate_is_the_finest_level(fixtures_dir):
    """Subgroup before group before the block's own symbolization field before subclass and class: Burien
    polygon 1865 has only a subclass in the hierarchy but substrate "mud"; Seattle "na" (land) is dropped."""
    feats = read_cmecs(_path(fixtures_dir, "burien"), "burien", PUGET)
    assert "mud" in {f.props["substrate"] for f in feats}
    seattle = read_cmecs(_path(fixtures_dir, "seattle"), "seattle", PUGET)
    assert "na" not in {f.props["substrate"] for f in seattle} and len(seattle) == 6


def test_cmecs_clipped_to_region_bbox(fixtures_dir):
    path = _path(fixtures_dir, "seattle")
    whole = read_cmecs(path, "seattle", PUGET)
    cell = read_cmecs(path, "seattle", TEST_CELL)
    # one fixture polygon crosses the cell's west edge (-122.4): it is cut there, not dropped
    assert len(cell) == len(whole)
    area = box(*TEST_CELL)
    assert all(area.buffer(1e-9).contains(shape(f.geometry)) for f in cell)
    assert sum(shape(f.geometry).area for f in cell) < sum(shape(f.geometry).area for f in whole)
    assert read_cmecs(_path(fixtures_dir, "admiralty-inlet"), "admiralty-inlet", TEST_CELL) == []


def test_fetch_cmecs_uses_cache(tmp_path, fixtures_dir, monkeypatch):
    calls = []

    def fake(url, dest, *, expected_size=None, timeout=120):
        calls.append((url, expected_size))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((fixtures_dir / "seabed" / dest.name).read_bytes())
        return dest

    monkeypatch.setattr("chartpack.cache.download", fake)
    blocks = {b: blk._replace(size=_path(fixtures_dir, b).stat().st_size) for b, blk in BLOCKS.items()}
    monkeypatch.setattr(cmecs, "BLOCKS", blocks)
    paths = fetch_cmecs(["seattle", "burien"], tmp_path)
    assert paths == [tmp_path / "seabed" / "CMECS_OffshoreSeattle.zip", tmp_path / "seabed" / "CMECS_OffshoreBurien.zip"]
    assert calls == [(blocks["seattle"].url, blocks["seattle"].size), (blocks["burien"].url, blocks["burien"].size)]
    fetch_cmecs(["seattle"], tmp_path)
    assert len(calls) == 2


def test_fetch_rejects_wrong_size(tmp_path, fixtures_dir, monkeypatch):
    """A cached zip of the wrong size (an interrupted download) is refetched; a download whose size does
    not match the published one fails and leaves nothing in the cache."""
    from chartpack.cache import DownloadError

    def fake(url, dest, *, expected_size=None, timeout=120):
        raise DownloadError(f"{url}: got 10 bytes, expected {expected_size}")

    monkeypatch.setattr("chartpack.cache.download", fake)
    dest = tmp_path / "seabed" / "CMECS_OffshoreSeattle.zip"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"PK partial")
    with pytest.raises(DownloadError):
        fetch_cmecs(["seattle"], tmp_path)
    assert not dest.exists()


def test_fetch_removes_damaged_download(tmp_path, fixtures_dir, monkeypatch):
    """A download of the published size whose member is damaged fails the zip check after the download:
    DownloadError, and the file is not left in the cache."""
    from chartpack.cache import DownloadError
    from zipdamage import flip_to_zlib_error

    damaged = tmp_path / "damaged.zip"
    damaged.write_bytes(_path(fixtures_dir, "seattle").read_bytes())
    flip_to_zlib_error(damaged, "CMECS_OffshoreSeattle.shp")

    def fake(url, dest, *, expected_size=None, timeout=120):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(damaged.read_bytes())
        return dest

    monkeypatch.setattr("chartpack.cache.download", fake)
    monkeypatch.setattr(cmecs, "BLOCKS", {"seattle": BLOCKS["seattle"]._replace(size=damaged.stat().st_size)})
    with pytest.raises(DownloadError, match="CMECS_OffshoreSeattle"):
        fetch_cmecs(["seattle"], tmp_path / "cache")
    assert not (tmp_path / "cache" / "seabed" / "CMECS_OffshoreSeattle.zip").exists()


@pytest.mark.online
def test_fetch_cmecs_online(tmp_path):
    paths = fetch_cmecs(sorted(BLOCKS), tmp_path)
    for block, path in zip(sorted(BLOCKS), paths):
        assert len(read_cmecs(path, block, PUGET)) > 1000, block
