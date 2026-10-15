"""Planner uses pantry stock first; the budget is checked against net shopping cost."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Ingredient

from .planner import (
    _load_candidates,
    _order_days_by_expiry,
    _prefer_stock,
    build_plan,
    quote_schedule,
    replacement_options,
)
from .snapshots import net_total

FRUIT_RECIPE = "RCP-MVP-021"  # sarapan with 400 g banana per base recipe
TODAY = timezone.localdate()


class StockAllocationTests(TestCase):
    fixtures = ["catalog_seed"]

    @classmethod
    def setUpTestData(cls):
        cls.catalog = _load_candidates(("sarapan",), 1, [])
        fruit = {"ING-PISANG", "ING-JERUK", "ING-MELON"}
        cls.plain = next(
            item["recipe"].pk
            for item in cls.catalog[5]["sarapan"]
            if not {link.ingredient_id for link in item["ingredients"]} & fruit
        )

    def quote(self, code, days=1, **options):
        return quote_schedule(
            [{"sarapan": code}] * days,
            servings=1,
            targets=["seimbang"],
            catalog=self.catalog,
            starts_on=TODAY,
            **options,
        )

    def item(self, result, code):
        return next(
            row
            for group in result["shopping_groups"]
            for row in group["items"]
            if row["ingredient_code"] == code
        )

    def main_ingredient(self, result):
        return max(
            (row for group in result["shopping_groups"] for row in group["items"]),
            key=lambda row: row["cost"],
        )

    def test_net_total_equals_total_without_stock(self):
        result = self.quote(self.plain, days=2)
        self.assertEqual(result["net_total"], result["total"])
        self.assertEqual(result["stock_used"], {})
        self.assertTrue(
            all(
                row["net_cost"] == row["cost"] and row["from_stock"] == 0
                for group in result["shopping_groups"]
                for row in group["items"]
            )
        )

    def test_allocation_never_exceeds_batch_grams(self):
        main = self.main_ingredient(self.quote(self.plain))
        per_day = Decimal(main["quantity"])
        batch = per_day * Decimal("1.5")
        result = self.quote(self.plain, days=3, stock=[(main["ingredient_code"], batch, None)])
        self.assertEqual(self.item(result, main["ingredient_code"])["from_stock"], int(batch))

    def test_stock_not_used_after_its_expiry_day(self):
        main = self.main_ingredient(self.quote(self.plain))
        per_day = Decimal(main["quantity"])
        stock = [(main["ingredient_code"], per_day * 10, TODAY)]  # good for day 1 only
        result = self.quote(self.plain, days=3, stock=stock)
        self.assertEqual(self.item(result, main["ingredient_code"])["from_stock"], int(per_day))

    def test_net_total_subtracts_stock_value_and_rounds_up_500(self):
        base = self.quote(self.plain)
        main = self.main_ingredient(base)
        stock = [(main["ingredient_code"], Decimal(main["quantity"]), None)]
        result = self.quote(self.plain, stock=stock)
        expected = sum(
            row["cost"]
            for group in base["shopping_groups"]
            for row in group["items"]
            if row["ingredient_code"] != main["ingredient_code"]
        )
        self.assertEqual(self.item(result, main["ingredient_code"])["net_cost"], 0)
        self.assertEqual(result["net_total"], -(-expected // 500) * 500)
        self.assertEqual(result["stock_used"], {main["ingredient_code"]: int(main["quantity"])})
        self.assertEqual(result["total"], base["total"])

    def test_fruit_net_cost_uses_whole_fruit_quote_on_remaining_grams(self):
        base = self.item(self.quote(FRUIT_RECIPE), "ING-PISANG")
        rule = self.catalog[3]["ING-PISANG"]
        # Whole-fruit weight that holds exactly the edible need.
        whole = Decimal(base["quantity"]) * rule["gross_grams"] / rule["edible_grams"]
        covered = self.item(
            self.quote(FRUIT_RECIPE, stock=[("ING-PISANG", whole, None)]), "ING-PISANG"
        )
        self.assertEqual(covered["net_cost"], 0)
        partial = self.item(
            self.quote(FRUIT_RECIPE, stock=[("ING-PISANG", whole - 1, None)]), "ING-PISANG"
        )
        # One gram short still means buying one whole banana, not a fraction of the price.
        self.assertGreater(partial["net_cost"], 0)
        self.assertLess(partial["net_cost"], base["cost"])

    def test_fruit_stock_counts_only_its_edible_part(self):
        rule = self.catalog[3]["ING-PISANG"]
        need = Decimal(self.item(self.quote(FRUIT_RECIPE), "ING-PISANG")["quantity"])
        # Whole bananas weighing exactly the edible need cover only their edible share.
        row = self.item(self.quote(FRUIT_RECIPE, stock=[("ING-PISANG", need, None)]), "ING-PISANG")
        self.assertEqual(row["from_stock"], int(need * rule["edible_grams"] / rule["gross_grams"]))
        self.assertGreater(row["net_cost"], 0)

    def test_frozen_days_do_not_use_stock(self):
        main = self.main_ingredient(self.quote(self.plain))
        stock = [(main["ingredient_code"], Decimal(main["quantity"]) * 5, None)]
        result = self.quote(self.plain, days=2, stock=stock, frozen_days=frozenset({1}))
        self.assertEqual(
            self.item(result, main["ingredient_code"])["from_stock"], int(main["quantity"])
        )


class NetBudgetPlanTests(TestCase):
    fixtures = ["catalog_seed"]

    inputs = {
        "budget": Decimal("1000000"),
        "days": 2,
        "servings": 1,
        "meal_types": ["sarapan", "makan_siang"],
        "targets": ["seimbang"],
        "exclude_ingredients": [],
    }

    def plan(self, **changes):
        return build_plan(**{**self.inputs, "seed": 7, **changes})

    def all_stock(self, grams=Decimal(100000)):
        return [(code, grams, None) for code in Ingredient.objects.values_list("pk", flat=True)]

    def test_no_stock_plan_has_net_equal_to_total(self):
        result = self.plan()
        self.assertEqual(result["net_total"], result["total"])
        self.assertEqual(result["within_budget"], result["total"] <= self.inputs["budget"])

    def test_stock_makes_otherwise_unaffordable_plan_feasible(self):
        budget = Decimal(5000)
        self.assertFalse(self.plan(budget=budget)["within_budget"])
        result = self.plan(budget=budget, stock=self.all_stock())
        self.assertTrue(result["within_budget"])
        self.assertLessEqual(result["net_total"], budget)

    def test_net_total_never_exceeds_budget_when_within_budget(self):
        stock = self.all_stock(Decimal(150))
        for seed in range(6):
            for budget in (Decimal(15000), Decimal(40000)):
                result = self.plan(budget=budget, stock=stock, seed=seed)
                if result["within_budget"]:
                    self.assertLessEqual(result["net_total"], budget)

    def test_stock_no_recipe_uses_does_not_trigger_extra_searches(self):
        from unittest.mock import patch

        from . import planner

        catalog = _load_candidates(("sarapan", "makan_siang"), 1, [])
        used = {
            link.ingredient_id
            for items in catalog[5].values()
            for item in items
            for link in item["ingredients"]
        }
        unused = next(code for code in catalog[1] if code not in used)  # priced, in no recipe
        with patch.object(planner, "_build_plan", wraps=planner._build_plan) as search:
            self.plan(stock=[(unused, Decimal(10**6), None)])
        self.assertEqual(search.call_count, 1)

    def test_legacy_snapshot_without_stock_fields_reads_net_as_total(self):
        self.assertEqual(net_total({"total": 25000}), 25000)
        self.assertEqual(net_total({"total": 25000, "net_total": 12000}), 12000)


class StockPreferenceTests(TestCase):
    fixtures = ["catalog_seed"]

    def test_stock_score_weights_grams_by_expiry(self):
        catalog = _load_candidates(("sarapan",), 1, [])
        item = catalog[5]["sarapan"][0]
        code = item["ingredients"][0].ingredient_id
        soon = _load_candidates(("sarapan",), 1, [], stock=[(code, Decimal(10**6), TODAY)])
        later = _load_candidates(
            ("sarapan",), 1, [], stock=[(code, Decimal(10**6), TODAY + timedelta(days=30))]
        )
        score = {
            name: next(c for c in cat[5]["sarapan"] if c["recipe"].pk == item["recipe"].pk)[
                "pantry_hits"
            ]
            for name, cat in (("soon", soon), ("later", later))
        }
        # Scores are rounded to whole grams after weighting, so allow the rounding gap.
        self.assertAlmostEqual(score["soon"], 3 * score["later"], delta=2)
        self.assertGreater(score["later"], 0)

    def test_plan_prefers_recipes_that_use_up_stock(self):
        inputs = {
            "budget": Decimal("1000000"),
            "days": 3,
            "servings": 1,
            "meal_types": ["makan_siang"],
            "targets": ["seimbang"],
            "exclude_ingredients": [],
        }
        catalog = _load_candidates(("makan_siang",), 1, [])
        counts = Counter(
            link.ingredient_id for item in catalog[5]["makan_siang"] for link in item["ingredients"]
        )
        # An ingredient used by a minority of recipes, so picking it is a real choice.
        code = next(c for c, n in counts.most_common() if n <= len(catalog[5]["makan_siang"]) // 4)
        stock = [(code, Decimal(5000), TODAY + timedelta(days=1))]
        uses = 0
        for seed in range(5):
            result = build_plan(**inputs, seed=seed, stock=stock)
            uses += bool(result["stock_used"].get(code))
        self.assertGreaterEqual(uses, 4)

    def test_alternatives_filtered_by_net_total(self):
        catalog = _load_candidates(("sarapan",), 1, [])
        cheapest = min(catalog[5]["sarapan"], key=lambda item: item["cost"])
        args = {
            "budget": Decimal(cheapest["cost"]) + 500,
            "days": 1,
            "servings": 1,
            "meal_types": ["sarapan"],
            "targets": ["seimbang"],
            "exclude_ingredients": [],
            "schedule": [{"sarapan": cheapest["recipe"].pk}],
            "day": 1,
            "meal": "sarapan",
            "current_total": cheapest["cost"],
        }
        without = replacement_options(**args)
        stock = [(code, Decimal(10**6), None) for code in catalog[1]]
        with_stock = replacement_options(**args, stock=stock, starts_on=TODAY)
        self.assertGreater(len(with_stock), len(without))
        self.assertTrue(all(option["delta"] <= 0 for option in with_stock))


def fake(code, *ingredients, group="ayam"):
    return {
        "recipe": SimpleNamespace(pk=code),
        "protein_group": group,
        "ingredients": [SimpleNamespace(ingredient_id=i) for i in ingredients],
    }


class PreferStockTests(TestCase):
    def test_swap_never_brings_back_recent_recipes(self):
        current = {**fake("A", "ING-X"), "cost": 10000, "pantry_hits": 0}
        recent = {**fake("B", "ING-BAYAM"), "cost": 10000, "pantry_hits": 500}
        chosen = {"sarapan": [current]}
        self.assertIsNone(_prefer_stock(chosen, {"sarapan": [current, recent]}, avoid={"B"}))
        swapped = _prefer_stock(chosen, {"sarapan": [current, recent]})
        self.assertEqual(swapped["sarapan"][0]["recipe"].pk, "B")


class DayOrderTests(TestCase):
    def test_day_using_soonest_expiring_stock_comes_first(self):
        chosen = {"sarapan": [fake("A", "ING-X"), fake("B", "ING-BAYAM", group="sayur")]}
        stock = [("ING-BAYAM", Decimal(100), TODAY + timedelta(days=1))]
        ordered = _order_days_by_expiry(chosen, ("sarapan",), stock, {})
        self.assertEqual([item["recipe"].pk for item in ordered["sarapan"]], ["B", "A"])

    def test_reorder_skipped_when_it_creates_back_to_back_repeat(self):
        chosen = {
            "sarapan": [fake("R1", "ING-BAYAM"), fake("R2", "ING-X"), fake("R1", "ING-BAYAM")]
        }
        stock = [("ING-BAYAM", Decimal(100), TODAY + timedelta(days=1))]
        ordered = _order_days_by_expiry(chosen, ("sarapan",), stock, {})
        self.assertEqual([item["recipe"].pk for item in ordered["sarapan"]], ["R1", "R2", "R1"])
