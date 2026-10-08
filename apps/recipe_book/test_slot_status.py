from datetime import date, datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.budget_planner.models import BudgetPlan
from apps.catalog.models import Ingredient

from . import tests as cooking
from .services import cooking_inputs, recipe_costs


class SlotStatusTests(TestCase):
    """Skip/undo of planned menus, rice on planner slots and Recipe Book filters."""

    setUp = cooking.CookingTests.setUp
    batch = cooking.CookingTests.batch
    post = cooking.CookingTests.post
    slot = cooking.CookingTests.slot

    def status(self, slot, status, version=None):
        return self.post(
            "modul4-slot-status",
            {
                "planned_meal": slot.pk,
                "status": status,
                "version": slot.plan.version if version is None else version,
            },
        )

    def test_skip_and_undo_bump_plan_version(self):
        slot = self.slot()
        response = self.status(slot, "skipped")
        self.assertEqual(response.status_code, 200)
        slot.refresh_from_db()
        slot.plan.refresh_from_db()
        self.assertEqual((slot.status, slot.plan.version), ("skipped", 2))
        self.assertEqual(self.status(slot, "planned").status_code, 200)
        slot.refresh_from_db()
        self.assertEqual(slot.status, "planned")

    def test_skip_rejects_stale_version_cooked_slot_and_other_user(self):
        slot = self.slot()
        self.assertEqual(self.status(slot, "skipped", version=99).status_code, 409)
        slot.status = "cooked"
        slot.save()
        self.assertEqual(self.status(slot, "skipped").status_code, 409)
        slot.plan.user = self.other
        slot.plan.save()
        self.assertEqual(self.status(slot, "planned").status_code, 404)

    def test_skip_requires_saved_plan(self):
        slot = self.slot()
        BudgetPlan.objects.filter(pk=slot.plan_id).update(status="draft")
        self.assertEqual(self.status(slot, "skipped").status_code, 409)

    def test_slot_with_rice_needs_rice_stock_when_cooking(self):
        rice = Ingredient.objects.create(
            ingredient_code="ING-BERAS-MEDIUM",
            name="Beras Medium",
            base_unit="g",
            category="karbohidrat",
            allergen_status="reviewed",
            allergens=[],
            allergen_source_url="https://example.org",
            calories_per_100g=350,
            protein_per_100g=8,
            carbs_per_100g=78,
            fat_per_100g=1,
        )
        slot = self.slot()
        slot.snapshot = {"name": self.recipe.name, "with_rice": True}
        slot.save()
        payload = {
            "recipe_code": self.recipe.pk,
            "servings": 2,
            "planned_meal": slot.pk,
            "version": slot.plan.version,
        }
        _, _, needs, ingredients, nutrition = cooking_inputs(self.user, payload)
        self.assertEqual(needs[rice.pk], 160)
        self.assertIn("nasi pendamping", ingredients[0]["name"])
        # 160 g rice (560 kkal) plus 100 g bayam (30 kkal) for two servings.
        self.assertEqual(nutrition["calories"], "590.0")
        response = self.client.get(reverse("modul4") + f"?slot={slot.pk}")
        self.assertContains(response, "dengan nasi dari rencana")

    def test_page_offers_skip_only_for_planned_slots(self):
        slot = self.slot()
        response = self.client.get(reverse("modul4") + f"?slot={slot.pk}")
        self.assertContains(response, "Lewati menu ini")
        slot.status = "skipped"
        slot.save()
        response = self.client.get(reverse("modul4") + f"?slot={slot.pk}")
        self.assertContains(response, "Batalkan lewati")

    def test_price_filter_hides_recipes_above_limit(self):
        with patch("apps.recipe_book.views.recipe_costs", return_value={"TEST-SUP": 12000}):
            cheap = self.client.get(reverse("modul4") + "?max_price=10000")
            fits = self.client.get(reverse("modul4") + "?max_price=15000")
        self.assertEqual(cheap.context["recipes"].paginator.count, 0)
        self.assertEqual(fits.context["recipes"].paginator.count, 1)
        # Unknown limits are ignored instead of filtering everything out.
        other = self.client.get(reverse("modul4") + "?max_price=123")
        self.assertIsNone(other.context["max_price"])

    def test_recipe_costs_skips_recipes_without_prices(self):
        # Without an imported price snapshot nothing is priced, and the page still works.
        self.assertEqual(recipe_costs(2, {"TEST-SUP"}), {})

    def test_soon_filter_uses_jakarta_date(self):
        # 18:00 UTC on 8 Oct is already 01:00 on 9 Oct in Jakarta.
        now = datetime(2026, 10, 8, 18, 0, tzinfo=dt_timezone.utc)
        self.batch(estimated_expires_on=date(2026, 10, 11))
        with patch("django.utils.timezone.now", return_value=now):
            response = self.client.get(reverse("modul4") + "?stock=soon")
        self.assertEqual(response.context["recipes"].paginator.count, 1)
