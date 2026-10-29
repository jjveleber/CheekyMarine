import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _chromium_installed() -> bool:
    if importlib.util.find_spec("playwright") is None:
        return False
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    skip_online = pytest.mark.skip(reason="needs network (set CHARTPACK_ONLINE=1)")
    skip_render = pytest.mark.skip(reason="needs Playwright and Chromium")
    online = os.environ.get("CHARTPACK_ONLINE") == "1"
    render_ok = None
    for item in items:
        if "online" in item.keywords and not online:
            item.add_marker(skip_online)
        if "render" in item.keywords:
            if render_ok is None:
                render_ok = _chromium_installed()
            if not render_ok:
                item.add_marker(skip_render)


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", help="rewrite golden files from the compared values")


class _Golden:
    def __init__(self, path: Path, update: bool):
        self.path, self.update = path, update

    def __eq__(self, other):
        if self.update:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(other, indent=2, sort_keys=True) + "\n")
            return True
        return json.loads(self.path.read_text()) == json.loads(json.dumps(other))


@pytest.fixture
def golden(request):
    """golden(name) compares equal to the JSON in tests/fixtures/golden/<name>.

    Under --update-golden the compared value is written to the file instead and the
    comparison passes, so `assert value == golden("x.json")` regenerates the file.
    """
    update = request.config.getoption("--update-golden")
    return lambda name: _Golden(ROOT / "tests" / "fixtures" / "golden" / name, update)


@pytest.fixture
def fixtures_dir() -> Path:
    return ROOT / "tests" / "fixtures"


@pytest.fixture
def regions_dir() -> Path:
    return ROOT / "regions"


@pytest.fixture
def work_dir(tmp_path) -> Path:
    return tmp_path


@pytest.fixture(scope="session")
def enc_pack_path(tmp_path_factory) -> Path:
    """enc.mbtiles built once per session from the US4WA1HK fixture and regions/test-cell.toml, plus the
    usSEABED and Seattle CMECS seabed fixtures (tests/fixtures/seabed) clipped to the test cell, so the
    session pack holds every seabed source. The test-cell region file itself lists the ENC source only."""
    from chartpack.enc.reader import read_cell
    from chartpack.enc.tiles import build_enc_mbtiles
    from chartpack.region import load_region
    from chartpack.seabed.cmecs import read_cmecs
    from chartpack.seabed.usseabed import FILES, read_usseabed

    base = tmp_path_factory.mktemp("enc_pack")
    region = load_region(ROOT / "regions" / "test-cell.toml")
    fixtures = ROOT / "tests" / "fixtures"
    cells = [read_cell(fixtures / "US4WA1HK.zip")]
    seabed = (read_usseabed([fixtures / "seabed" / name for name in FILES], region.bbox)
              + read_cmecs(fixtures / "seabed" / "CMECS_OffshoreSeattle.zip", "seattle", region.bbox))
    return build_enc_mbtiles(cells, base / "enc.mbtiles", region=region, work=base / "work", seabed=seabed)


@pytest.fixture(scope="session")
def test_region():
    from chartpack.region import load_region

    return load_region(ROOT / "regions" / "test-cell.toml")


@pytest.fixture(scope="session")
def charts_pack_root(test_region, enc_pack_path, tmp_path_factory) -> Path:
    from datetime import datetime, timezone

    from chartpack.pack.assemble import assemble_charts_pack
    from chartpack.pack.manifest import describe_pack, write_manifest

    root = assemble_charts_pack(test_region, enc_pack_path, tmp_path_factory.mktemp("charts_pack"))
    pack, sources, notice = describe_pack(root)
    write_manifest(root, pack=pack, region=test_region, sources=sources, notice=notice, built=datetime.now(timezone.utc))
    return root


@pytest.fixture
def charts_pack_root_copy(charts_pack_root, tmp_path) -> Path:
    """A private copy of the session pack, for tests that damage it."""
    import shutil

    return Path(shutil.copytree(charts_pack_root, tmp_path / charts_pack_root.name))


@pytest.fixture
def symbols_dir() -> Path:
    return ROOT / "symbols"


@pytest.fixture
def fonts_dir() -> Path:
    return ROOT / "fonts"


@pytest.fixture
def chartpack_dir() -> Path:
    return ROOT
