from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.budget_planner.models import BudgetPlan, PlannedMeal
from apps.catalog.models import Recipe
from apps.pantry.models import PantryItem, PantryOperation
from apps.recipe_book.models import CookingHistory

from .services import JAKARTA, dashboard_data


class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("dapurku")
        self.other = get_user_model().objects.create_user("tetangga")
        self.client.force_login(self.user)
        self.today = timezone.localdate(timezone=JAKARTA)
        self.recipe = Recipe.objects.create(
            recipe_code="RCP-DASH", name="Resep baru", base_servings=2
        )

    def plan(self, user=None, title="Rencana A", status="saved", offset=0, **changes):
        plan = BudgetPlan.objects.create(
            user=user or self.user,
            title=title,
            status=status,
            starts_on=self.today + timedelta(days=offset),
            inputs={"budget": 150000},
            snapshot={"total": 100000},
            **changes,
        )
        for day in range(1, 4):
            PlannedMeal.objects.create(
                plan=plan,
                day=day,
                meal_type="sarapan",
                scheduled_on=plan.starts_on + timedelta(days=day - 1),
                recipe=self.recipe,
                servings=2,
                snapshot={"name": "Nama snapshot"},
            )
        return plan

    def stock(self, **changes):
        defaults = {
            "user": self.user,
            "session_id": "dash",
            "name": "Tempe",
            "quantity": 100,
            "unit": "g",
            "source": "manual",
            "expiry_source": "estimate",
            "estimated_expires_on": self.today + timedelta(days=1),
        }
        return PantryItem.objects.create(**{**defaults, **changes})

    def history(self, **changes):
        event = PantryOperation.objects.create(
            user=self.user, key=uuid4(), kind="cook", payload_hash="test"
        )
        return CookingHistory.objects.create(
            user=self.user,
            recipe=self.recipe,
            operation=event,
            recipe_name="Sup snapshot",
            servings=2,
            snapshot={},
            **changes,
        )

    @override_settings(MAINTENANCE_MODE=True)
    def test_api_maintenance_response_is_json(self):
        response = self.client.get(reverse("modul5-places"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "maintenance")

    def test_jakarta_today_not_utc_and_cooked_slot_not_offered_as_new_cooking(self):
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 5, 18, tzinfo=UTC)):
            self.today = timezone.localdate(timezone=JAKARTA)
            plan = self.plan()
            slot = plan.meals.get(day=1)
            slot.status = "cooked"
            slot.save()
            result = dashboard_data(self.user)
            self.assertEqual(result["today"].isoformat(), "2026-10-06")
            self.assertEqual(result["plans"][0].today_meals[0].pk, slot.pk)
            self.assertEqual(result["plans"][0].today_meals[0].status, "cooked")

    def test_history_survives_plan_delete_and_is_limited_to_three(self):
        plan = self.plan()
        for _ in range(4):
            self.history()
        entry = CookingHistory.objects.first()
        entry.planned_meal = plan.meals.first()
        entry.save()
        plan.delete()
        data = dashboard_data(self.user)
        self.assertEqual(data["cooking_count"], 4)
        self.assertEqual(len(data["recent_cooking"]), 3)
        self.assertEqual(data["recent_cooking"][0].recipe_name, "Sup snapshot")

    def test_missing_malformed_and_over_budget_values_are_not_fake_savings(self):
        plan = self.plan()
        plan.snapshot = {"total": "NaN"}
        plan.save()
        self.assertIsNone(dashboard_data(self.user)["plans"][0].remaining)
        plan.snapshot = {"total": 160000}
        plan.save()
        result = dashboard_data(self.user)["plans"][0]
        self.assertTrue(result.over_budget)
        self.assertEqual(result.remaining, Decimal(10000))


class DashboardWeekTests(TestCase):
    setUp = DashboardTests.setUp
    plan = DashboardTests.plan

    def test_week_includes_future_meals_in_one_query(self):
        self.plan(offset=2)
        data = dashboard_data(self.user)
        week = data["week"]
        self.assertEqual(
            [day["date"] for day in week], [self.today + timedelta(days=d) for d in range(1, 8)]
        )
        self.assertEqual([len(day["meals"]) for day in week], [0, 1, 1, 1, 0, 0, 0])
        self.assertEqual(week[1]["meals"][0]["name"], "Nama snapshot")
        baseline = self.week_queries()  # measured before more plans exist
        self.plan(title="Rencana B", offset=1)
        self.plan(title="Rencana C", offset=3)
        with self.assertNumQueries(baseline):
            dashboard_data(self.user)

    def week_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            dashboard_data(self.user)
        return len(captured)

    def test_remaining_budget_uses_net_shopping_cost(self):
        plan = self.plan()
        plan.snapshot = {"total": 100000, "net_total": 40000}
        plan.save()
        [shown] = dashboard_data(self.user)["plans"]
        self.assertEqual(shown.pk, plan.pk)
        self.assertEqual(shown.remaining, 110000)
