"""CRM EGM2008 heights to NAVD88 with PROJ geoid grids (plan 7, Task 13, #88)."""

from types import SimpleNamespace

import pyproj
import pytest

from chartpack.datum import geoid
from chartpack.datum.geoid import GeoidError, check_pipeline, egm2008_to_navd88_m

SEATTLE = (-122.3393, 47.6026)

# NOAA VDatum (https://vdatum.noaa.gov/docs/services.html), queried 2026-11-09. VDatum takes EGM2008 heights
# only in WGS 84 (G1674), while CRM's WGS 84 heights are realized in ITRF2014 (the frame of the PROJ
# pipeline), so the check value is VDatum's three steps at Seattle, epoch 2010.0, each from height 0:
#   EGM2008 to WGS 84 (G1674) ellipsoid: -22.789 m
#     https://vdatum.noaa.gov/vdatumweb/api/convert?s_x=-122.3393&s_y=47.6026&s_z=0&region=westcoast&epoch_in=2010.0&epoch_out=2010.0&s_h_frame=WGS84_G1674&s_v_frame=EGM2008&s_v_geoid=egm2008&t_h_frame=WGS84_G1674&t_v_frame=WGS84_G1674
#   ITRF2014 ellipsoid to NAD83(2011) ellipsoid: +0.330 m
#     https://vdatum.noaa.gov/vdatumweb/api/convert?s_x=-122.3393&s_y=47.6026&s_z=0&region=westcoast&epoch_in=2010.0&epoch_out=2010.0&s_h_frame=ITRF2014&s_v_frame=ITRF2014&t_h_frame=NAD83_2011&t_v_frame=NAD83_2011
#   NAVD88 (GEOID18) to NAD83(2011) ellipsoid: -23.675 m
#     https://vdatum.noaa.gov/vdatumweb/api/convert?s_x=-122.3393&s_y=47.6026&s_z=0&region=westcoast&epoch_in=2010.0&epoch_out=2010.0&s_h_frame=NAD83_2011&s_v_frame=NAVD88&t_h_frame=NAD83_2011&t_v_frame=NAD83_2011
# EGM2008 height 0 is NAVD88 height -22.789 + 0.330 + 23.675 = 1.216 m. VDatum's one-step EGM2008 to NAVD88
# from G1674 gives 1.175 m; the 0.041 m between them is the G1674 to ITRF2014 frame step.
#   https://vdatum.noaa.gov/vdatumweb/api/convert?s_x=-122.3393&s_y=47.6026&s_z=0&region=westcoast&epoch_in=2010.0&epoch_out=2010.0&s_h_frame=WGS84_G1674&s_v_frame=EGM2008&s_v_geoid=egm2008&t_h_frame=NAD83_2011&t_v_frame=NAVD88&t_v_geoid=geoid18
VDATUM_SEATTLE_M = 1.216


def test_source_crs_is_itrf2014_2d():
    crs = pyproj.CRS("EPSG:9000")
    assert crs.name == "ITRF2014" and crs.type_name == "Geographic 2D CRS"


@pytest.mark.parametrize("description, accuracy", [
    ("Ballpark geographic offset from ITRF2014 to NAD83(2011)", 1.0),
    ("Inverse of WGS 84 to EGM2008 height (1) + NAD83(2011) to NAVD88 height (3)", -1.0),
])
def test_ballpark_or_unknown_accuracy_fails(description, accuracy):
    with pytest.raises(GeoidError):
        check_pipeline(SimpleNamespace(description=description, accuracy=accuracy))


@pytest.mark.online
def test_frame_change_matches_vdatum(tmp_path):
    res = 1 / 3600
    lon, lat = SEATTLE
    transform = (lon - 1.5 * res, res, 0.0, lat + 1.5 * res, 0.0, -res)
    dn = egm2008_to_navd88_m(transform, (3, 3), tmp_path)
    assert float(dn[1, 1]) == pytest.approx(VDATUM_SEATTLE_M, abs=0.05)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(geoid.GRIDS)
