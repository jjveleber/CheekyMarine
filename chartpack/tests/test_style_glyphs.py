from chartpack.style.glyphs import build_glyphs, parse_glyph_pbf


def test_glyph_range_roundtrip(tmp_path, fonts_dir):
    paths = build_glyphs(fonts_dir / "NotoSans-Regular.ttf", "Noto Sans Regular", tmp_path)
    assert [p.name for p in paths] == ["0-255.pbf", "256-511.pbf"] and paths[0].parent.name == "Noto Sans Regular"
    g = parse_glyph_pbf(paths[0].read_bytes())
    assert g["name"] == "Noto Sans Regular" and g["range"] == "0-255"
    seven = g["glyphs"][ord("7")]
    assert seven["advance"] > 0 and len(seven["bitmap"]) == (seven["width"] + 6) * (seven["height"] + 6)
