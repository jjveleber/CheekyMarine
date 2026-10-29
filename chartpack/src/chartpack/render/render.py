"""Render pack styles to PNGs with headless Chromium (Playwright) and the vendored MapLibre GL JS."""

from pathlib import Path
from urllib.parse import urlencode

from chartpack.region import View
from chartpack.render.server import PackServer

TIMEOUT_MS = 60_000


def render_views(
    pack_dirs: list[Path], views: list[View], styles: list[str], out_dir: Path, *, size: tuple[int, int] = (1024, 600)
) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    server = PackServer(pack_dirs)
    server.start()
    outputs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": size[0], "height": size[1]})
                for view in views:
                    for zoom in view.zooms:
                        for style in styles:
                            query = urlencode({"style": server.style_url(style), "lon": view.lon, "lat": view.lat, "zoom": zoom})
                            page.goto(f"{server.base}/page.html?{query}")
                            page.wait_for_function("window.__rendered === true", timeout=TIMEOUT_MS)
                            errors = page.evaluate("window.__errors || []")
                            if errors:
                                raise RuntimeError(f"{view.name} z{zoom} {style}: map errors: {errors}")
                            path = out_dir / f"{view.name}-z{zoom}-{style}.png"
                            page.screenshot(path=str(path))
                            outputs.append(path)
            finally:
                browser.close()
    finally:
        server.stop()
    return outputs
