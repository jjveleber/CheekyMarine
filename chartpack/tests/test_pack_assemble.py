import json

from chartpack.pack.assemble import assemble_charts_pack
from chartpack.style.validate import check_style_sprites_glyphs


def test_charts_pack_layout(test_region, enc_pack_path, tmp_path):
    root = assemble_charts_pack(test_region, enc_pack_path, tmp_path)
    assert root == tmp_path / "charts-test-cell-0.1.0"
    names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert "enc.mbtiles" in names and "styles/nav-night.json" in names and "sprites/nav@2x.json" in names
    assert "styles/nav-day.json" in names and "styles/nav-dusk.json" in names and "sprites/nav.png" in names
    assert "glyphs/Noto Sans Regular/0-255.pbf" in names and "glyphs/Noto Sans Bold/256-511.pbf" in names
    assert "README.md" in names and "NOTICE" in names


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
