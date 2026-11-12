import json

import numpy as np
import pytest
from PIL import Image

from chartpack.style.fish import GRADE_PATTERNS, fish_style
from chartpack.style.nav import HAZARD_SHAPES, nav_style
from chartpack.style.palette import PALETTES, night_palette
from chartpack.style.sprites import build_sprites, rasterize_svg
from chartpack.style.validate import check_style_sprites_glyphs


def test_all_symbols_rasterize_nonblank(symbols_dir):
    for svg in sorted(symbols_dir.glob("*.svg")):
        assert rasterize_svg(svg, 24).max() == 255, svg.name


def test_all_hazard_symbols_rasterize_nonblank(symbols_dir):
    for svg in sorted((symbols_dir / "hazard").glob("*.svg")):
        assert rasterize_svg(svg, 24).max() == 255, svg.name


HAZARD_ICONS = {f"hazard-{s}{d}-{p}" for s in HAZARD_SHAPES for d in ("", "-danger") for p in PALETTES}
PATTERNS = {f"pat-{g}-{p}" for g in ("coarse-survey", "rough") for p in PALETTES}


def test_sprite_sheet(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "nav")
    assert set(idx) == {p.stem for p in symbols_dir.glob("*.svg")} | HAZARD_ICONS | PATTERNS
    assert all(e["sdf"] is (name not in HAZARD_ICONS | PATTERNS) and e["pixelRatio"] == 1 for name, e in idx.items())
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


def _rgba(tmp_path, suffix, name):
    idx = json.loads((tmp_path / f"{name}{suffix}.json").read_text())
    with Image.open(tmp_path / f"{name}{suffix}.png") as im:
        return idx, np.asarray(im.convert("RGBA"))


@pytest.mark.parametrize("night", [None, "red"])
def test_patterns_in_all_palettes(tmp_path, symbols_dir, night):
    """The two grade patterns (plan 8 spec 6) in every palette, at 1x and 2x: baked (not SDF) in the palette's CHGRD,
    light (they overlay depth shading and contours), and told apart by their shape, not by color."""
    colors = night_palette(night) if night else None
    build_sprites(symbols_dir, tmp_path, "fish", colors)
    palettes = {**PALETTES, "night": colors} if colors else PALETTES
    assert set(GRADE_PATTERNS) == {"coarse-survey", "rough"}
    for scale, suffix in ((1, ""), (2, "@2x")):
        idx, sheet = _rgba(tmp_path, suffix, "fish")
        for palette, p in palettes.items():
            ink = tuple(int(p["CHGRD"][i : i + 2], 16) for i in (1, 3, 5))
            masks = {}
            for grade in GRADE_PATTERNS:
                entry = idx[f"pat-{grade}-{palette}"]
                assert entry["sdf"] is False and entry["pixelRatio"] == scale
                assert entry["width"] == entry["height"] == 8 * scale
                im = _pixels(sheet, entry)
                alpha = im[..., 3]
                assert (alpha > 0).any() and (im[alpha > 0][:, :3] == ink).all()
                assert alpha.max() <= 160 and (alpha > 0).mean() <= 0.2  # light: part-transparent and sparse
                masks[grade] = alpha > 0
            assert (masks["coarse-survey"] != masks["rough"]).any()
            # a diagonal hatch: the same one pixel down and one left, so it also tiles without seams; isolated dots
            # that leave the edges clear
            rough = masks["rough"]
            assert rough.any(axis=0).all() and rough.any(axis=1).all()
            assert (np.roll(np.roll(rough, 1, axis=0), -1, axis=1) == rough).all()
            assert not masks["coarse-survey"][0].any() and not masks["coarse-survey"][:, 0].any()


def test_validator_checks_fill_patterns(tmp_path, symbols_dir):
    idx = build_sprites(symbols_dir, tmp_path, "fish")
    style = {"layers": [{"id": "x", "type": "fill", "paint": {"fill-pattern": "pat-nothing-day"}}]}
    assert check_style_sprites_glyphs(style, idx, set()) == ["x: pattern 'pat-nothing-day' not in sprite"]
    del idx["pat-rough-dusk"]
    errors = check_style_sprites_glyphs(fish_style("dusk"), idx, {"Noto Sans Regular", "Noto Sans Bold"})
    assert errors == ["grade-rough-coarse: pattern 'pat-rough-dusk' not in sprite",
                      "grade-rough: pattern 'pat-rough-dusk' not in sprite"]
