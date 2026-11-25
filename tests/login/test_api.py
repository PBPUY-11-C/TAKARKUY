import json
from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.catalog.models import Ingredient
from apps.login.models import FoodPreference, UserProfile

PASSWORD = "Demo1234!"


class AuthApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user(
            "penakar", "dina@example.com", PASSWORD, first_name="Dina", last_name="Sari"
        )
        cls.other = users.create_user("other", "other@example.com", PASSWORD)
        cls.ingredient = Ingredient.objects.create(
            ingredient_code="TEMPE", name="Tempe", category="protein", base_unit="g"
        )

    def post(self, url, data, client=None):
        return (client or self.client).post(
            url, data=json.dumps(data), content_type="application/json"
        )

    def version(self, user=None):
        return UserProfile.objects.get_or_create(user=user or self.user)[0].version

    def details(self, **changes):
        return {
            "full_name": "Dina Sari",
            "username": "penakar",
            "email": "dina@example.com",
            "avatar": "chef",
            "version": self.version(),
            **changes,
        }

    def preferences(self, **changes):
        return {
            "targets": ["tinggi_protein"],
            "meal_types": ["sarapan", "makan_malam"],
            "servings": 3,
            "allergens": ["susu"],
            "avoided_ingredients": ["TEMPE"],
            "version": self.version(),
            **changes,
        }

    # Login dan logout

    def test_login_accepts_form_body_like_pbp_django_auth(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/api/auth/login/", {"username": "DINA@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["status"], True)
        self.assertEqual(body["username"], "penakar")
        self.assertIn("message", body)
        self.assertEqual(client.get("/api/auth/profile/").status_code, 200)

    def test_login_also_accepts_json(self):
        response = self.post("/api/auth/login/", {"username": "penakar", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["status"], True)

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post("/api/auth/login/", {"username": "penakar", "password": "salah"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], False)
        self.assertIn("message", response.json())
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 403)

    def test_login_with_missing_fields_is_bad_request(self):
        response = self.client.post("/api/auth/login/", {"username": "penakar"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], False)

    def test_inactive_account_cannot_log_in(self):
        get_user_model().objects.filter(pk=self.other.pk).update(is_active=False)
        response = self.client.post("/api/auth/login/", {"username": "other", "password": PASSWORD})
        self.assertEqual(response.status_code, 401)

    def test_logout_ends_session_without_body(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["status"], True)
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 403)

    # Registrasi

    def test_register_creates_account_profile_and_preferences(self):
        response = self.post("/api/auth/register/", {
            "full_name": "Budi  Santoso",
            "username": "Budi_S",
            "email": "Budi@Example.com",
            "password1": "Rahasia!123",
            "password2": "Rahasia!123",
        })
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()["status"], True)
        self.assertEqual(response.json()["username"], "budi_s")
        user = get_user_model().objects.get(username="budi_s")
        self.assertEqual((user.email, user.first_name, user.last_name), ("budi@example.com", "Budi", "Santoso"))
        self.assertTrue(user.check_password("Rahasia!123"))
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertTrue(FoodPreference.objects.filter(user=user).exists())

    def test_register_rejects_invalid_or_duplicate_data(self):
        response = self.post("/api/auth/register/", {
            "full_name": "Tiruan",
            "username": "baru",
            "email": "DINA@example.com",
            "password1": "lemah",
            "password2": "beda",
        })
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], False)
        self.assertIn("message", body)
        self.assertTrue({"email", "password2"} <= set(body["fields"]))
        self.assertFalse(get_user_model().objects.filter(username="baru").exists())

    def test_register_ignores_form_body(self):
        # Tanpa CSRF, form lintas situs tidak boleh membuat akun. Middleware rate limit sudah membaca
        # request.POST, jadi DRF menerima data kosong (400) alih-alih 415.
        response = self.client.post("/api/auth/register/", {
            "full_name": "Formulir", "username": "formulir", "email": "form@example.com",
            "password1": "Rahasia!123", "password2": "Rahasia!123",
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username="formulir").exists())

    # Profil dan preferensi

    def test_profile_requires_login(self):
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 403)
        self.assertEqual(self.post("/api/auth/profile/update/", self.details()).status_code, 403)
        self.assertEqual(self.post("/api/auth/preferences/update/", self.preferences()).status_code, 403)
        self.assertEqual(self.post("/api/auth/password/", {}).status_code, 403)

    def test_profile_returns_account_and_preferences(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/auth/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        body = response.json()
        self.assertEqual(body["username"], "penakar")
        self.assertEqual(body["full_name"], "Dina Sari")
        self.assertEqual(body["email"], "dina@example.com")
        self.assertEqual(body["avatar"], "initials")
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["preferences"]["targets"], ["seimbang"])
        self.assertIs(body["preferences"]["halal_only"], True)
        self.assertEqual(body["preferences"]["avoided_ingredients"], [])

    def test_update_profile_changes_name_username_and_avatar(self):
        self.client.force_login(self.user)
        response = self.post(
            "/api/auth/profile/update/", self.details(full_name="Dina  Ayu Sari", username="Dina.Baru")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "dina.baru")
        self.assertEqual(response.json()["version"], 2)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Dina", "Ayu Sari"))
        self.assertEqual(UserProfile.objects.get(user=self.user).avatar, "chef")

    def test_changing_email_needs_current_password(self):
        self.client.force_login(self.user)
        response = self.post("/api/auth/profile/update/", self.details(email="baru@example.com"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["fields"])
        response = self.post(
            "/api/auth/profile/update/",
            self.details(email="baru@example.com", current_password=PASSWORD),
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "baru@example.com")

    def test_update_profile_rejects_invalid_data(self):
        self.client.force_login(self.user)
        for changes in ({"avatar": "naga"}, {"username": "a b"}, {"full_name": ""}):
            with self.subTest(changes=changes):
                response = self.post("/api/auth/profile/update/", self.details(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())
        self.assertEqual(self.post("/api/auth/profile/update/", ["bukan objek"]).status_code, 400)
        self.assertEqual(self.version(), 1)

    def test_stale_version_is_a_conflict(self):
        self.client.force_login(self.user)
        response = self.post("/api/auth/profile/update/", self.details(version=5))
        self.assertEqual(response.status_code, 409)
        response = self.post("/api/auth/preferences/update/", self.preferences(version=5))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(FoodPreference.objects.filter(user=self.user, servings=3).count(), 0)

    def test_cannot_change_another_users_data(self):
        self.client.force_login(self.user)
        response = self.post("/api/auth/profile/update/", self.details(username="OTHER"))
        self.assertEqual(response.status_code, 400)
        response = self.post(
            "/api/auth/profile/update/", self.details(id=self.other.pk, user=self.other.pk, full_name="Ganti")
        )
        self.assertEqual(response.status_code, 200)
        self.post(
            "/api/auth/preferences/update/", self.preferences(user=self.other.pk, version=self.version())
        )
        self.other.refresh_from_db()
        self.assertEqual((self.other.username, self.other.first_name), ("other", ""))
        self.assertFalse(FoodPreference.objects.filter(user=self.other, servings=3).exists())
        self.assertTrue(FoodPreference.objects.filter(user=self.user, servings=3).exists())

    def test_update_preferences(self):
        self.client.force_login(self.user)
        response = self.post("/api/auth/preferences/update/", self.preferences(halal_only=False))
        self.assertEqual(response.status_code, 200)
        prefs = response.json()["preferences"]
        self.assertEqual(prefs["targets"], ["tinggi_protein"])
        self.assertEqual(prefs["servings"], 3)
        self.assertEqual(prefs["avoided_ingredients"], [{"code": "TEMPE", "name": "Tempe"}])
        self.assertIs(prefs["halal_only"], True)
        self.assertEqual(response.json()["version"], 2)

    def test_update_preferences_rejects_invalid_data(self):
        self.client.force_login(self.user)
        for changes in (
            {"targets": ["seimbang", "tinggi_protein"]},
            {"servings": 11},
            {"allergens": ["batu"]},
            {"avoided_ingredients": ["TIDAK-ADA"]},
        ):
            with self.subTest(changes=changes):
                response = self.post("/api/auth/preferences/update/", self.preferences(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertIn("fields", response.json())
        self.assertEqual(self.version(), 1)

    def test_writes_reject_form_body(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/auth/profile/update/", self.details())
        self.assertEqual(response.status_code, 415)

    # Ganti kata sandi

    def test_change_password_keeps_session(self):
        self.client.force_login(self.user)
        response = self.post("/api/auth/password/", {
            "old_password": PASSWORD, "new_password1": "Baru!45678", "new_password2": "Baru!45678",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Baru!45678"))
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 200)

    def test_change_password_rejects_wrong_old_password(self):
        self.client.force_login(self.user)
        response = self.post("/api/auth/password/", {
            "old_password": "salah", "new_password1": "Baru!45678", "new_password2": "Baru!45678",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("old_password", response.json()["fields"])

    # Rate limit

    def test_login_is_rate_limited_per_account(self):
        with patch("apps.login.rate_limits.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 11, 18, 9, 1, tzinfo=UTC)
            for _ in range(10):
                response = self.client.post("/api/auth/login/", {"username": "penakar", "password": "x"})
                self.assertEqual(response.status_code, 401)
            response = Client().post("/api/auth/login/", {"username": "DINA@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["status"], False)
        self.assertIn("message", response.json())
        self.assertGreater(int(response["Retry-After"]), 0)

    def test_register_is_rate_limited_per_email_from_json_body(self):
        payload = {"full_name": "A", "username": "a", "email": "spam@example.com", "password1": "x", "password2": "x"}
        with patch("apps.login.rate_limits.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 11, 18, 9, 1, tzinfo=UTC)
            for _ in range(5):
                self.assertEqual(self.post("/api/auth/register/", payload).status_code, 400)
            self.assertEqual(self.post("/api/auth/register/", payload).status_code, 429)
            # Kuota per email: email lain dari IP yang sama tidak ikut terblokir.
            other = self.post("/api/auth/register/", {**payload, "email": "lain@example.com"})
        self.assertEqual(other.status_code, 400)

    def test_password_change_is_rate_limited_per_account(self):
        self.client.force_login(self.user)
        payload = {"old_password": "salah", "new_password1": "Baru!45678", "new_password2": "Baru!45678"}
        with patch("apps.login.rate_limits.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 11, 18, 9, 1, tzinfo=UTC)
            for _ in range(5):
                self.assertEqual(self.post("/api/auth/password/", payload).status_code, 400)
            response = self.post("/api/auth/password/", {**payload, "old_password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
