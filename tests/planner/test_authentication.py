from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.planner.models import BudgetPlan


class PlannerAuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("member", password="Demo1234!")

    @patch("apps.planner.views.build_plan")
    def test_guest_get_and_post_are_blocked_on_every_page_alias(self, builder):
        self.client.cookies["takarkuy_trial"] = "old-trial-cookie"
        for path in ("/planner/", "/modul1/"):
            for method in ("get", "post"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path)
                    self.assertRedirects(response, f"{reverse('login')}?next={path}")
            response = self.client.get(path + "?new=1&plan=not-an-owned-plan")
            self.assertRedirects(
                response, f"{reverse('login')}?next={path}%3Fnew%3D1%26plan%3Dnot-an-owned-plan"
            )
        builder.assert_not_called()
        self.assertFalse(BudgetPlan.objects.exists())
        self.assertNotIn("guest_last_plan", self.client.session)

    def test_login_returns_to_requested_planner_alias(self):
        for path in ("/planner/", "/modul1/"):
            with self.subTest(path=path):
                self.client.logout()
                response = self.client.post(
                    reverse("login"),
                    {"username": "member", "password": "Demo1234!", "next": path},
                )
                self.assertRedirects(response, path)
                self.assertContains(self.client.get(path), "Buat rencana")

    def test_logout_revokes_planner_access(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("modul1")).status_code, 200)
        self.client.post(reverse("logout"))
        for path in ("/planner/", "/modul1/"):
            self.assertRedirects(self.client.get(path), f"{reverse('login')}?next={path}")

    def test_landing_calculator_remains_public(self):
        response = self.client.get(reverse("landing"))
        self.assertContains(response, 'id="budget-calculator"')
        self.assertNotContains(response, "Tanpa akun 3x")
