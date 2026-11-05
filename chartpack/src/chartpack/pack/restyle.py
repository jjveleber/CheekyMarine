"""Rewrite a built pack's styles and sprites from the current palette code, keeping the data and version."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from chartpack.pack.assemble import PROJECT, write_styles
from chartpack.pack.manifest import MANIFEST, write_manifest
from chartpack.style.palette import night_palette
from chartpack.style.sprites import build_sprites


def restyle_pack(root: Path, night: str = "amber") -> None:
    root = Path(root)
    old = json.loads((root / MANIFEST).read_text())
    pack = old["pack"]
    safety = None
    if pack == "charts":
        day = json.loads((root / "styles" / "nav-day.json").read_text())
        safety = day["metadata"]["cheekymarine"]["safety_contour_m"]
    colors = night_palette(night)
    write_styles(root, pack, safety, colors)
    build_sprites(PROJECT / "symbols", root / "sprites", "nav" if pack == "charts" else "fish", colors)
    # write_manifest reads only the region name and the pack's version from the region.
    region = SimpleNamespace(name=old["region"], charts_version=old["version"], bathy_version=old["version"])
    write_manifest(root, pack=pack, region=region, sources=old["sources"], notice=old["notice"],
                   built=datetime.strptime(old["built"], "%Y-%m-%dT%H:%M:%SZ"))
