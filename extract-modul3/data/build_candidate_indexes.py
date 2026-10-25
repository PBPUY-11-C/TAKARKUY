#!/usr/bin/env python3
"""Index licensed local recipe candidates without promoting them into the planner."""

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGING = ROOT / "staging"
MENDELEY_URL = "https://data.mendeley.com/datasets/8b4ztns76h/3"
THEMEALDB_URL = "https://www.themealdb.com/docs_api_guide.php"
RECIPE_FIELDS = (
    "candidate_id",
    "name",
    "source",
    "source_url",
    "source_license",
    "portions_as_reported",
    "cooking_minutes_as_reported",
    "instructions",
    "ingredients_as_reported",
    "calories_total_as_reported",
    "protein_total_g_as_reported",
    "carbs_total_g_as_reported",
    "fat_total_g_as_reported",
    "review_status",
)
TERM_FIELDS = (
    "raw_ingredient_name",
    "recipe_occurrences",
    "source",
    "source_url",
    "review_status",
)
PRODUCT_MAPPING_FIELDS = (
    "barcode",
    "product_name",
    "candidate_ingredient_code",
    "candidate_ingredient_name",
    "match_basis",
    "source_url",
    "review_status",
)


def write_csv(path, fieldnames, rows):
    STAGING.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    mendeley = json.loads(
        (ROOT / "scratch" / "mendeley_indonesian_recipe_nutrition_v3.json").read_text(
            encoding="utf-8"
        )
    )
    themealdb = json.loads(
        (ROOT / "scratch" / "themealdb_100_candidates.json").read_text(encoding="utf-8")
    )
    recipes = []
    unmatched = Counter()
    source_ids = set()

    for recipe in mendeley["data"]:
        candidate_id = f"MENDELEY-{int(recipe['id']):04d}"
        if candidate_id in source_ids:
            raise ValueError(f"Duplicate recipe ID: {candidate_id}")
        source_ids.add(candidate_id)
        recipes.append(
            {
                "candidate_id": candidate_id,
                "name": recipe.get("title", "").strip(),
                "source": "Mendeley Data, Purwanto et al., version 3 (2026)",
                "source_url": MENDELEY_URL,
                "source_license": "CC BY 4.0; attribution required",
                "portions_as_reported": recipe.get("portion", ""),
                "cooking_minutes_as_reported": recipe.get("time_to_cook", ""),
                "instructions": recipe.get("how_to_cook", "").strip(),
                "ingredients_as_reported": recipe.get("ingredient", "").strip(),
                "calories_total_as_reported": recipe.get("total_calories", ""),
                "protein_total_g_as_reported": recipe.get("total_protein", ""),
                "carbs_total_g_as_reported": recipe.get("total_carbohydrate", ""),
                "fat_total_g_as_reported": recipe.get("total_fat", ""),
                "review_status": "candidate_unverified_ingredient_mapping_and_nutrition",
            }
        )
        for term in recipe.get("bahan_tidak_ditemukan", []):
            if isinstance(term, str) and term.strip():
                unmatched[" ".join(term.casefold().split())] += 1

    for recipe in themealdb["recipes"]:
        candidate_id = f"THEMEALDB-{recipe['source_id']}"
        if candidate_id in source_ids:
            raise ValueError(f"Duplicate recipe ID: {candidate_id}")
        source_ids.add(candidate_id)
        recipes.append(
            {
                "candidate_id": candidate_id,
                "name": recipe.get("name", "").strip(),
                "source": "TheMealDB API",
                "source_url": recipe.get("themealdb_url", "") or THEMEALDB_URL,
                "source_license": "API access for development; source-use review required",
                "portions_as_reported": "",
                "cooking_minutes_as_reported": "",
                "instructions": "",
                "ingredients_as_reported": "",
                "calories_total_as_reported": "",
                "protein_total_g_as_reported": "",
                "carbs_total_g_as_reported": "",
                "fat_total_g_as_reported": "",
                "review_status": "candidate_source_rights_portions_ingredients_nutrition_unverified",
            }
        )

    write_csv(STAGING / "recipe_candidates.csv", RECIPE_FIELDS, recipes)
    terms = (
        {
            "raw_ingredient_name": name,
            "recipe_occurrences": count,
            "source": "Mendeley Data, Purwanto et al., version 3 (2026)",
            "source_url": MENDELEY_URL,
            "review_status": "needs_deduplication_and_nutrition_source",
        }
        for name, count in sorted(unmatched.items(), key=lambda pair: (-pair[1], pair[0]))
    )
    write_csv(STAGING / "mendeley_unmatched_ingredients.csv", TERM_FIELDS, terms)

    product_path = STAGING / "openfoodfacts_products.csv"
    product_mappings = []
    if product_path.exists():
        with product_path.open(newline="", encoding="utf-8") as stream:
            for product in csv.DictReader(stream):
                # An item is only a *candidate* for a generic cooking ingredient.
                # A packaged product's seasoning and nutrient profile must not be
                # silently substituted for plain noodles in a meal calculation.
                name = product["product_name"]
                looks_like_noodles = bool(re.search(r"\b(mi|mie|noodles?|indomie)\b", name, re.I))
                if not looks_like_noodles:
                    continue
                product_mappings.append(
                    {
                        "barcode": product["barcode"],
                        "product_name": name,
                        "candidate_ingredient_code": "ING-MIE-INSTAN",
                        "candidate_ingredient_name": "Mie Instan",
                        "match_basis": "product_name_keyword_only",
                        "source_url": product["source_url"],
                        "review_status": "needs_human_review_not_recipe_equivalent",
                    }
                )
    write_csv(
        STAGING / "product_ingredient_candidates.csv", PRODUCT_MAPPING_FIELDS, product_mappings
    )
    print(
        f"Indexed {len(recipes)} recipe candidates, {len(unmatched)} unmatched "
        f"ingredient terms, and {len(product_mappings)} product mappings for review"
    )


if __name__ == "__main__":
    main()
