"""The vector tile schema (spec 6.3). Attribute names are S-57 acronyms."""

from dataclasses import dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LayerSpec:
    name: str
    classes: tuple[str, ...]
    attributes: tuple[str, ...]
    geometry: str  # "point" | "line" | "polygon" | "any"


# A class listed in two layers (TSSLPT) goes to the first layer whose geometry accepts the feature.
LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec("depare", ("DEPARE", "DRGARE"), ("DRVAL1", "DRVAL2"), "polygon"),
    LayerSpec("depcnt", ("DEPCNT",), ("VALDCO",), "line"),
    LayerSpec("soundg", ("SOUNDG",), ("depth", "SCAMIN"), "point"),
    LayerSpec("coalne", ("COALNE", "SLCONS"), ("CATSLC",), "line"),
    LayerSpec("lndare", ("LNDARE",), (), "any"),
    LayerSpec(
        "hazard",
        ("UWTROC", "WRECKS", "OBSTRN"),
        ("VALSOU", "WATLEV", "CATWRK", "CATOBS", "EXPSOU", "QUASOU"),
        "any",
    ),
    LayerSpec(
        "navaid",
        (
            "BOYLAT", "BOYCAR", "BOYSAW", "BOYISD", "BOYSPP",
            "BCNLAT", "BCNCAR", "BCNSAW", "BCNISD", "BCNSPP", "DAYMAR",
        ),
        ("BOYSHP", "BCNSHP", "COLOUR", "COLPAT", "CATLAM", "CATCAM", "OBJNAM"),
        "point",
    ),
    LayerSpec(
        "light",
        ("LIGHTS",),
        ("COLOUR", "LITCHR", "SIGPER", "SIGGRP", "VALNMR", "SECTR1", "SECTR2", "OBJNAM"),
        "point",
    ),
    LayerSpec(
        "area",
        ("ACHARE", "RESARE", "HRBFAC", "SMCFAC", "MIPARE", "TSSLPT", "TSEZNE", "CTNARE", "SEAARE"),
        ("CATREA", "CATHAF", "CATSCF", "RESTRN", "OBJNAM", "SCAMIN"),
        "polygon",
    ),
    LayerSpec(
        "line",
        ("CBLSUB", "CBLARE", "PIPSOL", "PIPARE", "FERYRT", "TSSLPT", "NAVLNE", "RECTRC"),
        ("OBJNAM", "SCAMIN"),
        "any",
    ),
    LayerSpec("meta", ("M_COVR", "M_QUAL"), ("CATZOC",), "polygon"),
    # Bottom composition (spec 6.10). src and label are set by the reader, not read from the cell; folk
    # (usSEABED Folk class) and substrate (CMECS substrate name) come from the USGS sources, not the ENC.
    LayerSpec("seabed", ("SBDARE", "WEDKLP"),
              ("src", "NATSUR", "NATQUA", "CATWED", "label", "SCAMIN", "folk", "substrate"), "any"),
)

SAFETY_LAYERS = ("depare", "depcnt", "hazard", "navaid", "light", "coalne", "lndare")

# Schema layers a region may have no features in (ruling R21): the build and the pack check accept their absence.
OPTIONAL_LAYERS: frozenset[str] = frozenset({"seabed"})

# The bathy.mbtiles layers (Task 13). Not S-57 classes: classes is empty.
BATHY_LAYER_SPECS: tuple[LayerSpec, ...] = (
    LayerSpec("contour", (), ("depth_ft", "major", "minzoom", "source"), "line"),
    LayerSpec("band", (), ("depth_min_ft", "depth_max_ft", "minzoom"), "polygon"),
    LayerSpec("coverage", (), ("source", "resolution_m", "date"), "polygon"),
)
