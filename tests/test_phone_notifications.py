import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_build():
    spec = importlib.util.spec_from_file_location("build", ROOT / "build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def minimal_data():
    return {
        "updatedAt": "2026-05-18T12:00:00+00:00",
        "previousUpdatedAt": "2026-05-18T11:00:00+00:00",
        "source": "https://www.gigaparts.com",
        "lines": [],
        "changes": {"inStock": [], "outOfStock": []},
        "errors": [],
    }


class PhoneNotificationBuildTests(unittest.TestCase):
    def test_render_html_registers_service_worker_and_phone_controls(self):
        build = load_build()
        html = build.render_html(minimal_data())

        self.assertIn('rel="manifest" href="manifest.webmanifest"', html)
        self.assertIn('navigator.serviceWorker.register("sw.js")', html)
        self.assertIn('id="web-push-toggle"', html)
        self.assertIn('id="telegram-link"', html)
        self.assertIn('id="telegram-pairing-panel"', html)
        self.assertIn('id="telegram-pairing-url"', html)
        self.assertIn('id="telegram-copy-link"', html)
        self.assertIn("iPhone/iPad: install this site to your Home Screen", html)
        self.assertIn("syncSavedItemsToWorker", html)
        self.assertIn("pollTelegramLink", html)
        self.assertIn("mergeSavedItemKeys", html)
        self.assertIn("showTelegramPairingLink", html)
        self.assertIn("Telegram-linked browsers share one saved list", html)
        self.assertIn("Telegram bot commands include /list", html)

    def test_build_writes_manifest_and_service_worker(self):
        build = load_build()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            with mock.patch.object(build, "OUT_PATH", tmp_path / "index.html"), \
                mock.patch.object(build, "DATA_PATH", tmp_path / "stock-data.json"), \
                mock.patch.object(build, "MANIFEST_PATH", tmp_path / "manifest.webmanifest"), \
                mock.patch.object(build, "SERVICE_WORKER_PATH", tmp_path / "sw.js"), \
                mock.patch.object(build, "build_data", lambda previous=None: minimal_data()):
                self.assertEqual(build.main(), 0)

            manifest = json.loads((tmp_path / "manifest.webmanifest").read_text())
            service_worker = (tmp_path / "sw.js").read_text()
            self.assertEqual(manifest["name"], "GigaParts Filament Stock")
            self.assertEqual(manifest["display"], "standalone")
            self.assertIn('self.addEventListener("push"', service_worker)
            self.assertIn("showNotification", service_worker)

    def test_workflow_posts_stock_events_without_blocking_publish(self):
        workflow = (ROOT / ".github/workflows/update-stock.yml").read_text()

        self.assertIn("NOTIFY_WORKER_URL", workflow)
        self.assertIn("NOTIFY_WORKER_TOKEN", workflow)
        self.assertIn("Post stock notifications", workflow)
        self.assertIn("continue-on-error: true", workflow)


if __name__ == "__main__":
    unittest.main()
