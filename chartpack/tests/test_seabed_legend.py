import json
from pathlib import Path

from chartpack.mbtiles import MBTiles, decode_pbf
from chartpack.seabed.legend import build_legend, legend_markdown

DOC = Path(__file__).resolve().parents[2] / "docs" / "chartpack" / "seabed-legend.md"


def test_build_legend_lists_each_abbreviation_once_with_sources():
    legend = build_legend([
        {"src": "enc", "class": "SBDARE", "NATSUR": "4,1", "NATQUA": "1"},
        {"src": "enc", "class": "SBDARE", "NATSUR": "4"},
        {"src": "enc", "class": "SBDARE", "NATQUA": "10"},
        {"src": "enc", "class": "WEDKLP", "CATWED": 1},
        {"src": "enc", "class": "WEDKLP"},
    ])
    assert legend["schema"] == 1
    entries = {e["abbr"]: e for e in legend["entries"]}
    assert len(entries) == len(legend["entries"]) and set(entries) == {"S", "M", "f", "h", "Kelp", "Wd"}
    assert entries["S"] == {"abbr": "S", "meaning": "sand", "kind": "type", "sources": ["enc"]}
    assert entries["f"]["kind"] == "qualifier" and entries["f"]["meaning"] == "fine"
    assert entries["Kelp"]["kind"] == "type" and entries["Wd"]["kind"] == "type"


def test_build_legend_merges_sources():
    legend = build_legend([{"src": "usseabed", "class": "SBDARE", "NATSUR": "4"},
                           {"src": "enc", "class": "SBDARE", "NATSUR": "4"}])
    assert legend["entries"] == [{"abbr": "S", "meaning": "sand", "kind": "type", "sources": ["enc", "usseabed"]}]


def test_build_legend_empty():
    assert build_legend([]) == {"schema": 1, "entries": []}


def _split(label, types, qualifiers):
    """The abbreviations in a chart label such as "fS.M" or "fsoS", read against the legend."""
    out = []
    for part in label.split("."):
        type_ = next((t for t in sorted(types, key=len, reverse=True) if part.endswith(t)), "")
        out.append(type_)
        rest = part[: len(part) - len(type_)]
        while rest:
            q = next(q for q in sorted(qualifiers, key=len, reverse=True) if rest.startswith(q))
            out.append(q)
            rest = rest[len(q):]
    return [a for a in out if a]


def test_legend_covers_every_label(charts_pack_root):
    legend = json.loads((charts_pack_root / "legend.json").read_text())
    assert legend["schema"] == 1
    entries = {e["abbr"]: e for e in legend["entries"]}
    assert all(e["meaning"] and e["sources"] for e in entries.values())
    types = {a for a, e in entries.items() if e["kind"] == "type"}
    qualifiers = {a for a, e in entries.items() if e["kind"] == "qualifier"}
    labels = set()
    with MBTiles.open(charts_pack_root / "enc.mbtiles") as m:
        for z in range(6, 17):
            for _, _, data in m.tiles_at(z):
                labels |= {f["properties"].get("label") for f in decode_pbf(data).get("seabed", [])} - {None}
    assert {"fS", "S.M", "h", "Kelp"} <= labels
    used = {a for label in labels for a in _split(label, types, qualifiers)}
    assert used == set(entries)  # every abbreviation shown is explained, and nothing unused is listed


def test_legend_lists_sources(charts_pack_root):
    """Each abbreviation names every source whose features show it: the session pack holds the test cell's
    ENC marks plus the usSEABED and Seattle CMECS fixtures (tests/conftest.py)."""
    legend = json.loads((charts_pack_root / "legend.json").read_text())
    entries = {e["abbr"]: e for e in legend["entries"]}
    types = {a for a, e in entries.items() if e["kind"] == "type"}
    qualifiers = {a for a, e in entries.items() if e["kind"] == "qualifier"}
    seen: dict[str, set] = {}
    with MBTiles.open(charts_pack_root / "enc.mbtiles") as m:
        for z in range(6, 17):
            for _, _, data in m.tiles_at(z):
                for f in decode_pbf(data).get("seabed", []):
                    for abbr in _split(f["properties"].get("label") or "", types, qualifiers):
                        seen.setdefault(abbr, set()).add(f["properties"]["src"])
    assert {a: e["sources"] for a, e in entries.items()} == {a: sorted(s) for a, s in seen.items()}
    assert entries["M"]["sources"] == ["enc", "usgs-cmecs", "usseabed"]


def test_build_legend_reads_usgs_classes():
    legend = build_legend([{"src": "usseabed", "class": "SAMPLE", "folk": "gmS"},
                           {"src": "usseabed", "class": "SAMPLE", "folk": "H"},
                           {"src": "usseabed", "class": "SAMPLE", "folk": "xS"},
                           {"src": "usgs-cmecs", "class": "CMECS", "substrate": "Sandy cobble"},
                           {"src": "usgs-cmecs", "class": "CMECS", "substrate": "fine unconsolidated substrate"}])
    assert legend["entries"] == [
        {"abbr": "Cb", "meaning": "cobbles", "kind": "type", "sources": ["usgs-cmecs"]},
        {"abbr": "G", "meaning": "gravel", "kind": "type", "sources": ["usseabed"]},
        {"abbr": "M", "meaning": "mud", "kind": "type", "sources": ["usseabed"]},
        {"abbr": "S", "meaning": "sand", "kind": "type", "sources": ["usgs-cmecs", "usseabed"]},
        {"abbr": "h", "meaning": "hard", "kind": "qualifier", "sources": ["usseabed"]},
    ]


def test_legend_in_manifest(charts_pack_root):
    manifest = json.loads((charts_pack_root / "manifest.json").read_text())
    assert "legend.json" in {f["name"] for f in manifest["files"]}


def test_published_legend_doc_is_generated_from_codes(request):
    """docs/chartpack/seabed-legend.md is legend_markdown() verbatim (--update-golden rewrites it)."""
    if request.config.getoption("--update-golden"):
        DOC.write_text(legend_markdown())
    text = DOC.read_text()
    assert text == legend_markdown()
    assert "| Rk | rock | type | NATSUR 9 |" in text and "| f | fine | qualifier | NATQUA 1 |" in text
    assert "| Kelp | kelp | type | CATWED 1 |" in text and "fS.M" in text
    assert "| gmS | gravelly muddy sand | S.M.G |" in text and "| sandy cobble | Cb.S |" in text
