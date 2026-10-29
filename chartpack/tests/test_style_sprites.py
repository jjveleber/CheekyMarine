import json

import numpy as np
from PIL import Image

from chartpack.style.fish import fish_style
from chartpack.style.nav import HAZARD_SHAPES, nav_style
from chartpack.style.palette import PALETTES
from chartpack.style.sprites import build_sprites, rasterize_svg
from chartpack.style.validate import check_style_sprites_glyphs


def test_all_symbols_rasterize_nonblank(symbols_dir):
    for svg in sorted(symbols_dir.glob("*.svg")):
        assert rasterize_svg(svg, 24).max() == 255, svg.name


def test_all_hazard_symbols_rasterize_nonblank(symbols_dir):
    for svg in sorted((symbols_dir / "hazard").glob("*.svg")):
        assert rasterize_svg(svg, 24).max() == 255, svg.name


HAZARD_ICONS = {f"hazard-{s}{d}-{p}" for s in HAZARD_SHAPES for d in ("", "-danger") for p in PALETTES}


def test_sprite_sheet(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert set(idx) == {p.stem for p in symbols_dir.glob("*.svg")} | HAZARD_ICONS
    assert all(e["sdf"] is (name not in HAZARD_ICONS) and e["pixelRatio"] == 1 for name, e in idx.items())
    with Image.open(tmp_path / "nav.png") as one, Image.open(tmp_path / "nav@2x.png") as two:
        assert two.size == tuple(2 * v for v in one.size)


def test_nav_style_icons_exist(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert check_style_sprites_glyphs(nav_style("day"), idx, {"Noto Sans Regular", "Noto Sans Bold"}) == []


def _pixels(sheet, entry):
    x, y, w, h = entry["x"], entry["y"], entry["width"], entry["height"]
    return sheet[y : y + h, x : x + w]


def test_hazard_images_are_mark_and_ring_in_palette_colours(tmp_path, symbols_dir):
    """R34: hazards are about 11 px at 1x, drawn at one size; the danger image is the same mark inside a red
    dotted ring, baked in the palette's CHBLK and DNGHL (an SDF image takes one colour). Plain and danger
    images are the same size, so their collision boxes match."""
    build_sprites(symbols_dir, tmp_path, "nav")
    for scale, suffix in ((1, ""), (2, "@2x")):
        idx = json.loads((tmp_path / f"nav{suffix}.json").read_text())
        with Image.open(tmp_path / f"nav{suffix}.png") as im:
            sheet = np.asarray(im.convert("RGBA"))
        for palette, p in PALETTES.items():
            ink, red = (tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in (p["CHBLK"], p["DNGHL"]))
            for shape in HAZARD_SHAPES:
                plain, danger = idx[f"hazard-{shape}-{palette}"], idx[f"hazard-{shape}-danger-{palette}"]
                assert (plain["width"], plain["height"]) == (danger["width"], danger["height"]) == (13 * scale, 13 * scale)
                assert plain["pixelRatio"] == danger["pixelRatio"] == scale
                a, b = _pixels(sheet, plain), _pixels(sheet, danger)
                assert (a[a[..., 3] == 255][:, :3] == ink).all() and (a[..., 3] == 255).any()  # the mark is solid ink

                def reds(im):  # strong pixels nearer the palette's red than its ink
                    strong = im[im[..., 3] >= 128][:, :3].astype(int)
                    return (abs(strong - red).sum(axis=1) < abs(strong - ink).sum(axis=1)).sum()

                assert reds(a) == 0 and reds(b) >= 12  # twelve ring dots
                # the ring sits outside the mark: the danger image is the plain one plus red dots round it
                assert (b[..., 3] > 0).sum() > (a[..., 3] > 0).sum()


def test_fish_style_icons_exist(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "fish")
    for palette in PALETTES:
        assert check_style_sprites_glyphs(fish_style(palette), idx, {"Noto Sans Regular", "Noto Sans Bold"}) == []
        assert check_style_sprites_glyphs(nav_style(palette), idx, {"Noto Sans Regular", "Noto Sans Bold"}) == []
