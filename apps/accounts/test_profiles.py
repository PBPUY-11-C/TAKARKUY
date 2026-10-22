from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import patch

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import SignUpForm
from .models import AuthRateBucket, UserProfile
from .rate_limits import AuthLimited, client_ip, reserve_auth_attempt


class IdentityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "Penakar", "dina@example.com", "Password!827"
        )

    def test_username_and_email_authenticate_case_insensitively(self):
        for name in ("penakar", "PENAKAR", "DINA@EXAMPLE.COM"):
            self.assertEqual(authenticate(username=name, password="Password!827"), self.user)
        self.assertIsNone(authenticate(username="penakar", password="wrong"))
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(authenticate(username="penakar", password="Password!827"))

    def test_email_username_legacy_is_preserved_and_can_log_in(self):
        user = get_user_model().objects.create_user("legacy@example.com", "", "Password!827")
        self.assertEqual(authenticate(username="LEGACY@EXAMPLE.COM", password="Password!827"), user)
        user.refresh_from_db()
        self.assertEqual(user.username, "legacy@example.com")

    def test_database_enforces_both_case_insensitive_indexes(self):
        for username, email in (("pENAKAR", "other@example.com"), ("other", "DINA@EXAMPLE.COM")):
            with (
                self.subTest(username=username),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                get_user_model().objects.create_user(username, email)
        get_user_model().objects.create_user("blank-one")
        get_user_model().objects.create_user("blank-two")

    def test_new_username_requires_ascii_and_no_at_sign(self):
        for name in ("someone@example.com", "ab", "nama spasi", "alfredó"):
            form = SignUpForm(
                {
                    "username": name,
                    "full_name": "Dina",
                    "email": "new@example.com",
                    "password1": "Password!827",
                    "password2": "Password!827",
                }
            )
            self.assertFalse(form.is_valid())
            self.assertIn("username", form.errors)

    def test_migration_preflight_stops_without_mutating_users(self):
        migration = import_module("apps.accounts.migrations.0002_case_insensitive_identity")
        from django.apps import apps

        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX accounts_user_username_ci")
        get_user_model().objects.create_user("pENAKAR", "other@example.com")
        with self.assertRaisesRegex(RuntimeError, "tidak ada akun digabung"):
            migration.check_conflicts(apps, connection.schema_editor())
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_migration_email_conflicts_stop_without_deleting_records(self):
        from django.apps import apps

        migration = import_module("apps.accounts.migrations.0002_case_insensitive_identity")
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX accounts_user_email_ci")
        get_user_model().objects.create_user("other", "DINA@example.com")
        with self.assertRaisesRegex(RuntimeError, "email ganda"):
            migration.check_conflicts(apps, connection.schema_editor())
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_migration_rejects_legacy_username_email_shadowing(self):
        from django.apps import apps

        migration = import_module("apps.accounts.migrations.0002_case_insensitive_identity")
        get_user_model().objects.create_user("dina@example.com")
        with self.assertRaisesRegex(RuntimeError, "bertabrakan"):
            migration.check_conflicts(apps, connection.schema_editor())


class ProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "penakar", "dina@example.com", "Password!827"
        )
        self.other = get_user_model().objects.create_user(
            "other", "other@example.com", "Password!827"
        )
        self.client.force_login(self.user)

    def details(self, **changes):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        return {
            "action": "account",
            "full_name": "Dina Putri",
            "username": "penakar",
            "email": "dina@example.com",
            "version": profile.version,
            **changes,
        }

    def test_profile_write_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("modul3"), self.details()).status_code, 403)


class RateLimitTests(TestCase):
    def request(self, ip="192.0.2.1", forwarded=None):
        data = {"REMOTE_ADDR": ip}
        if forwarded is not None:
            data["HTTP_X_FORWARDED_FOR"] = forwarded
        return RequestFactory().post("/login/", **data)

    def test_identity_limit_shared_between_browsers_and_counter_is_hashed(self):
        now = timezone.now()
        for i in range(10):
            reserve_auth_attempt(
                self.request(f"192.0.2.{i + 1}"), "login", "Private@Example.com", now=now
            )
        with self.assertRaises(AuthLimited):
            reserve_auth_attempt(
                self.request("198.51.100.1"), "login", "PRIVATE@example.com", now=now
            )
        self.assertTrue(
            all(
                len(key) == 64 and "Private" not in key
                for key in AuthRateBucket.objects.values_list("key", flat=True)
            )
        )
        reserve_auth_attempt(
            self.request(), "login", "private@example.com", now=now + timedelta(minutes=16)
        )

    def test_email_and_username_share_the_same_account_counter(self):
        get_user_model().objects.create_user("penakar", "dina@example.com")
        for i in range(10):
            reserve_auth_attempt(
                self.request(), "login", "penakar" if i % 2 else "DINA@example.com"
            )
        with self.assertRaises(AuthLimited):
            reserve_auth_attempt(self.request(), "login", "PENAKAR")

    def test_ip_limit_remains_even_when_identity_changes(self):
        for i in range(30):
            reserve_auth_attempt(self.request(), "signup", f"different{i}@example.com")
        with self.assertRaises(AuthLimited):
            reserve_auth_attempt(self.request(), "signup", "another@example.com")

    def test_public_login_signup_and_admin_login_return_429(self):
        # Password hashing must not let this test cross a real quota window.
        with patch("apps.accounts.rate_limits.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 10, 5, 9, 1, tzinfo=UTC)
            for path, field, limit in (
                (reverse("login"), "username", 10),
                (reverse("signup"), "email", 5),
                (reverse("admin:login"), "username", 10),
            ):
                with self.subTest(path=path):
                    AuthRateBucket.objects.all().delete()
                    for _ in range(limit):
                        response = self.client.post(
                            path, {field: "no-account@example.com", "password": "wrong"}
                        )
                        self.assertNotEqual(response.status_code, 429)
                    response = Client().post(
                        path, {field: "NO-ACCOUNT@example.com", "password": "wrong"}
                    )
                    self.assertEqual(response.status_code, 429)
                    self.assertGreater(int(response["Retry-After"]), 0)

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=[])
    def test_untrusted_forwarded_header_cannot_spoof_identity_ip(self):
        self.assertEqual(client_ip(self.request(forwarded="203.0.113.5")), "192.0.2.1")

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_trusted_proxy_chain_uses_first_untrusted_hop_from_right(self):
        self.assertEqual(
            client_ip(self.request("10.0.0.2", "198.51.100.99, 203.0.113.8, 10.0.0.3")),
            "203.0.113.8",
        )
        self.assertEqual(client_ip(self.request("10.0.0.2", "invalid")), "10.0.0.2")

    def test_csrf_failure_does_not_consume_auth_quota(self):
        Client(enforce_csrf_checks=True).post(reverse("login"), {"username": "guess"})
        self.assertFalse(AuthRateBucket.objects.exists())
