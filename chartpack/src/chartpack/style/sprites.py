"""SDF sprite sheets from the in-house Chart No. 1 style SVG symbols, rasterized without an SVG library.

Supported SVG: circle, rect, polygon, line, polyline and path (M L H V A Z, absolute and relative).
Shapes are painted in document order. A black (default) fill paints opaque; fill="white" knocks the
shape out again, which is how rings are drawn. line and polyline need stroke-width and are stroked.

The hazard marks (symbols/hazard/) are not SDF: each is baked in each palette's colours, plain (CHBLK) and
inside the danger ring (DNGHL), so a hazard and its ring are one image that always shows or hides as one
(R34, R41). An SDF image takes one colour, and two symbol layers cannot be made to collide as one. That
is why hazard icon names carry the palette (hazard-rock-danger-night) and icon-color does not tint them.
"""

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from chartpack.style.nav import HAZARD_SHAPES, hazard_icon
from chartpack.style.palette import PALETTES
from chartpack.style.sdf import bitmap_to_sdf

_VIEWBOX = 24
_SUPERSAMPLE = 4
_SDF_BUFFER = 3
_GUTTER = 2
_HAZARD_PX = 11  # the hazard mark and its ring, drawn at this size at 1x (R34)
_HAZARD_PAD = 1  # transparent margin round it
_TOKEN = re.compile(r"[MLHVAZmlhvaz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "A": 7, "Z": 0}


def _arc_points(x0, y0, rx, ry, rot, large, sweep, x1, y1, steps=48):
    """Points along an SVG elliptical arc (endpoint to centre parameterisation, SVG 1.1 appendix F.6)."""
    if (x0, y0) == (x1, y1):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x1, y1)]
    phi = math.radians(rot)
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    xp, yp = c * dx + s * dy, -s * dx + c * dy
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    coef = math.sqrt(max(num / den, 0)) * (-1 if large == sweep else 1)
    cxp, cyp = coef * rx * yp / ry, -coef * ry * xp / rx
    cx, cy = c * cxp - s * cyp + (x0 + x1) / 2, s * cxp + c * cyp + (y0 + y1) / 2

    def angle(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    t1 = angle(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    dt = angle((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    points = []
    for i in range(1, steps + 1):
        t = t1 + dt * i / steps
        points.append((cx + rx * math.cos(t) * c - ry * math.sin(t) * s, cy + rx * math.cos(t) * s + ry * math.sin(t) * c))
    return points


def _path_subpaths(d: str, where: str) -> list[list[tuple[float, float]]]:
    tokens = _TOKEN.findall(d)
    if "".join(tokens) != re.sub(r"[\s,]", "", d):
        raise ValueError(f"{where}: unsupported path data {d!r}")
    subpaths, current, pos, start, i, cmd = [], [], (0.0, 0.0), (0.0, 0.0), 0, None
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        elif cmd is None:
            raise ValueError(f"{where}: path data must start with a command")
        up, rel = cmd.upper(), cmd.islower()
        if up not in _ARGS:
            raise ValueError(f"{where}: unsupported path command {cmd!r}")
        n = _ARGS[up]
        args = [float(t) for t in tokens[i : i + n]]
        if len(args) < n or any(t.isalpha() for t in tokens[i : i + n]):
            raise ValueError(f"{where}: bad arguments for {cmd!r}")
        i += n
        ox, oy = pos if rel else (0.0, 0.0)
        if up == "Z":
            if current:
                subpaths.append(current)
            current, pos = [], start
            cmd = None
            continue
        if up == "M":
            if current:
                subpaths.append(current)
            pos = (args[0] + ox, args[1] + oy)
            start, current = pos, [pos]
            cmd = "l" if rel else "L"
        elif up == "L":
            pos = (args[0] + ox, args[1] + oy)
            current.append(pos)
        elif up == "H":
            pos = (args[0] + ox, pos[1])
            current.append(pos)
        elif up == "V":
            pos = (pos[0], args[0] + oy)
            current.append(pos)
        else:
            end = (args[5] + ox, args[6] + oy)
            current += _arc_points(*pos, args[0], args[1], args[2], bool(args[3]), bool(args[4]), *end)
            pos = end
    if current:
        subpaths.append(current)
    return subpaths


def _numbers(text: str) -> list[float]:
    return [float(t) for t in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", text)]


def rasterize_svg(path: Path, size: int) -> np.ndarray:
    """Alpha mask (uint8, size by size) of an SVG with viewBox 0 0 24 24."""
    root = ET.parse(path).getroot()
    big = size * _SUPERSAMPLE
    k = big / _VIEWBOX
    image = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(image)
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        where = f"{Path(path).name}: <{tag}>"
        if tag in ("svg", "g", "title", "desc"):
            continue
        fill = {"white": 0, "#fff": 0, "#ffffff": 0}.get(el.get("fill", "black").lower(), 255)
        if tag == "circle":
            cx, cy, r = (float(el.get(a)) for a in ("cx", "cy", "r"))
            draw.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=fill)
        elif tag == "rect":
            x, y, w, h = (float(el.get(a)) for a in ("x", "y", "width", "height"))
            draw.rectangle([x * k, y * k, (x + w) * k - 1, (y + h) * k - 1], fill=fill)
        elif tag == "polygon":
            nums = _numbers(el.get("points", ""))
            draw.polygon([(nums[j] * k, nums[j + 1] * k) for j in range(0, len(nums) - 1, 2)], fill=fill)
        elif tag in ("line", "polyline"):
            if tag == "line":
                nums = [float(el.get(a)) for a in ("x1", "y1", "x2", "y2")]
            else:
                nums = _numbers(el.get("points", ""))
            pts = [(nums[j] * k, nums[j + 1] * k) for j in range(0, len(nums) - 1, 2)]
            draw.line(pts, fill=0 if el.get("stroke") == "white" else 255,
                      width=round(float(el.get("stroke-width", "1")) * k), joint="curve")
        elif tag == "path":
            for sub in _path_subpaths(el.get("d", ""), where):
                draw.polygon([(x * k, y * k) for x, y in sub], fill=fill)
        else:
            raise ValueError(f"{where}: unsupported element")
    return np.asarray(image.resize((size, size), Image.LANCZOS), dtype=np.uint8)


def _rgb(colour: str) -> np.ndarray:
    return np.array([int(colour[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float64)


def _paint(layers: list[tuple[np.ndarray, str]], pad: int) -> np.ndarray:
    """Alpha masks painted bottom to top in their colours (straight alpha "over"), as padded RGBA uint8."""
    shape = layers[0][0].shape
    rgb, alpha = np.zeros(shape + (3,)), np.zeros(shape)
    for mask, colour in layers:
        a = mask / 255.0
        out = a + alpha * (1 - a)
        with np.errstate(invalid="ignore", divide="ignore"):
            rgb = np.where(out[..., None] > 0,
                           (_rgb(colour) * a[..., None] + rgb * (alpha * (1 - a))[..., None]) / out[..., None], 0)
        alpha = out
    image = np.dstack([rgb, alpha * 255]).round().astype(np.uint8)
    return np.pad(image, ((pad, pad), (pad, pad), (0, 0)))


def _hazard_images(symbols_dir: Path, scale: int) -> dict[str, np.ndarray]:
    """hazard_icon(shape, danger, palette) -> RGBA image, for every shape, both states and every palette."""
    size, folder = _HAZARD_PX * scale, Path(symbols_dir) / "hazard"
    ring = rasterize_svg(folder / "danger-ring.svg", size)
    marks = {shape: rasterize_svg(folder / f"{shape}.svg", size) for shape in HAZARD_SHAPES}
    images = {}
    for palette, p in PALETTES.items():
        for shape, mark in marks.items():
            images[hazard_icon(shape, False, palette)] = _paint([(mark, p["CHBLK"])], _HAZARD_PAD * scale)
            images[hazard_icon(shape, True, palette)] = _paint([(ring, p["DNGHL"]), (mark, p["CHBLK"])], _HAZARD_PAD * scale)
    return images


def _sheet(symbols: list[Path], symbols_dir: Path, scale: int) -> tuple[Image.Image, dict]:
    size, buffer, gutter = _VIEWBOX * scale, _SDF_BUFFER * scale, _GUTTER * scale
    cells = [bitmap_to_sdf(rasterize_svg(p, size), buffer=buffer, radius=8.0 * scale) for p in symbols]
    baked = _hazard_images(symbols_dir, scale)
    width = size + 2 * buffer
    total = len(cells) * (width + gutter) + sum(im.shape[1] + gutter for im in baked.values()) - gutter
    sheet = np.zeros((width, total, 4), np.uint8)
    sheet[..., :3] = 255
    index = {}
    for i, (p, cell) in enumerate(zip(symbols, cells)):
        x = i * (width + gutter)
        sheet[:, x : x + width, 3] = cell
        index[p.stem] = {"width": width, "height": width, "x": x, "y": 0, "pixelRatio": scale, "sdf": True}
    x = len(cells) * (width + gutter)
    for name, im in baked.items():
        h, w = im.shape[:2]
        sheet[:h, x : x + w] = im
        index[name] = {"width": w, "height": h, "x": x, "y": 0, "pixelRatio": scale, "sdf": False}
        x += w + gutter
    return Image.fromarray(sheet, "RGBA"), index


def build_sprites(symbols_dir: Path, out_dir: Path, name: str) -> dict:
    """Write <name>.png/.json and <name>@2x.png/.json (SDF in the alpha channel); return the 1x index."""
    symbols = sorted(Path(symbols_dir).glob("*.svg"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for scale, suffix in ((1, ""), (2, "@2x")):
        image, index = _sheet(symbols, symbols_dir, scale)
        image.save(out_dir / f"{name}{suffix}.png")
        (out_dir / f"{name}{suffix}.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
        if not suffix:
            result = index
    return result
