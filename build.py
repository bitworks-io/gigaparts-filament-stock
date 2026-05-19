#!/usr/bin/env python3
"""
Build a static filament stock tracker for GigaParts.

The script downloads configured GigaParts configurable-product pages, parses the
embedded Magento variant config, and writes a self-contained index.html.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "index.html"
DATA_PATH = ROOT / "stock-data.json"
MANIFEST_PATH = ROOT / "manifest.webmanifest"
SERVICE_WORKER_PATH = ROOT / "sw.js"
ALERT_WORKER_BASE = "https://gigaparts-stock-alerts.bitworks-io.workers.dev"
BASE_URL = "https://www.gigaparts.com"
OPTION_LABELS = {
    "3899": "Blue",
    "3901": "Black",
    "3902": "White",
    "3903": "Green",
    "3906": "Red",
    "3907": "Orange",
    "3910": "Purple",
    "3913": "Gray",
    "3964": "Gold",
    "4099": "Natural",
    "4101": "Yellow",
    "4109": "Clear",
    "4111": "Dark Gray",
    "4122": "Blue Gray",
    "4244": "1kg",
    "4246": "Spool",
    "4247": "Refill",
}
OPTION_HEX = {
    "3899": "#2a4b91",
    "3901": "#000000",
    "3902": "#ffffff",
    "3903": "#0b8f42",
    "3906": "#e8102d",
    "3907": "#ff4800",
    "3910": "#b500b5",
    "3913": "#878787",
    "3964": "#ab8b3f",
    "4099": "#f0e2c7",
    "4101": "#f4ed2a",
    "4109": "#dcebf2",
    "4111": "#515151",
    "4122": "#5b6579",
}

PRODUCTS = [
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-basic-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-basic-gradient-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-glow-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-metal-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-sparkle-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-cf-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-marble-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-silk-multi-color-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-wood-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-translucent-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-aero-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-galaxy-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-matte-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-silk-plus-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pla-tough-plus-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-petg-basic-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-petg-translucent-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-petg-hf-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-petg-cf-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-tpu-95a-hf-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-tpu-for-ams-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-tpu-90a-85a-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-abs-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-abs-gf-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-asa-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pc-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pc-fr-3d-printer-filament.html"},
    {"brand": "Bambu", "url": "https://www.gigaparts.com/bambu-lab-pa6-gf-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-basic-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-dual-matte-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-dual-silk-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-matte-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-starlight-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-metallic-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-neon-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-satin-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-translucent-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-gradient-starlight-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-gradient-celestial-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-gradient-crystal-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-gradient-galaxy-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-glow-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-luminous-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-marble-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-gradient-matte-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-gradient-silk-pla-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polylite-metallic-pla-pro-metallic-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polylite-pla-pro-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-petg-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polymax-petg-3d-printer-filament.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-petg-esd-black-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-petg-rcf08-black-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pa6-gf25-grey-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pa6-cf20-black-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pa12-cf10-black-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pa612-cf15-black-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pa612-esd-black-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pet-gf15light-grey-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pet-gf15red-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pps-cf10-black-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-asa-cf08-black-1-75-mm-0-5-kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-fiberon-pps-gf20-grey-1-75-mm-0-5-kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polyflex-tpu95-black-1-75mm-750g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polyflex-tpu90black-1-75mm-750g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polyflex-tpu95-hf-black-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polylite-abs-black-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polylite-asa-black-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polylite-lw-pla-white-1-75mm-800g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polysupport-pearl-white-1-75mm-750g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-polysupport-grass-green-1-75mm-500g-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-cope-drab-green-1-75mm-1kg-filament-spool.html"},
    {"brand": "Polymaker", "url": "https://www.gigaparts.com/polymaker-panchroma-cope-stone-blue-1-75mm-1kg-filament-spool.html"},
]


def fetch(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def read_balanced_json(source: str, start: int) -> tuple[dict[str, Any], int]:
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(source)):
        ch = source[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = source[start : pos + 1]
                return json.loads(raw), pos + 1
    raise ValueError("Could not find balanced JSON object")


def parse_ld_product(source: str) -> dict[str, Any]:
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', source, re.S):
        try:
            data = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return {}


def parse_configurable(source: str) -> dict[str, Any]:
    marker = "initConfigurableOptions("
    for match in re.finditer(re.escape(marker), source):
        marker_pos = match.start()
        json_start = source.find("{", marker_pos)
        if json_start == -1:
            continue
        try:
            config, _ = read_balanced_json(source, json_start)
        except (json.JSONDecodeError, ValueError):
            continue
        if "attributes" in config and "index" in config:
            return config
    raise ValueError("No initConfigurableOptions call found")


def parse_swatches(source: str) -> dict[str, Any]:
    marker = "const swatchOptionsComponent = initSwatchOptions("
    marker_pos = source.find(marker)
    if marker_pos == -1:
        return {}
    data_start = marker_pos + len(marker)
    while data_start < len(source) and source[data_start].isspace():
        data_start += 1
    if data_start < len(source) and source[data_start] == "[":
        return {}
    json_start = source.find("{", data_start)
    swatches, _ = read_balanced_json(source, json_start)
    return swatches


def option_lookup(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    lookups = {}
    for attr_id, attr in config.get("attributes", {}).items():
        lookups[attr_id] = {str(opt["id"]): opt["label"] for opt in attr.get("options", [])}
    return lookups


def swatch_hex(swatches: dict[str, Any], attr_id: str, option_id: str) -> str:
    value = swatches.get(attr_id, {}).get(option_id, {}).get("value", "")
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value) else ""


def salable_product_ids(config: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for attr_map in config.get("salable", {}).values():
        for products in attr_map.values():
            ids.update(str(product_id) for product_id in products)
    return ids


def product_name_from_ld(ld_product: dict[str, Any], url: str) -> str:
    name = ld_product.get("name")
    if name:
        return re.sub(r"\s+", " ", name).strip()
    slug = url.rsplit("/", 1)[-1].removesuffix(".html")
    return slug.replace("-", " ").title()


def main_product_id(source: str) -> str:
    match = re.search(r'"ProductID":"(\d+)"', source)
    return match.group(1) if match else ""


def parse_notification_option_config(source: str, product_id: str) -> dict[str, Any]:
    if not product_id:
        return {}
    component = f"amNotificationProductViewComponent_{product_id}"
    component_pos = source.find(component)
    if component_pos == -1:
        return {}
    marker = "optionConfig:"
    marker_pos = source.find(marker, component_pos)
    if marker_pos == -1:
        return {}
    json_start = source.find("{", marker_pos)
    option_config, _ = read_balanced_json(source, json_start)
    return option_config


def short_line_name(name: str) -> str:
    cleaned = (
        name.replace("Bambu Lab ", "")
        .replace("Polymaker ", "")
        .replace(" 3D Printer Filament", "")
    )
    return cleaned.strip()


def group_for_line(line: str) -> str:
    upper = line.upper()
    for group in ("PLA", "PETG", "PET", "TPU", "ABS", "ASA", "PC", "PA", "PPS", "SUPPORT"):
        if upper.startswith(group) or f" {group}" in upper:
            return "Support" if group == "SUPPORT" else group
    return "Other"


def product_page_link(url: str, sku: str, product_id: str) -> str:
    sku_part = f"?sku={sku}" if sku else ""
    return f"{url}{sku_part}#product-{product_id}"


def item_key(line: dict[str, Any], item: dict[str, Any]) -> str:
    variant_id = item.get("productId") or item.get("sku") or item.get("name")
    return f"{line.get('brand', '')}|{line.get('name', '')}|{variant_id}"


def stock_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for line in data.get("lines", []):
        for item in line.get("items", []):
            indexed[item_key(line, item)] = {
                "brand": line.get("brand", ""),
                "line": line.get("name", ""),
                "group": line.get("group", ""),
                "name": item.get("name", ""),
                "sku": item.get("sku", ""),
                "productId": item.get("productId", ""),
                "url": item.get("url", line.get("url", "")),
                "price": item.get("price"),
                "inStock": bool(item.get("inStock")),
            }
    return indexed


def stock_changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if not previous:
        return {"inStock": [], "outOfStock": []}
    old = stock_index(previous)
    new = stock_index(current)
    changes = {"inStock": [], "outOfStock": []}
    for key, item in sorted(new.items(), key=lambda row: (row[1]["brand"], row[1]["line"], row[1]["name"])):
        old_item = old.get(key)
        if old_item is None or old_item["inStock"] == item["inStock"]:
            continue
        if item["inStock"]:
            changes["inStock"].append(item)
        else:
            changes["outOfStock"].append(item)
    return changes


def load_previous_data() -> dict[str, Any] | None:
    if not DATA_PATH.exists():
        return None
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def parse_product(brand: str, url: str, source: str) -> dict[str, Any]:
    ld_product = parse_ld_product(source)
    page_product_id = main_product_id(source)
    product_name = product_name_from_ld(ld_product, url)
    line = short_line_name(product_name)
    group = group_for_line(line)
    try:
        config = parse_configurable(source)
    except ValueError:
        offers = ld_product.get("offers", {})
        price = offers.get("price") if isinstance(offers, dict) else None
        try:
            price = float(price) if price not in (None, "") else None
        except (TypeError, ValueError):
            price = None
        availability = offers.get("availability", "") if isinstance(offers, dict) else ""
        in_stock = "InStock" in availability
        sku = ld_product.get("sku", "")
        product_id = page_product_id or str(ld_product.get("productID", ""))
        return {
            "brand": brand,
            "name": line,
            "group": group,
            "url": url,
            "items": [
                {
                    "name": "Default",
                    "color": "",
                    "hex": "",
                    "sku": sku,
                    "productId": product_id,
                    "inStock": in_stock,
                    "price": price,
                    "url": product_page_link(url, sku, product_id),
                }
            ],
        }
    swatches = parse_swatches(source)
    lookups = option_lookup(config)
    salable = salable_product_ids(config)
    color_attr = next(
        (attr_id for attr_id, attr in config.get("attributes", {}).items() if attr.get("code") == "color"),
        None,
    )
    items = []

    if page_product_id and str(config.get("productId")) != page_product_id:
        option_config = parse_notification_option_config(source, page_product_id)
        price = ld_product.get("offers", {}).get("price")
        for key, stock_info in option_config.items():
            if not isinstance(stock_info, dict):
                continue
            option_ids = key.split(",")
            color_id = option_ids[0]
            labels = [OPTION_LABELS.get(option_id, option_id) for option_id in option_ids]
            color_name = labels[0]
            label = color_name
            if len(labels) > 1:
                label = f"{label} ({', '.join(labels[1:])})"
            product_id = str(stock_info.get("product_id", ""))
            items.append(
                {
                    "name": label,
                    "color": color_name,
                    "hex": OPTION_HEX.get(color_id, ""),
                    "sku": "",
                    "productId": product_id,
                    "inStock": bool(stock_info.get("is_in_stock")),
                    "price": price,
                    "url": product_page_link(url, "", product_id),
                }
            )
        if items:
            return {
                "brand": brand,
                "name": line,
                "group": group,
                "url": url,
                "items": items,
            }

    for product_id, attr_values in sorted(config.get("index", {}).items(), key=lambda row: int(row[0])):
        label_parts = []
        color_name = ""
        color_hex = ""
        for attr_id, option_id in attr_values.items():
            attr_label = lookups.get(attr_id, {}).get(str(option_id), str(option_id))
            attr_code = config["attributes"].get(attr_id, {}).get("code", attr_id)
            if attr_code == "color":
                color_name = attr_label
                color_hex = swatch_hex(swatches, attr_id, str(option_id))
            else:
                label_parts.append(attr_label)

        price = None
        price_info = config.get("optionPrices", {}).get(str(product_id), {}).get("finalPrice", {})
        if isinstance(price_info, dict):
            price = price_info.get("amount")

        sku = config.get("sku", {}).get(str(product_id), "")
        label = color_name or "Default"
        if label_parts:
            label = f"{label} ({', '.join(label_parts)})"

        items.append(
            {
                "name": label,
                "color": color_name,
                "hex": color_hex,
                "sku": sku,
                "productId": str(product_id),
                "inStock": str(product_id) in salable,
                "price": price,
                "url": product_page_link(url, sku, str(product_id)),
            }
        )

    return {
        "brand": brand,
        "name": line,
        "group": group,
        "url": url,
        "items": items,
    }


def build_data(previous: dict[str, Any] | None = None) -> dict[str, Any]:
    lines = []
    errors = []
    for i, product in enumerate(PRODUCTS, 1):
        brand = product["brand"]
        url = product["url"]
        print(f"[{i:02d}/{len(PRODUCTS)}] {brand}: {url}")
        try:
            source = fetch(url)
            lines.append(parse_product(brand, url, source))
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"url": url, "error": str(exc)})
            print(f"  warning: {exc}", file=sys.stderr)
        time.sleep(0.2)

    data = {
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "previousUpdatedAt": previous.get("updatedAt") if previous else None,
        "source": BASE_URL,
        "lines": lines,
        "changes": {"inStock": [], "outOfStock": []},
        "errors": errors,
    }
    data["changes"] = stock_changes(previous, data)
    return data


def render_html(data: dict[str, Any]) -> str:
    payload = (
        json.dumps(data, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    worker_base = json.dumps(ALERT_WORKER_BASE)
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GigaParts Filament Stock</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23172033'/%3E%3Ccircle cx='28' cy='30' r='20' fill='%230088d6'/%3E%3Ccircle cx='28' cy='30' r='12' fill='%23ffffff'/%3E%3Ccircle cx='28' cy='30' r='5' fill='%23172033'/%3E%3Cpath d='M42 30c10 0 15 5 15 12 0 5-3 9-8 9-4 0-7-3-7-7 0-3 2-5 5-5' fill='none' stroke='%23f5547c' stroke-width='6' stroke-linecap='round'/%3E%3Cpath d='M13 16h30' stroke='%23fec700' stroke-width='5' stroke-linecap='round'/%3E%3C/svg%3E">
  <link rel="manifest" href="manifest.webmanifest">
  <style>
    *,*::before,*::after{{box-sizing:border-box}}
    :root{{
      --bg:#f7f8fb;--surface:#fff;--surface2:#eef2f7;--border:#d8dee8;--text:#172033;
      --muted:#5a667a;--dim:#8490a3;--accent:#1768ac;--in-bg:#dff4e7;--in-fg:#126133;
      --out-bg:#f8e1e1;--out-fg:#982626;--shadow:0 8px 26px rgba(25,34,52,.08)
    }}
    [data-theme="dark"]{{
      --bg:#14171d;--surface:#20252e;--surface2:#2a313c;--border:#384250;--text:#eef2f7;
      --muted:#b8c1cf;--dim:#808a9b;--accent:#66aee8;--in-bg:#143b27;--in-fg:#a8ecc1;
      --out-bg:#421f22;--out-fg:#ffb8b8;--shadow:0 10px 28px rgba(0,0,0,.22)
    }}
    body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
    header{{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--border);box-shadow:var(--shadow)}}
    .topbar{{max-width:1280px;margin:0 auto;padding:14px 18px;display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap}}
    h1{{font-size:18px;line-height:1.2;margin:0;font-weight:750}}
    .meta{{color:var(--muted);font-size:13px;margin-top:3px}}
    .controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .search-wrap{{position:relative;display:flex;align-items:center}}
    .search-wrap input[type="search"]{{padding-right:60px;min-width:250px}}
    .search-tip{{position:absolute;right:8px;width:18px;height:18px;border-radius:50%;border:1px solid var(--border);color:var(--muted);display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;background:var(--surface2)}}
    .color-button{{position:absolute;right:32px;width:20px;height:20px;border-radius:50%;padding:0;border:1px solid var(--border);background:conic-gradient(#e8102d,#f4ed2a,#00ae43,#0088d6,#b500b5,#e8102d);box-shadow:inset 0 0 0 3px var(--surface);font-size:0}}
    .color-button:hover{{filter:saturate(1.1);background:conic-gradient(#e8102d,#f4ed2a,#00ae43,#0088d6,#b500b5,#e8102d)}}
    .color-picker{{position:absolute;right:32px;width:20px;height:20px;opacity:0;pointer-events:none}}
    input,select,button{{border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:7px;padding:8px 10px;font:inherit;font-size:13px}}
    button{{cursor:pointer}}
    button:hover{{background:var(--surface2)}}
    main{{max-width:1280px;margin:0 auto;padding:18px}}
    .summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}}
    .stat{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;box-shadow:var(--shadow)}}
    .stat strong{{display:block;font-size:22px;margin-bottom:2px}}
    .stat span{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
    .alerts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:16px}}
    .alert-panel{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;box-shadow:var(--shadow);min-height:84px}}
    .alert-panel h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 8px;color:var(--muted)}}
    .alert-panel ul{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}}
    .alert-panel li{{font-size:13px;color:var(--muted)}}
    .alert-panel a{{color:var(--accent);text-decoration:none}}
    .alert-more{{margin-top:8px;font-size:12px;padding:5px 8px}}
    .alert-extra[hidden]{{display:none}}
    .new-in li{{font-weight:800;color:var(--text)}}
    .no-alerts{{color:var(--dim);font-size:13px}}
    .saved-list{{background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow);margin-bottom:16px;overflow:hidden}}
    .saved-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px;border-bottom:1px solid var(--border);flex-wrap:wrap}}
    .saved-head h2{{font-size:15px;margin:0}}
    .saved-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .phone-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-top:1px solid var(--border)}}
    .phone-status{{color:var(--muted);font-size:12px;min-width:180px}}
    .telegram-pairing{{display:none;gap:8px;align-items:center;flex-wrap:wrap;padding:0 12px 10px}}
    .telegram-pairing[aria-hidden="false"]{{display:flex}}
    .telegram-pairing input{{flex:1;min-width:260px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
    .saved-note{{color:var(--muted);font-size:12px;margin:8px 12px 0}}
    .saved-items{{list-style:none;margin:0;padding:0}}
    .saved-items li{{display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:10px;align-items:center;padding:10px 12px;border-top:1px solid var(--border);font-size:13px}}
    .saved-items li:first-child{{border-top:0}}
    .saved-main strong{{display:block;font-size:13px}}
    .saved-main span{{display:block;color:var(--muted);font-size:12px;margin-top:2px}}
    .saved-status{{border-radius:999px;padding:4px 8px;font-size:12px;white-space:nowrap}}
    .saved-status.in{{background:var(--in-bg);color:var(--in-fg)}}
    .saved-status.out{{background:var(--out-bg);color:var(--out-fg)}}
    .remove-saved,.save-btn{{font-size:12px;padding:6px 8px}}
    .save-btn{{width:100%;margin-top:7px}}
    .brand-tabs{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 16px}}
    .brand-tab{{border-radius:999px;padding:8px 14px;font-weight:750}}
    .brand-tab[aria-selected="true"]{{background:var(--accent);border-color:var(--accent);color:white}}
    .groups{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;align-items:start}}
    .group{{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:visible;box-shadow:var(--shadow)}}
    .group-header{{padding:14px 14px 10px;border-bottom:1px solid var(--border);background:linear-gradient(180deg,var(--surface),var(--surface2))}}
    .group-title{{display:flex;align-items:baseline;justify-content:space-between;gap:10px}}
    .group-title h2{{font-size:16px;margin:0}}
    .group-title span{{font-size:13px;color:var(--muted)}}
    .bar{{height:6px;background:var(--border);border-radius:99px;overflow:hidden;margin-top:10px}}
    .bar i{{display:block;height:100%;background:#25955a;border-radius:inherit}}
    details{{border-top:1px solid var(--border)}}
    details:first-of-type{{border-top:0}}
    summary{{list-style:none;padding:10px 12px;display:flex;align-items:center;gap:8px;cursor:pointer}}
    summary::-webkit-details-marker{{display:none}}
    summary:hover{{background:var(--surface2)}}
    .twisty{{font-size:13px;color:var(--dim);transition:transform .16s}}
    details[open] .twisty{{transform:rotate(90deg)}}
    .line-name{{font-weight:700;font-size:14px;flex:1}}
    .counts{{font-size:12px;color:var(--muted);white-space:nowrap}}
    .shop{{font-size:12px;color:var(--accent);text-decoration:none}}
    .pills{{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 12px}}
    .pill{{position:relative;border:1px solid transparent;border-radius:999px;padding:5px 9px;font-size:12px;line-height:1.25;white-space:nowrap}}
    .pill.in{{background:var(--in-bg);color:var(--in-fg)}}
    .pill.out{{background:var(--out-bg);color:var(--out-fg)}}
    .pill[data-hex]::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--chip);border:1px solid rgba(0,0,0,.24);margin-right:5px;vertical-align:-1px}}
    .pill a{{color:inherit;text-decoration:none}}
    .pill::after{{content:"";display:none;position:absolute;left:0;right:0;top:100%;height:10px}}
    .pill .hover-card{{display:none;position:absolute;left:0;top:calc(100% - 1px);min-width:210px;background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow);padding:9px;z-index:20;color:var(--text)}}
    .pill:hover::after,.pill:focus-within::after{{display:block}}
    .pill:hover .hover-card,.pill:focus-within .hover-card{{display:block}}
    .hover-card a{{display:block;background:var(--accent);color:white;text-align:center;border-radius:6px;padding:7px 8px;margin-top:7px;font-weight:700}}
    .hover-card small{{display:block;color:var(--muted);margin-top:3px}}
    .empty{{padding:18px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--muted)}}
    footer{{max-width:1280px;margin:0 auto;padding:8px 18px 28px;color:var(--dim);font-size:12px}}
    footer a{{color:var(--muted)}}
    @media (max-width:1000px){{.groups{{grid-template-columns:repeat(2,minmax(0,1fr))}}.summary{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
    @media (max-width:680px){{.groups{{grid-template-columns:1fr}}main{{padding:12px}}.summary{{grid-template-columns:1fr 1fr}}.saved-items li{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
<header>
  <div class="topbar">
    <div>
      <h1>GigaParts Filament Stock</h1>
      <div class="meta" id="updated"></div>
    </div>
    <div class="controls">
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search color, HEX, type, SKU..." aria-describedby="search-tip">
        <button class="color-button" id="color-button" type="button" title="Choose a color" aria-label="Choose a color"></button>
        <input class="color-picker" id="color-picker" type="color" value="#f24573" aria-label="Selected search color">
        <span class="search-tip" id="search-tip" title="Color names match text; HEX searches show closest swatch colors across all filament types.">?</span>
      </div>
      <select id="status">
        <option value="all">All stock</option>
        <option value="in">In stock</option>
        <option value="out">Out of stock</option>
      </select>
      <select id="sort">
      <option value="line">Sort by line</option>
        <option value="stock">Sort in-stock first</option>
        <option value="name">Sort by color</option>
      </select>
      <button id="notify" type="button" title="Subscribe to browser alerts">Notify</button>
      <button id="theme" type="button" title="Toggle theme">Dark</button>
    </div>
  </div>
</header>
<main>
  <section class="alerts" id="alerts"></section>
  <section class="saved-list" id="saved-list"></section>
  <nav class="brand-tabs" id="brand-tabs" aria-label="Filament brand"></nav>
  <section class="summary" id="summary"></section>
  <section class="groups" id="groups"></section>
</main>
<footer>
  Data from <a href="https://www.gigaparts.com" target="_blank" rel="noreferrer">GigaParts</a>.
  In-stock pills show an add-to-cart link on hover or keyboard focus.
</footer>
<script>
let DATA={payload};
const GROUP_ORDER=["PLA","PETG","PET","TPU","ABS","ASA","PC","PA","PPS","Support","Other"];
const BRANDS=[...new Set(DATA.lines.map(line=>line.brand||"Filament"))];
const POLL_MS=60*60*1000;
const NOTIFY_KEY="gigapartsNotifyInStock";
const SAVED_KEY="gigapartsSavedFilaments";
const BROWSER_ID_KEY="gigapartsBrowserListId";
const ALERT_DEVICE_ID_KEY="gigapartsAlertDeviceId";
const ALERT_DEVICE_TOKEN_KEY="gigapartsAlertDeviceToken";
const ALERT_WORKER_BASE=(window.GIGAPARTS_ALERTS_WORKER_URL||{worker_base}).replace(/\\/$/,"");
const MAX_SAVED_ITEMS=500;
const MAX_SAVED_BYTES=200000;
let query="", statusFilter="all", sortMode="line";
let activeBrand=BRANDS[0]||"Filament";
let currentItems=new Map();
let colorMatchKeys=new Set();

const $=id=>document.getElementById(id);
const money=v=>typeof v==="number"?"$"+v.toFixed(2):"";
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
const words=(line,item)=>[line.brand,line.name,line.group,item.name,item.color,item.hex,item.sku,item.productId].join(" ").toLowerCase();
const itemId=(line,item)=>`${{line.brand||""}}|${{line.name}}|${{item.productId||item.sku||item.name}}`;
const legacyItemId=(line,item)=>`${{line.name}}|${{item.productId||item.sku||item.name}}`;
function normalizeHex(value){{
  const raw=String(value||"").trim().replace(/^#/,"");
  if(/^[0-9a-f]{{3}}$/i.test(raw))return raw.split("").map(ch=>ch+ch).join("").toLowerCase();
  if(/^[0-9a-f]{{6}}$/i.test(raw))return raw.toLowerCase();
  return "";
}}
function hexToRgb(hex){{
  const clean=normalizeHex(hex);
  if(!clean)return null;
  return [0,2,4].map(i=>parseInt(clean.slice(i,i+2),16));
}}
function colorDistance(a,b){{
  const ar=hexToRgb(a), br=hexToRgb(b);
  if(!ar||!br)return Infinity;
  return Math.hypot(ar[0]-br[0],ar[1]-br[1],ar[2]-br[2]);
}}
function updateColorMatches(lines=DATA.lines){{
  colorMatchKeys=new Set();
  const target=normalizeHex(query);
  if(!target)return;
  const ranked=[];
  for(const line of lines){{
    for(const item of line.items){{
      if(!item.hex)continue;
      ranked.push({{key:itemId(line,item),dist:colorDistance(target,item.hex)}});
    }}
  }}
  ranked.sort((a,b)=>a.dist-b.dist);
  const best=ranked[0]?.dist;
  if(best==null||!Number.isFinite(best))return;
  for(const row of ranked.slice(0,36)){{
    if(row.dist<=Math.max(best+70,110))colorMatchKeys.add(row.key);
  }}
}}
function browserListId(){{
  let id=localStorage.getItem(BROWSER_ID_KEY);
  if(!id){{
    id=(crypto.randomUUID?crypto.randomUUID():`${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`);
    localStorage.setItem(BROWSER_ID_KEY,id);
  }}
  return id;
}}
function flatten(data,includeLegacy=false){{
  const map=new Map();
  for(const line of data.lines){{
    for(const item of line.items){{
      const key=itemId(line,item);
      const entry={{key,brand:line.brand,line:line.name,group:line.group,...item}};
      map.set(key,entry);
      if(includeLegacy)map.set(legacyItemId(line,item),entry);
    }}
  }}
  return map;
}}
function transitionChanges(oldData,newData){{
  const oldMap=flatten(oldData), newMap=flatten(newData);
  const changes={{inStock:[],outOfStock:[]}};
  for(const [key,item] of newMap){{
    const old=oldMap.get(key);
    if(!old||old.inStock===item.inStock)continue;
    if(item.inStock)changes.inStock.push(item);
    else changes.outOfStock.push(item);
  }}
  changes.inStock.sort((a,b)=>(a.line+a.name).localeCompare(b.line+b.name));
  changes.outOfStock.sort((a,b)=>(a.line+a.name).localeCompare(b.line+b.name));
  return changes;
}}
function visibleItems(line){{
  return line.items.filter(item=>{{
    if(statusFilter==="in"&&!item.inStock)return false;
    if(statusFilter==="out"&&item.inStock)return false;
    if(!query)return true;
    if(colorMatchKeys.size)return colorMatchKeys.has(itemId(line,item));
    return words(line,item).includes(query);
  }});
}}
function sortItems(items){{
  const copy=[...items];
  if(sortMode==="stock")copy.sort((a,b)=>Number(b.inStock)-Number(a.inStock)||a.name.localeCompare(b.name));
  else copy.sort((a,b)=>a.name.localeCompare(b.name));
  return copy;
}}
function totals(lines=DATA.lines){{
  const items=lines.flatMap(l=>l.items);
  const inStock=items.filter(i=>i.inStock).length;
  return {{lines:lines.length,total:items.length,inStock,out:items.length-inStock}};
}}
function renderSummary(filteredLines){{
  const brandLines=DATA.lines.filter(line=>(line.brand||"Filament")===activeBrand);
  const all=totals(brandLines), shown=totals(filteredLines);
  $("summary").innerHTML=[
    ["Lines",shown.lines+"/"+all.lines],
    ["Shown variants",shown.total+"/"+all.total],
    ["In stock",shown.inStock],
    ["Out of stock",shown.out],
  ].map(([label,value])=>`<div class="stat"><strong>${{value}}</strong><span>${{label}}</span></div>`).join("");
}}
function loadSaved(){{
  try{{
    const raw=localStorage.getItem(SAVED_KEY)||"[]";
    if(raw.length>MAX_SAVED_BYTES){{
      localStorage.removeItem(SAVED_KEY);
      return [];
    }}
    const parsed=JSON.parse(raw);
    if(!Array.isArray(parsed))return [];
    return parsed.filter(item=>item&&typeof item==="object"&&typeof item.key==="string").slice(0,MAX_SAVED_ITEMS);
  }}catch(error){{
    return [];
  }}
}}
function saveSaved(items){{
  localStorage.setItem(SAVED_KEY,JSON.stringify(items.slice(0,MAX_SAVED_ITEMS)));
}}
function itemDetailsForKey(key){{
  return flatten(DATA,true).get(key)||{{key,brand:"",line:"Saved filament",name:key,sku:"",inStock:false,url:""}};
}}
function mergeSavedItemKeys(itemKeys){{
  if(!Array.isArray(itemKeys)||!itemKeys.length)return false;
  const current=savedWithFreshStock();
  const byKey=new Map(current.map(item=>[item.key,item]));
  let changed=false;
  for(const key of itemKeys){{
    if(typeof key!=="string"||!key||byKey.has(key))continue;
    byKey.set(key,itemDetailsForKey(key));
    changed=true;
  }}
  if(changed)saveSaved([...byKey.values()].slice(0,MAX_SAVED_ITEMS));
  return changed;
}}
function alertDevice(){{
  const id=localStorage.getItem(ALERT_DEVICE_ID_KEY);
  const token=localStorage.getItem(ALERT_DEVICE_TOKEN_KEY);
  return id&&token?{{id,token}}:null;
}}
function setAlertStatus(message){{
  const status=$("phone-alert-status");
  if(status)status.textContent=message;
}}
function showTelegramPairingLink(url){{
  const panel=$("telegram-pairing-panel");
  const input=$("telegram-pairing-url");
  if(!panel||!input||!url)return;
  input.value=url;
  panel.setAttribute("aria-hidden","false");
  input.focus();
  input.select();
}}
async function copyTelegramPairingLink(){{
  const input=$("telegram-pairing-url");
  if(!input||!input.value)return;
  input.focus();
  input.select();
  try{{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(input.value);
    else document.execCommand("copy");
    setAlertStatus("Telegram pairing link copied.");
  }}catch(error){{
    console.warn("Telegram pairing link copy failed",error);
    setAlertStatus("Copy failed. Select and copy the Telegram link manually.");
  }}
}}
async function alertsRequest(path,options={{}}){{
  if(!ALERT_WORKER_BASE)throw new Error("Notification backend is not configured.");
  const headers={{"content-type":"application/json",...(options.headers||{{}})}};
  const response=await fetch(`${{ALERT_WORKER_BASE}}${{path}}`,{{...options,headers}});
  if(!response.ok){{
    const text=await response.text().catch(()=>"");
    throw new Error(text||`HTTP ${{response.status}}`);
  }}
  return response.status===204?null:response.json();
}}
async function ensureAlertDevice(){{
  const existing=alertDevice();
  if(existing)return existing;
  const created=await alertsRequest("/api/devices",{{method:"POST",body:JSON.stringify({{browserListId:browserListId()}})}});
  localStorage.setItem(ALERT_DEVICE_ID_KEY,created.deviceId);
  localStorage.setItem(ALERT_DEVICE_TOKEN_KEY,created.deviceToken);
  return {{id:created.deviceId,token:created.deviceToken}};
}}
async function syncSavedItemsToWorker(){{
  if(!ALERT_WORKER_BASE)return;
  const device=alertDevice();
  if(!device)return;
  const itemKeys=savedWithFreshStock().map(item=>item.key).slice(0,MAX_SAVED_ITEMS);
  try{{
    await alertsRequest(`/api/devices/${{encodeURIComponent(device.id)}}/saved-items`,{{
      method:"PUT",
      headers:{{authorization:`Bearer ${{device.token}}`}},
      body:JSON.stringify({{itemKeys}})
    }});
    if(itemKeys.length)setAlertStatus("Saved items synced for phone alerts.");
  }}catch(error){{
    console.warn("Saved alert sync failed",error);
    setAlertStatus("Phone alert sync failed.");
  }}
}}
async function getTelegramLinkStatus(){{
  const device=alertDevice();
  if(!device)return {{linked:false,itemKeys:[]}};
  return alertsRequest(`/api/devices/${{encodeURIComponent(device.id)}}/telegram-link`,{{
    method:"GET",
    headers:{{authorization:`Bearer ${{device.token}}`}}
  }});
}}
async function syncTelegramSavedItemsFromWorker({{pushAfterMerge=false}}={{}}){{
  try{{
    const status=await getTelegramLinkStatus();
    if(!status.linked)return false;
    const changed=mergeSavedItemKeys(status.itemKeys||[]);
    if(changed){{
      renderSavedList();
    }}
    if(pushAfterMerge)await syncSavedItemsToWorker();
    if((status.itemKeys||[]).length)setAlertStatus("Telegram shared saved list synced.");
    return true;
  }}catch(error){{
    console.warn("Telegram shared list sync failed",error);
    return false;
  }}
}}
async function pollTelegramLink(){{
  for(let attempt=0;attempt<30;attempt+=1){{
    const linked=await syncTelegramSavedItemsFromWorker({{pushAfterMerge:true}});
    if(linked){{
      setAlertStatus("Telegram connected. Shared saved list is synced.");
      return;
    }}
    await new Promise(resolve=>setTimeout(resolve,2000));
  }}
  setAlertStatus("Telegram pairing not confirmed yet. Return here after starting the bot.");
}}
async function initializeAlertSync(){{
  const merged=await syncTelegramSavedItemsFromWorker({{pushAfterMerge:true}});
  if(!merged)await syncSavedItemsToWorker();
}}
async function registerServiceWorker(){{
  if(!("serviceWorker" in navigator))throw new Error("Service workers are not supported in this browser.");
  return navigator.serviceWorker.register("sw.js");
}}
function urlBase64ToUint8Array(value){{
  const padding="=".repeat((4-value.length%4)%4);
  const base64=(value+padding).replace(/-/g,"+").replace(/_/g,"/");
  const raw=atob(base64);
  return Uint8Array.from([...raw].map(ch=>ch.charCodeAt(0)));
}}
async function connectWebPush(){{
  if(!("PushManager" in window)){{setAlertStatus("Web Push is not supported here.");return;}}
  const permission=await Notification.requestPermission();
  if(permission!=="granted"){{setAlertStatus("Web Push permission was not granted.");return;}}
  try{{
    const [device,config]=await Promise.all([ensureAlertDevice(),alertsRequest("/api/config")]);
    const registration=await registerServiceWorker();
    const subscription=await registration.pushManager.subscribe({{
      userVisibleOnly:true,
      applicationServerKey:urlBase64ToUint8Array(config.vapidPublicKey)
    }});
    await alertsRequest(`/api/devices/${{encodeURIComponent(device.id)}}/web-push-subscription`,{{
      method:"POST",
      headers:{{authorization:`Bearer ${{device.token}}`}},
      body:JSON.stringify({{subscription:subscription.toJSON()}})
    }});
    await syncSavedItemsToWorker();
    setAlertStatus("Web Push connected.");
  }}catch(error){{
    console.warn("Web Push setup failed",error);
    setAlertStatus("Web Push setup failed.");
  }}
}}
async function disconnectWebPush(){{
  const device=alertDevice();
  if(!device)return;
  try{{
    const registration=await navigator.serviceWorker?.getRegistration?.();
    const subscription=await registration?.pushManager?.getSubscription?.();
    await subscription?.unsubscribe?.();
    await alertsRequest(`/api/devices/${{encodeURIComponent(device.id)}}/web-push-subscription`,{{
      method:"DELETE",
      headers:{{authorization:`Bearer ${{device.token}}`}}
    }});
    setAlertStatus("Web Push disconnected.");
  }}catch(error){{
    console.warn("Web Push disconnect failed",error);
    setAlertStatus("Web Push disconnect failed.");
  }}
}}
async function connectTelegram(){{
  try{{
    const device=await ensureAlertDevice();
    const response=await alertsRequest(`/api/devices/${{encodeURIComponent(device.id)}}/telegram-link`,{{
      method:"POST",
      headers:{{authorization:`Bearer ${{device.token}}`}}
    }});
    await syncSavedItemsToWorker();
    showTelegramPairingLink(response.pairingUrl);
    window.open(response.pairingUrl,"_blank","noopener,noreferrer");
    setAlertStatus("Telegram pairing link opened. Waiting for bot confirmation.");
    pollTelegramLink();
  }}catch(error){{
    console.warn("Telegram pairing failed",error);
    setAlertStatus("Telegram pairing failed.");
  }}
}}
async function disconnectTelegram(){{
  const device=alertDevice();
  if(!device)return;
  try{{
    await alertsRequest(`/api/devices/${{encodeURIComponent(device.id)}}/telegram-link`,{{
      method:"DELETE",
      headers:{{authorization:`Bearer ${{device.token}}`}}
    }});
    setAlertStatus("Telegram disconnected.");
  }}catch(error){{
    console.warn("Telegram disconnect failed",error);
    setAlertStatus("Telegram disconnect failed.");
  }}
}}
function savedWithFreshStock(){{
  const current=flatten(DATA,true);
  const saved=loadSaved();
  let changed=false;
  const fresh=saved.map(item=>{{
    const currentItem=current.get(item.key);
    if(!currentItem)return item;
    if(currentItem.key!==item.key)changed=true;
    return currentItem;
  }});
  if(changed)saveSaved(fresh);
  return fresh;
}}
function addSavedItem(key){{
  const item=currentItems.get(key);
  if(!item)return;
  const saved=savedWithFreshStock();
  if(!saved.some(row=>row.key===key)){{
    saved.push({{key,...item}});
    saveSaved(saved);
  }}
  renderSavedList();
  syncSavedItemsToWorker();
}}
function removeSavedItem(key){{
  saveSaved(loadSaved().filter(item=>item.key!==key));
  renderSavedList();
  syncSavedItemsToWorker();
}}
function savedListText(){{
  const items=savedWithFreshStock();
  if(!items.length)return "";
  const lines=items.map(item=>[
    `${{item.brand?item.brand+" - ":""}}${{item.line}} - ${{item.name}}`,
    item.sku?`SKU: ${{item.sku}}`:null,
    `Status: ${{item.inStock?"In stock":"Out of stock"}}`,
    item.price!=null?`Price: ${{money(item.price)}}`:null,
    item.url
  ].filter(Boolean).join("\\n"));
  return `Saved GigaParts filament list\\nBrowser list ID: ${{browserListId()}}\\n\\n${{lines.join("\\n\\n")}}`;
}}
function emailSavedList(){{
  const body=savedListText();
  if(!body)return;
  location.href=`mailto:?subject=${{encodeURIComponent("GigaParts filament list")}}&body=${{encodeURIComponent(body)}}`;
}}
async function copySavedList(){{
  const body=savedListText();
  if(!body)return;
  await navigator.clipboard.writeText(body);
}}
function printSavedList(){{
  const body=savedListText();
  if(!body)return;
  const win=window.open("", "_blank", "noopener,noreferrer");
  if(!win)return;
  win.document.write(`<pre style="font:14px/1.5 system-ui, sans-serif; white-space:pre-wrap">${{esc(body)}}</pre>`);
  win.document.close();
  win.print();
}}
function renderSavedList(){{
  const items=savedWithFreshStock();
  $("saved-list").innerHTML=`
    <div class="saved-head">
      <div>
        <h2>Saved Filament List</h2>
        <div class="meta">${{items.length}} saved in this browser</div>
      </div>
      <div class="saved-actions">
        <button id="email-list" type="button" ${{items.length?"":"disabled"}}>Email to Myself</button>
        <button id="copy-list" type="button" ${{items.length?"":"disabled"}}>Copy</button>
        <button id="print-list" type="button" ${{items.length?"":"disabled"}}>Print</button>
        <button id="clear-list" type="button" ${{items.length?"":"disabled"}}>Clear</button>
      </div>
    </div>
    <div class="saved-note">Saved items are included in browser notifications when they newly come in stock while this page is open.</div>
    <div class="phone-actions">
      <button id="web-push-toggle" type="button">Connect Web Push</button>
      <button id="web-push-disconnect" type="button">Disconnect Web Push</button>
      <button id="telegram-link" type="button">Connect Telegram</button>
      <button id="telegram-unlink" type="button">Disconnect Telegram</button>
      <span class="phone-status" id="phone-alert-status">Phone alerts sync saved items to the notification backend.</span>
    </div>
    <div class="telegram-pairing" id="telegram-pairing-panel" aria-hidden="true">
      <input id="telegram-pairing-url" type="text" readonly aria-label="Telegram pairing link">
      <button id="telegram-copy-link" type="button">Copy Telegram Link</button>
    </div>
    <div class="saved-note">iPhone/iPad: install this site to your Home Screen before enabling Web Push. Telegram works from any browser after pairing. Telegram-linked browsers share one saved list; removing or clearing here updates that shared list. Telegram bot commands include /list, /status, and /help.</div>
    ${{items.length?`<ul class="saved-items">${{items.map(item=>`<li>
      <div class="saved-main"><strong>${{item.brand?esc(item.brand)+" - ":""}}${{esc(item.line)}} - ${{esc(item.name)}}</strong><span>${{item.sku?esc(item.sku)+" - ":""}}${{item.price!=null?money(item.price):""}}</span></div>
      <span class="saved-status ${{item.inStock?"in":"out"}}">${{item.inStock?"In stock":"Out of stock"}}</span>
      <button class="remove-saved" type="button" data-remove-key="${{esc(item.key)}}">Remove</button>
    </li>`).join("")}}</ul>`:`<div class="empty">No saved filament yet. Hover a filament and choose Save to List.</div>`}}`;
}}
function renderAlerts(changes=DATA.changes||{{inStock:[],outOfStock:[]}}){{
  const alertKey=item=>`${{item.brand||""}}|${{item.line||""}}|${{item.productId||item.sku||item.name||""}}`;
  const outKeys=new Set((changes.outOfStock||[]).map(alertKey));
  const outItems=(changes.outOfStock||[]).slice(0,100);
  const inItems=(changes.inStock||[]).filter(item=>!outKeys.has(alertKey(item))).slice(0,100);
  const row=(item,attrs="")=>`<li${{attrs}}><a href="${{esc(item.url)}}" target="_blank" rel="noreferrer">${{item.brand?esc(item.brand)+" - ":""}}${{esc(item.line)}} - ${{esc(item.name)}}</a>${{item.sku?` <span>(${{esc(item.sku)}})</span>`:""}}</li>`;
  const list=(items,id)=>{{
    if(!items.length)return `<div class="no-alerts">No changes in this snapshot.</div>`;
    const visible=items.slice(0,12);
    const hidden=items.slice(12);
    return `<ul>${{visible.map(item=>row(item)).join("")}}${{hidden.map(item=>row(item,` class="alert-extra" data-alert-extra="${{id}}" hidden`)).join("")}}</ul>${{hidden.length?`<button class="alert-more" type="button" data-alert-more="${{id}}" aria-expanded="false">+${{hidden.length}} more</button>`:""}}`;
  }};
  $("alerts").innerHTML=`
    <article class="alert-panel new-out">
      <h2>Newly Out of Stock</h2>
      ${{list(outItems,"out")}}
    </article>
    <article class="alert-panel new-in">
      <h2>Newly In Stock</h2>
      ${{list(inItems,"in")}}
    </article>`;
}}
function groupStats(lines){{
  const items=lines.flatMap(l=>visibleItems(l));
  const inStock=items.filter(i=>i.inStock).length;
  const pct=items.length?Math.round(inStock/items.length*100):0;
  return {{total:items.length,inStock,out:items.length-inStock,pct}};
}}
function renderBrandTabs(){{
  $("brand-tabs").innerHTML=BRANDS.map(brand=>{{
    const lines=DATA.lines.filter(line=>(line.brand||"Filament")===brand);
    const stats=totals(lines);
    return `<button class="brand-tab" type="button" data-brand="${{esc(brand)}}" aria-selected="${{brand===activeBrand}}">${{esc(brand)}} <span>${{stats.inStock}}/${{stats.total}}</span></button>`;
  }}).join("");
}}
function lineHtml(line){{
  const items=sortItems(visibleItems(line));
  if(!items.length)return "";
  const inStock=items.filter(i=>i.inStock).length;
  const pills=items.map(item=>{{
    const key=itemId(line,item);
    currentItems.set(key,{{key,brand:line.brand,line:line.name,group:line.group,...item}});
    const style=item.hex?` style="--chip:${{esc(item.hex)}}" data-hex="${{esc(item.hex)}}"`:"";
    const body=`${{item.inStock?"In":"Out"}} &middot; ${{esc(item.name)}}`;
    const cart=item.inStock?`<a href="${{esc(item.url)}}" target="_blank" rel="noreferrer">Add to Cart</a>`:"";
    const hover=`<span class="hover-card"><strong>${{esc(item.name)}}</strong><small>${{esc(item.sku)}} ${{money(item.price)}}</small>${{cart}}<button class="save-btn" type="button" data-save-key="${{esc(key)}}">Save to List</button></span>`;
    return `<span class="pill ${{item.inStock?"in":"out"}}"${{style}} tabindex="0">${{body}}${{hover}}</span>`;
  }}).join("");
  return `<details open><summary><span class="twisty">&#9658;</span><span class="line-name">${{esc(line.name)}}</span><span class="counts">${{inStock}} in / ${{items.length-inStock}} out</span><a class="shop" href="${{esc(line.url)}}" target="_blank" rel="noreferrer" onclick="event.stopPropagation()">Shop</a></summary><div class="pills">${{pills}}</div></details>`;
}}
function render(){{
  currentItems=new Map();
  if(!BRANDS.includes(activeBrand))activeBrand=BRANDS[0]||"Filament";
  const brandLines=DATA.lines.filter(line=>(line.brand||"Filament")===activeBrand);
  updateColorMatches(brandLines);
  const lines=brandLines.map(line=>({{...line,items:visibleItems(line)}})).filter(line=>line.items.length);
  renderAlerts();
  renderSavedList();
  renderBrandTabs();
  renderSummary(lines);
  const byGroup=new Map();
  for(const line of brandLines){{
    if(!visibleItems(line).length)continue;
    if(!byGroup.has(line.group))byGroup.set(line.group,[]);
    byGroup.get(line.group).push(line);
  }}
  const groups=[...byGroup.keys()].sort((a,b)=>GROUP_ORDER.indexOf(a)-GROUP_ORDER.indexOf(b)||a.localeCompare(b));
  $("groups").innerHTML=groups.map(group=>{{
    let lines=byGroup.get(group);
    lines=[...lines].sort((a,b)=>a.name.localeCompare(b.name));
    const stats=groupStats(lines);
    return `<section class="group"><div class="group-header"><div class="group-title"><h2>${{esc(group)}}</h2><span>${{stats.inStock}} in / ${{stats.out}} out</span></div><div class="bar"><i style="width:${{stats.pct}}%"></i></div></div>${{lines.map(lineHtml).join("")}}</section>`;
  }}).join("")||`<div class="empty">No filaments match the current filters.</div>`;
}}
function updateTimestamp(){{
  const updated=new Date(DATA.updatedAt).toLocaleString();
  $("updated").textContent=`Updated ${{updated}}. Auto-checks every hour.`;
}}
async function refreshStock(){{
  try{{
    const response=await fetch(`stock-data.json?ts=${{Date.now()}}`,{{cache:"no-store"}});
    if(!response.ok)throw new Error(`HTTP ${{response.status}}`);
    const latest=await response.json();
    if(!latest.updatedAt||latest.updatedAt===DATA.updatedAt)return;
    const changes=transitionChanges(DATA,latest);
    latest.changes=changes;
    DATA=latest;
    updateTimestamp();
    render();
    sendInStockNotifications(changes.inStock||[]);
  }}catch(error){{
    console.warn("Stock refresh failed",error);
  }}
}}
function notificationEnabled(){{
  return "Notification" in window&&localStorage.getItem(NOTIFY_KEY)==="1"&&Notification.permission==="granted";
}}
function updateNotifyButton(){{
  const btn=$("notify");
  if(!("Notification" in window)){{
    btn.textContent="No Notifications";
    btn.disabled=true;
    return;
  }}
  const enabled=localStorage.getItem(NOTIFY_KEY)==="1"&&Notification.permission==="granted";
  btn.textContent=enabled?"Notifying":"Notify";
}}
async function toggleNotifications(){{
  if(!("Notification" in window))return;
  if(localStorage.getItem(NOTIFY_KEY)==="1"){{
    localStorage.removeItem(NOTIFY_KEY);
    updateNotifyButton();
    return;
  }}
  const permission=Notification.permission==="granted"?"granted":await Notification.requestPermission();
  if(permission==="granted"){{
    localStorage.setItem(NOTIFY_KEY,"1");
    new Notification("GigaParts stock alerts enabled",{{body:"Newly in-stock filament alerts will appear while this page is open."}});
  }}
  updateNotifyButton();
}}
function sendInStockNotifications(items){{
  if(!notificationEnabled()||!items.length)return;
  const savedKeys=new Set(savedWithFreshStock().map(item=>item.key));
  const savedItems=items.filter(item=>savedKeys.has(item.key));
  const savedShown=savedItems.slice(0,4);
  for(const item of savedShown){{
    new Notification(`${{item.brand?item.brand+" - ":""}}${{item.line}} saved filament in stock`,{{body:item.sku?`${{item.name}} (${{item.sku}})`:item.name}});
  }}
  if(savedItems.length>savedShown.length){{
    new Notification("More saved GigaParts filament in stock",{{body:`${{savedItems.length-savedShown.length}} additional saved variants became available.`}});
  }}
  const savedItemKeys=new Set(savedItems.map(item=>item.key));
  const otherItems=items.filter(item=>!savedItemKeys.has(item.key));
  const shown=otherItems.slice(0,4);
  for(const item of shown){{
    new Notification(`${{item.brand?item.brand+" - ":""}}${{item.line}} in stock`,{{body:item.sku?`${{item.name}} (${{item.sku}})`:item.name}});
  }}
  if(otherItems.length>shown.length){{
    new Notification("More GigaParts filament in stock",{{body:`${{otherItems.length-shown.length}} additional variants became available.`}});
  }}
}}
updateTimestamp();
$("search").addEventListener("input",e=>{{query=e.target.value.trim().toLowerCase();render();}});
$("color-button").addEventListener("click",()=>{{$("color-picker").click();}});
$("color-picker").addEventListener("input",e=>{{
  query=e.target.value.toLowerCase();
  $("search").value=query;
  render();
}});
$("status").addEventListener("change",e=>{{statusFilter=e.target.value;render();}});
$("sort").addEventListener("change",e=>{{sortMode=e.target.value;render();}});
$("notify").addEventListener("click",toggleNotifications);
$("saved-list").addEventListener("click",e=>{{
  const remove=e.target.closest("[data-remove-key]");
  if(remove)removeSavedItem(remove.dataset.removeKey);
  if(e.target.id==="email-list")emailSavedList();
  if(e.target.id==="copy-list")copySavedList();
  if(e.target.id==="print-list")printSavedList();
  if(e.target.id==="clear-list"){{
    saveSaved([]);
    renderSavedList();
    syncSavedItemsToWorker();
  }}
  if(e.target.id==="web-push-toggle")connectWebPush();
  if(e.target.id==="web-push-disconnect")disconnectWebPush();
  if(e.target.id==="telegram-link")connectTelegram();
  if(e.target.id==="telegram-copy-link")copyTelegramPairingLink();
  if(e.target.id==="telegram-unlink")disconnectTelegram();
}});
$("alerts").addEventListener("click",e=>{{
  const more=e.target.closest("[data-alert-more]");
  if(!more)return;
  const id=more.dataset.alertMore;
  const expanded=more.getAttribute("aria-expanded")==="true";
  for(const item of document.querySelectorAll(`[data-alert-extra="${{id}}"]`)){{
    item.hidden=expanded;
  }}
  more.setAttribute("aria-expanded",String(!expanded));
  more.textContent=expanded?`+${{document.querySelectorAll(`[data-alert-extra="${{id}}"]`).length}} more`:"Show fewer";
}});
$("brand-tabs").addEventListener("click",e=>{{
  const tab=e.target.closest("[data-brand]");
  if(!tab)return;
  activeBrand=tab.dataset.brand;
  render();
}});
$("groups").addEventListener("click",e=>{{
  const save=e.target.closest("[data-save-key]");
  if(save)addSavedItem(save.dataset.saveKey);
}});
$("theme").addEventListener("click",()=>{{
  const html=document.documentElement;
  const dark=html.dataset.theme==="dark";
  html.dataset.theme=dark?"light":"dark";
  $("theme").textContent=dark?"Dark":"Light";
  localStorage.setItem("theme",html.dataset.theme);
}});
const saved=localStorage.getItem("theme");
if(saved){{document.documentElement.dataset.theme=saved;$("theme").textContent=saved==="dark"?"Light":"Dark";}}
updateNotifyButton();
registerServiceWorker().catch(error=>console.warn("Service worker registration failed",error));
initializeAlertSync();
setInterval(refreshStock,POLL_MS);
render();
</script>
</body>
</html>
"""


def render_manifest() -> str:
    manifest = {
        "name": "GigaParts Filament Stock",
        "short_name": "Filament Stock",
        "description": "Saved filament restock alerts for GigaParts.",
        "start_url": ".",
        "scope": ".",
        "display": "standalone",
        "background_color": "#f7f8fb",
        "theme_color": "#1768ac",
        "icons": [
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23172033'/%3E%3Ccircle cx='28' cy='30' r='20' fill='%230088d6'/%3E%3Ccircle cx='28' cy='30' r='12' fill='%23ffffff'/%3E%3Ccircle cx='28' cy='30' r='5' fill='%23172033'/%3E%3Cpath d='M42 30c10 0 15 5 15 12 0 5-3 9-8 9-4 0-7-3-7-7 0-3 2-5 5-5' fill='none' stroke='%23f5547c' stroke-width='6' stroke-linecap='round'/%3E%3Cpath d='M13 16h30' stroke='%23fec700' stroke-width='5' stroke-linecap='round'/%3E%3C/svg%3E",
                "sizes": "64x64",
                "type": "image/svg+xml",
            }
        ],
    }
    return json.dumps(manifest, indent=2) + "\n"


def render_service_worker() -> str:
    return """self.addEventListener("push", event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (error) {
    data = { title: "GigaParts filament in stock", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "GigaParts filament in stock";
  const options = {
    body: data.body || "",
    data: { url: data.url || "./" },
    icon: data.icon || undefined,
    badge: data.badge || undefined,
    tag: data.tag || undefined,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : "./";
  event.waitUntil(clients.openWindow(targetUrl));
});
"""


def main() -> int:
    previous = load_previous_data()
    data = build_data(previous)
    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    OUT_PATH.write_text(render_html(data), encoding="utf-8")
    MANIFEST_PATH.write_text(render_manifest(), encoding="utf-8")
    SERVICE_WORKER_PATH.write_text(render_service_worker(), encoding="utf-8")
    print(f"Wrote {DATA_PATH}")
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Wrote {SERVICE_WORKER_PATH}")
    if data["errors"]:
        print(f"Completed with {len(data['errors'])} scrape warning(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
