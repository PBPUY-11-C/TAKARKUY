import json
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.budget_planner.models import BudgetPlan

from .middleware import MaintenanceMiddleware


@override_settings(MAINTENANCE_MODE=True)
class MaintenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username="penakar")
        cls.staff = user_model.objects.create_user(
            username="admin-maintenance", password="TestAdmin!827", is_staff=True
        )
        cls.inactive_staff = user_model.objects.create_user(
            username="inactive-admin", is_staff=True, is_active=False
        )

    def test_all_public_pages_are_closed_including_login_signup_and_unknown_routes(self):
        for path in (
            "/",
            "/login/",
            "/signup/",
            "/modul1/",
            "/modul2/",
            "/modul3/",
            "/modul4/",
            "/modul5/",
            "/unknown/",
            "/admin-other/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, "Sedang dalam pengembangan", status_code=503)
                self.assertEqual(response["Retry-After"], "3600")
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_existing_user_session_does_not_bypass_maintenance(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("modul5")).status_code, 503)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_signup_post_is_rejected_without_creating_accounts(self):
        client = Client(enforce_csrf_checks=True)
        count = get_user_model().objects.count()
        response = client.post(reverse("signup"), {"email": "new@example.com"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(get_user_model().objects.count(), count)

    def test_json_api_is_rejected_before_body_parsing_or_gemini_calls(self):
        client = Client(enforce_csrf_checks=True)
        with patch("apps.pantry.receipt_ocr.generate_json") as generate:
            response = client.post(
                reverse("modul2-suggestions"), data="invalid-json", content_type="application/json"
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "maintenance")
        generate.assert_not_called()

    def test_json_accept_header_returns_json_for_api_get(self):
        response = self.client.get(reverse("modul2-recipes"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["retry_after"], 3600)

    def test_multipart_upload_is_rejected_without_reading_body(self):
        request = RequestFactory().post(reverse("modul2-ocr-fallback"), {"photo": "unread"})
        request.user = AnonymousUser()
        downstream = Mock(return_value=HttpResponse("unexpected"))
        response = MaintenanceMiddleware(downstream)(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["code"], "maintenance")
        self.assertFalse(request._read_started)
        downstream.assert_not_called()

    def test_named_api_get_returns_json_even_without_accept_header(self):
        response = self.client.get(reverse("modul2-recipes"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "maintenance")

    def test_planner_write_is_closed_with_json_without_creating_a_plan(self):
        count = BudgetPlan.objects.count()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("modul1-plan-save", args=[uuid4()]), {"title": "Blocked"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "maintenance")
        self.assertEqual(BudgetPlan.objects.count(), count)

    def test_admin_login_remains_available_and_authenticates_staff(self):
        path = reverse("admin:login")
        self.assertEqual(self.client.get(path).status_code, 200)
        response = self.client.post(
            path,
            {
                "username": self.staff.username,
                "password": "TestAdmin!827",
                "next": reverse("admin:index"),
            },
        )
        self.assertRedirects(response, reverse("admin:index"))
        self.assertEqual(self.client.get(reverse("modul5")).status_code, 200)

    def test_admin_login_keeps_csrf_protection(self):
        response = Client(enforce_csrf_checks=True).post(
            reverse("admin:login"), {"username": self.staff.username, "password": "TestAdmin!827"}
        )
        self.assertEqual(response.status_code, 403)

    def test_normal_user_cannot_access_admin(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_staff_can_test_application_but_still_needs_csrf_for_writes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        response = client.get(reverse("modul5"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
        response = client.post(reverse("modul2-items"), "{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_inactive_staff_cannot_bypass(self):
        request = RequestFactory().get("/modul5/")
        request.user = self.inactive_staff
        downstream = Mock()
        self.assertEqual(MaintenanceMiddleware(downstream)(request).status_code, 503)
        downstream.assert_not_called()

    def test_query_parameters_and_headers_do_not_bypass(self):
        response = self.client.get(
            "/?maintenance=false&admin=true", HTTP_X_MAINTENANCE_BYPASS="true"
        )
        self.assertEqual(response.status_code, 503)

    def test_static_prefix_is_not_a_bypass_for_unserved_routes(self):
        self.assertEqual(self.client.get("/static/not-a-real-file/").status_code, 503)

    @override_settings(MAINTENANCE_MODE=False)
    def test_switching_off_restores_normal_pages_and_authorization(self):
        for name in ("landing", "login", "signup", "modul1"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("modul5")).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("modul5")).status_code, 200)
