import json

import pytest

from chartpack.cli import main
from chartpack.pack.check import check_pack
from chartpack.pack.restyle import restyle_pack
from chartpack.style.palette import PALETTES

KEPT = ("pack", "region", "version", "schema", "built", "sources", "notice")


def test_restyle_rewrites_styles_and_manifest(charts_pack_root_copy, monkeypatch):
    root = charts_pack_root_copy
    before = json.loads((root / "manifest.json").read_text())
    monkeypatch.setitem(PALETTES["night"], "DEPDW", "#010203")
    restyle_pack(root)
    assert "#010203" in (root / "styles" / "nav-night.json").read_text()
    assert "#010203" not in (root / "styles" / "nav-day.json").read_text()
    after = json.loads((root / "manifest.json").read_text())
    assert {k: after[k] for k in KEPT} == {k: before[k] for k in KEPT}
    assert after["files"] != before["files"]
    assert check_pack(root) == []


def test_restyle_night_variants_write_their_text(charts_pack_root_copy):
    root = charts_pack_root_copy

    def shallow():
        style = json.loads((root / "styles" / "nav-night.json").read_text())
        return next(l for l in style["layers"] if l["id"] == "soundg-shallow")["paint"]["text-color"]

    assert main(["restyle", str(root)]) == 0
    assert shallow() == "#E0A000"
    assert main(["restyle", str(root), "--night", "amber"]) == 0
    assert shallow() == "#E0A000"
    nav = json.loads((root / "styles" / "nav-night.json").read_text())
    exprs = [l["paint"]["icon-color"] for l in nav["layers"] if isinstance(l.get("paint", {}).get("icon-color"), list)]
    assert any("4" in e and e[e.index("4") + 1] == "#20A040" for e in exprs if e[0] == "match" or "match" in e)
    assert main(["restyle", str(root), "--night", "red"]) == 0
    assert shallow() == "#FF2020"
    assert check_pack(root) == []


def test_restyle_refuses_a_pack_of_another_schema(charts_pack_root_copy, capsys):
    root = charts_pack_root_copy
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["schema"] = "0.0.1-old"
    (root / "manifest.json").write_text(json.dumps(manifest))
    before = (root / "styles" / "nav-night.json").read_text()
    with pytest.raises(ValueError, match="rebuild"):
        restyle_pack(root)
    assert main(["restyle", str(root)]) == 1
    assert "rebuild" in capsys.readouterr().err
    assert (root / "styles" / "nav-night.json").read_text() == before
    assert json.loads((root / "manifest.json").read_text())["schema"] == "0.0.1-old"


def test_restyle_keeps_the_charts_kind(charts_pack_root_copy):
    manifest = json.loads((charts_pack_root_copy / "manifest.json").read_text())
    manifest["charts"] = {"kind": "derived-inshore"}
    (charts_pack_root_copy / "manifest.json").write_text(json.dumps(manifest))
    restyle_pack(charts_pack_root_copy)
    assert json.loads((charts_pack_root_copy / "manifest.json").read_text())["charts"] == {"kind": "derived-inshore"}
