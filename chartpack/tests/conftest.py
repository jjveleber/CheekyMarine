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
