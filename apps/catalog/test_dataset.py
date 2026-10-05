"""Regression checks for catalog estimates, promotion and stable identifiers."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from data import build_final, fetch_themealdb_candidates
from data.recipe_estimation import (
    estimate_candidates,
    estimate_quantity,
    ingredient_components,
    is_section_heading,
    replace_recipe,
    resolve_ingredient,
    unique_rows,
)

from .models import Ingredient, Recipe, RecipeIngredient, RecipeTag


class FixtureDiscoveryTests(TestCase):
    fixtures = ["catalog_seed.json"]

    def test_django_loads_the_single_canonical_fixture_by_name(self):
        fixture_dir = settings.BASE_DIR / "data" / "fixtures"
        self.assertIn(fixture_dir, settings.FIXTURE_DIRS)
        self.assertTrue((fixture_dir / "catalog_seed.json").is_file())
        self.assertFalse((settings.BASE_DIR / "apps/catalog/fixtures/catalog_seed.json").exists())
        records = json.loads((fixture_dir / "catalog_seed.json").read_text(encoding="utf-8"))
        self.assertEqual(
            Ingredient.objects.count(),
            sum(row["model"] == "catalog.ingredient" for row in records),
        )
        self.assertEqual(
            Recipe.objects.count(), sum(row["model"] == "catalog.recipe" for row in records)
        )


class DatasetEstimationTests(SimpleTestCase):
    def test_themealdb_selection_keeps_source_ids_unique_across_categories(self):
        pool = {
            "Chicken": [("1", "Chicken"), ("2", "Chicken")],
            "Miscellaneous": [("1", "Miscellaneous"), ("3", "Miscellaneous")],
        }
        selected = fetch_themealdb_candidates.pick_balanced(pool, 3)
        self.assertEqual([row[0] for row in selected], ["1", "2", "3"])

    @patch("data.fetch_themealdb_candidates.time.sleep")
    def test_themealdb_fetch_exports_compact_csv_and_full_json(self, sleep):
        categories = [
            "Beef",
            "Chicken",
            "Seafood",
            "Vegetarian",
            "Vegan",
            "Pasta",
            "Miscellaneous",
            "Lamb",
            "Goat",
        ]

        def response(path, params=None):
            if path == "lookup.php":
                return {
                    "meals": [
                        {
                            "idMeal": params["i"],
                            "strMeal": "Test Recipe",
                            "strCategory": "Chicken",
                            "strInstructions": "Cook.",
                            "strIngredient1": "Chicken",
                            "strMeasure1": "100 g",
                        }
                    ]
                }
            if params.get("i") == "banana":
                return {"meals": []}
            start, count = (
                (1, 20)
                if params["c"] == "Breakfast"
                else (100 + categories.index(params["c"]) * 10, 10)
            )
            return {
                "meals": [
                    {"idMeal": str(number), "strMeal": "Test"}
                    for number in range(start, start + count)
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            with (
                patch.object(fetch_themealdb_candidates, "SCRATCH", scratch),
                patch.object(fetch_themealdb_candidates, "get_json", side_effect=response),
            ):
                fetch_themealdb_candidates.main()
            snapshot = json.loads((scratch / "themealdb_100_candidates.json").read_text())
            rows = build_final.read_csv(scratch / "themealdb_100_candidates.csv")
            self.assertEqual(len(rows), 100)
            self.assertEqual(len({row["source_id"] for row in rows}), 100)
            self.assertEqual(snapshot["recipes"][0]["instructions"], "Cook.")
            self.assertNotIn("instructions", rows[0])

    def test_common_unit_abbreviations_are_equivalent(self):
        for short, long, code in [
            ("bh", "buah", "ING-WORTEL"),
            ("btr", "butir", "ING-TELUR-AYAM-BROILER"),
            ("btg", "batang", "ING-DAUN-BAWANG"),
            ("lmbr", "lembar", "ING-DAUN-SALAM"),
            ("tbs", "tbsp", "ING-MINYAK-ZAITUN"),
            ("tblsp", "tbsp", "ING-MINYAK-ZAITUN"),
            ("grm", "g", "ING-DAGING-AYAM-BROILER"),
            ("cc", "ml", "ING-SANTAN"),
        ]:
            with self.subTest(short=short):
                self.assertEqual(
                    estimate_quantity("2 " + short, code)[0],
                    estimate_quantity("2 " + long, code)[0],
                )

    def test_headings_are_not_food_and_specific_forms_win(self):
        for text in (
            "Pelapis:",
            "Bahan Saus",
            "Bumbu dihaluskan :",
            "🐔 Bahan Utama:",
            "Bumbu ungkep :",
        ):
            self.assertTrue(is_section_heading(text), text)
        self.assertFalse(is_section_heading("Bumbu ayam goreng jadi"))
        for raw, code in [
            ("3 sdm saus tomat", "ING-SAUS-TOMAT"),
            ("1 sdt minyak wijen", "ING-MINYAK-WIJEN"),
            ("1/4 sdt kunyit bubuk", "ING-KUNYIT-BUBUK"),
            ("2 btr bawang bombai", "ING-BAWANG-BOMBAY"),
            ("4 lbr daun jeruk, buang tulangnya", "ING-DAUN-JERUK"),
            ("secukupnya Tepung roti/ tepung panir", "ING-TEPUNG-PANIR"),
        ]:
            self.assertEqual(resolve_ingredient(raw, "id"), code, raw)
        self.assertIsNone(resolve_ingredient("kaldu jamur", "id"))
        self.assertNotEqual(
            resolve_ingredient("Bay Leaf", "en"), resolve_ingredient("daun salam", "id")
        )

    def test_compound_lists_preserve_unknowns_and_shared_amounts(self):
        parts = ingredient_components(
            "Secukupnya garam, gula dan misteri", "Secukupnya garam, gula dan misteri", "id"
        )
        self.assertEqual(len(parts), 3)
        self.assertIn("misteri", [p[0] for p in parts])
        raw = "1 sdm garam dan gula"
        self.assertEqual(ingredient_components(raw, raw, "id"), [(raw, raw, "")])
        parts = ingredient_components("1 sdm butter / margarin", "1 sdm butter / margarin", "id")
        self.assertEqual(parts[0][0], "1 sdm margarin")
        self.assertIn("alternatif sumber", parts[0][2])

    def test_split_audit_retains_source_and_unknown_component_blocks(self):
        original = "Secukupnya garam, gula dan misteri"
        candidate = dict(
            code="RCP-KAGGLE-X",
            name="Test",
            language="id",
            source_url="https://cookpad.com/resep/x",
            category="Chicken",
            instructions="Masak.",
            ingredients=[{"ingredient": original, "measure": original}],
        )
        item = {n + "_per_100g": "1" for n in ("calories", "protein", "carbs", "fat")}
        items = {code: item for code in ("ING-GARAM", "ING-GULA-PASIR-DALAM-NEGERI")}
        with patch("data.recipe_estimation.source_candidates", return_value=[candidate]):
            updates, audit = estimate_candidates(Path("."), items, {code: {} for code in items})
        self.assertEqual({a["raw_ingredient"] for a in audit}, {original})
        self.assertEqual({a["ingredient_position"] for a in audit}, {"1.1", "1.2", "1.3"})
        self.assertEqual(updates[0]["is_plannable"], "false")
        self.assertIn("misteri", updates[0]["missing_data_reason"])

    def test_whole_chicken_audit_separates_purchase_from_edible_mass(self):
        original = "1 ekor ayam"
        candidate = dict(
            code="RCP-KAGGLE-X",
            name="Test",
            language="id",
            source_url="https://cookpad.com/resep/x",
            category="Chicken",
            instructions="Masak.",
            ingredients=[{"ingredient": original, "measure": original}],
        )
        item = {n + "_per_100g": "1" for n in ("calories", "protein", "carbs", "fat")}
        with patch("data.recipe_estimation.source_candidates", return_value=[candidate]):
            updates, audit = estimate_candidates(
                Path("."), {"ING-DAGING-AYAM-BROILER": item}, {"ING-DAGING-AYAM-BROILER": {}}
            )
        self.assertEqual(updates[0]["is_plannable"], "true")
        self.assertEqual(updates[0]["quantities"]["ING-DAGING-AYAM-BROILER"], 600)
        self.assertEqual(updates[0]["purchase_quantities"]["ING-DAGING-AYAM-BROILER"], 1000)
        self.assertEqual(audit[0]["purchase_quantity_g"], 1000)

    def test_standard_mass_does_not_confuse_indonesian_ons_with_ounces(self):
        self.assertAlmostEqual(estimate_quantity("8 oz", "ING-DAGING-SAPI")[0], 226.796185)
        self.assertEqual(estimate_quantity("2 ons", "ING-DAGING-SAPI")[0], 200)
        self.assertEqual(estimate_quantity("1 1/2 kg", "ING-DAGING-SAPI")[0], 1500)
        self.assertEqual(estimate_quantity("¼ kg", "ING-DAGING-SAPI")[0], 250)
        self.assertIsNone(estimate_quantity("8 fl oz", "ING-DAGING-SAPI")[0])
        self.assertIsNone(estimate_quantity("1/0 kg ayam", "ING-DAGING-AYAM-BROILER", "id")[0])

    def test_household_mass_is_ingredient_specific_and_estimated(self):
        self.assertEqual(estimate_quantity("3 cloves", "ING-BAWANG-PUTIH")[0], 9)
        self.assertEqual(estimate_quantity("2 butir", "ING-TELUR-AYAM-BROILER", "id")[0], 100)
        flour = estimate_quantity("1 cup", "ING-TEPUNG-TERIGU-CURAH")
        sugar = estimate_quantity("1 cup", "ING-GULA-PASIR-DALAM-NEGERI")
        self.assertEqual(flour[0], 120)
        self.assertEqual(sugar[0], 198)
        salt = estimate_quantity("to taste", "ING-GARAM")
        self.assertEqual(salt[0], 3)
        self.assertIn("asumsi TAKARKUY", salt[1])
        self.assertIsNone(estimate_quantity("1 pack", "ING-TEPUNG-TERIGU-CURAH")[0])
        self.assertIsNone(estimate_quantity("1 bungkus ayam", "ING-DAGING-AYAM-BROILER", "id")[0])

    def test_prepared_food_and_compound_ingredients_are_not_misclassified(self):
        self.assertIsNone(resolve_ingredient("ayam (yg sudah direbus sebelumnya)", "id"))
        self.assertIsNone(resolve_ingredient("tepung bumbu ayam", "id"))
        self.assertIsNone(resolve_ingredient("1 bks bumbu ayam goreng sajiku", "id"))
        self.assertIsNone(resolve_ingredient("secukupnya garam dan gula", "id"))
        self.assertIsNone(resolve_ingredient("Secukupnya cabe rawit merah dan bwg putih", "id"))
        self.assertEqual(
            resolve_ingredient("1 butir telur ayam (kocok)", "id"), "ING-TELUR-AYAM-BROILER"
        )
        self.assertNotEqual(resolve_ingredient("Basil", "en"), resolve_ingredient("kemangi", "id"))
        self.assertIsNone(resolve_ingredient("Mushrooms", "en"))

    def test_exact_duplicate_collapses_but_conflicting_ids_raise(self):
        first = {"pk": "RCP-1", "name": "A"}
        self.assertEqual(unique_rows([first, first.copy()], "pk"), [first])
        with self.assertRaisesRegex(ValueError, "isi berbeda"):
            unique_rows([first, {"pk": "RCP-1", "name": "B"}], "pk")

    def test_promotion_replaces_metadata_at_same_id(self):
        recipes = [{"recipe_code": "RCP-TMDB-1", "is_plannable": "false"}]
        replacement = {"recipe_code": "RCP-TMDB-1", "is_plannable": "true"}
        replace_recipe(recipes, replacement)
        replace_recipe(recipes, replacement)
        self.assertEqual(recipes, [replacement])

    def test_every_source_ingredient_is_audited_and_unknown_food_blocks(self):
        candidate = dict(
            code="RCP-TMDB-1",
            name="Test",
            language="en",
            source_url="https://www.themealdb.com/meal/1",
            category="Beef",
            meal_type="makan_siang",
            instructions="Cook.",
            ingredients=[
                {"ingredient": "Beef", "measure": "1 kg"},
                {"ingredient": "Beef", "measure": "100 g"},
                {"ingredient": "Unknown sauce", "measure": "to taste"},
            ],
        )
        item = {n + "_per_100g": "1" for n in ("calories", "protein", "carbs", "fat")}
        with patch("data.recipe_estimation.source_candidates", return_value=[candidate]):
            updates, audit = estimate_candidates(
                Path("."), {"ING-DAGING-SAPI": item}, {"ING-DAGING-SAPI": {}}
            )
        self.assertEqual(len(audit), 3)
        self.assertEqual(updates[0]["quantities"]["ING-DAGING-SAPI"], 1100)
        self.assertEqual(updates[0]["is_plannable"], "false")
        self.assertIn("Unknown sauce", updates[0]["missing_data_reason"])

    def test_juice_is_not_discarded_as_water(self):
        candidate = dict(
            code="RCP-KAGGLE-1",
            name="Ayam",
            language="id",
            source_url="https://cookpad.com/resep/1",
            category="Chicken",
            instructions="Masak.",
            ingredients=[{"ingredient": "Air jeruk nipis", "measure": "Air jeruk nipis"}],
        )
        with patch("data.recipe_estimation.source_candidates", return_value=[candidate]):
            _, audit = estimate_candidates(Path("."), {}, {})
        self.assertEqual(audit[0]["ingredient_code"], "ING-JERUK-NIPIS")
        self.assertNotEqual(audit[0]["status"], "excluded_utility")

    def test_unmapped_food_can_have_known_mass_without_becoming_plannable(self):
        candidate = dict(
            code="RCP-TMDB-2",
            name="Test",
            language="en",
            source_url="https://www.themealdb.com/meal/2",
            category="Chicken",
            instructions="Cook.",
            ingredients=[{"ingredient": "Unknown seasoning", "measure": "8 oz"}],
        )
        with patch("data.recipe_estimation.source_candidates", return_value=[candidate]):
            updates, audit = estimate_candidates(Path("."), {}, {})
        self.assertAlmostEqual(audit[0]["quantity_g"], 226.796, places=3)
        self.assertEqual(audit[0]["status"], "blocked")
        self.assertEqual(updates[0]["quantities"], {})
        self.assertEqual(updates[0]["is_plannable"], "false")

    def test_garut_price_has_priority_and_package_quantity_is_preserved(self):
        local = dict(
            ingredient_code="ING-A",
            unit="kg",
            region="Kabupaten Garut",
            recorded_at="2026-09-28",
            price_status="published",
            price_code="1",
        )
        reference = dict(
            local,
            region="Non-Garut",
            recorded_at="2026-10-01",
            price_status="retail_reference",
            price_code="2",
        )
        other = dict(
            reference, ingredient_code="ING-B", quantity="0.25", price_rupiah="5600", price_code="3"
        )
        selected = build_final.planning_prices([reference, other, local])
        self.assertIs(selected["ING-A"], local)
        self.assertEqual(
            float(selected["ING-B"]["price_rupiah"]) / float(selected["ING-B"]["quantity"]), 22400
        )

    def test_manual_themealdb_promotion_reuses_candidate_id_and_aggregates_links(self):
        fixture = json.loads((build_final.ROOT / "fixtures/catalog_seed.json").read_text())
        items = {
            x["pk"]: dict(ingredient_code=x["pk"], **x["fields"])
            for x in fixture
            if x["model"] == "catalog.ingredient"
        }
        prices = [
            dict(price_code=x["pk"], ingredient_code=x["fields"]["ingredient"], **x["fields"])
            for x in fixture
            if x["model"] == "catalog.ingredientprice"
        ]
        metadata = dict(
            source_id="53281",
            curation_status="approved",
            name="Reviewed Kefta",
            source_url="https://www.themealdb.com/meal/53281",
            meal_type="makan_siang",
            base_servings="2",
            instructions="Masak hingga matang.",
            ingredient_code="ING-DAGING-SAPI",
            quantity_g="100",
            ingredient_mapping_reviewed="true",
            source_use_reviewed="true",
            halal_reviewed="true",
        )
        original_read = build_final.read_csv

        def read(path):
            return (
                [metadata, metadata.copy(), dict(metadata, quantity_g="200")]
                if path.name == "themealdb_recipe_curation.csv"
                else original_read(path)
            )

        with (
            patch.object(build_final, "read_csv", side_effect=read),
            patch.object(build_final, "write_csv"),
        ):
            recipes, links, tags, _ = build_final.build_recipes(items, prices)
        promoted = [r for r in recipes if r["recipe_code"] == "RCP-TMDB-53281"]
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["name"], "Reviewed Kefta")
        relation = [r for r in links if r["recipe_code"] == "RCP-TMDB-53281"]
        self.assertEqual(len(relation), 1)
        self.assertEqual(relation[0]["quantity"], "300")
        self.assertFalse(
            any(
                r["tag"].startswith(("kandidat_", "slot_saran_"))
                for r in tags
                if r["recipe_code"] == "RCP-TMDB-53281"
            )
        )


class CatalogImportTests(TestCase):
    def test_fixture_text_fits_postgresql_column_limits(self):
        fixture = json.loads((build_final.ROOT / "fixtures/catalog_seed.json").read_text())
        for record in fixture:
            model = apps.get_model(record["model"])
            for name, value in record["fields"].items():
                field = model._meta.get_field(name)
                if isinstance(value, str) and field.max_length:
                    with self.subTest(model=record["model"], pk=record["pk"], field=name):
                        self.assertLessEqual(len(value), field.max_length)

    def test_long_nutrition_provenance_is_preserved(self):
        note = "ESTIMASI PROKSI " + "a" * 400
        self.import_records(
            [
                dict(
                    model="catalog.ingredient",
                    pk="ING-TEST",
                    fields={
                        "name": "A",
                        "category": "bumbu",
                        "base_unit": "g",
                        "calories_method": note,
                    },
                )
            ]
        )
        self.assertEqual(Ingredient.objects.get().calories_method, note)

    def test_overlong_field_rejected_before_any_write(self):
        first = dict(
            model="catalog.ingredient",
            pk="ING-VALID",
            fields={"name": "A", "category": "bumbu", "base_unit": "g"},
        )
        invalid = dict(first, pk="ING-INVALID", fields=dict(first["fields"], name="x" * 256))
        with self.assertRaisesRegex(CommandError, "Field terlalu panjang"):
            self.import_records([first, invalid])
        self.assertFalse(Ingredient.objects.exists())

    def test_unknown_field_rejected_before_any_write(self):
        invalid = dict(model="catalog.ingredient", pk="ING-INVALID", fields={"typo": "A"})
        with self.assertRaisesRegex(CommandError, "Field tidak dikenal"):
            self.import_records([invalid])
        self.assertFalse(Ingredient.objects.exists())

    def import_records(self, records, **options):
        # Temporary fixture generation is test data, not an edit to repo files.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(records))
            call_command("import_catalog", str(path), verbosity=0, **options)

    def test_conflicting_duplicate_rejected_without_partial_import(self):
        first = dict(
            model="catalog.ingredient",
            pk="ING-TEST",
            fields={"name": "A", "category": "bumbu", "base_unit": "g"},
        )
        other = dict(first, fields=dict(first["fields"], name="B"))
        with self.assertRaisesRegex(CommandError, "ID duplikat"):
            self.import_records([first, other])
        self.assertFalse(Ingredient.objects.exists())

    def test_identical_duplicate_import_is_idempotent(self):
        first = dict(
            model="catalog.ingredient",
            pk="ING-TEST",
            fields={"name": "A", "category": "bumbu", "base_unit": "g"},
        )
        self.import_records([first, first])
        self.import_records([first])
        self.assertEqual(Ingredient.objects.count(), 1)

    def test_promoting_recipe_removes_discovery_badges_but_keeps_user_tags(self):
        recipe = Recipe.objects.create(recipe_code="RCP-TMDB-1", name="A", source="TheMealDB")
        for tag in ("kandidat_belum_dikurasi", "slot_saran_sarapan", "favorit_user"):
            RecipeTag.objects.create(recipe_tag_code="TAG-" + tag, recipe=recipe, tag=tag)
        self.import_records(
            [
                dict(
                    model="catalog.recipe",
                    pk=recipe.pk,
                    fields={"name": "A", "source": "TheMealDB", "is_plannable": True},
                )
            ]
        )
        self.assertEqual(list(recipe.recipetag_set.values_list("tag", flat=True)), ["favorit_user"])

    def test_promotion_does_not_delete_user_owned_tag_with_discovery_name(self):
        recipe = Recipe.objects.create(recipe_code="RCP-TMDB-1", name="A", source="TheMealDB")
        RecipeTag.objects.create(
            recipe_tag_code="TAG-USER", recipe=recipe, tag="slot_saran_sarapan", source="Pengguna"
        )
        self.import_records(
            [
                dict(
                    model="catalog.recipe",
                    pk=recipe.pk,
                    fields={"name": "A", "source": "TheMealDB", "is_plannable": True},
                )
            ],
            sync_generated_relations=True,
        )
        self.assertTrue(RecipeTag.objects.filter(pk="TAG-USER").exists())

    def test_scoped_sync_removes_old_generated_links_not_user_or_other_recipe_links(self):
        item = Ingredient.objects.create(
            ingredient_code="ING-TEST", name="A", category="bumbu", base_unit="g"
        )
        recipe = Recipe.objects.create(recipe_code="RCP-TEST", name="A", source="TAKARKUY")
        other = Recipe.objects.create(recipe_code="RCP-OTHER", name="B", source="TAKARKUY")
        for pk, parent, source in [
            ("RIN-OLD", recipe, "TAKARKUY estimasi"),
            ("RIN-USER", recipe, "Pengguna"),
            ("RIN-OTHER", other, "TAKARKUY"),
        ]:
            RecipeIngredient.objects.create(
                recipe_ingredient_code=pk,
                recipe=parent,
                ingredient=item,
                quantity=10,
                unit="g",
                source=source,
            )
        records = [
            dict(model="catalog.recipe", pk=recipe.pk, fields={"name": "A", "source": "TAKARKUY"})
        ]
        self.import_records(records, sync_generated_relations=True)
        self.assertEqual(
            set(RecipeIngredient.objects.values_list("pk", flat=True)), {"RIN-USER", "RIN-OTHER"}
        )
