#!/usr/bin/env python3
"""Collect and rank 100 Western home-style TheMealDB recipe candidates.

This writes a review snapshot only. It never promotes candidates into the
active catalog: localized ingredients, halal/source-use review, quantities,
prices, and nutrition must still pass data/build_final.py's curation gate.
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

if __package__:
    from .recipe_estimation import resolve_ingredient
else:
    from recipe_estimation import resolve_ingredient

ROOT = Path(__file__).resolve().parent
SCRATCH = ROOT / "scratch"
BASE = "https://www.themealdb.com/api/json/v1/1"
LIMIT = 100
DELAY_SECONDS = 1.0
MAX_DETAIL_LOOKUPS = 320
SNAPSHOT_PATH = SCRATCH / "themealdb_western_100_candidates.json"
CSV_PATH = SCRATCH / "themealdb_western_100_candidates.csv"
CSV_FIELDS = [
    "source_id", "name", "source_area", "source_category", "source_url",
    "themealdb_url", "image_url", "image_credit", "local_mapping_coverage",
    "has_restricted_content", "local_fit_score", "suggested_local_mappings_json",
    "unmapped_ingredients_json", "localization_review_notes", "review_status",
]

# Areas with recognizable Western cuisines; keep this list explicit so that
# unrelated areas do not leak into a “Western” collection.
WESTERN_AREAS = {
    "american", "australian", "british", "canadian", "croatian", "dutch",
    "french", "greek", "irish", "italian", "polish", "spanish",
}
HOME_STYLE_CATEGORIES = {
    "beef", "breakfast", "chicken", "miscellaneous", "pasta", "seafood",
    "vegetarian", "vegan",
}
RESTRICTED_TERMS = {
    "bacon", "ham", "lard", "pancetta", "pork", "prosciutto", "wine", "beer",
    "brandy", "sherry", "rum", "vodka", "whisky", "whiskey",
}


def get_json(path, params=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "TAKARKUY educational recipe catalog/1.0"})
    last_error = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 3:
                break
            time.sleep(DELAY_SECONDS * (attempt + 1))
    raise RuntimeError(f"Gagal mengambil {url}: {last_error}") from last_error


def meal_ingredients(meal):
    rows = []
    for index in range(1, 21):
        ingredient = (meal.get(f"strIngredient{index}") or "").strip()
        measure = (meal.get(f"strMeasure{index}") or "").strip()
        if ingredient:
            rows.append({"ingredient": ingredient, "measure": measure})
    return rows


def area_key(value):
    return " ".join((value or "").casefold().split())


def evaluate_local_fit(meal, ingredients):
    mapped = []
    unmapped = []
    restricted = []
    for row in ingredients:
        name = row["ingredient"]
        code = resolve_ingredient(name, "en")
        if code:
            mapped.append({**row, "suggested_ingredient_code": code})
        else:
            unmapped.append(name)
        if any(term in name.casefold().split() for term in RESTRICTED_TERMS):
            restricted.append(name)
    total = len(ingredients)
    coverage = len(mapped) / total if total else 0.0
    instructions = (meal.get("strInstructions") or "").casefold()
    restricted_instructions = sorted(
        term for term in RESTRICTED_TERMS if term in instructions
    )
    flags = []
    if restricted:
        flags.append("bahan sumber perlu substitusi atau dikeluarkan: " + ", ".join(restricted))
    if restricted_instructions:
        flags.append(
            "langkah menyebut alkohol/bahan terbatas: " + ", ".join(restricted_instructions)
        )
    if unmapped:
        flags.append("bahan belum punya padanan lokal: " + ", ".join(unmapped))
    if not flags:
        flags.append("tetap perlu review takaran, harga, gizi, halal, dan sumber")
    has_restricted_content = bool(restricted or restricted_instructions)
    fit_score = coverage - (0.35 if has_restricted_content else 0.0)
    return coverage, mapped, unmapped, "; ".join(flags), has_restricted_content, fit_score


def write_csv(recipes):
    """Write the compact review index without re-fetching API data."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in recipes:
            writer.writerow({
                **row,
                "suggested_local_mappings_json": json.dumps(
                    row.get("suggested_local_mappings", []), ensure_ascii=False
                ),
                "unmapped_ingredients_json": json.dumps(
                    row.get("unmapped_ingredients", []), ensure_ascii=False
                ),
            })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-existing",
        action="store_true",
        help="Regenerate the CSV from the existing JSON snapshot without API requests.",
    )
    args = parser.parse_args()
    if args.export_existing:
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        recipes = snapshot.get("recipes", [])
        if len(recipes) != LIMIT:
            raise RuntimeError(f"Snapshot harus berisi {LIMIT} resep; ditemukan {len(recipes)}.")
        write_csv(recipes)
        print(f"CSV diperbarui dari snapshot lokal: {CSV_PATH}", flush=True)
        return

    print("Mengambil daftar area TheMealDB...", flush=True)
    areas = get_json("list.php", {"a": "list"}).get("meals") or []
    supported_areas = [
        row["strArea"] for row in areas
        if area_key(row.get("strArea")) in WESTERN_AREAS
    ]
    if not supported_areas:
        raise RuntimeError("TheMealDB tidak mengembalikan area Barat yang didukung.")

    # Keep this expansion additive: do not select IDs already present in the
    # broad snapshot or already under review in the curation table.
    excluded_source_ids = set()
    broad_snapshot = SCRATCH / "themealdb_100_candidates.json"
    if broad_snapshot.exists():
        excluded_source_ids.update(
            str(row.get("source_id", "")).strip()
            for row in json.loads(broad_snapshot.read_text(encoding="utf-8")).get("recipes", [])
        )
    curation_path = ROOT / "mapping" / "themealdb_recipe_curation.csv"
    if curation_path.exists():
        with curation_path.open(newline="", encoding="utf-8-sig") as stream:
            excluded_source_ids.update(
                row.get("source_id", "").strip() for row in csv.DictReader(stream)
            )
    excluded_source_ids.discard("")

    # Candidate IDs are collected from selected Western areas and common home
    # meal categories, then deduplicated before detail lookups.
    ids = {}
    for area in supported_areas:
        print(f"Mencari resep area {area}...", flush=True)
        for result in get_json("filter.php", {"a": area}).get("meals") or []:
            source_id = str(result["idMeal"])
            if source_id not in excluded_source_ids:
                ids.setdefault(source_id, {"area": area, "name": result.get("strMeal", "")})
        time.sleep(DELAY_SECONDS)

    # Category filters add western staples whose area metadata may be absent.
    print(f"{len(ids)} ID ditemukan dari area. Mengambil daftar kategori...", flush=True)
    categories = get_json("list.php", {"c": "list"}).get("meals") or []
    western_categories = [
        row["strCategory"] for row in categories
        if row.get("strCategory", "").casefold() in HOME_STYLE_CATEGORIES
    ]
    for category in western_categories:
        print(f"Menambah kandidat kategori {category}...", flush=True)
        for result in get_json("filter.php", {"c": category}).get("meals") or []:
            source_id = str(result["idMeal"])
            if source_id not in excluded_source_ids:
                ids.setdefault(source_id, {"area": "", "name": result.get("strMeal", "")})
        time.sleep(DELAY_SECONDS)

    # Area-filtered IDs come first (215 in the current free API snapshot).
    # Inspect all of them, plus a bounded category-filter fallback, because
    # some area results are desserts/other categories excluded from this set.
    details = []
    detail_ids = list(ids.items())[:MAX_DETAIL_LOOKUPS]
    print(f"Memeriksa detail maksimal {len(detail_ids)} resep (dengan jeda API)...", flush=True)
    for index, (meal_id, listing) in enumerate(detail_ids, start=1):
        if index == 1 or index % 10 == 0 or index == len(detail_ids):
            print(f"Detail resep: {index}/{len(detail_ids)}", flush=True)
        found = get_json("lookup.php", {"i": meal_id}).get("meals") or []
        if found:
            meal = found[0]
            source_area = (meal.get("strArea") or listing["area"]).strip()
            source_category = (meal.get("strCategory") or "").strip()
            # Do not classify an unknown-area meal as Western solely because it
            # happened to appear in a broad category filter.
            if area_key(source_area) not in WESTERN_AREAS:
                time.sleep(DELAY_SECONDS)
                continue
            if source_category.casefold() not in HOME_STYLE_CATEGORIES:
                time.sleep(DELAY_SECONDS)
                continue
            ingredients = meal_ingredients(meal)
            coverage, mapped, unmapped, notes, has_restricted_content, fit_score = evaluate_local_fit(
                meal, ingredients
            )
            details.append({
                "source_id": meal_id,
                "name": (meal.get("strMeal") or "").strip(),
                "source_area": source_area,
                "source_category": source_category,
                "source_url": (meal.get("strSource") or "").strip()
                    or f"https://www.themealdb.com/meal/{meal_id}",
                "themealdb_url": f"https://www.themealdb.com/meal/{meal_id}",
                "image_url": (meal.get("strMealThumb") or "").strip(),
                "image_credit": (meal.get("strCreativeCommons") or "").strip(),
                "instructions": (meal.get("strInstructions") or "").strip(),
                "raw_ingredients": ingredients,
                "suggested_local_mappings": mapped,
                "unmapped_ingredients": unmapped,
                "local_mapping_coverage": round(coverage, 4),
                "has_restricted_content": has_restricted_content,
                "local_fit_score": round(fit_score, 4),
                "localization_review_notes": notes,
                "review_status": "candidate_only_manual_localization_and_rights_review_required",
            })
        time.sleep(DELAY_SECONDS)

    details.sort(
        key=lambda row: (-row["local_fit_score"], -row["local_mapping_coverage"], row["source_area"], row["name"].casefold())
    )
    if len(details) < LIMIT:
        raise RuntimeError(
            f"Hanya ditemukan {len(details)} resep Barat yang memenuhi filter dari API. "
            "Tidak menulis snapshot parsial; perluas area/kategori atau gunakan akses TheMealDB yang sesuai."
        )
    selected = details[:LIMIT]
    print("Menulis snapshot kandidat 100 resep...", flush=True)
    snapshot = {
        "source": "TheMealDB API; candidate references only",
        "api_docs_url": "https://www.themealdb.com/docs_api_guide.php",
        "terms_url": "https://themealdb.com/terms_of_use.php",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "selection": "100 additional, non-duplicate Western-area home-style candidates ranked by exact local ingredient mapping coverage",
        "counts_by_area": {
            area: sum(row["source_area"] == area for row in selected)
            for area in sorted({row["source_area"] for row in selected})
        },
        "note": (
            "Not active/plannable. Suggested ingredient codes are exact alias matches only, "
            "not approved substitutions, measured quantities, nutrition, price, or halal review. "
            "Promote only after per-ingredient review in mapping/themealdb_recipe_curation.csv."
        ),
        "recipes": selected,
    }
    SCRATCH.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(selected)
    print(json.dumps({"selected": len(selected), "by_area": snapshot["counts_by_area"]}, ensure_ascii=False))
    print(f"Wrote review-only candidates to {SCRATCH}")


if __name__ == "__main__":
    main()
