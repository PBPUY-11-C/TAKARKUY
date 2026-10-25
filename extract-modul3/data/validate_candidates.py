#!/usr/bin/env python3
"""Check provenance and internal consistency of review-only dataset indexes."""

import csv
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(relative_path):
    with (ROOT / relative_path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    products = rows("staging/openfoodfacts_products.csv")
    product_mappings = rows("staging/product_ingredient_candidates.csv")
    recipes = rows("staging/recipe_candidates.csv")
    unmatched = rows("staging/mendeley_unmatched_ingredients.csv")
    raw_products = json.loads(
        (ROOT / "raw/openfoodfacts_indonesia_sample.json").read_text(encoding="utf-8")
    )
    mendeley = json.loads(
        (ROOT / "scratch/mendeley_indonesian_recipe_nutrition_v3.json").read_text(encoding="utf-8")
    )
    themealdb = json.loads(
        (ROOT / "scratch/themealdb_100_candidates.json").read_text(encoding="utf-8")
    )
    ingredients = {row["ingredient_code"] for row in rows("processed/ingredients.csv")}

    barcodes = [row["barcode"] for row in products]
    require(len(barcodes) == len(set(barcodes)), "Duplicate staged product barcode")
    require(
        all(code.isdigit() and 8 <= len(code) <= 14 for code in barcodes), "Invalid product barcode"
    )
    require(
        set(barcodes) == {str(row["code"]) for row in raw_products["products"]},
        "Product index differs from raw snapshot",
    )
    for row in products:
        require(row["review_status"] == "candidate_not_for_planner", "Unreviewed product promoted")
        require(row["source_url"].endswith("/" + row["barcode"]), "Product source URL mismatch")
        values = [
            row[field]
            for field in (
                "energy_kcal_100g",
                "protein_g_100g",
                "carbohydrates_g_100g",
                "fat_g_100g",
            )
        ]
        require(
            row["nutrition_complete"] == str(all(values)).lower(),
            "Incorrect nutrition completeness flag",
        )
        require(
            all(math.isfinite(float(value)) and float(value) >= 0 for value in values if value),
            "Invalid packaged-food nutrient",
        )
    mapping_barcodes = [row["barcode"] for row in product_mappings]
    require(
        len(mapping_barcodes) == len(set(mapping_barcodes)), "Duplicate product mapping candidate"
    )
    require(set(mapping_barcodes) <= set(barcodes), "Product mapping without product snapshot")
    require(
        all(row["candidate_ingredient_code"] in ingredients for row in product_mappings),
        "Mapping to unknown ingredient",
    )
    require(
        all(
            row["review_status"] == "needs_human_review_not_recipe_equivalent"
            for row in product_mappings
        ),
        "Unreviewed mapping promoted",
    )

    recipe_ids = [row["candidate_id"] for row in recipes]
    require(len(recipe_ids) == len(set(recipe_ids)), "Duplicate recipe candidate ID")
    require(
        len(recipes) == len(mendeley["data"]) + len(themealdb["recipes"]),
        "Recipe candidate count mismatch",
    )
    require(
        all(
            row["name"] and row["source_url"] and row["review_status"].startswith("candidate_")
            for row in recipes
        ),
        "Incomplete recipe candidate",
    )
    source_counts = Counter(
        "Mendeley" if row["candidate_id"].startswith("MENDELEY-") else "TheMealDB"
        for row in recipes
    )
    require(source_counts["Mendeley"] == len(mendeley["data"]), "Mendeley recipe count mismatch")
    require(
        source_counts["TheMealDB"] == len(themealdb["recipes"]), "TheMealDB recipe count mismatch"
    )
    require(
        all(row["instructions"] for row in recipes if row["candidate_id"].startswith("MENDELEY-")),
        "Missing Mendeley instructions",
    )

    source_terms = Counter(
        " ".join(term.casefold().split())
        for recipe in mendeley["data"]
        for term in recipe.get("bahan_tidak_ditemukan", [])
        if isinstance(term, str) and term.strip()
    )
    staged_terms = {row["raw_ingredient_name"]: int(row["recipe_occurrences"]) for row in unmatched}
    require(len(staged_terms) == len(unmatched), "Duplicate unmatched ingredient term")
    require(staged_terms == source_terms, "Unmatched ingredient index differs from raw source")
    require(
        all(
            row["review_status"] == "needs_deduplication_and_nutrition_source" for row in unmatched
        ),
        "Unmatched term promoted",
    )

    print("VALID candidate indexes (not planner-ready):")
    print(
        f"  packaged products: {len(products)}; complete reported nutrients: {sum(row['nutrition_complete'] == 'true' for row in products)}"
    )
    print(f"  product-to-ingredient proposals: {len(product_mappings)}")
    print(
        f"  recipe candidates: {len(recipes)} (Mendeley {source_counts['Mendeley']}, TheMealDB {source_counts['TheMealDB']})"
    )
    print(
        f"  unmatched ingredient terms: {len(unmatched)} ({sum(source_terms.values())} occurrences)"
    )


if __name__ == "__main__":
    main()
