"""Exercise the government data watchlist at a project subpath in Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    screenshots = ROOT / "browser-checks"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        shutil.copytree(ROOT / "dist", Path(temporary) / "example-tool")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=temporary))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/example-tool/")
                page.locator(".dataset-button").first.wait_for()
                assert page.locator(".dataset-button").count() >= 8
                page.locator("#search").fill("border")
                assert page.locator(".dataset-button").count() == 3
                page.locator(".dataset-button").filter(has_text="Historical border waits").click()
                assert "Historical Border Wait Times" in page.locator("#detail h3").inner_text()
                page.locator("#toggle-resources").click()
                assert page.locator(".resource").count() > 2
                with page.expect_download() as download:
                    page.locator("#export-csv").click()
                assert download.value.suggested_filename.endswith(".csv")
                page.locator("#search").fill("not-a-record-<script>")
                assert page.locator("#empty").is_visible()
                assert page.locator("#export-csv").is_disabled()
                page.locator("#search").fill("")
                page.locator("#threshold").select_option("90")
                page.locator("#state").select_option("review")
                assert page.locator(".dataset-button").count() > 0
                page.locator("#state").select_option("")
                page.screenshot(path=str(screenshots / "desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
            print("Browser checks passed: project subpath, filters, evidence detail, CSV download and mobile layout")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
