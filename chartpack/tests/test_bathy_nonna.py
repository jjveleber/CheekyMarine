import re
import math

import numpy as np
import pytest
from osgeo import gdal

from chartpack.bathy import nonna
from chartpack.cache import DownloadError
from make_nonna import (
    A_COL, A_ROW, GRID, NODATA, SIZE, chunk_box, chunk_values, edge_transform, write_index, write_nonna,
)
from osgeo import osr

gdal.UseExceptions()


def test_constants_match_task1():
    assert nonna.WCS_BASE == "https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs"
    assert nonna.COVERAGE == {"nonna10": "nonna__NONNA 10 Coverage", "nonna100": "nonna__NONNA 100 Coverage"}
    assert nonna.GRID == GRID
    assert nonna.NODATA == NODATA


def test_wcs_url_has_coverage_and_subsets():
    url = nonna.wcs_url("nonna10", (-13848154.127129, 6515827.224624, -13837000.515575, 6533322.201362))
    assert url.startswith(nonna.WCS_BASE + "?")
    assert "service=WCS" in url and "version=2.0.1" in url and "request=GetCoverage" in url
    assert "coverageId=nonna__NONNA%2010%20Coverage" in url
    assert "subset=X(-13848154.127129,-13837000.515575)" in url
    assert "subset=Y(6515827.224624,6533322.201362)" in url
    assert "format=image/tiff" in url


@pytest.mark.parametrize("product, expected", [
    # The subsets Task 1 sent for the box -124.40, 50.40, -124.30, 50.50; both came back on the native grid.
    ("nonna10", (-13848154.127129, 6515827.224624, -13837000.515575, 6533322.201362)),
    ("nonna100", (-13848171.702436, 6515801.172984, -13836865.263944, 6533391.809404)),
])
def test_box_snaps_outward_to_cell_edges(product, expected):
    got = nonna.snap_box(product, (-124.40, 50.40, -124.30, 50.50))
    assert got == pytest.approx(expected, abs=1e-5)


class ListSession:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.urls = []
        self.retries = []
        self.backoffs = 0

    def get(self, url, retry=True):
        self.urls.append(url)
        self.retries.append(retry)
        return self.bodies.pop(0)

    def backoff(self):
        self.backoffs += 1


BOXES = [chunk_box("a"), chunk_box("b")]  # lon/lat boxes whose requests chunk-a.tif and chunk-b.tif answer


def test_chunk_boxes_snap_to_the_fixture_chunks():
    for which, (dc, dr) in (("a", (0, 0)), ("b", (62, 10))):
        x0, px, _, y0, _, py = edge_transform("nonna10", A_COL + dc, A_ROW + dr)
        expected = (x0, y0 + SIZE * py, x0 + SIZE * px, y0)
        assert nonna.snap_box("nonna10", chunk_box(which)) == pytest.approx(expected, abs=1e-6)


def _truncated(fixtures_dir) -> bytes:
    chunk = (fixtures_dir / "nonna" / "chunk-a.tif").read_bytes()
    return chunk[: len(chunk) // 2]  # header intact, strips cut


@pytest.mark.parametrize("kind", ["xml", "truncated"])
@pytest.mark.parametrize("bad", [0, 1])
def test_wcs_error_body_is_not_stored(tmp_path, fixtures_dir, bad, kind):
    """A chunk that comes back as an XML error body or a cut TIFF twice fails the fetch naming its box, after
    one retry behind the back-off; nothing is left at out or beside it."""
    chunks = [(fixtures_dir / "nonna" / f"chunk-{w}.tif").read_bytes() for w in "ab"]
    error = (fixtures_dir / "nonna" / "error.xml").read_bytes() if kind == "xml" else _truncated(fixtures_dir)
    bodies = chunks[:bad] + [error, error] + chunks[bad + 1:]
    session = ListSession(bodies)
    out = tmp_path / "nonna10-x.tif"
    with pytest.raises(DownloadError, match=re.escape(str(BOXES[bad]))) as info:
        nonna.fetch_nonna("nonna10", BOXES, out, session)
    if kind == "xml":
        assert "NoSuchCoverage" in str(info.value)
    else:
        assert "truncated TIFF" in str(info.value) and "II*" not in str(info.value)  # no raw TIFF bytes
    bad_url = nonna.wcs_url("nonna10", nonna.snap_box("nonna10", BOXES[bad]))
    assert session.urls.count(bad_url) == 2 and session.backoffs == 1
    assert session.retries[-1] is False  # the bad-body retry does not stack the session's own retry
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []  # no mosaic, no chunk left behind


@pytest.mark.parametrize("kind", ["xml", "truncated"])
def test_bad_chunk_then_good_one_succeeds(tmp_path, fixtures_dir, kind):
    paths = [fixtures_dir / "nonna" / f"chunk-{w}.tif" for w in "ab"]
    error = (fixtures_dir / "nonna" / "error.xml").read_bytes() if kind == "xml" else _truncated(fixtures_dir)
    session = ListSession([paths[0].read_bytes(), error, paths[1].read_bytes()])
    out = tmp_path / "nonna10-x.tif"
    assert nonna.fetch_nonna("nonna10", BOXES, out, session)["chunks"] == 2
    assert len(session.urls) == 3 and session.urls[1] == session.urls[2] and session.backoffs == 1
    assert session.retries == [True, True, False]
    ds = gdal.Open(str(out))
    b_src = gdal.Open(str(paths[1]))
    np.testing.assert_array_equal(ds.GetRasterBand(1).ReadAsArray(62, 10, 64, 64), b_src.GetRasterBand(1).ReadAsArray())


def _edited_chunk_a(tmp_path, transform=None, epsg=None, data=None) -> bytes:
    path = write_nonna(tmp_path / "edited.tif", chunk_values("a") if data is None else data)
    ds = gdal.Open(str(path), gdal.GA_Update)
    if transform:
        ds.SetGeoTransform(transform(ds.GetGeoTransform()))
    if epsg:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)
        ds.SetProjection(srs.ExportToWkt())
    ds = None
    body = path.read_bytes()
    path.unlink()
    return body


def _half_cell(gt):
    x0, px, _, y0, _, py = gt
    return (x0 + px / 2, px, 0.0, y0, 0.0, py)  # the half-cell shift Task 1 saw with corner snapping


def _far_away(gt):
    x0, px, _, y0, _, py = gt
    return (x0 + 50000 * px, px, 0.0, y0, 0.0, py)  # on the native grid, but not where it was asked for


@pytest.mark.parametrize("case, match", [
    ({"transform": _half_cell}, "native grid"),
    ({"transform": _far_away}, "requested box"),
    ({"data": chunk_values("a")[:60, :]}, "requested box"),  # clipped smaller than the request
    ({"epsg": 32610}, "EPSG:3857"),
])
def test_wrong_chunk_fails_at_once(tmp_path, case, match):
    """A readable TIFF that is not the requested box on the native grid in EPSG:3857 cannot get better: the fetch
    fails naming the box with no back-off and no second request."""
    session = ListSession([_edited_chunk_a(tmp_path, **case)])
    out = tmp_path / "out.tif"
    with pytest.raises(DownloadError, match=match) as info:
        nonna.fetch_nonna("nonna10", BOXES[:1], out, session)
    assert str(BOXES[0]) in str(info.value)
    assert len(session.urls) == 1 and session.backoffs == 0
    assert not out.exists()


def test_mosaic_keeps_native_values(tmp_path, fixtures_dir):
    paths = [fixtures_dir / "nonna" / f"chunk-{w}.tif" for w in "ab"]
    session = ListSession([p.read_bytes() for p in paths])
    out = tmp_path / "nonna10-x.tif"
    stats = nonna.fetch_nonna("nonna10", BOXES, out, session)
    assert stats["chunks"] == 2 and stats["bytes"] == out.stat().st_size and stats["seconds"] >= 0
    assert [u.split("subset=X(")[1].split(")")[0] for u in session.urls] == [
        ",".join(repr(v) for v in (nonna.snap_box("nonna10", b)[0], nonna.snap_box("nonna10", b)[2])) for b in BOXES]

    ds = gdal.Open(str(out))
    assert ds.GetGeoTransform() == pytest.approx(edge_transform("nonna10", A_COL, A_ROW))
    assert (ds.RasterXSize, ds.RasterYSize) == (62 + 64, 10 + 64)
    band = ds.GetRasterBand(1)
    assert band.DataType == gdal.GDT_Float32 and band.GetNoDataValue() == pytest.approx(NODATA)
    assert ds.GetMetadata("IMAGE_STRUCTURE")["COMPRESSION"] == "DEFLATE"
    assert band.GetBlockSize() != [ds.RasterXSize, 1]  # tiled, not strips
    mosaic = band.ReadAsArray()
    covered = np.zeros(mosaic.shape, bool)
    for (dc, dr), path in zip([(0, 0), (62, 10)], paths):
        src_ds = gdal.Open(str(path))
        src = src_ds.GetRasterBand(1).ReadAsArray()
        np.testing.assert_array_equal(mosaic[dr:dr + 64, dc:dc + 64], src)
        covered[dr:dr + 64, dc:dc + 64] = True
    assert (mosaic[~covered] == np.float32(NODATA)).all()


def test_index_boxes_filters_and_sorts(tmp_path):
    shp = write_index(tmp_path / "NONNA10.shp", [
        ("NONNA10_5040N12450W", (-124.5, 50.4, -124.4, 50.5)),
        ("NONNA10_5040N12460W", (-124.6, 50.4, -124.5, 50.5)),
        ("NONNA10_5040N12470W", (-124.7, 50.4, -124.6, 50.5)),  # touches the box's west edge only
    ])
    assert nonna.index_boxes(shp, (-124.6, 50.3, -124.2, 50.6)) == [
        (-124.6, 50.4, -124.5, 50.5),
        (-124.5, 50.4, -124.4, 50.5),
    ]


def test_nonna_sign_and_nodata(tmp_path):
    """Raw NONNA is elevation (depths negative, drying heights positive); read_nonna gives depth positive down,
    so a drying height reads as a negative depth, and nan where the grid has no data."""
    path = write_nonna(tmp_path / "n.tif", np.array([[NODATA, -30.0, 1.5]], np.float32), "nonna100", A_COL // 8,
                       A_ROW // 8)
    ds = gdal.Open(str(path))
    x0, px, _, y0, _, py = ds.GetGeoTransform()
    lon = [math.degrees((x0 + (i + 0.5) * px) / 6378137.0) for i in range(3)]
    lat = math.degrees(2 * math.atan(math.exp((y0 + py / 2) / 6378137.0)) - math.pi / 2)
    res = 0.0001
    grid = nonna.read_nonna(path, (lon[0] - 0.0005, lat - 0.0005, lon[2] + 0.0005, lat + 0.0005), res)
    gx0, gdx, _, gy0, _, gdy = grid.transform
    assert gdx == pytest.approx(res) and gdy == pytest.approx(-res)
    row = int((lat - gy0) / gdy)
    values = [grid.data[row, int((x - gx0) / gdx)] for x in lon]
    assert math.isnan(values[0]) and values[1:] == [30.0, -1.5]
    assert math.isnan(grid.data[0, 0])  # outside the raster
    assert grid.data.dtype == np.float32 and math.isnan(grid.nodata)


def test_stats_count_only_chunks_in_the_mosaic(tmp_path, fixtures_dir, monkeypatch):
    """BuildVRT skips a source it cannot place (another CRS) with a warning only; the fetch fails rather than
    report a chunk the mosaic does not hold. The chunk check is switched off to reach that point."""
    monkeypatch.setattr(nonna, "_check_chunk", lambda *args: None)
    b_other_crs = _edited_chunk_a(tmp_path, epsg=32610)
    session = ListSession([(fixtures_dir / "nonna" / "chunk-a.tif").read_bytes(), b_other_crs])
    out = tmp_path / "out.tif"
    with pytest.raises(DownloadError, match="1 of 2 chunks"):
        nonna.fetch_nonna("nonna10", BOXES, out, session)
    assert not out.exists()
