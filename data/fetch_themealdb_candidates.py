#!/usr/bin/env python3
"""Collect 100 TheMealDB recipe references into scratch; do not plan from them."""
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
SCRATCH = ROOT / "scratch"
BASE = "https://www.themealdb.com/api/json/v1/1"
SOURCE = "TheMealDB API (unverified recipe candidate; attribution required)"


def get_json(path, params=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "TAKARKUY/0.1 educational recipe catalog"})
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def add_to_pool(pool, category, meals):
    for meal in meals:
        pool.setdefault(str(meal["idMeal"]), (meal["strMeal"], category))


def pick_balanced(pool, limit):
    categories = list(pool)
    selected = []
    while len(selected) < limit:
        made_progress = False
        for category in categories:
            if pool[category]:
                selected.append(pool[category].pop(0))
                made_progress = True
                if len(selected) == limit:
                    break
        if not made_progress:
            break
    return selected


def get_ingredients(meal):
    ingredients = []
    for index in range(1, 21):
        name = (meal.get(f"strIngredient{index}") or "").strip()
        measure = (meal.get(f"strMeasure{index}") or "").strip()
        if name:
            ingredients.append({"ingredient": name, "measure": measure})
    return ingredients


def main():
    breakfast_list = get_json("filter.php", {"c": "Breakfast"}).get("meals") or []
    breakfast_ids = {str(meal["idMeal"]) for meal in breakfast_list}
    breakfast_pool = {"Breakfast": [(str(m["idMeal"]), "Breakfast") for m in breakfast_list]}

    # The Breakfast category has 19 meals at collection time. Add one banana
    # recipe as an explicitly tentative breakfast suggestion to reach 20.
    banana_list = get_json("filter.php", {"i": "banana"}).get("meals") or []
    banana_candidate = next((m for m in banana_list if str(m["idMeal"]) not in breakfast_ids), None)
    if len(breakfast_pool["Breakfast"]) < 20 and banana_candidate:
        breakfast_pool["Breakfast"].append((str(banana_candidate["idMeal"]), "Breakfast suggestion (banana filter)"))
    breakfast_selected = breakfast_pool["Breakfast"][:20]

    savory_categories = ["Beef", "Chicken", "Seafood", "Vegetarian", "Vegan", "Pasta", "Miscellaneous", "Lamb", "Goat"]
    meal_pool = {}
    for category in savory_categories:
        meals = get_json("filter.php", {"c": category}).get("meals") or []
        # Keep portions suitable as lunch/dinner ideas; skip dessert/side courses
        # and recipes already selected for breakfast.
        meal_pool[category] = [
            (str(m["idMeal"]), category) for m in meals
            if str(m["idMeal"]) not in {item[0] for item in breakfast_selected}
        ]
    savory_selected = pick_balanced(meal_pool, 80)
    if len(breakfast_selected) < 20 or len(savory_selected) < 80:
        raise RuntimeError(f"API returned too few candidates: breakfast={len(breakfast_selected)}, savory={len(savory_selected)}")

    candidate_rows = []
    all_selected = [(meal_id, api_category, "sarapan")
                    for meal_id, api_category in breakfast_selected]
    all_selected.extend((meal_id, api_category, "makan_siang" if i % 2 == 0 else "makan_malam")
                        for i, (meal_id, api_category) in enumerate(savory_selected))
    for meal_id, api_category, suggested_slot in all_selected:
        result = get_json("lookup.php", {"i": meal_id}).get("meals") or []
        if not result:
            continue
        meal = result[0]
        if not isinstance(meal, dict):
            raise RuntimeError(f"Unexpected TheMealDB lookup response for id {meal_id}: {meal!r}")
        ingredients = get_ingredients(meal)
        source_url = (meal.get("strSource") or "").strip() or f"https://www.themealdb.com/meal/{meal_id}"
        candidate_rows.append({
            "source_id": meal_id,
            "name": (meal.get("strMeal") or "").strip(),
            "source_category": (meal.get("strCategory") or api_category).strip(),
            "source_area": (meal.get("strArea") or "").strip(),
            "suggested_meal_type": suggested_slot,
            "source_url": source_url,
            "themealdb_url": f"https://www.themealdb.com/meal/{meal_id}",
            "image_url": (meal.get("strMealThumb") or "").strip(),
            "instructions": (meal.get("strInstructions") or "").strip(),
            "ingredients": ingredients,
            "raw_ingredients_json": json.dumps(ingredients, ensure_ascii=False),
            "review_status": "needs_manual_mapping_portion_nutrition_price_rights_and_meal_slot_review",
        })
        time.sleep(0.12)

    if len(candidate_rows) != 100:
        raise RuntimeError(f"Expected 100 details, received {len(candidate_rows)}")

    SCRATCH.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "source": SOURCE,
        "api_docs_url": "https://www.themealdb.com/docs_api_guide.php",
        "terms_url": "https://themealdb.com/terms_of_use.php",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "counts_by_suggested_meal_type": {
            slot: sum(row["suggested_meal_type"] == slot for row in candidate_rows)
            for slot in ("sarapan", "makan_siang", "makan_malam")
        },
        "note": "Candidate suggestions only; meal slots are tentative; none are plannable until reviewed.",
        "recipes": candidate_rows,
    }
    (SCRATCH / "themealdb_100_candidates.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fields = ["source_id", "name", "source_category", "source_area", "suggested_meal_type",
              "source_url", "themealdb_url", "image_url", "raw_ingredients_json", "review_status"]
    with (SCRATCH / "themealdb_100_candidates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidate_rows)
    print(json.dumps(snapshot["counts_by_suggested_meal_type"], ensure_ascii=False))
    print(f"Wrote {len(candidate_rows)} candidates to {SCRATCH}")


if __name__ == "__main__":
    main()
