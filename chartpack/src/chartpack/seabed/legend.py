"""legend.json: the meaning and sources of every seabed abbreviation in a pack (spec 6.10)."""

from collections.abc import Iterable

from chartpack.seabed.codes import CATWED, CHART_NO1, NATQUA, NATSUR, split_codes

LEGEND_SCHEMA = 1


def _abbreviations(props: dict) -> list[tuple[str, str, str]]:
    """(abbr, meaning, kind) of each code on one seabed feature."""
    if props["class"] == "WEDKLP":
        catwed = props.get("CATWED")
        return [(*CATWED[2 if catwed is None else catwed], "type")]
    out = [(*NATSUR[int(c)], "type") for c in split_codes(props.get("NATSUR")) if c]
    return out + [(*NATQUA[int(c)], "qualifier") for c in split_codes(props.get("NATQUA")) if c]


def build_legend(features: Iterable[dict]) -> dict:
    """One entry per abbreviation present in the features (tile properties), types before qualifiers."""
    entries: dict[str, dict] = {}
    for props in features:
        for abbr, meaning, kind in _abbreviations(props):
            entry = entries.setdefault(abbr, {"abbr": abbr, "meaning": meaning, "kind": kind, "sources": []})
            if props["src"] not in entry["sources"]:
                entry["sources"].append(props["src"])
    for entry in entries.values():
        entry["sources"].sort()
    return {"schema": LEGEND_SCHEMA,
            "entries": sorted(entries.values(), key=lambda e: (e["kind"] != "type", e["abbr"]))}


_DOC_HEAD = """# Seabed legend

Generated from `chartpack/src/chartpack/seabed/codes.py` (`legend_markdown`); do not edit by hand.

The charts pack `seabed` layer labels each ENC seabed area (`SBDARE`) and weed or kelp feature
(`WEDKLP`) with the chart abbreviations below. Each pack's `legend.json` lists the ones it uses.

Sources: US Chart No. 1, 13th edition, section J "Nature of the Seabed" (NOAA and NGA, public domain),
NOAA column where it differs from INT, INT otherwise; codes from the IHO S-57 Edition 3.1 attribute
catalogue (Appendix A chapter 2: NATSUR 113, NATQUA 114, CATWED 70).

Mixtures (Chart No. 1 J 12.2): the main constituent comes first, the types are joined with a dot, and
each qualifier is written in front of the type in the same list position, so NATSUR `4,1` with NATQUA
`1` reads `fS.M`, fine sand with mud. A qualifier with no type (S-57 allows NATQUA alone) is shown on
its own, for example `h`, hard bottom. Kelp is drawn with its J 13.2 symbol beside the word Kelp; a
weed or kelp feature with no category reads `Wd` (J 13.1, weed including kelp).

| Abbreviation | Meaning | Kind | S-57 code | Chart No. 1 |
|---|---|---|---|---|
"""


def legend_markdown() -> str:
    """docs/chartpack/seabed-legend.md: every code the tool can label, with its source."""
    rows = []
    for name, table, kind in (("NATSUR", NATSUR, "type"), ("CATWED", CATWED, "type"), ("NATQUA", NATQUA, "qualifier")):
        for code, (abbr, meaning) in table.items():
            rows.append(f"| {abbr} | {meaning} | {kind} | {name} {code} | {CHART_NO1[name][code]} |")
    return _DOC_HEAD + "\n".join(rows) + "\n"
