import csv
import io
import zipfile

import pytest

from chartpack.seabed import usseabed
from chartpack.seabed.codes import FOLK, folk_label
from chartpack.seabed.usseabed import FILES, MINZOOM, fetch_usseabed, read_usseabed

TEST_CELL = (-122.4, 47.7, -122.1, 48.0)
PUGET = (-123.0, 47.3, -122.2, 48.3)


def _rows(path, member):
    return list(csv.DictReader(io.StringIO(zipfile.ZipFile(path).read(member).decode("latin1"))))


def _zips(fixtures_dir):
    return [fixtures_dir / "seabed" / name for name in FILES]


def test_usseabed_maps_to_labels(fixtures_dir):
    feats = read_usseabed(_zips(fixtures_dir), TEST_CELL)
    assert {(f.layer, f.geometry["type"], f.props["src"], f.props["class"]) for f in feats} == {
        ("seabed", "Point", "usseabed", "SAMPLE")}
    # the Folk class is kept as the source gives it, and the label comes from it
    for f in feats:
        assert f.props["label"] == folk_label(f.props["folk"]) and "cell" not in f.props and "band" not in f.props
        assert f.props["tippecanoe"] == {"minzoom": MINZOOM, "maxzoom": 16}
    by_folk = {f.props["folk"]: f.props["label"] for f in feats}
    # ruling R26: a slightly gravelly (g) class (under 5 % gravel) reads as its main classes, no G
    assert by_folk == {"M": "M", "sM": "M.S", "(g)S": "S", "(g)sM": "M.S", "(g)M": "M", "(g)mS": "S.M",
                       "S": "S", "gS": "S.G", "mG": "G.M"}
    # exact duplicates by position and type are dropped, computed here from the raw rows of both files
    rows = [r for name, member in FILES.items() for r in _rows(fixtures_dir / "seabed" / name, member[2])]
    inside = {(float(r["Longitude"]), float(r["Latitude"]), r["FolkCode"]) for r in rows
              if TEST_CELL[0] <= float(r["Longitude"]) <= TEST_CELL[2] and TEST_CELL[1] <= float(r["Latitude"]) <= TEST_CELL[3]}
    assert len(feats) == len(inside) == 28  # 31 rows in the cell; "M" three times and "(g)M" twice at 47.9025, -122.38
    assert {(*f.geometry["coordinates"], f.props["folk"]) for f in feats} == inside
    at = [f.props["folk"] for f in feats if f.geometry["coordinates"] == [-122.38, 47.9025]]
    assert sorted(at) == ["(g)M", "(g)sM", "M"]  # different types at one position are all kept


def test_hard_ground_is_the_hard_qualifier(fixtures_dir):
    feats = read_usseabed(_zips(fixtures_dir), PUGET)
    assert {f.props["folk"]: f.props["label"] for f in feats}["H"] == "h"


def _zip_with_rows(path, member, rows):
    header = _HEADER.split(",")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(k, "-99") for k in header])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, buf.getvalue())
    return path


_HEADER = ("Latitude,Longitude,WaterDepth,SampleTop,SampleBase,SiteName,DataSetKey,SiteKey,SampleKey,Sampler,"
           "DataTypes,Gravel,Sand,Mud,Clay,Grainsize,Sorting,SeabedCls,ClsMshp,FolkCode,ShepardCode,RockMshp,"
           "WeedMshp,Carbonate,MunslCode,OrgCarbon,LgShearStr,Porosity,PWaveVel,Roughness,LgCrShSt,SamplePhase")


def test_unknown_class_is_kept_unlabelled(tmp_path):
    """An unmapped class keeps its raw value and gets no label; never guessed. A row with no class at all
    has nothing to show and is left out."""
    assert folk_label("xS") is None and folk_label("") is None
    from chartpack.seabed.codes import cmecs_label

    assert cmecs_label("megaclast") is None and cmecs_label("unconsolidated mineral substrate") is None
    path = _zip_with_rows(tmp_path / "pac_ext.zip", "PAC_EXT.txt", [
        {"Latitude": "47.8", "Longitude": "-122.3", "FolkCode": "xS"},
        {"Latitude": "47.81", "Longitude": "-122.3", "FolkCode": ""},
    ])
    feats = read_usseabed([path], TEST_CELL)
    assert len(feats) == 1 and feats[0].props["folk"] == "xS" and "label" not in feats[0].props


def test_sources_clipped_to_region_bbox(fixtures_dir):
    wide = read_usseabed(_zips(fixtures_dir), PUGET)
    cell = read_usseabed(_zips(fixtures_dir), TEST_CELL)
    assert len(wide) > len(cell)
    for f in cell:
        lon, lat = f.geometry["coordinates"]
        assert TEST_CELL[0] <= lon <= TEST_CELL[2] and TEST_CELL[1] <= lat <= TEST_CELL[3]
    assert read_usseabed(_zips(fixtures_dir), (-120.0, 30.0, -119.0, 31.0)) == []


def test_every_folk_class_maps_to_chart_abbreviations():
    """The Folk classes in the DS 182 metadata (FolkCode domain), each to a Chart No. 1 label or none."""
    assert set(FOLK) == {"(g)M", "(g)mS", "(g)sM", "(g)S", "G", "gM", "gmS", "gS", "M", "mG", "mS", "msG",
                         "S", "sG", "sM", "H"}


def _fake_download(fixtures_dir, calls):
    def fake(url, dest, *, expected_size=None, timeout=120):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((fixtures_dir / "seabed" / dest.name).read_bytes())
        return dest
    return fake


def test_fetch_uses_cache_and_checks_size(tmp_path, fixtures_dir, monkeypatch):
    calls = []
    monkeypatch.setattr("chartpack.cache.download", _fake_download(fixtures_dir, calls))
    sizes = {name: (fixtures_dir / "seabed" / name).stat().st_size for name in FILES}
    monkeypatch.setattr(usseabed, "FILES", {n: (u, sizes[n], m) for n, (u, _, m) in FILES.items()})
    paths = fetch_usseabed(tmp_path)
    assert paths == [tmp_path / "seabed" / name for name in FILES] and len(calls) == 2
    fetch_usseabed(tmp_path)
    assert len(calls) == 2  # cache hit
    paths[0].write_bytes(paths[0].read_bytes()[:-10] + b"x" * 10)  # same size, damaged
    fetch_usseabed(tmp_path)
    assert len(calls) == 3 and paths[0].read_bytes() == (fixtures_dir / "seabed" / paths[0].name).read_bytes()


@pytest.mark.online
def test_fetch_usseabed_online(tmp_path):
    paths = fetch_usseabed(tmp_path)
    feats = read_usseabed(paths, PUGET)
    assert len(feats) > 500 and all(f.props["src"] == "usseabed" for f in feats)
