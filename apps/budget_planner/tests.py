from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import Ingredient, Recipe
from .forms import PlannerForm
from .planner import MEALS, _recipe_patterns, budget_target_minimum, build_plan


class PlannerCatalogTests(TestCase):
    fixtures = ["catalog_seed"]

    def test_kubis_is_grouped_as_vegetable_even_with_old_catalog_category(self):
        kubis = Ingredient.objects.get(pk="ING-KUBIS")
        self.assertEqual(kubis.category, "sayur")
        kubis.category = "karbohidrat"
        kubis.save(update_fields=["category"])
        result = build_plan(
            budget=Decimal("1000000"), days=7, servings=2, meal_types=MEALS,
            targets=["seimbang"], exclude_ingredients=[],
        )
        kubis_groups = [group["name"] for group in result["shopping_groups"]
                        if any(item["name"] == "Kubis" for item in group["items"])]
        self.assertEqual(kubis_groups, ["Sayur"])

    def test_budget_accepts_indonesian_thousands_separator(self):
        form = PlannerForm({
            "budget": "1.000.000", "days": "1", "servings": "1",
            "meal_types": ["sarapan"], "targets": ["seimbang"], "exclude_ingredients": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["budget"], Decimal("1000000"))

    def test_can_select_high_protein_and_low_calorie_together(self):
        form = PlannerForm({
            "budget": "150.000", "days": "1", "servings": "1",
            "meal_types": list(MEALS),
            "targets": ["tinggi_protein", "rendah_kalori"],
            "exclude_ingredients": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["targets"], ["tinggi_protein", "rendah_kalori"])
        result = build_plan(
            budget=form.cleaned_data["budget"], days=1, servings=1,
            meal_types=MEALS, targets=form.cleaned_data["targets"],
            exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["protein_floor"], 80)
        self.assertEqual(result["calorie_cap"], 1150)
        self.assertGreaterEqual(result["schedule"][0]["protein"], 80)
        self.assertLessEqual(result["schedule"][0]["calories"], 1150)

    def test_nutritional_targets_apply_to_each_selected_day_not_each_recipe(self):
        result = build_plan(
            budget=Decimal("1000000"), days=7, servings=1, meal_types=MEALS,
            targets=["tinggi_protein", "rendah_kalori"], exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["protein_floor"], 80)
        self.assertEqual(result["calorie_cap"], 1150)
        self.assertEqual(len(result["schedule"]), 7)
        self.assertTrue(result["repeated_recipes"])
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
                    budget=Decimal("300000"), days=1, servings=1,
                    meal_types=MEALS, targets=targets, exclude_ingredients=[],
                )
                self.assertEqual(result["protein_floor"], expected_protein)
                self.assertEqual(result["calorie_cap"], expected_calories)
                if expected_protein is not None:
                    self.assertGreaterEqual(result["schedule"][0]["protein"], expected_protein)
                if expected_calories is not None:
                    self.assertLessEqual(result["schedule"][0]["calories"], expected_calories)

    def test_partial_meal_targets_do_not_claim_full_day_totals(self):
        result = build_plan(
            budget=Decimal("300000"), days=1, servings=1,
            meal_types=["makan_siang", "makan_malam"],
            targets=["tinggi_protein", "rendah_kalori"], exclude_ingredients=[],
        )
        self.assertEqual(result["protein_floor"], 54)
        self.assertEqual(result["calorie_cap"], 650)
        self.assertGreaterEqual(result["schedule"][0]["protein"], 54)
        self.assertLessEqual(result["schedule"][0]["calories"], 650)

    def test_no_high_protein_breakfast_does_not_return_under_target_menu(self):
        with self.assertRaisesMessage(ValueError, "Belum ada kombinasi menu"):
            build_plan(
                budget=Decimal("300000"), days=1, servings=1,
                meal_types=["sarapan"], targets=["tinggi_protein"],
                exclude_ingredients=[],
            )

    def test_nutritional_target_does_not_silently_fall_back(self):
        with patch("apps.budget_planner.planner.HIGH_PROTEIN_GRAMS_PER_DAY", Decimal("10000")):
            with self.assertRaisesMessage(ValueError, "Belum ada kombinasi menu"):
                build_plan(
                    budget=Decimal("1000000"), days=1, servings=1,
                    meal_types=MEALS, targets=["tinggi_protein"], exclude_ingredients=[],
                )

    def test_nutritional_target_reports_insufficient_budget(self):
        with self.assertRaisesMessage(ValueError, "Budget belum cukup untuk target gizi"):
            build_plan(
                budget=Decimal("1000"), days=1, servings=1,
                meal_types=MEALS, targets=["tinggi_protein", "rendah_kalori"],
                exclude_ingredients=[],
            )

    def test_nutritional_result_renders_daily_targets(self):
        response = self.client.post("/modul1/", {
            "budget": "300.000", "days": "1", "servings": "1",
            "meal_types": list(MEALS),
            "targets": ["tinggi_protein", "rendah_kalori"],
            "exclude_ingredients": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "minimal 80 g protein")
        self.assertContains(response, "maksimal 1150 kkal")
        self.assertContains(response, "kkal / orang (waktu makan terpilih)")

    def test_balanced_cannot_be_combined_with_specific_targets(self):
        form = PlannerForm({
            "budget": "150.000", "days": "1", "servings": "1",
            "meal_types": ["sarapan"],
            "targets": ["seimbang", "tinggi_protein"],
            "exclude_ingredients": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Seimbang tidak bisa digabung", str(form.errors["targets"]))
        with self.assertRaisesMessage(ValueError, "Seimbang tidak bisa digabung"):
            build_plan(
                budget=Decimal("150000"), days=1, servings=1,
                meal_types=["sarapan"], targets=["seimbang", "tinggi_protein"],
                exclude_ingredients=[],
            )

    def test_same_cost_prefers_recipe_matching_both_targets(self):
        candidates = [
            {"recipe": SimpleNamespace(pk="protein"), "cost": 100,
             "tags": {"tinggi_protein"}},
            {"recipe": SimpleNamespace(pk="both"), "cost": 100,
             "tags": {"tinggi_protein", "rendah_kalori"}},
            {"recipe": SimpleNamespace(pk="low_calorie"), "cost": 100,
             "tags": {"rendah_kalori"}},
        ]
        patterns = _recipe_patterns(
            candidates, 1, {"tinggi_protein", "rendah_kalori"}, set()
        )
        self.assertEqual(patterns[100]["items"][0]["recipe"].pk, "both")

    def test_egg_and_tomato_exclusion_keeps_banana_breakfast(self):
        result = build_plan(
            budget=Decimal("1000000"), days=1, servings=1, meal_types=MEALS,
            targets=["seimbang"], exclude_ingredients=["telur", "tomat"],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["missing_meal_labels"], [])
        self.assertTrue(any(meal["label"] == "Pagi" for meal in result["schedule"][0]["meals"]))

    def test_catalog_has_at_least_five_recipes_for_each_meal(self):
        for meal in ("sarapan", "makan_siang", "makan_malam"):
            self.assertGreaterEqual(Recipe.objects.filter(
                is_active=True, is_plannable=True, meal_type=meal,
            ).count(), 5)

    def test_seven_day_plan_varies_across_available_egg_free_breakfasts(self):
        result = build_plan(
            budget=Decimal("1000000"), days=7, servings=1, meal_types=["sarapan"],
            targets=["seimbang"], exclude_ingredients=["telur"],
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
            budget=Decimal("1000000"), days=7, servings=1, meal_types=["sarapan"],
            targets=["seimbang"], exclude_ingredients=[],
        )
        previous_day_five_recipe = first["schedule"][4]["meals"][0]["recipe_code"]
        replanned = build_plan(
            budget=Decimal("1000000"), days=1, servings=1, meal_types=["sarapan"],
            targets=["seimbang"], exclude_ingredients=[],
            recent_recipe_codes=first["planned_recipe_codes"],
            prior_slot_recipes={"sarapan": [previous_day_five_recipe]},
        )
        self.assertNotEqual(replanned["schedule"][0]["meals"][0]["recipe_code"], previous_day_five_recipe)

    def test_empty_meal_type_does_not_hide_other_meals(self):
        Recipe.objects.filter(meal_type="sarapan").update(is_active=False)
        result = build_plan(
            budget=Decimal("1000000"), days=1, servings=1, meal_types=MEALS,
            targets=["seimbang"], exclude_ingredients=[],
        )
        self.assertIn("Pagi", result["missing_meal_labels"])
        self.assertEqual(result["meal_labels"], ["Siang", "Malam"])

    def test_plan_never_exceeds_budget_and_maximizes_available_recipe_mix(self):
        result = build_plan(
            budget=Decimal("1000000"), days=1, servings=1, meal_types=MEALS,
            targets=["seimbang"], exclude_ingredients=[],
        )
        self.assertLessEqual(result["total"], 1000000)
        self.assertTrue(result["catalog_cannot_use_all_budget"])
        self.assertGreaterEqual(result["catalog_ceiling"], result["total"])

    def test_seven_day_large_budget_reaches_catalog_ceiling(self):
        result = build_plan(
            budget=Decimal("1000000"), days=7, servings=1, meal_types=MEALS,
            targets=["seimbang"], exclude_ingredients=[],
        )
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["total"], result["catalog_ceiling"])
        self.assertEqual(len(result["planned_recipe_codes"]), 21)

    def test_minimum_budget_accounts_for_distinct_recipes(self):
        result = build_plan(
            budget=Decimal("1000"), days=7, servings=5, meal_types=MEALS,
            targets=["seimbang"], exclude_ingredients=[],
        )
        self.assertFalse(result["within_budget"])
        self.assertEqual(result["minimum_budget"], result["total"])

    def test_target_range_uses_twenty_percent_capped_at_fifty_thousand(self):
        self.assertEqual(budget_target_minimum(Decimal("100000")), 80000)
        self.assertEqual(budget_target_minimum(Decimal("200000")), 160000)
        self.assertEqual(budget_target_minimum(Decimal("250000")), 200000)
        self.assertEqual(budget_target_minimum(Decimal("300000")), 250000)
        self.assertEqual(budget_target_minimum(Decimal("380000")), 330000)

        settings = dict(days=7, servings=2, meal_types=MEALS,
                        targets=["seimbang"], exclude_ingredients=[])
        near = build_plan(budget=Decimal("400000"), **settings)
        self.assertEqual(near["target_minimum"], 350000)
        self.assertTrue(near["within_target_range"])
        self.assertGreaterEqual(near["total"], 350000)
        self.assertLessEqual(near["total"], 400000)

        too_far = build_plan(budget=Decimal("450000"), **settings)
        self.assertEqual(too_far["target_minimum"], 400000)
        self.assertTrue(too_far["within_budget"])
        self.assertFalse(too_far["within_target_range"])
        self.assertTrue(too_far["catalog_below_target"])
