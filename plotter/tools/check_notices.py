#!/usr/bin/env python3
"""Check that every license named in the plotter section of THIRD_PARTY_NOTICES has its full text.

Usage: check_notices.py THIRD_PARTY_NOTICES
Exit 0 and print "notices ok: N license texts", or exit 1 and print the missing names.
"""
import re
import sys

PLOTTER_START = "Third-party components used by the plotter"
TEXTS_START = "Plotter license texts"
HEADER_ONLY_START = "Header-only code"

# Rows whose license is satisfied by a pointer in the row itself instead of a text heading.
POINTER_PREFIXES = ("LGPL-3.0", "SIL Open Font", "MIT (full text:", "CC0 1.0")
# Spellings used in the rows, mapped to the heading name.
ALIASES = {"Unicode / ICU licence": "ICU", "curl licence (MIT-style)": "curl"}


def names_in(value):
    """License names mentioned by one 'License:' value or table cell."""
    for spelled, name in ALIASES.items():
        value = value.replace(spelled, name)
    value = value.split("(")[0].replace("at your option", "")  # remarks such as "(parts Apache-2.0)"
    return [p.strip() for p in re.split(r",| or ", value) if p.strip()]


def main(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(PLOTTER_START))
    texts = next(i for i, line in enumerate(lines) if line == TEXTS_START)
    needed = set()
    unresolved = []
    in_table = False
    for line in lines[start:texts]:
        if line.startswith(HEADER_ONLY_START):
            in_table = True  # the header-only table runs to the next blank line
        elif in_table and not line.strip():
            in_table = False
        elif in_table:
            # Every row is "names  License" (two or more spaces before the license), or a run of
            # names ending in a comma that the next row continues.
            row = line.strip()
            if re.search(r"\S\s{2,}\S", row):
                needed.update(names_in(re.split(r"\s{2,}", row)[-1]))
            elif not row.endswith(","):
                unresolved.append(row)
        elif line.startswith("  License:"):
            value = line[len("  License:"):].strip()
            if not value.startswith(POINTER_PREFIXES):
                needed.update(names_in(value))
    have = {lines[i][: -len(" license text")] for i in range(texts, len(lines) - 1)
            if lines[i].endswith(" license text") and set(lines[i + 1]) == {"-"}}
    missing = sorted(needed - have)
    if unresolved:
        print("header-only rows with no license column: " + "; ".join(unresolved))
    if missing:
        print("missing license texts: " + ", ".join(missing))
    if unresolved or missing:
        return 1
    print(f"notices ok: {len(have)} license texts")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
