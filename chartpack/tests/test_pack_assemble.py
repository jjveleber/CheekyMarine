import json

from chartpack.mbtiles import MBTiles
from chartpack.pack.assemble import assemble_charts_pack
from chartpack.style.validate import check_style_sprites_glyphs


def test_charts_pack_layout(test_region, enc_pack_path, tmp_path):
    root = assemble_charts_pack(test_region, enc_pack_path, tmp_path)
    assert root == tmp_path / "charts-test-cell-0.1.0"
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert "enc.mbtiles" in names and "styles/nav-night.json" in names and "sprites/nav@2x.json" in names
    assert "styles/nav-day.json" in names and "styles/nav-dusk.json" in names and "sprites/nav.png" in names
    assert "glyphs/Noto Sans Regular/0-255.pbf" in names and "glyphs/Noto Sans Bold/256-511.pbf" in names
    assert "README.md" in names and "NOTICE" in names and "legend.json" in names


def test_legend_from_enc_metadata(charts_pack_root):
    from chartpack.seabed.legend import build_legend

    with MBTiles.open(charts_pack_root / "enc.mbtiles") as m:
        features = json.loads(m.metadata()["cheekymarine:seabed"])
    assert json.loads((charts_pack_root / "legend.json").read_text()) == build_legend(features)


def test_shipped_style_matches_sprite_and_glyphs(charts_pack_root):
    fonts = {p.name for p in (charts_pack_root / "glyphs").iterdir()}
    sprite = json.loads((charts_pack_root / "sprites" / "nav.json").read_text())
    styles = sorted((charts_pack_root / "styles").glob("*.json"))
    assert len(styles) == 3
    for path in styles:
        assert check_style_sprites_glyphs(json.loads(path.read_text()), sprite, fonts) == []


def test_safety_contour_is_a_charted_value(charts_pack_root):
    for path in (charts_pack_root / "styles").glob("*.json"):
        value = json.loads(path.read_text())["metadata"]["cheekymarine"]["safety_contour_m"]
        assert isinstance(value, float) and value >= 3.048


def test_notice_and_readme(charts_pack_root):
    notice = (charts_pack_root / "NOTICE").read_text()
    assert "NOAA ENC" in notice and "not certified for navigation" in notice and "US4WA1HK" in notice
    assert "SIL Open Font License" in notice
    assert "Pack contract" in (charts_pack_root / "README.md").read_text()


def test_bathy_pack_layout(test_region, tmp_path):
    import numpy as np

    from chartpack.bathy.dem import build_dem_mbtiles
    from chartpack.pack.assemble import assemble_bathy_pack

    with MBTiles.create(tmp_path / "bathy.mbtiles", fmt="pbf") as m:
        m.set_metadata({"cheekymarine:sources": json.dumps({
            "cudem": [{"name": "t1", "url": "u", "year": 2023, "version": 1}], "crm": "https://crm.test",
            "datum": {"station": "9447130", "navd88_to_mllw_m": 0.715, "msl_to_mllw_m": 2.02}})})
    dem = tmp_path / "dem.mbtiles"
    build_dem_mbtiles(np.full((40, 40), 20.0, np.float32), (-122.3, 0.001, 0, 47.9, 0, -0.001), dem, maxzoom=11)
    root = assemble_bathy_pack(test_region, tmp_path / "bathy.mbtiles", dem, tmp_path / "out")
    assert root == tmp_path / "out" / "bathy-test-cell-0.1.0"
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    for want in ("bathy.mbtiles", "dem.mbtiles", "styles/fish-day.json", "styles/fish-dusk.json", "styles/fish-night.json",
                 "sprites/fish.json", "sprites/fish.png", "sprites/fish@2x.json", "sprites/fish@2x.png",
                 "glyphs/Noto Sans Bold/0-255.pbf", "README.md", "NOTICE"):
        assert want in names
    assert not any(n.startswith("styles/nav") for n in names)
    fonts = {p.name for p in (root / "glyphs").iterdir()}
    sprite = json.loads((root / "sprites" / "fish.json").read_text())
    for palette in ("day", "dusk", "night"):
        style = json.loads((root / "styles" / f"fish-{palette}.json").read_text())
        assert check_style_sprites_glyphs(style, sprite, fonts) == []
    notice = (root / "NOTICE").read_text()
    assert "10.25921/ds9v-ky35" in notice and "Coastal Relief Model" in notice and "SIL Open Font License" in notice
    assert "Pack contract" in (root / "README.md").read_text()
