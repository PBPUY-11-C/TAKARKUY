import json
from datetime import timedelta
from decimal import Decimal
from random import Random
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe
from apps.pantry.models import PantryItem, PantryMovement

from .models import BudgetPlan, ShoppingListItem
from .planner import RICE_CODE, _candidate_pool, build_plan, rice_included
from .services import clean_inputs, pantry_priority, save_plan, stored_inputs, write_draft

TODAY = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))


def lunch(code, **inputs):
    data = {
        "budget": "1000000",
        "days": 1,
        "servings": 1,
        "meal_types": ["makan_siang"],
        "targets": ["seimbang"],
        "exclude_ingredients": "",
        **inputs,
    }
    form = clean_inputs(data)
    return form, build_plan(**form.cleaned_data, fixed_schedule=[{"makan_siang": code}])


def lunch_codes():
    """A lunch lauk without carbohydrates, and a lunch that already has rice."""
    lunches = Recipe.objects.filter(
        meal_type="makan_siang", is_active=True, is_plannable=True
    ).prefetch_related("recipeingredient_set__ingredient")
    lauk = next(
        recipe.pk
        for recipe in lunches
        if not any(
            link.ingredient.category == "karbohidrat" for link in recipe.recipeingredient_set.all()
        )
    )
    with_rice = next(
        recipe.pk
        for recipe in lunches
        if any(link.ingredient_id == RICE_CODE for link in recipe.recipeingredient_set.all())
    )
    return lauk, with_rice


def meal(result):
    return result["schedule"][0]["meals"][0]


def shopping_codes(result):
    return {
        item["ingredient_code"] for group in result["shopping_groups"] for item in group["items"]
    }


class RiceTests(TestCase):
    fixtures = ["catalog_seed"]

    @classmethod
    def setUpTestData(cls):
        cls.lauk, cls.with_carbs = lunch_codes()

    def test_auto_rice_follows_servings_and_low_calorie_target(self):
        self.assertTrue(rice_included("auto", 2, ["seimbang"]))
        self.assertFalse(rice_included("auto", 3, ["seimbang"]))
        self.assertFalse(rice_included("auto", 1, ["rendah_kalori"]))
        self.assertTrue(rice_included("yes", 6, ["rendah_kalori"]))
        self.assertFalse(rice_included("no", 1, ["seimbang"]))

    def test_lauk_gets_priced_rice_only_when_enabled(self):
        _, plain = lunch(self.lauk, rice="no")
        _, rice = lunch(self.lauk, rice="yes")
        self.assertNotIn("with_rice", meal(plain))  # older snapshots stay identical
        self.assertTrue(meal(rice)["with_rice"])
        self.assertNotIn(RICE_CODE, shopping_codes(plain))
        rice_row = next(
            item
            for group in rice["shopping_groups"]
            for item in group["items"]
            if item["ingredient_code"] == RICE_CODE
        )
        self.assertEqual(rice_row["quantity"], 80)
        self.assertGreater(rice["total"], plain["total"])
        self.assertGreater(meal(rice)["calories"], meal(plain)["calories"])

    def test_no_rice_for_carb_recipes_or_when_rice_is_avoided(self):
        _, carbs = lunch(self.with_carbs, rice="yes")
        self.assertNotIn("with_rice", meal(carbs))
        _, avoided = lunch(self.lauk, rice="yes", exclude_ingredients="beras")
        self.assertNotIn("with_rice", meal(avoided))

    def test_missing_choice_means_no_rice_and_is_stored(self):
        form, result = lunch(self.lauk)
        self.assertEqual(form.cleaned_data["rice"], "no")
        self.assertNotIn("with_rice", meal(result))
        form, _ = lunch(self.lauk, rice="auto")
        self.assertEqual(stored_inputs(form)["rice"], "auto")


class PantryPriorityTests(TestCase):
    def item(self, code, cost, hits=0):
        return {
            "recipe": SimpleNamespace(pk=code),
            "cost": cost,
            "tags": set(),
            "protein_group": code,
            "nutrition": {"protein": Decimal(1), "calories": Decimal(1)},
            "pantry_hits": hits,
        }

    def test_pool_keeps_recipes_that_use_expiring_stock(self):
        items = [self.item(f"R{index:03}", 1000 + index) for index in range(100)]
        items.append(self.item("PANTRY", 99999, hits=1))
        pool = _candidate_pool(items, 10, 1, Random(1), set(), ["seimbang"])
        self.assertIn("PANTRY", {item["recipe"].pk for item in pool})
        self.assertEqual(len(pool), 10)

    def test_without_pantry_hits_the_pool_is_unchanged(self):
        items = [self.item(f"R{index:03}", 1000 + index) for index in range(100)]
        plain = [
            {key: value for key, value in item.items() if key != "pantry_hits"} for item in items
        ]
        first = _candidate_pool(items, 10, 1, Random(7), set(), ["seimbang"])
        second = _candidate_pool(plain, 10, 1, Random(7), set(), ["seimbang"])
        self.assertEqual(
            [item["recipe"].pk for item in first], [item["recipe"].pk for item in second]
        )


class PlanPantryTests(TestCase):
    fixtures = ["catalog_seed"]

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("belanja", password="Demo1234!")
        cls.other = get_user_model().objects.create_user("lain", password="Demo1234!")
        cls.lauk = lunch_codes()[0]

    def setUp(self):
        self.client.force_login(self.user)
        form, result = lunch(self.lauk, rice="yes")
        draft = write_draft(self.user, stored_inputs(form), result)
        self.plan = save_plan(self.user, draft.pk, draft.version, "Belanja", TODAY)

    def batch(self, code, grams, days):
        return PantryItem.objects.create(
            user=self.user,
            session_id="test",
            name="Stok",
            quantity=grams,
            unit="g",
            grams_per_unit=1,
            ingredient_id=code,
            expiry_source="estimate",
            estimated_expires_on=TODAY + timedelta(days=days) if days is not None else None,
        )

    def add(self, items, version=None, plan=None):
        plan = plan or self.plan
        return self.client.post(
            reverse("modul1-plan-pantry", args=[plan.pk]),
            json.dumps({"version": plan.version if version is None else version, "items": items}),
            content_type="application/json",
        )

    def test_pantry_priority_only_counts_stock_expiring_soon(self):
        self.batch(RICE_CODE, 500, 2)
        self.batch("ING-TOMAT", 500, 10)
        unknown = self.batch("ING-KENTANG", 500, None)
        unknown.expiry_source = "unknown"
        unknown.save()
        self.assertEqual(pantry_priority(self.user), {RICE_CODE})

    def test_bought_items_move_into_pantry_once(self):
        response = self.add([{"ingredient_code": RICE_CODE, "grams": 80}])
        self.assertEqual(response.status_code, 201)
        stock = PantryItem.objects.get(user=self.user, ingredient_id=RICE_CODE)
        self.assertEqual((stock.quantity, stock.unit, stock.source), (80, "g", "manual"))
        self.assertTrue(PantryMovement.objects.filter(batch=stock, kind="in").exists())
        self.assertIsNotNone(stock.estimated_expires_on)  # rice has a shelf-life reference
        self.assertTrue(
            ShoppingListItem.objects.get(plan=self.plan, ingredient_id=RICE_CODE).added_to_pantry_at
        )
        # A double click replays; a different request for the same item is refused.
        self.assertEqual(self.add([{"ingredient_code": RICE_CODE, "grams": 80}]).status_code, 201)
        self.assertEqual(self.add([{"ingredient_code": RICE_CODE, "grams": 90}]).status_code, 409)
        self.assertEqual(PantryItem.objects.filter(user=self.user).count(), 1)

    def test_invalid_purchase_requests_are_rejected(self):
        self.assertEqual(
            self.add([{"ingredient_code": "ING-TIDAK-ADA", "grams": 5}]).status_code, 400
        )
        self.assertEqual(self.add([{"ingredient_code": RICE_CODE, "grams": 0}]).status_code, 400)
        self.assertEqual(
            self.add([{"ingredient_code": RICE_CODE, "grams": 80}], version=99).status_code, 409
        )
        self.client.force_login(self.other)
        self.assertEqual(self.add([{"ingredient_code": RICE_CODE, "grams": 80}]).status_code, 404)
        self.assertFalse(PantryItem.objects.exists())

    def test_draft_plans_must_be_saved_first(self):
        draft = BudgetPlan.objects.get(user=self.user, status="draft")
        response = self.add([{"ingredient_code": RICE_CODE, "grams": 80}], plan=draft)
        self.assertEqual(response.status_code, 409)

    def test_plan_page_shows_pantry_stock_and_rice(self):
        self.batch(RICE_CODE, 50, 30)
        response = self.client.get(reverse("modul1") + f"?plan={self.plan.pk}")
        self.assertContains(response, "Sudah ada di Pantry 50 g · perlu beli 30 g")
        self.assertContains(response, "+ Nasi")
        self.assertContains(response, "Masukkan ke Pantry")
