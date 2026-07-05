import csv
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_history_module():
    spec = importlib.util.spec_from_file_location("update_stock_history", ROOT / "scripts/update_stock_history.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stock_data():
    return {
        "updatedAt": "2026-07-05T12:00:00+00:00",
        "previousUpdatedAt": "2026-07-05T11:00:00+00:00",
        "source": "https://www.gigaparts.com",
        "lines": [
            {
                "brand": "Bambu",
                "name": "PLA Basic",
                "group": "PLA",
                "url": "https://example.com/bambu",
                "items": [
                    {"name": "Red", "sku": "SKU1", "productId": "1", "inStock": True, "price": 19.99, "url": "https://example.com/red"},
                    {"name": "Blue", "sku": "SKU2", "productId": "2", "inStock": False, "price": 19.99, "url": "https://example.com/blue"},
                ],
            },
            {
                "brand": "Polymaker",
                "name": "PETG",
                "group": "PETG",
                "url": "https://example.com/poly",
                "items": [
                    {"name": "Black", "sku": "SKU3", "productId": "3", "inStock": True, "price": 22.99, "url": "https://example.com/black"},
                ],
            },
        ],
        "changes": {
            "inStock": [
                {
                    "brand": "Bambu",
                    "line": "PLA Basic",
                    "group": "PLA",
                    "name": "Red",
                    "sku": "SKU1",
                    "productId": "1",
                    "url": "https://example.com/red",
                    "price": 19.99,
                    "inStock": True,
                }
            ],
            "outOfStock": [
                {
                    "brand": "Bambu",
                    "line": "PLA Basic",
                    "group": "PLA",
                    "name": "Blue",
                    "sku": "SKU2",
                    "productId": "2",
                    "url": "https://example.com/blue",
                    "price": 19.99,
                    "inStock": False,
                }
            ],
        },
        "errors": [],
    }


class StockHistoryTests(unittest.TestCase):
    def test_writes_compact_events_metrics_latest_and_site_summaries(self):
        history = load_history_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            current = tmp_path / "stock-data.json"
            history_root = tmp_path / "history-branch"
            site_history = tmp_path / "site" / "history"
            current.write_text(json.dumps(stock_data()), encoding="utf-8")

            self.assertEqual(history.main([
                "--current", str(current),
                "--history-root", str(history_root),
                "--site-history-root", str(site_history),
            ]), 0)

            events_path = history_root / "events" / "2026" / "07.ndjson"
            events = [json.loads(row) for row in events_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([event["to"] for event in events], [True, False])
            self.assertEqual(events[0]["key"], "Bambu|PLA Basic|1")

            metrics_path = history_root / "metrics" / "hourly" / "2026" / "07.csv"
            with metrics_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[-1]["total"], "3")
            self.assertEqual(rows[-1]["in_stock"], "2")
            self.assertEqual(rows[-1]["bambu_in_stock"], "1")
            self.assertEqual(rows[-1]["polymaker_in_stock"], "1")

            latest = json.loads((history_root / "latest" / "stock-data.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["updatedAt"], "2026-07-05T12:00:00+00:00")

            recent_events = json.loads((site_history / "recent-events.json").read_text(encoding="utf-8"))
            hourly = json.loads((site_history / "hourly-30d.json").read_text(encoding="utf-8"))
            self.assertEqual(len(recent_events), 2)
            self.assertEqual(hourly[-1]["in_stock"], 2)

    def test_update_workflow_deploys_artifact_and_does_not_commit_generated_site_to_main(self):
        workflow = (ROOT / ".github/workflows/update-stock.yml").read_text(encoding="utf-8")

        self.assertIn("actions/deploy-pages", workflow)
        self.assertIn("stock-history", workflow)
        self.assertIn("scripts/update_stock_history.py", workflow)
        self.assertNotIn("git commit -m \"Update GigaParts stock snapshot\"", workflow)
        self.assertNotIn("git add index.html stock-data.json manifest.webmanifest sw.js", workflow)


if __name__ == "__main__":
    unittest.main()
