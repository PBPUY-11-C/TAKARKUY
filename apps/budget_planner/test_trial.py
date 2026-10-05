from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import GuestTrial
from .trial import COOKIE_NAME, WINDOW, record_success, trial_state


class GuestTrialTests(TestCase):
    def setUp(self):
        self.inputs = {
            "budget": "150000",
            "days": "1",
            "servings": "1",
            "meal_types": ["sarapan"],
            "targets": ["seimbang"],
        }
        self.plan = {
            "within_budget": True,
            "schedule": [],
            "shopping_groups": [],
            "total": Decimal("1234.00"),
            "difference": 148766,
            "snapshot": date(2026, 9, 28),
            "meal_labels": ["Pagi"],
            "meal_count": 1,
            "nutrition": {},
        }
        self.builder_patch = patch("apps.budget_planner.views.build_plan", return_value=self.plan)
        self.builder = self.builder_patch.start()
        self.addCleanup(self.builder_patch.stop)

    def calculate(self, client=None, **changes):
        return (client or self.client).post(reverse("modul1"), {**self.inputs, **changes})

    def test_initial_page_issues_signed_cookie_without_creating_usage(self):
        response = self.client.get(reverse("modul1"))
        self.assertContains(response, "Sisa percobaan: 3 dari 3")
        self.assertNotContains(response, "Guest bisa membuat")
        self.assertNotContains(response, "Daftar gratis")
        self.assertNotContains(response, 'class="trial-links"')
        self.assertEqual(GuestTrial.objects.count(), 0)
        cookie = response.cookies[COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertIn("no-store", response["Cache-Control"])

    def test_fourth_success_is_blocked_in_backend_and_last_result_survives_reload(self):
        for remaining in (2, 1, 0):
            response = self.calculate()
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"Sisa percobaan: {remaining} dari 3")
        response = self.calculate()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.builder.call_count, 3)
        self.assertEqual(GuestTrial.objects.get().successful_uses, 3)
        self.assertEqual(response.context["result"]["total"], Decimal("1234.00"))
        self.assertEqual(response.context["result"]["snapshot"], self.plan["snapshot"])
        self.assertContains(response, "Kuota percobaan sudah habis", status_code=429)
        page = self.client.get(reverse("modul1"))
        self.assertEqual(page.context["result"]["total"], Decimal("1234.00"))
        self.assertContains(page, "Rp 1.234")
        self.assertContains(page, 'class="calculate-button" disabled')

    def test_invalid_input_does_not_call_builder_or_consume_trial(self):
        self.assertEqual(self.calculate(days="0").status_code, 200)
        self.builder.assert_not_called()
        self.assertEqual(GuestTrial.objects.count(), 0)

    def test_unaffordable_plan_and_calculation_error_do_not_consume_trial(self):
        self.builder.return_value = {**self.plan, "within_budget": False}
        response = self.calculate()
        self.assertEqual(response.context["trial"]["remaining"], 3)
        self.builder.side_effect = ValueError("Belum tersedia.")
        response = self.calculate()
        self.assertEqual(response.context["error"], "Belum tersedia.")
        self.assertEqual(GuestTrial.objects.count(), 0)

    def test_window_starts_on_first_success_and_resets_exactly_after_24_hours(self):
        now = timezone.now()
        with patch("apps.budget_planner.trial.timezone.now", return_value=now):
            for _ in range(3):
                self.calculate()
        trial = GuestTrial.objects.get()
        self.assertEqual(trial.window_started_at, now)
        with patch(
            "apps.budget_planner.trial.timezone.now",
            return_value=now + WINDOW - timedelta(seconds=1),
        ):
            self.assertEqual(self.calculate().status_code, 429)
        with patch("apps.budget_planner.trial.timezone.now", return_value=now + WINDOW):
            response = self.calculate()
        self.assertEqual(response.context["trial"]["remaining"], 2)
        trial.refresh_from_db()
        self.assertEqual(trial.window_started_at, now + WINDOW)
        self.assertEqual(trial.successful_uses, 1)

    def test_cookie_replay_and_session_flush_do_not_reset_server_usage(self):
        self.client.get(reverse("modul1"))
        original_cookie = self.client.cookies[COOKIE_NAME].value
        for _ in range(3):
            self.calculate()
        session = self.client.session
        session.flush()
        self.client.cookies[COOKIE_NAME] = original_cookie
        self.assertEqual(self.calculate().status_code, 429)
        self.assertEqual(self.builder.call_count, 3)

    def test_authenticated_user_bypasses_trial_but_logout_keeps_guest_limit(self):
        for _ in range(3):
            self.calculate()
        self.client.force_login(get_user_model().objects.create_user(username="member"))
        for _ in range(4):
            draft = self.client.get(reverse("modul1")).context["plan"]
            data = {**self.inputs}
            if draft:
                data.update(plan_id=str(draft.pk), version=draft.version)
            response = self.client.post(reverse("modul1"), data, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context["trial"])
        self.client.post(reverse("logout"))
        self.assertEqual(self.calculate().status_code, 429)
        self.assertEqual(GuestTrial.objects.get().successful_uses, 3)

    def test_other_browser_gets_separate_quota_and_tampered_cookie_is_not_trusted(self):
        self.calculate()
        other = Client()
        other.cookies[COOKIE_NAME] = "invalid-signed-cookie"
        response = self.calculate(other)
        self.assertEqual(response.context["trial"]["remaining"], 2)
        self.assertEqual(GuestTrial.objects.count(), 2)

    def test_atomic_claim_does_not_trust_stale_counter(self):
        stale = GuestTrial()
        now = timezone.now()
        for _ in range(3):
            self.assertTrue(record_success(GuestTrial(id=stale.pk), now=now))
        self.assertFalse(record_success(stale, now=now))
        self.assertEqual(trial_state(stale, now)["remaining"], 0)

    def test_race_losing_final_slot_does_not_show_new_uncounted_plan(self):
        self.calculate()
        original = self.client.session["guest_last_plan"]
        with patch("apps.budget_planner.views.record_success", return_value=False):
            self.builder.return_value = {**self.plan, "total": 9999}
            response = self.calculate()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.context["result"]["total"], Decimal("1234.00"))
        self.assertEqual(self.client.session["guest_last_plan"], original)

    def test_database_constraint_and_csrf_protection(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GuestTrial.objects.create(successful_uses=4)
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("modul1"))
        self.assertEqual(self.calculate(client).status_code, 403)
        self.assertEqual(GuestTrial.objects.count(), 0)

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_trial_cookie_is_secure_in_production(self):
        response = self.client.get(reverse("modul1"), secure=True)
        self.assertTrue(response.cookies[COOKIE_NAME]["secure"])


class GuestTrialRealPlannerTests(TestCase):
    fixtures = ["catalog_seed.json"]

    def test_actual_plan_can_be_restored_without_losing_prices_and_types(self):
        response = self.client.post(
            reverse("modul1"),
            {
                "budget": "150000",
                "days": "2",
                "servings": "2",
                "meal_types": ["sarapan", "makan_siang"],
                "targets": ["seimbang"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["result"]["within_budget"])
        page = self.client.get(reverse("modul1"))
        self.assertEqual(page.context["result"], response.context["result"])
        self.assertNotContains(page, "Rp —")
        self.assertEqual(GuestTrial.objects.get().successful_uses, 1)
