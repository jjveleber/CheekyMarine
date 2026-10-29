from PIL import Image

from chartpack.style.nav import nav_style
from chartpack.style.sprites import build_sprites, rasterize_svg
from chartpack.style.validate import check_style_sprites_glyphs


def test_all_symbols_rasterize_nonblank(symbols_dir):
    for svg in sorted(symbols_dir.glob("*.svg")):
        assert rasterize_svg(svg, 24).max() == 255, svg.name


def test_sprite_sheet(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert set(idx) == {p.stem for p in symbols_dir.glob("*.svg")}
    assert all(e["sdf"] is True and e["pixelRatio"] == 1 for e in idx.values())
    with Image.open(tmp_path / "nav.png") as one, Image.open(tmp_path / "nav@2x.png") as two:
        assert two.size == tuple(2 * v for v in one.size)


def test_nav_style_icons_exist(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert check_style_sprites_glyphs(nav_style("day"), idx, {"Noto Sans Regular", "Noto Sans Bold"}) == []
