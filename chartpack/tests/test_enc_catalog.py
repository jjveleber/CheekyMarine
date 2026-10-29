from chartpack.enc.catalog import parse_catalog, cells_in_bbox


def _cat(fixtures_dir):
    return parse_catalog((fixtures_dir / "ENCProdCat_excerpt.xml").read_bytes())


def test_parse_excerpt(fixtures_dir):
    c = _cat(fixtures_dir)["US4WA1HK"]
    assert (c.band, c.status) == (4, "Active")
    assert c.zip_url == "https://charts.noaa.gov/ENCs/US4WA1HK.zip"
    assert c.edtn >= 1 and c.updn >= 0 and len(c.polygon) >= 4
    assert c.isdt.isoformat() == "2026-09-09"


def test_cells_in_bbox_excludes_cancelled(fixtures_dir):
    cat = _cat(fixtures_dir)
    assert cat["US5WA13M"].status == "Cancelled"
    assert "US5WA13M" not in cells_in_bbox(cat, (-122.9, 47.5, -122.1, 48.3), 5)
    assert "US5SEAKL" in cells_in_bbox(cat, (-122.4, 47.9, -122.3, 48.0), 5)


def test_cells_in_bbox_band_and_sorted(fixtures_dir):
    names = cells_in_bbox(_cat(fixtures_dir), (-122.4, 47.7, -122.1, 48.0), 4)
    assert names == sorted(names) and "US4WA1HK" in names
    assert not any(n[2] != "4" for n in names)
