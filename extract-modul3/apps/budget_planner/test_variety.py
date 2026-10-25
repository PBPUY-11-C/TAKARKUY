from decimal import Decimal
from random import Random
from types import SimpleNamespace

from django.test import TestCase

from apps.catalog.models import Ingredient, RecipeTag

from .planner import (
    HALAL_TAG,
    _balance_days,
    _candidate_pool,
    build_plan,
    meal_cost_cap,
    replacement_options,
    spend_floor,
)
from .protein_groups import GROUP_BY_CODE, NOT_MAIN_PROTEIN, main_protein_group

ALL_MEALS = ["sarapan", "makan_siang", "makan_malam"]


def plan_codes(result):
    return [meal["recipe_code"] for day in result["schedule"] for meal in day["meals"]]


def fake_item(code, cost, group):
    return {
        "recipe": SimpleNamespace(pk=code),
        "cost": cost,
        "tags": set(),
        "nutrition": {"protein": Decimal(cost % 30), "calories": Decimal(300)},
        "protein_group": group,
    }


class PlannerVarietyTests(TestCase):
    fixtures = ["catalog_seed"]

    def plan(self, **overrides):
        inputs = {
            "budget": Decimal("300000"),
            "days": 7,
            "servings": 2,
            "meal_types": ALL_MEALS,
            "targets": ["seimbang"],
            "exclude_ingredients": [],
        }
        inputs.update(overrides)
        return build_plan(**inputs)

    def test_recipes_without_halal_tag_are_never_planned(self):
        first = plan_codes(self.plan(seed=1))
        RecipeTag.objects.filter(recipe_id__in=first, tag=HALAL_TAG).delete()
        for seed in range(3):
            self.assertFalse(set(first) & set(plan_codes(self.plan(seed=seed))))

    def test_no_halal_recipes_means_no_plan(self):
        RecipeTag.objects.filter(tag=HALAL_TAG).delete()
        with self.assertRaisesMessage(ValueError, "Belum ada resep siap hitung"):
            self.plan()

    def test_same_seed_repeats_and_new_seeds_vary(self):
        self.assertEqual(plan_codes(self.plan(seed=7)), plan_codes(self.plan(seed=7)))
        plans = {tuple(plan_codes(self.plan(seed=seed))) for seed in range(4)}
        self.assertGreater(len(plans), 1)

    def test_nutrition_targets_vary_by_seed_and_keep_limits(self):
        plans = set()
        for seed in range(3):
            result = self.plan(
                budget=Decimal("500000"), targets=["tinggi_protein", "rendah_kalori"], seed=seed
            )
            plans.add(tuple(plan_codes(result)))
            for day in result["schedule"]:
                self.assertGreaterEqual(day["protein"], result["protein_floor"])
                self.assertLessEqual(day["calories"], result["calorie_cap"])
        self.assertGreater(len(plans), 1)

    def test_budget_is_an_upper_limit_not_a_spending_goal(self):
        totals = set()
        for seed in range(6):
            result = self.plan(budget=Decimal("1000000"), servings=1, seed=seed)
            self.assertTrue(result["within_budget"])
            self.assertLessEqual(result["total"], Decimal("1000000"))
            self.assertEqual(result["difference"], (1000000 - result["total"]) // 100 * 100)
            totals.add(result["total"])
        # A large budget no longer forces the priciest recipes every time.
        self.assertGreater(len(totals), 1)
        self.assertLess(min(totals), result["catalog_ceiling"])

    def test_nutrition_plan_also_treats_budget_as_limit(self):
        for seed in range(3):
            result = self.plan(budget=Decimal("1000000"), targets=["tinggi_protein"], seed=seed)
            self.assertLessEqual(result["total"], Decimal("1000000"))
            for day in result["schedule"]:
                self.assertGreaterEqual(day["protein"], result["protein_floor"])

    def test_total_stays_between_sixty_percent_and_budget(self):
        self.assertEqual(spend_floor(Decimal("150000")), 90000)
        for seed in range(4):
            result = self.plan(budget=Decimal("150000"), seed=seed)
            self.assertTrue(result["within_budget"])
            self.assertGreaterEqual(result["total"], 90000)
            self.assertLessEqual(result["total"], 150000)

    def test_single_menu_cost_is_capped_by_budget_share(self):
        cap = meal_cost_cap(Decimal("150000"), 7, 3)
        self.assertEqual(cap, 14285)
        for seed in range(3):
            result = self.plan(budget=Decimal("150000"), seed=seed)
            self.assertEqual(result["meal_cost_cap"], cap)
            for day in result["schedule"]:
                for meal in day["meals"]:
                    self.assertLessEqual(meal["cost"], cap)

    def test_replacement_options_keep_plan_within_budget(self):
        inputs = dict(
            budget=Decimal("300000"),
            days=7,
            servings=2,
            meal_types=ALL_MEALS,
            targets=["seimbang"],
            exclude_ingredients=[],
        )
        result = build_plan(**inputs, seed=4)
        schedule = [
            {m["type"]: m["recipe_code"] for m in day["meals"]} for day in result["schedule"]
        ]
        options = replacement_options(
            **inputs, schedule=schedule, day=1, meal="makan_malam", current_total=result["total"]
        )
        self.assertTrue(options)
        self.assertNotIn(schedule[0]["makan_malam"], {o["recipe_code"] for o in options})
        headroom = 300000 - result["total"]
        self.assertTrue(all(o["delta"] <= headroom for o in options))
        # With no budget headroom, only menus that cost the same or less remain.
        tight = replacement_options(
            **{**inputs, "budget": Decimal(result["total"])},
            schedule=schedule,
            day=1,
            meal="makan_malam",
            current_total=result["total"],
        )
        self.assertLess(len(tight), len(options))
        self.assertTrue(all(o["delta"] <= 0 for o in tight))


class CandidatePoolTests(TestCase):
    def test_pool_is_bounded_keeps_cheapest_and_spans_prices(self):
        groups = ["ayam", "telur", "ikan", "tahu_tempe"]
        items = [fake_item(f"R{i}", 1000 + i * 100, groups[i % 4]) for i in range(200)]
        pool = _candidate_pool(items, 40, 7, Random(3), set(), ["seimbang"])
        costs = sorted(item["cost"] for item in pool)
        self.assertEqual(len(pool), 40)
        self.assertEqual(len({item["recipe"].pk for item in pool}), 40)
        self.assertEqual(costs[:7], [1000 + i * 100 for i in range(7)])
        self.assertGreater(costs[-1], items[-20]["cost"])

    def test_pool_spreads_protein_groups(self):
        items = [fake_item(f"A{i}", 1000 + i * 10, "ayam") for i in range(150)]
        items += [fake_item(f"I{i}", 1005 + i * 30, "ikan") for i in range(50)]
        pool = _candidate_pool(items, 40, 1, Random(5), set(), ["seimbang"])
        fish = sum(item["protein_group"] == "ikan" for item in pool)
        # Fish is a quarter of the catalog; group balancing should lift its share.
        self.assertGreater(fish, 10)

    def test_small_catalog_keeps_every_recipe(self):
        items = [fake_item(f"R{i}", 1000 + i, "ayam") for i in range(12)]
        pool = _candidate_pool(items, 40, 7, Random(1), set(), ["seimbang"])
        self.assertEqual({item["recipe"].pk for item in pool}, {f"R{i}" for i in range(12)})

    def test_balance_days_separates_same_protein_without_changing_recipes(self):
        chosen = {
            "makan_siang": [fake_item("L1", 1, "ayam"), fake_item("L2", 1, "ikan")],
            "makan_malam": [fake_item("D1", 1, "ayam"), fake_item("D2", 1, "ikan")],
        }
        before = {meal: sorted(i["recipe"].pk for i in items) for meal, items in chosen.items()}
        balanced = _balance_days(chosen, ("makan_siang", "makan_malam"), {})
        for day in range(2):
            self.assertNotEqual(
                balanced["makan_siang"][day]["protein_group"],
                balanced["makan_malam"][day]["protein_group"],
            )
        after = {meal: sorted(i["recipe"].pk for i in items) for meal, items in balanced.items()}
        self.assertEqual(before, after)


class ProteinGroupTests(TestCase):
    fixtures = ["catalog_seed"]

    def test_egg_codes_are_not_chicken(self):
        links = [SimpleNamespace(ingredient_id="ING-TELUR-AYAM-BROILER", quantity=100)]
        self.assertEqual(main_protein_group(links), "telur")

    def test_heaviest_protein_wins_and_vegetables_do_not_count(self):
        links = [
            SimpleNamespace(ingredient_id="ING-TELUR-AYAM-BROILER", quantity=50),
            SimpleNamespace(ingredient_id="ING-TEMPE", quantity=120),
            SimpleNamespace(ingredient_id="ING-KACANG-PANJANG", quantity=300),
        ]
        self.assertEqual(main_protein_group(links), "tahu_tempe")

    def test_every_catalog_protein_is_classified(self):
        codes = set(Ingredient.objects.filter(category="protein").values_list("pk", flat=True))
        self.assertFalse(codes - set(GROUP_BY_CODE) - NOT_MAIN_PROTEIN)
