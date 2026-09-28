#!/usr/bin/env python3
"""Fetch raw TheMealDB candidates for human review; never publishes them to planner tables."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "themealdb_breakfast_snapshot.json"
STAGING = ROOT / "staging" / "themealdb_breakfast_review.csv"
BASE = "https://www.themealdb.com/api/json/v1/1"


def get_json(path, params=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "TAKARKUY/0.1 (educational catalog review)"})
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def main():
    breakfast = get_json("filter.php", {"c": "Breakfast"}).get("meals") or []
    banana = get_json("filter.php", {"i": "banana"}).get("meals") or []
    ids = list(dict.fromkeys(item["idMeal"] for item in breakfast + banana))
    details = []
    for meal_id in ids:
        result = get_json("lookup.php", {"i": meal_id}).get("meals") or []
        if result:
            details.append(result[0])

    snapshot = {
        "source": "TheMealDB API",
        "source_url": "https://www.themealdb.com/docs_api_guide.php",
        "terms_url": "https://themealdb.com/terms_of_use.php",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "query_categories": ["Breakfast", "ingredient:banana"],
        "meals": details,
    }
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    STAGING.parent.mkdir(parents=True, exist_ok=True)
    fields = ["source_id", "name", "area", "category", "source_url", "image_url",
              "raw_ingredients_json", "instructions", "review_status"]
    with STAGING.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for meal in details:
            raw_ingredients = []
            for index in range(1, 21):
                ingredient = (meal.get(f"strIngredient{index}") or "").strip()
                measure = (meal.get(f"strMeasure{index}") or "").strip()
                if ingredient:
                    raw_ingredients.append({"ingredient": ingredient, "measure": measure})
            writer.writerow({
                "source_id": meal.get("idMeal", ""),
                "name": meal.get("strMeal", ""),
                "area": meal.get("strArea", ""),
                "category": meal.get("strCategory", ""),
                "source_url": meal.get("strSource") or f"https://www.themealdb.com/meal/{meal.get('idMeal', '')}",
                "image_url": meal.get("strMealThumb", ""),
                "raw_ingredients_json": json.dumps(raw_ingredients, ensure_ascii=False),
                "instructions": meal.get("strInstructions", ""),
                "review_status": "needs_manual_mapping_and_rights_review",
            })
    print(f"Fetched {len(details)} recipes; raw snapshot: {RAW}; review queue: {STAGING}")


if __name__ == "__main__":
    try:
        main()
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise SystemExit(f"TheMealDB fetch failed: {error}") from error
