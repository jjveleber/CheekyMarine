import pytest

from chartpack.seabed.codes import CATWED, NATQUA, NATSUR, label, weed_label

# Every expected input of the S-57 attribute catalogue (IHO S-57 Edition 3.1 Appendix A chapter 2):
# NATSUR (code 113), NATQUA (code 114), CATWED (code 70).
S57_NATSUR = range(1, 19)
S57_NATQUA = range(1, 11)
S57_CATWED = range(1, 5)


def test_label_single_and_mixed():
    assert label("4", None) == "S" and label("1", None) == "M" and label("9", None) == "Rk"
    # US Chart No. 1 J 12.2: main constituent first, qualifier written before the type it qualifies, "fS.M.Sh"
    assert label("4,1", "1") == "fS.M"
    assert label("4,1", "1,") == "fS.M"
    assert label("4,1,17", "1,,4") == "fS.M.bkSh"
    assert label(None, None) is None and label("", "") is None


def test_qualifier_without_type():
    """S-57 Appendix B.1 requires at least one of NATSUR and NATQUA on SBDARE, so a quality alone is
    charted data (the test cell has NATQUA 10 alone) and is labelled, not dropped."""
    assert label(None, "10") == "h" and label(None, "6") == "so"


def test_more_qualifiers_than_types_go_on_the_last_type():
    assert label("4", "1,6") == "fsoS"


def test_chart_no1_abbreviations():
    assert {c: NATSUR[c][0] for c in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 14, 17, 18)} == {
        1: "M", 2: "Cy", 3: "Si", 4: "S", 5: "St", 6: "G", 7: "P", 8: "Cb", 9: "Rk", 11: "La", 14: "Co",
        17: "Sh", 18: "Blds"}
    assert {c: NATQUA[c][0] for c in S57_NATQUA} == {
        1: "f", 2: "m", 3: "c", 4: "bk", 5: "sy", 6: "so", 7: "sf", 8: "vol", 9: "Ca", 10: "h"}


def test_every_code_has_meaning():
    for table, codes in ((NATSUR, S57_NATSUR), (NATQUA, S57_NATQUA), (CATWED, S57_CATWED)):
        assert set(table) == set(codes)
        assert all(abbr and meaning for abbr, meaning in table.values())
    for code in S57_NATSUR:
        assert label(str(code), None) == NATSUR[code][0]


def test_abbreviations_are_unambiguous():
    """One meaning per abbreviation, and no type abbreviation doubles as a qualifier."""
    by_abbr = {}
    for table in (NATSUR, CATWED):
        for abbr, meaning in table.values():
            assert by_abbr.setdefault(abbr, meaning) == meaning, abbr
    assert not set(by_abbr) & {a for a, _ in NATQUA.values()}


def test_unknown_code_is_an_error():
    with pytest.raises(ValueError, match="NATSUR 99"):
        label("99", None)
    with pytest.raises(ValueError, match="NATQUA 42"):
        label("4", "42")


def test_weed_label():
    assert weed_label(1) == "Kelp" and weed_label(2) == "Wd" and weed_label(3) == "Sg" and weed_label(4) == "Wd"
    assert weed_label(None) == "Wd"


def test_usgs_labels_use_only_chart_no1_abbreviations():
    """usSEABED Folk classes and CMECS substrate names map onto the same Chart No. 1 set (ruling R25):
    every part of every label is an abbreviation the S-57 tables already define."""
    from chartpack.seabed.codes import ABBREVIATIONS, CMECS, FOLK

    labels = [(code, abbr_label) for code, (abbr_label, _) in FOLK.items()] + list(CMECS.items())
    for name, abbr_label in labels:
        assert all(part in ABBREVIATIONS for part in abbr_label.split(".")), name
    assert ABBREVIATIONS["Cb"] == ("cobbles", "type") and ABBREVIATIONS["h"] == ("hard", "qualifier")


def test_usgs_labels_main_constituent_first():
    from chartpack.seabed.codes import cmecs_label, folk_label

    assert folk_label("mS") == "S.M" and folk_label("sM") == "M.S" and folk_label("msG") == "G.S.M"
    assert folk_label("H") == "h" and folk_label("G") == "G" and folk_label("gS") == "S.G"
    # ruling R26: slightly gravelly (g) classes (under 5 % gravel) are labelled by their main classes only
    assert {c: folk_label(c) for c in ("(g)M", "(g)S", "(g)mS", "(g)sM")} == {
        "(g)M": "M", "(g)S": "S", "(g)mS": "S.M", "(g)sM": "M.S"}
    assert cmecs_label("muddy sand") == "S.M" and cmecs_label("bedrock") == "Rk" and cmecs_label("boulder") == "Blds"
    assert cmecs_label("Sandy cobble") == cmecs_label("sandy cobble") == "Cb.S"  # Admiralty Inlet capitalises one
    # a CMECS level that does not say which grain dominates gets no label
    for name in ("gravelly", "slightly gravelly", "gravel mix", "cobble mix", "cobbley", "fine unconsolidated substrate",
                 "coarse unconsolidated substrate", "unconsolidated mineral substrate", "anthropogenic rock rubble"):
        assert cmecs_label(name) is None, name
