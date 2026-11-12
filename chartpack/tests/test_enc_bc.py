import json
import math
import shutil

import pytest
from shapely.geometry import Point, Polygon, box, shape
from shapely.affinity import translate

from chartpack.enc.bc import (
    JDF_STRIP_BOX,
    NOTICE_CELLS,
    BcError,
    area_km2,
    chs_notice_areas,
    load_canada,
)

# The bc-offshore-south outline of the plan 8 spec appendix.
OFFSHORE_SOUTH = [(-132.864, 51.0), (-129.2, 51.0), (-129.184, 50.85), (-128.6, 50.85), (-128.595, 49.407),
                  (-126.6, 49.4), (-126.6, 48.45), (-128.302, 48.45), (-129.469, 49.135), (-130.024, 49.683),
                  (-132.44, 50.756), (-132.864, 51.0)]


def _committed(regions_dir):
    return json.loads((regions_dir / "clip" / "canada-chs.geojson").read_text())


def _shape(path):
    data = json.loads(path.read_text())
    return shape(data.get("geometry", data))


def test_chs_notice_found_by_dfo_text_only():
    notice = box(-123.4, 48.5, -123.2, 48.7)
    general = box(-124.0, 48.0, -123.0, 48.4)
    source = box(-125.0, 48.0, -124.5, 48.4)
    notes = [
        (notice, "(c) Fisheries and Oceans Canada 2024. Published by the Canadian Hydrographic Service. A licence"
                 " is required from the Canadian Hydrographic Service (www.charts.gc.ca) to reproduce or distribute"
                 " this work."),
        (general, "COPYRIGHT\r\nHowever, this product contains Canadian Hydrographic Service copyrighted works, and"
                  " is published with the authorization of the Canadian Hydrographic Service."),
        (source, "AUTHORITIES\r\nHydrography and topography by the National Ocean Service, with additional data"
                 " from the Canadian Hydrographic Service."),
        (box(-122.0, 48.0, -121.5, 48.4), None),
    ]
    assert chs_notice_areas(notes).equals(notice)
    assert chs_notice_areas(notes[1:]).is_empty


def test_canada_chs_file_is_valid_and_lists_cells(regions_dir):
    data = _committed(regions_dir)
    assert data["type"] == "Feature" and data["properties"]["name"] == "canada-chs"
    geometry = shape(data["geometry"])
    assert geometry.is_valid and not geometry.is_empty
    cells = {c["cell"]: c for c in data["properties"]["cells"]}
    assert {"US1GLBDD", "US1GLBDC", *NOTICE_CELLS} <= set(cells)
    assert {name for name, c in cells.items() if c["notice"]} == set(NOTICE_CELLS)
    for c in cells.values():
        assert c["band"] == int(c["cell"][2])
        assert isinstance(c["edition"], int) and isinstance(c["update"], int)
        assert len(c["issued"]) == 10 and c["issued"][4] == "-"


def test_canada_chs_covers_west_of_134_4(regions_dir):
    polygon = shape(_committed(regions_dir)["geometry"])
    assert polygon.contains(Point(-135.0, 53.5))
    assert polygon.contains(Polygon(OFFSHORE_SOUTH))


def test_jdf_strip_is_inside_polygon(regions_dir):
    polygon = shape(_committed(regions_dir)["geometry"])
    wa = _shape(regions_dir / "clip" / "canada-wa.geojson")
    assert 35.0 <= area_km2(polygon.difference(wa).intersection(box(*JDF_STRIP_BOX))) <= 45.0


def test_canada_chs_agrees_with_canada_wa(regions_dir):
    assert load_canada(regions_dir).equals(shape(_committed(regions_dir)["geometry"]))


def test_border_disagreement_fails(regions_dir, tmp_path):
    shutil.copytree(regions_dir / "clip", tmp_path / "clip")
    path = tmp_path / "clip" / "canada-wa.geojson"
    data = json.loads(path.read_text())
    shifted = translate(shape(data["geometry"]), xoff=50 / (111320 * math.cos(math.radians(48.5))), yoff=50 / 111320)
    data["geometry"] = shifted.__geo_interface__
    path.write_text(json.dumps(data))
    with pytest.raises(BcError, match="wider than 20 m"):
        load_canada(tmp_path)
