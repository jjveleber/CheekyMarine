from shapely.geometry import Polygon, box

from chartpack.enc.catalog import parse_catalog
from chartpack.region import load_region


def _shape(cell):
    return Polygon([(lon, lat) for lat, lon in cell.polygon])


def test_puget_north_region_is_consistent(regions_dir, fixtures_dir):
    r = load_region(regions_dir / "puget-north.toml")
    cat = parse_catalog((fixtures_dir / "ENCProdCat_excerpt.xml").read_bytes())  # holds every cell the region names
    for band, names in r.cells.items():
        for n in names:
            assert cat[n].status == "Active" and cat[n].band == band and _shape(cat[n]).intersects(box(*r.bbox)), n
    assert set(r.cells[4]) >= {"US4WA1GJ", "US4WA1GK", "US4WA1HJ", "US4WA1HK", "US4WA1II", "US4WA1IJ", "US4WA1IK"}
    assert r.cells[3] == ["US3WA1DF", "US3WA1DG", "US3WA1EF", "US3WA1EG"]
    assert len(r.views) == 5 and {v.name for v in r.views} == {"everett", "possession-bar", "point-no-point", "jeff-head", "admiralty-inlet"}
