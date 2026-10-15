from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
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

    def test_guest_redirect_and_empty_account_no_example_figures(self):
        self.assertEqual(Client().get(reverse("modul5")).status_code, 302)
        response = self.client.get(reverse("modul5"))
        self.assertContains(response, "Belum ada rencana untuk hari ini")
        self.assertContains(response, "Masakan yang dicatat di Recipe Book")
        self.assertNotContains(response, "Rp 420")
        self.assertEqual(response.context["cooking_count"], 0)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_all_overlapping_saved_plans_are_separate_drafts_and_other_accounts_excluded(self):
        first = self.plan()
        second = self.plan(title="Rencana B")
        second.inputs = {"budget": 200000}
        second.snapshot = {"total": 120000}
        second.save()
        self.plan(status="draft", title="Draft rahasia")
        self.plan(user=self.other, title="Rencana tetangga")
        self.plan(title="Sudah lewat", offset=-5)
        self.plan(title="Belum mulai", offset=2)
        response = self.client.get(reverse("modul5"))
        self.assertEqual({p.pk for p in response.context["plans"]}, {first.pk, second.pk})
        self.assertContains(response, "Rp 50.000")
        self.assertContains(response, "Rp 80.000")
        self.assertNotContains(response, "Rp 130.000")
        for title in ("Draft rahasia", "Rencana tetangga", "Sudah lewat"):
            self.assertNotContains(response, title)
        # A plan starting later is not active today, but its days show in the 7-day panel.
        self.assertNotIn("Belum mulai", {plan.title for plan in response.context["plans"]})
        self.assertContains(response, "Belum mulai", count=3)
        # Today: one meal from each active plan (2). The 7-day panel adds the next
        # days of those plans (2 + 2) and of "Belum mulai" (3); drafts and other
        # accounts never appear.
        self.assertContains(response, "Nama snapshot", count=9)
        self.assertNotContains(response, "Rencana tetangga")
        self.assertNotContains(response, "Resep baru")

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

    def test_priority_sources_unknown_dates_and_expired_are_distinct(self):
        for source in ("label", "manual", "estimate"):
            self.stock(name=source, expiry_source=source)
        self.stock(name="Tanpa tanggal", estimated_expires_on=None)
        self.stock(name="Status tidak diketahui", expiry_source="unknown")
        self.stock(name="Lewat", estimated_expires_on=self.today - timedelta(days=1))
        self.stock(name="Stok habis", quantity=0)
        self.stock(name="Diarsipkan", archived_at=timezone.now())
        self.stock(name="Milik tetangga", user=self.other)
        result = dashboard_data(self.user)
        self.assertEqual(
            result["stock_counts"], {"total": 6, "soon": 3, "unknown": 2, "expired": 1}
        )
        self.assertEqual(len(result["stock_groups"]["soon"]), 3)
        response = self.client.get(reverse("modul5"))
        for text in (
            "Label kemasan",
            "Manual",
            "Estimasi",
            "Tanggal belum diketahui",
            "Lewat tanggal",
        ):
            self.assertContains(response, text)
        for text in ("Stok habis", "Diarsipkan", "Milik tetangga"):
            self.assertNotContains(response, text)

    def test_eight_queries_do_not_grow_with_number_of_plans_and_batches(self):
        # +2 bounded queries since the 7-day schedule and unsaved-draft notice.
        self.plan()
        self.stock()
        with self.assertNumQueries(8):
            dashboard_data(self.user)
        for index in range(12):
            self.plan(title=f"Plan {index}")
            self.stock(name=f"Item {index}")
            self.stock(name=f"Unknown {index}", estimated_expires_on=None)
        with self.assertNumQueries(8):
            data = dashboard_data(self.user)
        self.assertEqual(len(data["plans"]), 13)
        self.assertEqual(len(data["stock_groups"]["soon"]), 3)
        self.assertEqual(len(data["stock_groups"]["unknown"]), 3)
        # Includes two extra queries for session and auth; templates must not
        # secretly load relations after the eight business-data queries.
        with self.assertNumQueries(10):
            self.client.get(reverse("modul5"))

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

    def test_stored_titles_and_food_names_are_escaped(self):
        plan = self.plan(title='<script>alert("bad")</script>')
        self.stock(name='<img src=x onerror="alert(1)">')
        response = self.client.get(reverse("modul5"))
        self.assertNotContains(response, plan.title)
        self.assertContains(response, "&lt;script&gt;")


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

    def test_week_panel_names_the_plan_and_marks_skipped_meals(self):
        plan = self.plan(title="Bekal Kos", offset=1)
        plan.meals.filter(day=1).update(status="skipped")
        response = self.client.get(reverse("modul5"))
        self.assertContains(response, "Bekal Kos")
        self.assertContains(response, "dilewati")

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

    def test_dashboard_shows_unsaved_draft_link_but_not_clean_draft(self):
        draft = self.plan(status="draft", title="Draft")
        self.assertEqual(dashboard_data(self.user)["unsaved_draft"], draft)
        response = self.client.get(reverse("modul5"))
        self.assertContains(response, f"?plan={draft.pk}")
        saved = self.plan(title="Tersimpan")
        draft.source_plan, draft.source_version = saved, saved.version
        draft.snapshot, draft.inputs = saved.snapshot, saved.inputs
        draft.save()
        self.assertIsNone(dashboard_data(self.user)["unsaved_draft"])
