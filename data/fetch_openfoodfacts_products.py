#!/usr/bin/env python3
"""Fetch a bounded, review-only Indonesian packaged-food snapshot from Open Food Facts.

The public search API is rate-limited and intended for small snapshots. For a full
catalogue, use Open Food Facts' bulk export instead of increasing --pages.
"""

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
API = "https://world.openfoodfacts.org/api/v2/search"
SOURCE = "https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/"
LICENSE = "Open Database License (ODbL); verify reuse and attribution requirements"
USER_AGENT = "TAKARKUY/0.1 (https://github.com/PBPUY-11-C/TAKARKUY)"
FIELDS = ",".join(
    (
        "code",
        "product_name",
        "product_name_id",
        "brands",
        "quantity",
        "serving_size",
        "categories_tags",
        "countries_tags",
        "nutriments",
        "nutrition_data",
        "data_quality_errors_tags",
        "data_quality_warnings_tags",
        "last_modified_t",
        "ingredients_text",
    )
)
CSV_FIELDS = (
    "barcode",
    "product_name",
    "brands",
    "quantity",
    "serving_size",
    "category_tags",
    "energy_kcal_100g",
    "protein_g_100g",
    "carbohydrates_g_100g",
    "fat_g_100g",
    "nutrition_complete",
    "data_quality_error_count",
    "source_modified_at",
    "source_url",
    "source_license",
    "review_status",
)


def get_page(page, page_size, brand=None):
    params = {
        "countries_tags_en": "indonesia",
        "page": page,
        "page_size": page_size,
        "fields": FIELDS,
        "sort_by": "popularity_key",
    }
    if brand:
        params["brands_tags"] = brand
    request = Request(f"{API}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(8 * (attempt + 1))


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return ""


def stage(product):
    nutriments = product.get("nutriments") or {}
    energy = number(nutriments.get("energy-kcal_100g"))
    protein = number(nutriments.get("proteins_100g"))
    carbs = number(nutriments.get("carbohydrates_100g"))
    fat = number(nutriments.get("fat_100g"))
    modified = product.get("last_modified_t")
    return {
        "barcode": product.get("code", ""),
        "product_name": product.get("product_name") or product.get("product_name_id") or "",
        "brands": product.get("brands", ""),
        "quantity": product.get("quantity", ""),
        "serving_size": product.get("serving_size", ""),
        "category_tags": ";".join(product.get("categories_tags") or []),
        "energy_kcal_100g": energy,
        "protein_g_100g": protein,
        "carbohydrates_g_100g": carbs,
        "fat_g_100g": fat,
        "nutrition_complete": str(
            all(isinstance(x, (int, float)) for x in (energy, protein, carbs, fat))
        ).lower(),
        "data_quality_error_count": len(product.get("data_quality_errors_tags") or []),
        "source_modified_at": (
            datetime.fromtimestamp(modified, timezone.utc).date().isoformat()
            if isinstance(modified, (int, float))
            else ""
        ),
        "source_url": f"https://world.openfoodfacts.org/product/{product.get('code', '')}",
        "source_license": LICENSE,
        "review_status": "candidate_not_for_planner",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2, help="Popular Indonesia pages, at most 3")
    parser.add_argument("--page-size", type=int, default=100, help="Products per page, at most 100")
    parser.add_argument("--brand", default="indomie", help="Additional brand tag to sample")
    args = parser.parse_args()
    if not 1 <= args.pages <= 3 or not 1 <= args.page_size <= 100:
        parser.error("Use 1–3 pages and 1–100 products per page; use bulk export for more.")

    batches = [(None, page) for page in range(1, args.pages + 1)]
    if args.brand:
        batches.append((args.brand, 1))
    products = {}
    source_counts = {}
    for index, (brand, page) in enumerate(batches):
        if index:
            time.sleep(7)  # Open Food Facts allows at most 10 search requests/min/IP.
        data = get_page(page, args.page_size, brand)
        if not isinstance(data.get("products"), list):
            raise ValueError("Open Food Facts returned no product list")
        key = f"brand:{brand}" if brand else f"indonesia_page:{page}"
        source_counts[key] = {
            "total_matching": data.get("count"),
            "received": len(data["products"]),
        }
        for product in data["products"]:
            code = str(product.get("code", ""))
            if code.isdigit() and 8 <= len(code) <= 14:
                products[code] = product

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw_path = ROOT / "raw" / "openfoodfacts_indonesia_sample.json"
    staging_path = ROOT / "staging" / "openfoodfacts_products.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(
            {
                "source": "Open Food Facts",
                "api_url": API,
                "documentation_url": SOURCE,
                "license": LICENSE,
                "fetched_at": fetched_at,
                "selection": "Most popular products tagged Indonesia plus one brand page; not a complete store catalogue",
                "request_counts": source_counts,
                "products": list(products.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with staging_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(stage(product) for product in products.values())
    print(f"Fetched {len(products)} distinct products into {raw_path} and {staging_path}")


if __name__ == "__main__":
    main()
