#!/usr/bin/env python3
"""Write compact stock history files from the current stock snapshot."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CURRENT = ROOT / "stock-data.json"
DEFAULT_HISTORY_ROOT = ROOT / "_stock_history"
DEFAULT_SITE_HISTORY_ROOT = ROOT / "_site" / "history"
METRIC_FIELDS = [
    "at",
    "total",
    "in_stock",
    "out_of_stock",
    "bambu_in_stock",
    "polymaker_in_stock",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--history-root", type=Path, default=DEFAULT_HISTORY_ROOT)
    parser.add_argument("--site-history-root", type=Path, default=DEFAULT_SITE_HISTORY_ROOT)
    return parser.parse_args(argv)


def parse_timestamp(value: str) -> dt.datetime:
    cleaned = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def item_key(item: dict[str, Any]) -> str:
    variant = item.get("productId") or item.get("sku") or item.get("name") or ""
    return f"{item.get('brand', '')}|{item.get('line', '')}|{variant}"


def compact_event(at: str, item: dict[str, Any], to_stock: bool) -> dict[str, Any]:
    return {
        "at": at,
        "key": item_key(item),
        "brand": str(item.get("brand", "")),
        "line": str(item.get("line", "")),
        "group": str(item.get("group", "")),
        "name": str(item.get("name", "")),
        "sku": str(item.get("sku", "")),
        "productId": str(item.get("productId", "")),
        "url": str(item.get("url", "")),
        "price": item.get("price"),
        "from": not to_stock,
        "to": to_stock,
    }


def stock_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    at = str(data.get("updatedAt", ""))
    changes = data.get("changes") if isinstance(data.get("changes"), dict) else {}
    events: list[dict[str, Any]] = []
    for item in changes.get("inStock", []) if isinstance(changes, dict) else []:
        if isinstance(item, dict):
            events.append(compact_event(at, item, True))
    for item in changes.get("outOfStock", []) if isinstance(changes, dict) else []:
        if isinstance(item, dict):
            events.append(compact_event(at, item, False))
    return events


def metric_row(data: dict[str, Any]) -> dict[str, int | str]:
    total = 0
    in_stock = 0
    brand_counts = {"Bambu": 0, "Polymaker": 0}
    for line in data.get("lines", []):
        if not isinstance(line, dict):
            continue
        brand = str(line.get("brand", ""))
        for item in line.get("items", []):
            if not isinstance(item, dict):
                continue
            total += 1
            if item.get("inStock"):
                in_stock += 1
                if brand in brand_counts:
                    brand_counts[brand] += 1
    return {
        "at": str(data.get("updatedAt", "")),
        "total": total,
        "in_stock": in_stock,
        "out_of_stock": total - in_stock,
        "bambu_in_stock": brand_counts["Bambu"],
        "polymaker_in_stock": brand_counts["Polymaker"],
    }


def month_paths(root: Path, at: dt.datetime) -> tuple[Path, Path]:
    events_path = root / "events" / f"{at:%Y}" / f"{at:%m}.ndjson"
    metrics_path = root / "metrics" / "hourly" / f"{at:%Y}" / f"{at:%m}.csv"
    return events_path, metrics_path


def append_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if path.exists():
        for row in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(row)
            except json.JSONDecodeError:
                continue
            existing.add((event.get("at"), event.get("key"), event.get("to")))
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            identity = (event.get("at"), event.get("key"), event.get("to"))
            if identity in existing:
                continue
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def append_metric(path: Path, row: dict[str, int | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    rows = [existing for existing in rows if existing.get("at") != row["at"]]
    rows.append({field: str(row[field]) for field in METRIC_FIELDS})
    rows.sort(key=lambda value: value["at"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_all_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sorted((root / "events").glob("*/*.ndjson")):
        for row in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(row)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    events.sort(key=lambda event: str(event.get("at", "")))
    return events


def read_all_metrics(root: Path) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for path in sorted((root / "metrics" / "hourly").glob("*/*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                metrics.append({key: int(value) if key != "at" else value for key, value in row.items()})
    metrics.sort(key=lambda row: str(row.get("at", "")))
    return metrics


def write_site_summaries(history_root: Path, site_history_root: Path, now: dt.datetime) -> None:
    site_history_root.mkdir(parents=True, exist_ok=True)
    recent_events = read_all_events(history_root)[-200:]
    cutoff = now - dt.timedelta(days=30)
    recent_metrics = [
        row for row in read_all_metrics(history_root)
        if parse_timestamp(str(row.get("at", "1970-01-01T00:00:00+00:00"))) >= cutoff
    ]
    (site_history_root / "recent-events.json").write_text(json.dumps(recent_events, indent=2) + "\n", encoding="utf-8")
    (site_history_root / "hourly-30d.json").write_text(json.dumps(recent_metrics, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data = json.loads(args.current.read_text(encoding="utf-8"))
    updated_at = parse_timestamp(str(data.get("updatedAt", "")))
    args.history_root.mkdir(parents=True, exist_ok=True)

    events_path, metrics_path = month_paths(args.history_root, updated_at)
    append_events(events_path, stock_events(data))
    append_metric(metrics_path, metric_row(data))

    latest_path = args.history_root / "latest" / "stock-data.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.current, latest_path)
    write_site_summaries(args.history_root, args.site_history_root, updated_at)
    print(f"Wrote stock history under {args.history_root}")
    print(f"Wrote site history summaries under {args.site_history_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
