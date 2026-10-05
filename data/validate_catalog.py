#!/usr/bin/env python3
"""Validate the eight deliverable tables and the Django fixture."""

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NON_HALAL_TERMS = re.compile(
    r"\b(babi|pork|bacon|ham|lard|angciu|arak|ciu|mirin|sake|wine|rum|bir|beer|brandy|whisky)\b",
    re.IGNORECASE,
)
FILES = {
    "ingredients": "processed/ingredients.csv",
    "ingredient_prices": "processed/ingredient_prices.csv",
    "ingredient_shelf_life": "processed/ingredient_shelf_life.csv",
    "recipes": "processed/recipes.csv",
    "recipe_ingredients": "processed/recipe_ingredients.csv",
    "recipe_tags": "processed/recipe_tags.csv",
    "ingredient_aliases": "mapping/ingredient_aliases.csv",
    "unit_conversions": "mapping/unit_conversions.csv",
}
KEYS = {
    "ingredients": "ingredient_code",
    "ingredient_prices": "price_code",
    "ingredient_shelf_life": "shelf_life_code",
    "recipes": "recipe_code",
    "recipe_ingredients": "recipe_ingredient_code",
    "recipe_tags": "recipe_tag_code",
    "ingredient_aliases": "alias_code",
    "unit_conversions": "conversion_code",
}
tables = {}
for name, rel in FILES.items():
    with open(ROOT / rel, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 80, (name, "kurang dari 80 baris", len(rows))
    key = KEYS[name]
    assert len({r[key] for r in rows}) == len(rows), (name, "primary key ganda")
    tables[name] = rows

# Stable IDs alone do not prevent the same relation from being emitted twice
# under different IDs. Reject redundant relations without merging food variants.
for name, fields in {
    "recipe_ingredients": ("recipe_code", "ingredient_code"),
    "recipe_tags": ("recipe_code", "tag"),
    "ingredient_aliases": ("source", "raw_name", "ingredient_code"),
    "unit_conversions": ("ingredient_code", "unit"),
}.items():
    values = [tuple(row[field] for field in fields) for row in tables[name]]
    assert len(values) == len(set(values)), (name, "relasi semantik ganda")

ingredient = {r["ingredient_code"]: r for r in tables["ingredients"]}
recipe = {r["recipe_code"]: r for r in tables["recipes"]}
for name in (
    "ingredient_prices",
    "ingredient_shelf_life",
    "recipe_ingredients",
    "ingredient_aliases",
    "unit_conversions",
):
    for row in tables[name]:
        assert row["ingredient_code"] in ingredient, (name, row)
for name in ("recipe_ingredients", "recipe_tags"):
    for row in tables[name]:
        assert row["recipe_code"] in recipe, (name, row)
for row in tables["ingredient_prices"]:
    assert all(
        math.isfinite(float(row[k])) and float(row[k]) > 0 for k in ("price_rupiah", "quantity")
    )
    assert row["region"] and row["recorded_at"] and row["source_url"]
    assert row["source_license"]
    if row["price_status"] == "retail_reference":
        assert row["region"] != "Kabupaten Garut" and not row["source_recorded_at"]
    else:
        assert row["source_recorded_at"]
for row in tables["ingredient_shelf_life"]:
    assert 0 < int(row["min_days"]) <= int(row["max_days"])
    assert 0 < int(row["warning_days"]) <= int(row["min_days"])
    assert row["source_url"] and row["source_license"]
    assert row["shelf_life_status"] == "referensi_perlu_verifikasi_lokal"
for row in tables["unit_conversions"]:
    if row["conversion_status"] == "unusable":
        assert not row["gram_equivalent"]
    else:
        assert math.isfinite(float(row["gram_equivalent"])) and float(row["gram_equivalent"]) > 0

prices = defaultdict(list)
for p in tables["ingredient_prices"]:
    prices[p["ingredient_code"]].append(p)
links = defaultdict(list)
for r in tables["recipe_ingredients"]:
    links[r["recipe_code"]].append(r)
tags = defaultdict(set)
for r in tables["recipe_tags"]:
    tags[r["recipe_code"]].add(r["tag"])
ready = [r for r in tables["recipes"] if r["is_plannable"] == "true"]
assert len(ready) >= 15
ready_names = [r["name"].casefold() for r in ready]
assert len(ready_names) == len(set(ready_names)), "nama resep siap hitung harus unik"
for r in ready:
    assert int(r["base_servings"]) > 0 and r["meal_type"] in (
        "sarapan",
        "makan_siang",
        "makan_malam",
    )
    assert not r["missing_data_reason"]
    if r["recipe_code"].startswith("RCP-MDL-"):
        metadata = json.loads(r["raw_ingredients"])
        assert not r["instructions"], (
            r["recipe_code"],
            "teks belum ditinjau tidak boleh dipublikasikan",
        )
        assert metadata["instructions_status"] == "withheld_pending_rights_review"
        assert metadata["license"] == "CC BY 4.0" and metadata["attribution"]
    else:
        assert r["instructions"]
    assert links[r["recipe_code"]] and "halal" in tags[r["recipe_code"]]
    # TAKARKUY only plans halal menus; a halal tag must not hide such an ingredient.
    non_halal = [
        ingredient[x["ingredient_code"]]["name"]
        for x in links[r["recipe_code"]]
        if NON_HALAL_TERMS.search(ingredient[x["ingredient_code"]]["name"])
    ]
    assert not non_halal, (r["recipe_code"], non_halal)
    for x in links[r["recipe_code"]]:
        assert x["unit"] == "g" and math.isfinite(float(x["quantity"])) and float(x["quantity"]) > 0
        assert x["quantity_status"] in ("curated", "estimated")
        if x["quantity_status"] == "estimated":
            audit = json.loads(x["raw_text"])
            assert audit and all(a["estimation_note"] and a["rules_version"] for a in audit)
        assert all(
            ingredient[x["ingredient_code"]][n + "_per_100g"] != ""
            and math.isfinite(float(ingredient[x["ingredient_code"]][n + "_per_100g"]))
            and float(ingredient[x["ingredient_code"]][n + "_per_100g"]) >= 0
            for n in ("calories", "protein", "carbs", "fat")
        )
        assert any(
            p["unit"] == "kg"
            and (
                p["region"] == "Kabupaten Garut"
                and p["price_status"] == "published"
                or p["price_status"] == "retail_reference"
            )
            for p in prices[x["ingredient_code"]]
        )

fixture = json.loads((ROOT / "fixtures/catalog_seed.json").read_text(encoding="utf-8"))
assert len(fixture) == sum(map(len, tables.values()))
assert len({(x["model"], x["pk"]) for x in fixture}) == len(fixture)
assert (ROOT / "fixtures/catalog_seed.json").read_bytes() == (
    ROOT.parent / "apps/catalog/fixtures/catalog_seed.json"
).read_bytes()
for x in fixture:
    assert x["model"].startswith("catalog.") and isinstance(x["fields"], dict)

with open(ROOT / "staging/recipe_quantity_estimates.csv", newline="", encoding="utf-8") as handle:
    audit = list(csv.DictReader(handle))
assert len({(r["recipe_code"], r["ingredient_position"]) for r in audit}) == len(audit)
assert {r["recipe_code"] for r in audit} == {
    r["recipe_code"]
    for r in tables["recipes"]
    if r["recipe_code"].startswith(("RCP-TMDB-", "RCP-KAGGLE-"))
}
for row in audit:
    assert row["recipe_code"] in recipe and row["estimation_note"] and row["recipe_source_url"]
    if row["status"] == "estimated":
        assert (
            row["ingredient_code"]
            and math.isfinite(float(row["quantity_g"]))
            and float(row["quantity_g"]) > 0
        )
        assert math.isfinite(float(row["purchase_quantity_g"])) and float(
            row["purchase_quantity_g"]
        ) >= float(row["quantity_g"])

print("VALID:")
for name, rows in tables.items():
    print(f"  {name}: {len(rows)} baris")
print(f"  resep siap dihitung: {len(ready)}")
print(f"  fixture Django: {len(fixture)} objek")
counts = json.loads((ROOT / "dataset_counts.json").read_text(encoding="utf-8"))
for name, relative_path in FILES.items():
    assert counts[relative_path] == len(tables[name]), (name, "hitungan dokumentasi tidak sinkron")
assert counts["plannable_recipes"] == len(ready)
assert counts["ingredients_with_four_macros"] == sum(
    all(row[n + "_per_100g"] != "" for n in ("calories", "protein", "carbs", "fat"))
    for row in tables["ingredients"]
)
