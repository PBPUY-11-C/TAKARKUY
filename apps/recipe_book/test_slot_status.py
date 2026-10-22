from django.test import TestCase

from apps.budget_planner.models import BudgetPlan

from . import tests as cooking
from .services import recipe_costs


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

    def test_recipe_costs_skips_recipes_without_prices(self):
        # Without an imported price snapshot nothing is priced, and the page still works.
        self.assertEqual(recipe_costs(2, {"TEST-SUP"}), {})
