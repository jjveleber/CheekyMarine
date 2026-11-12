"""chartpack command line."""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import box, shape
from shapely.ops import unary_union

from chartpack import __version__
from chartpack.bathy.blocks import (
    BLOCK_MARGIN_DEG,
    BlockSources,
    area_datum,
    build_block,
    build_overview,
    dem_tiles,
    fine_owned_z12,
    iter_blocks,
    overview_bounds,
)
from chartpack.bathy.crm import crm_path, crm_tile_requests, crm_wcs_url, fetch_crm
from chartpack.bathy.crm import crm_request as crm_request_bounds  # crm_request names the metadata string below
from chartpack.bathy.cudem import URLLIST, parse_urllist, tiles_for_bbox
from chartpack.bathy.dem import build_dem_mbtiles, empty_dem_mbtiles
from chartpack.bathy.etopo import etopo_paths, fetch_etopo
from chartpack.bathy.nonna import fetch_index, fetch_nonna, index_boxes
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
from chartpack.coast import fetch_coastline
from chartpack.datum import geoid
from chartpack.datum.offsets import load_datum
from chartpack.enc.catalog import CATALOG_URL, cells_meeting, parse_catalog
from chartpack.enc.fetch import fetch_cells
from chartpack.enc.reader import read_cell
from chartpack.enc.tiles import OVERVIEW_ZOOMS, REGION_ZOOMS, build_enc_mbtiles
from chartpack.fetching import USER_AGENT, PoliteSession
from chartpack.grid import (
    canada_side,
    content_tiles,
    fetch_extent,
    keep_tiles,
    owned_tiles,
    owners,
    tiles_area,
    tiles_meeting,
)
from chartpack.pack.archive import archive_pack
from chartpack.pack.assemble import BATHY_FILES, assemble_bathy_pack, assemble_charts_pack
from chartpack.pack.check import check_pack
from chartpack.pack.manifest import describe_pack, write_manifest
from chartpack.pack.restyle import restyle_pack
from chartpack.region import COARSE_SOURCES, load_region
from chartpack.style.palette import NIGHT_VARIANTS
from chartpack.seabed.cmecs import BLOCKS, fetch_cmecs, read_cmecs
from chartpack.seabed.usseabed import FILES, fetch_usseabed, read_usseabed


# The Canadian source data (NONNA grids, the BC coastline) is read from this release, which only the fetch workflow
# writes; no pack build calls a Canadian host (plan 8 spec 5).
SOURCES_RELEASE = "sources-bc-1"
SOURCES_URL = f"https://github.com/jjveleber/CheekyMarine/releases/download/{SOURCES_RELEASE}/"
SOURCES_WORKFLOW = "chartpack-sources.yml"


def _asset_name(region_path: Path, region) -> str:
    """The name in the region's asset files: [sources] assets, read by this module alone, else the region name."""
    with Path(region_path).open("rb") as f:
        return tomllib.load(f).get("sources", {}).get("assets", region.name)


def _nonna_files(region, name: str) -> list[str]:
    """The region's NONNA asset files, in the order of its sources; none when it lists no NONNA."""
    return [f"{p}-{name}.tif" for p in ("nonna10", "nonna100") if p in region.bathy_sources]


def _fetch_assets(region_path: Path, region, cache: Path) -> list[Path]:
    """Download the region's assets from the release (its fetch stats, NONNA grids and coastline) into
    cache/sources-bc-1, each checked against the sha256 in the stats; an asset already cached with that sha256
    is kept. A region that lists no NONNA downloads nothing."""
    name = _asset_name(region_path, region)
    files = _nonna_files(region, name)
    if not files:
        return []
    files.append(f"coast-{name}.geojson.gz")
    folder = cache / SOURCES_RELEASE
    stats_name = f"fetch-stats-{name}.json"
    stats = json.loads(download(SOURCES_URL + stats_name, folder / stats_name).read_text())
    paths = [folder / stats_name]
    for file in files:
        entry = stats["files"].get(file)
        if entry is None:
            raise SystemExit(f"{file} is not in {stats_name} of release {SOURCES_RELEASE}; run the fetch workflow"
                             f" {SOURCES_WORKFLOW} for region {region.name}")
        dest = folder / file
        if not (dest.is_file() and _sha256(dest) == entry["sha256"]):
            download(SOURCES_URL + file, dest)
            if (got := _sha256(dest)) != entry["sha256"]:
                dest.unlink()
                raise SystemExit(f"{file}: sha256 {got} does not match {entry['sha256']} in {stats_name}; run the"
                                 f" fetch workflow {SOURCES_WORKFLOW} for region {region.name} again")
        paths.append(dest)
    return paths


def _check_assets(region_path: Path, region, cache: Path, files: list[str], boxes) -> dict[str, Path]:
    """The cached assets `files` of the region by name, after checking that each is there and that every read
    box (W, S, E, N) lies inside the extent the fetch workflow pulled, as its fetch stats record (the mosaics'
    own bounds are smaller where NONNA has no data). Either failure stops the build naming the region, the file
    and the fetch workflow."""
    if not files:
        return {}
    name = _asset_name(region_path, region)
    folder = cache / SOURCES_RELEASE
    stats = folder / f"fetch-stats-{name}.json"
    for path in [stats] + [folder / file for file in files]:
        if not path.is_file():
            raise SystemExit(f"region {region.name}: {path} not found; run fetch-bathy, which downloads it from"
                             f" release {SOURCES_RELEASE} (written by the fetch workflow {SOURCES_WORKFLOW})")
    w, s, e, n = json.loads(stats.read_text())["extent"]
    eps = 1e-9  # the stats round the extent to 9 decimals
    for bw, bs, be, bn in boxes:
        if bw < w - eps or bs < s - eps or be > e + eps or bn > n + eps:
            raise SystemExit(f"region {region.name}: the read box {(bw, bs, be, bn)} reaches past the extent"
                             f" {[w, s, e, n]} of {', '.join(files)} ({stats.name}); run the fetch workflow"
                             f" {SOURCES_WORKFLOW} for region {region.name} again")
    return {file: folder / file for file in files}


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
    """The Active cells of the band meeting the region's owned zoom-10 tiles (the overview: every owned tile)."""
    region = load_region(args.region)
    area = tiles_area(content_tiles(region, args.region.parent))
    for name in cells_meeting(_load_catalog(args.cache), area, args.band):
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


def _usgs_seabed(region, cache: Path, area=None) -> list:
    """The region's USGS seabed features from the fetch-seabed cache, read over the bounds of `area` (a region
    pack's owned tiles plus the margin, which reach past its bbox), or over the bbox for the overview."""
    usseabed = [cache / "seabed" / name for name in FILES] if "usseabed" in region.seabed_sources else []
    blocks = {block: cache / "seabed" / f"{BLOCKS[block].name}.zip" for block in region.cmecs_blocks}
    missing = [p for p in usseabed + list(blocks.values()) if not p.is_file()]
    if missing:
        raise SystemExit(f"{missing[0]} not found; run fetch-seabed first")
    bbox = region.bbox if area is None else area.bounds
    features = read_usseabed(usseabed, bbox) if usseabed else []
    for block, path in blocks.items():
        features += read_cmecs(path, block, bbox)
    return features


def _build_enc(args: argparse.Namespace) -> int:
    region = load_region(args.region)
    names = [n for band in sorted(region.cells) for n in region.cells[band]]
    cells = [read_cell(_newest_cached_zip(args.cache, name)) for name in names]
    owned = owned_tiles(region, args.region.parent)  # before the slow build: a bad grid fails fast
    zooms = OVERVIEW_ZOOMS if region.overview else REGION_ZOOMS
    # The quilt output is kept on the owned tiles (the overview: every owned tile) plus a margin wider than
    # tippecanoe's tile buffer (5 of 256 px, about 0.007 degrees at zoom 10), so a feature across an owned edge
    # still renders over the seam, and a band 1 cell spanning far past wave 1 adds nothing beyond it.
    content = content_tiles(region, args.region.parent)
    area = tiles_area(content, BLOCK_MARGIN_DEG)
    name = _asset_name(args.region, region)
    if _nonna_files(region, name):  # a region with Canadian sources: the coastline the derived charts read
        _check_assets(args.region, region, args.cache, [f"coast-{name}.geojson.gz"], [area.bounds])
    enc = build_enc_mbtiles(cells, args.work / "enc.mbtiles", region=region, work=args.work / "tippecanoe",
                            seabed=_usgs_seabed(region, args.cache, None if owned is None else area), zooms=zooms,
                            area=area)
    keep_tiles(enc, owned, minzoom=zooms[0], maxzoom=zooms[1], content=content)
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
    geoid.fetch_grids(args.cache / "proj")  # CRM (EGM2008 heights) converts through NAVD88; kept for every region
    for path in _fetch_assets(args.region, region, args.cache):
        print(path)
    if owned is None:  # the overview: one native CRM request over the region, no CUDEM
        print(fetch_crm(overview_bounds(region.bbox), args.cache))
        return 0
    blocks = list(iter_blocks(owned))
    if "cudem" in region.bathy_sources:
        # The tile list changes as NCEI adds tiles, so it is fetched on every run.
        tiles = parse_urllist(download(URLLIST, args.cache / "cudem" / "urllist8483.txt").read_text())
        for name in sorted({t.name for _, _, read in blocks for t in tiles_for_bbox(tiles, read)}):
            print(name)
    if "crm" in region.bathy_sources:
        for _, _, read in blocks:  # one CRM request per owned tile, over its read bounds cut to CRM's coverage
            if (path := fetch_crm(read, args.cache)) is not None:  # None: the tile is wholly outside CRM
                print(path)
    if "etopo" in region.bathy_sources:  # every ETOPO tile the region's fetch extent meets
        for path in fetch_etopo(fetch_extent(region, args.region.parent), args.cache):
            print(path)
    return 0


class _CountedSession:
    """Counts the requests made through it (each get is one page of the coastline)."""

    def __init__(self, session):
        self.session = session
        self.gets = 0

    def get(self, url: str) -> bytes:
        self.gets += 1
        return self.session.get(url)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_sources(args: argparse.Namespace) -> int:
    """A region's Canadian source data (NONNA grids from the CHS WCS, the BC coastline from the BC WFS) for the
    release sources-bc-1. Only the fetch workflow (chartpack-sources.yml) runs this; no pack build calls a
    Canadian host. Files are named by the region's [sources] assets (default: its name).

    A run of both kinds writes fresh stats. A run of one kind keeps the other kind's entries of a stats file
    already in --out (the workflow downloads it from the release) and fails when that file's extent differs:
    a changed extent needs a run of both kinds. Each file entry holds its sha256, so a reader can tell the file
    the stats describe from a stale one."""
    region = load_region(args.region)
    name = _asset_name(args.region, region)
    if not re.fullmatch(r"[a-z0-9-]+", name):
        print(f"fetch-sources: [sources] assets must match [a-z0-9-]+, got {name!r}", file=sys.stderr)
        return 1
    bathy_sources = region.bathy_sources
    extent = [round(v, 9) for v in fetch_extent(region, args.region.parent)]
    stats = args.out / f"fetch-stats-{name}.json"
    files = {}
    if args.only != "both" and stats.exists():
        previous = json.loads(stats.read_text())
        if previous["extent"] != extent:
            print(f"fetch-sources: {stats} has extent {previous['extent']}, this run's is {extent}: the extent changed,"
                  " so fetch both kinds (--only both)", file=sys.stderr)
            return 1
        files = previous["files"]
    session = PoliteSession(USER_AGENT)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.only in ("both", "nonna"):
        with tempfile.TemporaryDirectory() as work:
            for product in ("nonna10", "nonna100"):
                if product in bathy_sources:
                    boxes = index_boxes(fetch_index(product, session, Path(work)), extent)
                    path = args.out / f"{product}-{name}.tif"
                    files[path.name] = {**fetch_nonna(product, boxes, path, session), "sha256": _sha256(path)}
                    print(path)
    if args.only in ("both", "coast"):
        path = args.out / f"coast-{name}.geojson.gz"
        start = time.monotonic()
        pages = _CountedSession(session)
        features = fetch_coastline(extent, path, pages)
        files[path.name] = {"chunks": pages.gets, "features": features, "bytes": path.stat().st_size,
                            "sha256": _sha256(path), "seconds": round(time.monotonic() - start, 3)}
        print(path)
    stats.write_text(json.dumps({"extent": extent, "files": files}, indent=2) + "\n")
    print(stats)
    return 0


def _canada(read, tile_owners: dict, region, clips: dict):
    """The Canadian column of plan 8 spec 6 over the read box: for each zoom-10 tile it meets, canada_side by the
    tile's owner (a tile no pack owns by the region's own rule), so two blocks see the same side in a shared read
    margin. None when no part of the box is Canadian. clips caches the clip polygons by path."""
    parts = []
    for tile in tiles_meeting(read):
        owner = tile_owners.get(tile, region)
        if owner.charts_kind == "enc" and owner.clip is None:  # a US pack with no clip: all US side
            continue
        clip = None
        if owner.charts_kind == "enc":
            if owner.clip not in clips:
                data = json.loads(owner.clip.read_text())
                clips[owner.clip] = shape(data.get("geometry", data))
            clip = clips[owner.clip]
        parts.append(canada_side(clip, tile, owner))
    canada = unary_union(parts).intersection(box(*read)) if parts else None
    return None if canada is None or canada.is_empty else canada


def _append_layers(work: Path, contours: list[dict], bands: list[dict], coverage: list[dict]) -> None:
    for name, feats in (("contour", contours), ("band", bands), ("coverage", coverage)):
        append_features(feats, work / f"{name}.geojsonseq")


def _build_bathy(args: argparse.Namespace) -> int:
    """Region packs: one block per owned zoom-10 tile, each appending its features to the fine and coarse
    layer files and its DEM tiles to the two DEM files; then one tippecanoe run per vector file and
    keep_tiles on all four. Each block takes its depth sources by side of the border (_canada, build_block).
    The overview: the coarse outputs only, from one CRM read."""
    region = load_region(args.region)
    owned = owned_tiles(region, args.region.parent)
    urllist = args.cache / "cudem" / "urllist8483.txt"
    has_cudem, has_crm = "cudem" in region.bathy_sources, "crm" in region.bathy_sources
    has_etopo = "etopo" in region.bathy_sources
    has_coarse = bool(set(COARSE_SOURCES) & set(region.bathy_sources))
    if owned is None:
        needed = [crm_path(overview_bounds(region.bbox), args.cache)]
    else:
        blocks = list(iter_blocks(owned))
        etopo = etopo_paths(fetch_extent(region, args.region.parent), args.cache) if has_etopo else []
        needed = ([urllist] if has_cudem else []) + etopo + [
            path for _, _, read in blocks if has_crm and (path := crm_path(read, args.cache)) is not None]
        name = _asset_name(args.region, region)
        paths = _check_assets(args.region, region, args.cache, _nonna_files(region, name), [r for _, _, r in blocks])
        assets = {product: paths.get(f"{product}-{name}.tif") for product in ("nonna10", "nonna100")}
    for path in needed:
        if not path.exists():
            raise SystemExit(f"{path} not found; run fetch-bathy first")
    if missing := geoid.missing_grids(args.cache / "proj"):
        raise SystemExit(f"{missing[0]} missing or damaged; run fetch-bathy first")
    datum = area_datum(region, args.cache / "proj")
    # Lakes with no datum rule are left out: their bottoms are not on a tidal datum.
    mask = load_datum(region.datum_file).lake_mask
    lake_mask = unary_union([shape(g) for g in mask]) if mask else None

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
        crm_request = crm_wcs_url(crm_request_bounds(overview_bounds(region.bbox)))
        clip = None  # the overview keeps plan 7's clip until it is rebuilt over US and BC water
        if region.clip is not None:
            data = json.loads(region.clip.read_text())
            clip = shape(data.get("geometry", data))
        if lake_mask is not None:
            clip = lake_mask if clip is None else unary_union([clip, lake_mask])
        result = build_overview(region.bbox, needed[0], datum, clip)
        _append_layers(coarse_work, result.coarse_contours, result.coarse_bands, result.coarse_coverage)
        build_dem_mbtiles(result.coarse_grid.data, result.coarse_grid.transform, files["dem-coarse.mbtiles"],
                          minzoom=OVERVIEW_ZOOMS[0], maxzoom=OVERVIEW_ZOOMS[1], skip_empty=True)
    else:
        all_tiles = parse_urllist(urllist.read_text()) if has_cudem else []
        enc_fallback = region.coarse_fallback == "enc"  # ENC lines where CUDEM is absent; no coarse layers
        crm_request = crm_tile_requests(BLOCK_MARGIN_DEG) if has_crm else None
        cells = [read_cell(_newest_cached_zip(args.cache, name)) for band in sorted(region.cells) for name in region.cells[band]]
        depcnt = enc_depcnt(cells)  # quilted once; each block clips it to its uncovered water
        del cells
        tile_owners, clips = owners(region, args.region.parent), {}
        for tile, core, read in blocks:
            tiles = tiles_for_bbox(all_tiles, read)
            used.update((t.name, t) for t in tiles_for_bbox(tiles, core))  # the tiles drawn in the owned tile
            canada = _canada(read, tile_owners, region, clips)
            sources = BlockSources(tiles, crm_path(read, args.cache) if has_crm else None, assets["nonna10"],
                                   assets["nonna100"], etopo or None)
            r = build_block(core, read, sources, datum, canada, lake_mask=lake_mask)
            covered = r.fine_coverage + ([] if enc_fallback else r.coarse_coverage)
            uncovered = box(*core).difference(unary_union([shape(f["geometry"]) for f in covered]))
            # A region without CUDEM writes no fine layers (a fine file with contours alone fails tile_bathy). No
            # ENC line is drawn on the Canadian column (its coarse sources cover it) or in a masked lake.
            leave_out = [g for g in (canada, lake_mask) if g is not None]
            enc_lines = enc_fallback_contours(depcnt, uncovered, unary_union(leave_out) if leave_out else None
                                              ) if has_cudem else []
            _append_layers(fine_work, r.fine_contours + enc_lines, r.fine_bands, r.fine_coverage)
            # One DEM source per place per zoom, decided per zoom-12 tile: the fine DEM where a zoom-12 tile holds
            # a fine-tier cell (CUDEM or NONNA-10), the coarse DEM elsewhere. With a coarse source listed the fine
            # DEM is the whole merge, so the coarse sources fill past the fine edge and there is no cliff; a
            # CUDEM-only fine DEM is nan past that edge.
            owned12 = set() if r.fine_grid is None else fine_owned_z12(r.fine_cudem, r.fine_grid.transform, tile)
            fine_tiles, coarse_tiles = dem_tiles(owned12, tile, region.dem_maxzoom)
            outputs = [(r.fine_grid, fine_tiles, False, "dem.mbtiles")]
            if has_coarse and not enc_fallback:
                _append_layers(coarse_work, r.coarse_contours, r.coarse_bands, r.coarse_coverage)
                outputs.append((r.coarse_grid, coarse_tiles, True, "dem-coarse.mbtiles"))
            for grid, dem, skip_empty, name in outputs:
                if dem and grid is not None:  # no coarse grid where the tile is wholly outside CRM
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
    print(_finish(assemble_bathy_pack(region, files, args.out, owned=owned), region))
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
    p = sub.add_parser("fetch-sources", help="Canadian source data for release sources-bc-1 (the fetch workflow only)")
    p.add_argument("--region", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--only", choices=["both", "coast", "nonna"], default="both")
    p.set_defaults(func=_fetch_sources)
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
