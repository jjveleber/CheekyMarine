"""chartpack command line."""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import box, shape
from shapely.ops import unary_union

from chartpack import __version__
from chartpack.bathy.blocks import (
    BLOCK_MARGIN_DEG,
    area_datum,
    build_block,
    build_overview,
    dem_tiles,
    fine_owned_z12,
    iter_blocks,
    overview_bounds,
)
from chartpack.bathy.crm import crm_path, crm_tile_requests, crm_wcs_url, fetch_crm
from chartpack.bathy.cudem import URLLIST, parse_urllist, tiles_for_bbox
from chartpack.bathy.dem import build_dem_mbtiles, empty_dem_mbtiles
from chartpack.bathy.tiles import (
    COARSE_ZOOMS,
    MAXZOOM,
    MINZOOM,
    append_features,
    enc_depcnt,
    enc_fallback_contours,
    tile_bathy,
)
from chartpack.cache import download
from chartpack.datum import geoid
from chartpack.enc.catalog import CATALOG_URL, cells_in_bbox, parse_catalog
from chartpack.enc.fetch import fetch_cells
from chartpack.enc.reader import read_cell
from chartpack.enc.tiles import OVERVIEW_ZOOMS, REGION_ZOOMS, build_enc_mbtiles
from chartpack.grid import keep_tiles, owned_tiles
from chartpack.pack.archive import archive_pack
from chartpack.pack.assemble import BATHY_FILES, assemble_bathy_pack, assemble_charts_pack
from chartpack.pack.check import check_pack
from chartpack.pack.manifest import describe_pack, write_manifest
from chartpack.pack.restyle import restyle_pack
from chartpack.region import load_region
from chartpack.style.palette import NIGHT_VARIANTS
from chartpack.seabed.cmecs import BLOCKS, fetch_cmecs, read_cmecs
from chartpack.seabed.usseabed import FILES, fetch_usseabed, read_usseabed


def _load_catalog(cache: Path):
    # The catalog changes nightly, so it is fetched on every run.
    return parse_catalog(download(CATALOG_URL, cache / "ENCProdCat.xml").read_bytes())


def _fetch_enc(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    catalog = _load_catalog(args.cache)
    names = [n for band in sorted(region.cells) for n in region.cells[band]]
    for name, _ in zip(names, fetch_cells(names, catalog, args.cache)):
        c = catalog[name]
        print(f"{name} {c.edtn}.{c.updn} {c.isdt.isoformat()}")
    return 0


def _cells(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    for name in cells_in_bbox(_load_catalog(args.cache), region.bbox, args.band):
        print(name)
    return 0


def _newest_cached_zip(cache: Path, name: str) -> Path:
    """The cached zip of the newest edition.update for a cell; fail if there is none."""
    found = []
    for path in (cache / "enc").glob(f"{name}-*.zip"):
        m = re.fullmatch(rf"{re.escape(name)}-(\d+)\.(\d+)\.zip", path.name)
        if m:
            found.append(((int(m[1]), int(m[2])), path))
    if not found:
        raise SystemExit(f"{name}: no cached zip under {cache / 'enc'}; run fetch-enc first")
    return max(found)[1]


def _fetch_seabed(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    paths = fetch_usseabed(args.cache) if "usseabed" in region.seabed_sources else []
    for path in paths + fetch_cmecs(list(region.cmecs_blocks), args.cache):
        print(path)
    return 0


def _usgs_seabed(region, cache: Path) -> list:
    """The region's USGS seabed features from the fetch-seabed cache."""
    usseabed = [cache / "seabed" / name for name in FILES] if "usseabed" in region.seabed_sources else []
    blocks = {block: cache / "seabed" / f"{BLOCKS[block].name}.zip" for block in region.cmecs_blocks}
    missing = [p for p in usseabed + list(blocks.values()) if not p.is_file()]
    if missing:
        raise SystemExit(f"{missing[0]} not found; run fetch-seabed first")
    features = read_usseabed(usseabed, region.bbox) if usseabed else []
    for block, path in blocks.items():
        features += read_cmecs(path, block, region.bbox)
    return features


def _build_enc(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    names = [n for band in sorted(region.cells) for n in region.cells[band]]
    cells = [read_cell(_newest_cached_zip(args.cache, name)) for name in names]
    owned = owned_tiles(region, args.region.parent)  # before the slow build: a bad grid fails fast
    zooms = OVERVIEW_ZOOMS if region.overview else REGION_ZOOMS
    enc = build_enc_mbtiles(cells, args.work / "enc.mbtiles", region=region, work=args.work / "tippecanoe",
                            seabed=_usgs_seabed(region, args.cache), zooms=zooms)
    keep_tiles(enc, owned, minzoom=zooms[0], maxzoom=zooms[1])
    print(_finish(assemble_charts_pack(region, enc, args.out), region))
    return 0


def _finish(root: Path, region) -> Path:
    """Write the manifest, the last step of a build: a built pack is always complete."""
    pack, sources, notice = describe_pack(root)
    write_manifest(root, pack=pack, region=region, sources=sources, notice=notice, built=datetime.now(timezone.utc))
    return root


def _manifest(args: argparse.Namespace) -> int:
    _finish(args.packdir, load_region(args.region))
    return 0


def _restyle(args: argparse.Namespace) -> int:
    try:
        restyle_pack(args.packdir, args.night)
    except ValueError as error:
        print(f"restyle: {error}", file=sys.stderr)
        return 1
    return 0


def _check(args: argparse.Namespace) -> int:
    errors, zips = [], None
    if args.enc_cache:
        try:
            manifest = json.loads((args.packdir / "manifest.json").read_text())
            cells = manifest["sources"] if manifest["pack"] == "charts" else []
            paths = [args.enc_cache / "enc" / f"{s['cell']}-{s['edtn']}.{s['updn']}.zip" for s in cells]
        except (OSError, ValueError, KeyError, TypeError):
            paths = []  # check_pack reports the manifest problem
        errors = [f"{p}: ENC zip not found in --enc-cache" for p in paths if not p.is_file()]
        zips = [p for p in paths if p.is_file()]
    errors += check_pack(args.packdir, enc_zips=zips)
    for error in errors:
        print(error)
    return 1 if errors else 0


def _archive(args: argparse.Namespace) -> int:
    tar, sums = archive_pack(args.packdir, args.out)
    print(tar)
    print(sums)
    return 0


def _fetch_bathy(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    owned = owned_tiles(region, args.region.parent)
    geoid.fetch_grids(args.cache / "proj")  # every build converts CRM (EGM2008 heights) through NAVD88
    if owned is None:  # the overview: one native CRM request over the region, no CUDEM
        print(fetch_crm(overview_bounds(region.bbox), args.cache))
        return 0
    # The tile list changes as NCEI adds tiles, so it is fetched on every run.
    tiles = parse_urllist(download(URLLIST, args.cache / "cudem" / "urllist8483.txt").read_text())
    blocks = list(iter_blocks(owned))
    for name in sorted({t.name for _, _, read in blocks for t in tiles_for_bbox(tiles, read)}):
        print(name)
    for _, _, read in blocks:  # one CRM request per owned tile, over its read bounds
        print(fetch_crm(read, args.cache))
    return 0


def _append_layers(work: Path, contours: list[dict], bands: list[dict], coverage: list[dict]) -> None:
    for name, feats in (("contour", contours), ("band", bands), ("coverage", coverage)):
        append_features(feats, work / f"{name}.geojsonseq")


def _build_bathy(args: argparse.Namespace) -> int:
    """Region packs: one block per owned zoom-10 tile, each appending its features to the fine and coarse
    layer files and its DEM tiles to the two DEM files; then one tippecanoe run per vector file and
    keep_tiles on all four. The overview: the coarse outputs only, from one CRM read."""
    region = load_region(args.region)
    owned = owned_tiles(region, args.region.parent)
    urllist = args.cache / "cudem" / "urllist8483.txt"
    if owned is None:
        needed = [crm_path(overview_bounds(region.bbox), args.cache)]
    else:
        blocks = list(iter_blocks(owned))
        needed = [urllist] + [crm_path(read, args.cache) for _, _, read in blocks]
    for path in needed:
        if not path.exists():
            raise SystemExit(f"{path} not found; run fetch-bathy first")
    if missing := geoid.missing_grids(args.cache / "proj"):
        raise SystemExit(f"{missing[0]} missing or damaged; run fetch-bathy first")
    datum = area_datum(region, args.cache / "proj")
    clip = None
    if region.clip is not None:
        data = json.loads(region.clip.read_text())
        clip = shape(data.get("geometry", data))

    files = {name: args.work / name for name in BATHY_FILES}
    fine_work, coarse_work = args.work / "tippecanoe", args.work / "tippecanoe-coarse"
    for work in (fine_work, coarse_work):  # the layer files are appended to, so start them empty
        shutil.rmtree(work, ignore_errors=True)
    for path in files.values():
        path.unlink(missing_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    zooms = {"bathy.mbtiles": (MINZOOM, MAXZOOM), "dem.mbtiles": (MINZOOM, region.dem_maxzoom),
             "bathy-coarse.mbtiles": OVERVIEW_ZOOMS if owned is None else COARSE_ZOOMS}
    zooms["dem-coarse.mbtiles"] = zooms["bathy-coarse.mbtiles"]

    used = {}
    if owned is None:
        crm_request = crm_wcs_url(overview_bounds(region.bbox))
        result = build_overview(region.bbox, needed[0], datum, clip)
        _append_layers(coarse_work, result.coarse_contours, result.coarse_bands, result.coarse_coverage)
        build_dem_mbtiles(result.coarse_grid.data, result.coarse_grid.transform, files["dem-coarse.mbtiles"],
                          minzoom=OVERVIEW_ZOOMS[0], maxzoom=OVERVIEW_ZOOMS[1], skip_empty=True)
    else:
        all_tiles = parse_urllist(urllist.read_text())
        enc_fallback = region.coarse_fallback == "enc"  # ENC lines where CUDEM is absent; no coarse layers
        crm_request = crm_tile_requests(BLOCK_MARGIN_DEG)
        cells = [read_cell(_newest_cached_zip(args.cache, name)) for band in sorted(region.cells) for name in region.cells[band]]
        depcnt = enc_depcnt(cells)  # quilted once; each block clips it to its uncovered water
        del cells
        for tile, core, read in blocks:
            tiles = tiles_for_bbox(all_tiles, read)
            used.update((t.name, t) for t in tiles_for_bbox(tiles, core))  # the tiles drawn in the owned tile
            r = build_block(core, read, tiles, crm_path(read, args.cache), datum, clip)
            covered = r.fine_coverage + ([] if enc_fallback else r.coarse_coverage)
            uncovered = box(*core).difference(unary_union([shape(f["geometry"]) for f in covered]))
            _append_layers(fine_work, r.fine_contours + enc_fallback_contours(depcnt, uncovered), r.fine_bands,
                           r.fine_coverage)
            # One DEM source per place per zoom, decided per zoom-12 tile: the fine DEM (the whole merge, so no
            # cliff at the CUDEM edge) where a zoom-12 tile holds CUDEM, the coarse DEM elsewhere.
            owned12 = set() if r.fine_grid is None else fine_owned_z12(r.fine_cudem, r.fine_grid.transform, tile)
            fine_tiles, coarse_tiles = dem_tiles(owned12, tile, region.dem_maxzoom)
            outputs = [(r.fine_grid, fine_tiles, False, "dem.mbtiles")]
            if not enc_fallback:
                _append_layers(coarse_work, r.coarse_contours, r.coarse_bands, r.coarse_coverage)
                outputs.append((r.coarse_grid, coarse_tiles, True, "dem-coarse.mbtiles"))
            for grid, dem, skip_empty, name in outputs:
                if dem:
                    build_dem_mbtiles(grid.data, grid.transform, files[name], minzoom=zooms[name][0],
                                      maxzoom=zooms[name][1], skip_empty=skip_empty, tiles=dem, within=core,
                                      append=True)
            del r

    cudem_tiles = [used[name] for name in sorted(used)]
    tile_bathy(fine_work, files["bathy.mbtiles"], region=region, crm_request=crm_request, zooms=zooms["bathy.mbtiles"],
               cudem_tiles=cudem_tiles)
    tile_bathy(coarse_work, files["bathy-coarse.mbtiles"], region=region, crm_request=crm_request,
               zooms=zooms["bathy-coarse.mbtiles"], coarse=True, cudem_tiles=cudem_tiles)
    for name in ("dem.mbtiles", "dem-coarse.mbtiles"):
        if not files[name].exists():  # nothing to draw (the overview's fine DEM, the ENC path's coarse DEM)
            empty_dem_mbtiles(files[name], minzoom=zooms[name][0], maxzoom=zooms[name][1], bounds=region.bbox)
    for name, path in files.items():
        keep_tiles(path, owned, minzoom=zooms[name][0], maxzoom=zooms[name][1])
    print(_finish(assemble_bathy_pack(region, files, args.out), region))
    return 0


def _render(args: argparse.Namespace) -> int:
    from chartpack.render.render import render_views

    if args.styles:
        styles = args.styles.split(",")
    else:
        styles = sorted({p.stem for pack in args.packdirs for p in (pack / "styles").glob("*.json")})
    for path in render_views(args.packdirs, load_region(args.views).views, styles, args.out):
        print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chartpack")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("fetch-enc")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_enc)
    p = sub.add_parser("fetch-bathy")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_bathy)
    p = sub.add_parser("fetch-seabed")
    p.add_argument("region", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_fetch_seabed)
    p = sub.add_parser("build-enc")
    p.add_argument("region", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.set_defaults(func=_build_enc)
    p = sub.add_parser("build-bathy")
    p.add_argument("region", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.set_defaults(func=_build_bathy)
    p = sub.add_parser("manifest")
    p.add_argument("packdir", type=Path, metavar="PACKDIR")
    p.add_argument("--region", type=Path, required=True, help="region file the pack was built from")
    p.set_defaults(func=_manifest)
    p = sub.add_parser("restyle")
    p.add_argument("packdir", type=Path, metavar="PACKDIR")
    p.add_argument("--night", choices=sorted(NIGHT_VARIANTS), default="amber", help="night style (default amber)")
    p.set_defaults(func=_restyle)
    p = sub.add_parser("check")
    p.add_argument("packdir", type=Path, metavar="PACKDIR")
    p.add_argument("--enc-cache", type=Path, help="download cache holding the ENC zips, for the hazard and coverage checks")
    p.set_defaults(func=_check)
    p = sub.add_parser("archive")
    p.add_argument("packdir", type=Path, metavar="PACKDIR")
    p.add_argument("out", type=Path)
    p.set_defaults(func=_archive)
    p = sub.add_parser("render")
    p.add_argument("packdirs", type=Path, nargs="+", metavar="PACKDIR")
    p.add_argument("--views", type=Path, required=True, help="region file whose render views are drawn")
    p.add_argument("--styles", help="comma-separated style names (default: every styles/*.json)")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=_render)
    p = sub.add_parser("cells")
    p.add_argument("region", type=Path)
    p.add_argument("--band", type=int, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.set_defaults(func=_cells)
    args = parser.parse_args(argv)
    if args.version:
        print(f"chartpack {__version__}")
        return 0
    if args.command is None:
        parser.error("a command is required")
    return args.func(args)
