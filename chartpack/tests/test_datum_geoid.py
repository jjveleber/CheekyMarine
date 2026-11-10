"""CRM EGM2008 heights to NAVD88 with PROJ geoid grids (plan 7, Task 13, #88)."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pyproj
import pytest

from chartpack.datum import geoid
from chartpack.datum.geoid import GeoidError, check_pipeline, egm2008_to_navd88_m, fetch_grids, missing_grids

PROJ_CACHE = Path(__file__).resolve().parent.parent / "cache" / "proj"  # cached between CI runs
GOOD = "step proj=vgridshift grids=us_nga_egm08_25.tif ... step inv proj=vgridshift grids=us_noaa_g2018u0.tif"

SEATTLE = (-122.3393, 47.6026)

# NOAA VDatum (https://vdatum.noaa.gov/docs/services.html), one-step EGM2008 to NAVD88 at Seattle, epoch 2010.0,
# from height 0, queried 2026-11-09 (t_z = 1.175):
#   https://vdatum.noaa.gov/vdatumweb/api/convert?s_x=-122.3393&s_y=47.6026&s_z=0&region=westcoast&epoch_in=2010.0&epoch_out=2010.0&s_h_frame=WGS84_G1674&s_v_frame=EGM2008&s_v_geoid=egm2008&t_h_frame=NAD83_2011&t_v_frame=NAVD88&t_v_geoid=geoid18
# The tolerance is 0.07 m, not 0.05: our source is ITRF2014 2D (EPSG:9000, the frame CRM's WGS 84 heights are
# realized in, per the plan), while VDatum takes EGM2008 heights only in WGS 84 (G1674). That frame step is a
# modeling gap of about 4 cm at Seattle (VDatum's ITRF2014 to NAD83(2011) step is +0.330 m, its G1674 one +0.289 m;
# composing VDatum's single steps in ITRF2014 gives 1.216 m). 0.07 m still fails a pipeline that drops the
# ITRF2014 to NAD83(2011) frame change (about 0.33 m here) or takes a ballpark (no geoid) step.
VDATUM_SEATTLE_M = 1.175


def test_source_crs_is_itrf2014_2d():
    crs = pyproj.CRS("EPSG:9000")
    assert crs.name == "ITRF2014" and crs.type_name == "Geographic 2D CRS"


@pytest.mark.parametrize("description, accuracy, definition", [
    ("Ballpark geographic offset from ITRF2014 to NAD83(2011)", 1.0, GOOD),
    ("Inverse of WGS 84 to EGM2008 height (1) + NAD83(2011) to NAVD88 height (3)", -1.0, GOOD),
    ("Inverse of WGS 84 to EGM2008 height (1) + NAD83(2011) to NAVD88 height (3)", 0.148,
     "step proj=vgridshift grids=us_nga_egm08_25.tif ... step proj=helmert x=1.0053"),  # no GEOID18 step
])
def test_ballpark_unknown_accuracy_or_missing_grid_fails(description, accuracy, definition):
    with pytest.raises(GeoidError):
        check_pipeline(SimpleNamespace(description=description, accuracy=accuracy, definition=definition))


def test_grid_pipeline_passes():
    check_pipeline(SimpleNamespace(description="Inverse of WGS 84 to EGM2008 height (1)", accuracy=0.148,
                                   definition=GOOD))


@pytest.fixture
def fake_grids(monkeypatch):
    """GRIDS replaced by two small files; download serves served[name] and counts the calls."""
    served = {"a.tif": b"abc", "b.tif": b"defg"}
    monkeypatch.setattr(geoid, "GRIDS", {n: (len(b), hashlib.sha256(b).hexdigest()) for n, b in served.items()})
    calls = []

    def fake_download(url, dest, *, expected_size=None):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(served[dest.name])
        return dest

    monkeypatch.setattr(geoid, "download", fake_download)
    return served, calls


def test_fetch_grids_downloads_missing_and_keeps_good(tmp_path, fake_grids):
    _, calls = fake_grids
    assert missing_grids(tmp_path) == [tmp_path / "a.tif", tmp_path / "b.tif"]
    fetch_grids(tmp_path)
    assert calls == [geoid.CDN + "a.tif", geoid.CDN + "b.tif"] and missing_grids(tmp_path) == []
    fetch_grids(tmp_path)
    assert len(calls) == 2  # both verified, nothing refetched


def test_fetch_grids_refetches_a_damaged_grid(tmp_path, fake_grids):
    _, calls = fake_grids
    fetch_grids(tmp_path)
    (tmp_path / "a.tif").write_bytes(b"xyz")  # right size, wrong sha256
    assert missing_grids(tmp_path) == [tmp_path / "a.tif"]
    fetch_grids(tmp_path)
    assert calls[-1] == geoid.CDN + "a.tif" and (tmp_path / "a.tif").read_bytes() == b"abc"


def test_fetch_grids_fails_on_wrong_sha256(tmp_path, fake_grids):
    served, _ = fake_grids
    served["b.tif"] = b"zzzz"  # the CDN serves other bytes of the same size
    with pytest.raises(GeoidError, match="sha256"):
        fetch_grids(tmp_path)
    assert not (tmp_path / "b.tif").exists()


def test_transform_needs_fetched_grids(tmp_path):
    with pytest.raises(GeoidError, match="fetch-bathy"):
        egm2008_to_navd88_m((-122.4, 1 / 3600, 0.0, 47.7, 0.0, -1 / 3600), (3, 3), tmp_path)


@pytest.mark.online
def test_frame_change_matches_vdatum():
    fetch_grids(PROJ_CACHE)
    assert missing_grids(PROJ_CACHE) == []
    res = 1 / 3600
    lon, lat = SEATTLE
    transform = (lon - 1.5 * res, res, 0.0, lat + 1.5 * res, 0.0, -res)
    dn = egm2008_to_navd88_m(transform, (3, 3), PROJ_CACHE)
    assert float(dn[1, 1]) == pytest.approx(VDATUM_SEATTLE_M, abs=0.07)
