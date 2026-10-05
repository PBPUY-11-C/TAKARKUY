from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import Ingredient, IngredientPrice, Recipe

from .forms import PlannerForm
from .planner import (
    MEALS,
    _recipe_patterns,
    build_plan,
    money,
    purchase_grams,
)
from .purchase_units import load_fruit_rules, whole_fruit_quote


class PlannerCatalogTests(TestCase):
    fixtures = ["catalog_seed"]

    def test_whole_chicken_purchase_uses_gross_mass_but_nutrition_uses_meat(self):
        recipe = Recipe.objects.get(pk="RCP-KAGGLE-4473027")
        Recipe.objects.exclude(pk=recipe.pk).update(is_active=False)
        links = list(recipe.recipeingredient_set.select_related("ingredient").all())
        chicken = next(link for link in links if link.ingredient_id == "ING-DAGING-AYAM-KAMPUNG")
        self.assertEqual(purchase_grams(chicken), Decimal("1000"))
        result = build_plan(
            budget=Decimal("100000"),
            days=1,
            servings=1,
            meal_types=[recipe.meal_type],
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        item = next(
            item
            for group in result["shopping_groups"]
            for item in group["items"]
            if item["name"] == chicken.ingredient.name
        )
        self.assertEqual(item["quantity"], money(Decimal("1000") / recipe.base_servings))
        protein = sum(
            Decimal(str(link.quantity)) * Decimal(str(link.ingredient.protein_per_100g)) / 100
            for link in links
        )
        self.assertEqual(result["schedule"][0]["protein"], money(protein / recipe.base_servings))
        self.assertTrue(result["purchase_yield_estimates"])
        self.assertIn("Daun Salam Segar (Estimasi)", result["nutrition_proxy_names"])
        response = self.client.post(
            "/modul1/",
            {
                "budget": "100000",
                "days": "1",
                "servings": "1",
                "meal_types": [recipe.meal_type],
                "targets": ["seimbang"],
                "exclude_ingredients": "",
            },
        )
        self.assertContains(response, "Biaya dan daftar belanja memakai berat utuh")
        self.assertContains(response, "Daun Salam Segar (Estimasi)")
        self.assertNotContains(response, "Proksi ikan dori menggunakan patin")

    def test_legacy_estimates_without_purchase_metadata_keep_original_quantity(self):
        link = SimpleNamespace(
            quantity=150, quantity_status="estimated", raw_text='[{"quantity_g": 150}]'
        )
        self.assertEqual(purchase_grams(link), Decimal("150"))

    def test_estimated_recipe_uses_package_price_and_exposes_provenance(self):
        Recipe.objects.exclude(pk="RCP-TMDB-53281").update(is_active=False)
        result = build_plan(
            budget=Decimal("100000"),
            days=1,
            servings=1,
            meal_types=["makan_siang"],
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertTrue(result["estimated_quantities"])
        self.assertTrue(result["retail_price_references"])
        ingredients = {
            item["name"]: item for group in result["shopping_groups"] for item in group["items"]
        }
        self.assertEqual(
            ingredients["Parsley Segar"]["price_reference"], "UbiFresh Pasar Modern BSD"
        )
        response = self.client.post(
            "/modul1/",
            {
                "budget": "100000",
                "days": "1",
                "servings": "1",
                "meal_types": ["makan_siang"],
                "targets": ["seimbang"],
                "exclude_ingredients": "",
            },
        )
        self.assertContains(response, "estimasi takaran dan jumlah porsi")
        self.assertContains(response, "bukan harga Garut")

    def test_local_price_overrides_newer_retail_reference_for_same_ingredient(self):
        Recipe.objects.exclude(pk="RCP-TMDB-53281").update(is_active=False)
        IngredientPrice.objects.create(
            price_code="PRC-TEST-PARSLEY",
            ingredient_id="ING-PARSLEY",
            price_rupiah=10000,
            quantity=1,
            unit="kg",
            region="Kabupaten Garut",
            recorded_at="2026-09-28",
            source="Tes harga lokal",
            source_url="https://example.com/price",
            price_status="published",
        )
        result = build_plan(
            budget=Decimal("100000"),
            days=1,
            servings=1,
            meal_types=["makan_siang"],
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        parsley = next(
            item
            for group in result["shopping_groups"]
            for item in group["items"]
            if item["name"] == "Parsley Segar"
        )
        self.assertEqual(parsley["price_reference"], "")

    def test_dori_nutrition_proxy_is_visible_in_result(self):
        Recipe.objects.exclude(pk="RCP-MVP-070").update(is_active=False)
        result = build_plan(
            budget=Decimal("100000"),
            days=1,
            servings=1,
            meal_types=["makan_siang", "makan_malam"],
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        self.assertTrue(result["nutrition_proxies"])

    def test_whole_fruit_quote_aggregates_servings_and_keeps_leftovers(self):
        banana = load_fruit_rules()["ING-PISANG"]
        daily = whole_fruit_quote(Decimal("120"), Decimal("6588"), banana)
        combined = whole_fruit_quote(Decimal("360"), Decimal("6588"), banana)
        self.assertEqual(daily["units"], 2)
        self.assertEqual(combined["units"], 5)
        self.assertLess(combined["cost"], daily["cost"] * 3)
        self.assertGreater(combined["leftover_edible_grams"], 0)

    def test_three_people_one_day_and_one_person_three_days_buy_same_fruit(self):
        Recipe.objects.exclude(pk="RCP-MVP-022").update(is_active=False)
        self.assertTrue(Recipe.objects.get(pk="RCP-MVP-022").is_plannable)
        settings = dict(
            budget=Decimal("18000"),
            meal_types=["sarapan"],
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        together = build_plan(days=1, servings=3, **settings)
        spread = build_plan(days=3, servings=1, **settings)
        self.assertTrue(together["within_budget"])
        self.assertTrue(spread["within_budget"])
        self.assertEqual(together["total"], spread["total"])
        self.assertEqual(together["total"], 18000)
        first = {
            item["name"]: item for group in together["shopping_groups"] for item in group["items"]
        }
        second = {
            item["name"]: item for group in spread["shopping_groups"] for item in group["items"]
        }
        for name in ("Pisang", "Jeruk"):
            self.assertEqual(first[name]["purchase_units"], second[name]["purchase_units"])
            self.assertEqual(first[name]["cost"], second[name]["cost"])
            self.assertGreater(first[name]["leftover_edible_grams"], 0)
        response = self.client.post(
            "/modul1/",
            {
                "budget": "18.000",
                "days": "3",
                "servings": "1",
                "meal_types": ["sarapan"],
                "targets": ["seimbang"],
                "exclude_ingredients": "",
            },
        )
        self.assertContains(response, "Perkiraan beli 5 buah")
        self.assertContains(response, "harga per kg Kabupaten Garut")

    def test_kubis_is_grouped_as_vegetable_even_with_old_catalog_category(self):
        kubis = Ingredient.objects.get(pk="ING-KUBIS")
        self.assertEqual(kubis.category, "sayur")
        kubis.category = "karbohidrat"
        kubis.save(update_fields=["category"])
        result = build_plan(
            budget=Decimal("1000000"),
            days=7,
            servings=2,
            meal_types=MEALS,
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        kubis_groups = [
            group["name"]
            for group in result["shopping_groups"]
            if any(item["name"] == "Kubis" for item in group["items"])
        ]
        self.assertEqual(kubis_groups, ["Sayur"])

    def test_budget_accepts_indonesian_thousands_separator(self):
        form = PlannerForm(
            {
                "budget": "1.000.000",
                "days": "1",
                "servings": "1",
                "meal_types": ["sarapan"],
                "targets": ["seimbang"],
                "exclude_ingredients": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["budget"], Decimal("1000000"))

    def test_can_select_high_protein_and_low_calorie_together(self):
        form = PlannerForm(
            {
                "budget": "150.000",
                "days": "1",
                "servings": "1",
                "meal_types": list(MEALS),
                "targets": ["tinggi_protein", "rendah_kalori"],
                "exclude_ingredients": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["targets"], ["tinggi_protein", "rendah_kalori"])
        result = build_plan(
            budget=form.cleaned_data["budget"],
            days=1,
            servings=1,
            meal_types=MEALS,
            targets=form.cleaned_data["targets"],
            exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["protein_floor"], 80)
        self.assertEqual(result["calorie_cap"], 1150)
        self.assertGreaterEqual(result["schedule"][0]["protein"], 80)
        self.assertLessEqual(result["schedule"][0]["calories"], 1150)

    def test_nutritional_targets_apply_to_each_selected_day_not_each_recipe(self):
        result = build_plan(
            budget=Decimal("1000000"),
            days=7,
            servings=1,
            meal_types=MEALS,
            targets=["tinggi_protein", "rendah_kalori"],
            exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["protein_floor"], 80)
        self.assertEqual(result["calorie_cap"], 1150)
        self.assertEqual(len(result["schedule"]), 7)
        for day in result["schedule"]:
            self.assertGreaterEqual(day["protein"], 80)
            self.assertLessEqual(day["calories"], 1150)
            self.assertEqual(len(day["meals"]), 3)

    def test_single_nutritional_targets_use_only_their_own_metric(self):
        for targets, expected_protein, expected_calories in (
            (["tinggi_protein"], 80, None),
            (["rendah_kalori"], None, 1150),
        ):
            with self.subTest(targets=targets):
                result = build_plan(
                    budget=Decimal("300000"),
                    days=1,
                    servings=1,
                    meal_types=MEALS,
                    targets=targets,
                    exclude_ingredients=[],
                )
                self.assertEqual(result["protein_floor"], expected_protein)
                self.assertEqual(result["calorie_cap"], expected_calories)
                if expected_protein is not None:
                    self.assertGreaterEqual(result["schedule"][0]["protein"], expected_protein)
                if expected_calories is not None:
                    self.assertLessEqual(result["schedule"][0]["calories"], expected_calories)

    def test_partial_meal_targets_do_not_claim_full_day_totals(self):
        result = build_plan(
            budget=Decimal("300000"),
            days=1,
            servings=1,
            meal_types=["makan_siang", "makan_malam"],
            targets=["tinggi_protein", "rendah_kalori"],
            exclude_ingredients=[],
        )
        self.assertEqual(result["protein_floor"], 54)
        self.assertEqual(result["calorie_cap"], 650)
        self.assertGreaterEqual(result["schedule"][0]["protein"], 54)
        self.assertLessEqual(result["schedule"][0]["calories"], 650)

    def test_no_high_protein_breakfast_does_not_return_under_target_menu(self):
        with self.assertRaisesMessage(ValueError, "Belum ada kombinasi menu"):
            build_plan(
                budget=Decimal("300000"),
                days=1,
                servings=1,
                meal_types=["sarapan"],
                targets=["tinggi_protein"],
                exclude_ingredients=[],
            )

    def test_nutritional_target_does_not_silently_fall_back(self):
        with patch("apps.budget_planner.planner.HIGH_PROTEIN_GRAMS_PER_DAY", Decimal("10000")):
            with self.assertRaisesMessage(ValueError, "Belum ada kombinasi menu"):
                build_plan(
                    budget=Decimal("1000000"),
                    days=1,
                    servings=1,
                    meal_types=MEALS,
                    targets=["tinggi_protein"],
                    exclude_ingredients=[],
                )

    def test_nutritional_target_reports_insufficient_budget(self):
        with self.assertRaisesMessage(ValueError, "Budget belum cukup untuk target gizi"):
            build_plan(
                budget=Decimal("1000"),
                days=1,
                servings=1,
                meal_types=MEALS,
                targets=["tinggi_protein", "rendah_kalori"],
                exclude_ingredients=[],
            )

    def test_nutritional_result_renders_daily_targets(self):
        response = self.client.post(
            "/modul1/",
            {
                "budget": "300.000",
                "days": "1",
                "servings": "1",
                "meal_types": list(MEALS),
                "targets": ["tinggi_protein", "rendah_kalori"],
                "exclude_ingredients": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "minimal 80 g protein")
        self.assertContains(response, "maksimal 1150 kkal")
        self.assertContains(response, "kkal / orang (waktu makan terpilih)")

    def test_balanced_cannot_be_combined_with_specific_targets(self):
        form = PlannerForm(
            {
                "budget": "150.000",
                "days": "1",
                "servings": "1",
                "meal_types": ["sarapan"],
                "targets": ["seimbang", "tinggi_protein"],
                "exclude_ingredients": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Seimbang tidak bisa digabung", str(form.errors["targets"]))
        with self.assertRaisesMessage(ValueError, "Seimbang tidak bisa digabung"):
            build_plan(
                budget=Decimal("150000"),
                days=1,
                servings=1,
                meal_types=["sarapan"],
                targets=["seimbang", "tinggi_protein"],
                exclude_ingredients=[],
            )

    def test_same_cost_prefers_recipe_matching_both_targets(self):
        candidates = [
            {"recipe": SimpleNamespace(pk="protein"), "cost": 100, "tags": {"tinggi_protein"}},
            {
                "recipe": SimpleNamespace(pk="both"),
                "cost": 100,
                "tags": {"tinggi_protein", "rendah_kalori"},
            },
            {"recipe": SimpleNamespace(pk="low_calorie"), "cost": 100, "tags": {"rendah_kalori"}},
        ]
        for item in candidates:
            item["protein_group"] = "telur"
        patterns = _recipe_patterns(candidates, 1, {"tinggi_protein", "rendah_kalori"}, set())
        self.assertEqual(patterns[100]["items"][0]["recipe"].pk, "both")

    def test_egg_and_tomato_exclusion_keeps_banana_breakfast(self):
        result = build_plan(
            budget=Decimal("1000000"),
            days=1,
            servings=1,
            meal_types=MEALS,
            targets=["seimbang"],
            exclude_ingredients=["telur", "tomat"],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["missing_meal_labels"], [])
        self.assertTrue(any(meal["label"] == "Pagi" for meal in result["schedule"][0]["meals"]))

    def test_catalog_has_at_least_five_recipes_for_each_meal(self):
        for meal in ("sarapan", "makan_siang", "makan_malam"):
            self.assertGreaterEqual(
                Recipe.objects.filter(
                    is_active=True,
                    is_plannable=True,
                    meal_type=meal,
                ).count(),
                5,
            )

    def test_seven_day_plan_varies_across_available_egg_free_breakfasts(self):
        result = build_plan(
            budget=Decimal("1000000"),
            days=7,
            servings=1,
            meal_types=["sarapan"],
            targets=["seimbang"],
            exclude_ingredients=["telur"],
        )
        breakfast_codes = [day["meals"][0]["recipe_code"] for day in result["schedule"]]
        counts = {}
        for code in breakfast_codes:
            counts[code] = counts.get(code, 0) + 1
        self.assertEqual(len(breakfast_codes), 7)
        self.assertGreaterEqual(len(counts), 2)
        self.assertLessEqual(max(counts.values()), 4)

    def test_replanning_same_day_avoids_previous_recipe_when_alternative_exists(self):
        first = build_plan(
            budget=Decimal("1000000"),
            days=7,
            servings=1,
            meal_types=["sarapan"],
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        previous_day_five_recipe = first["schedule"][4]["meals"][0]["recipe_code"]
        replanned = build_plan(
            budget=Decimal("1000000"),
            days=1,
            servings=1,
            meal_types=["sarapan"],
            targets=["seimbang"],
            exclude_ingredients=[],
            recent_recipe_codes=first["planned_recipe_codes"],
            prior_slot_recipes={"sarapan": [previous_day_five_recipe]},
        )
        self.assertNotEqual(
            replanned["schedule"][0]["meals"][0]["recipe_code"], previous_day_five_recipe
        )

    def test_empty_meal_type_does_not_hide_other_meals(self):
        Recipe.objects.filter(meal_type="sarapan").update(is_active=False)
        result = build_plan(
            budget=Decimal("1000000"),
            days=1,
            servings=1,
            meal_types=MEALS,
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        self.assertIn("Pagi", result["missing_meal_labels"])
        self.assertEqual(result["meal_labels"], ["Siang", "Malam"])

    def test_plan_never_exceeds_budget_and_maximizes_available_recipe_mix(self):
        result = build_plan(
            budget=Decimal("1000000"),
            days=1,
            servings=1,
            meal_types=MEALS,
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        self.assertLessEqual(result["total"], 1000000)
        self.assertTrue(result["catalog_cannot_use_all_budget"])
        self.assertGreaterEqual(result["catalog_ceiling"], result["total"])

    def test_seven_day_large_budget_stays_varied_and_below_limit(self):
        result = build_plan(
            budget=Decimal("1000000"),
            days=7,
            servings=1,
            meal_types=MEALS,
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertLessEqual(result["total"], result["catalog_ceiling"])
        self.assertEqual(len(result["planned_recipe_codes"]), 21)

    def test_minimum_budget_accounts_for_distinct_recipes(self):
        result = build_plan(
            budget=Decimal("1000"),
            days=7,
            servings=5,
            meal_types=MEALS,
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        self.assertFalse(result["within_budget"])
        self.assertEqual(result["minimum_budget"], result["total"])

    def test_budget_limit_is_never_exceeded(self):
        settings = dict(
            days=7, servings=2, meal_types=MEALS, targets=["seimbang"], exclude_ingredients=[]
        )
        for budget in ("150000", "400000", "1000000"):
            result = build_plan(budget=Decimal(budget), **settings)
            self.assertTrue(result["within_budget"])
            self.assertLessEqual(result["total"], Decimal(budget))
