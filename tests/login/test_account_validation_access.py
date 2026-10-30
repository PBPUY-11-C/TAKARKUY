"""Account validation must be atomic and every settings write must use its session owner."""

from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.catalog.models import Ingredient
from apps.login.models import FoodPreference, UserProfile
from apps.login.preferences import preferences_for, profile_for


class AccountValidationAccessTests(TestCase):
    password = "Validation!827"
    settings_routes = ("modul3", "food-preferences", "password-change")

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            "validation-owner", "owner@example.com", self.password, first_name="Pemilik"
        )
        self.other = get_user_model().objects.create_user(
            "validation-other", "other@example.com", self.password, first_name="Pengguna Lain"
        )
        for user in (self.owner, self.other):
            profile_for(user)
            preferences_for(user)
        self.ingredient = Ingredient.objects.create(
            ingredient_code="ACCESS-KEEP", name="Bahan tersimpan", category="sayur", base_unit="g"
        )
        preferences_for(self.owner).avoided_ingredients.add(self.ingredient)
        self.client.force_login(self.owner)

    def account_data(self, **changes):
        return {
            "action": "account", "full_name": "Nama Diperbarui",
            "username": self.owner.username, "email": self.owner.email,
            "avatar": "chef", "version": profile_for(self.owner).version, **changes,
        }

    def preference_data(self, **changes):
        return {
            "targets": ["tinggi_protein"], "meal_types": ["sarapan"],
            "servings": 4, "allergens": ["telur"],
            "avoided_ingredients": [self.ingredient.pk],
            "version": profile_for(self.owner).version, **changes,
        }

    def state(self, user):
        return (
            get_user_model().objects.filter(pk=user.pk).values(
                "username", "email", "first_name", "last_name", "password", "is_staff", "is_superuser"
            ).get(),
            UserProfile.objects.filter(user=user).values().get(),
            FoodPreference.objects.filter(user=user).values().get(),
            list(preferences_for(user).avoided_ingredients.order_by("pk").values_list("pk", flat=True)),
        )

    def test_guest_cannot_read_or_write_any_settings_page(self):
        guest = Client()
        before = self.state(self.owner)
        for route in self.settings_routes:
            url = reverse(route)
            for method in ("get", "post"):
                with self.subTest(route=route, method=method):
                    response = getattr(guest, method)(url, {"user_id": self.owner.pk} if method == "post" else {})
                    self.assertRedirects(response, f"{reverse('login')}?next={url}",
                                         fetch_redirect_response=False)
        self.assertEqual(self.state(self.owner), before)
        self.assertNotIn(SESSION_KEY, guest.session)

    def test_forged_account_owner_and_admin_flags_cannot_change_another_user(self):
        other_before = self.state(self.other)
        response = self.client.post(reverse("modul3"), self.account_data(
            user_id=self.other.pk, profile_id=profile_for(self.other).pk,
            is_staff="true", is_superuser="true",
        ))
        self.assertRedirects(response, reverse("modul3"), fetch_redirect_response=False)
        self.assertEqual(self.state(self.other), other_before)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.get_full_name(), "Nama Diperbarui")
        self.assertFalse(self.owner.is_staff)
        self.assertFalse(self.owner.is_superuser)
        self.assertEqual(profile_for(self.owner).avatar, "chef")

    def test_forged_preference_owner_cannot_change_another_users_choices(self):
        other_before = self.state(self.other)
        response = self.client.post(reverse("food-preferences"), self.preference_data(
            user_id=self.other.pk, preference_id=preferences_for(self.other).pk,
        ))
        self.assertRedirects(response, reverse("food-preferences"), fetch_redirect_response=False)
        self.assertEqual(self.state(self.other), other_before)
        self.assertEqual(preferences_for(self.owner).servings, 4)
        self.assertEqual(preferences_for(self.owner).allergens, ["telur"])

    def test_forged_password_owner_changes_only_the_authenticated_account(self):
        other_before = self.state(self.other)
        response = self.client.post(reverse("password-change"), {
            "user_id": self.other.pk, "old_password": self.password,
            "new_password1": "Updated!938", "new_password2": "Updated!938",
        })
        self.assertRedirects(response, reverse("modul3"), fetch_redirect_response=False)
        self.assertEqual(self.state(self.other), other_before)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("Updated!938"))
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.owner.pk)

    def test_invalid_account_fields_do_not_save_other_valid_changes(self):
        before = self.state(self.owner)
        for field, value in (("full_name", "   "), ("email", "invalid-email")):
            with self.subTest(field=field):
                response = self.client.post(reverse("modul3"), self.account_data(**{field: value}))
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.context["account_form"].errors)
                self.assertEqual(self.state(self.owner), before)

    def test_unknown_ingredient_does_not_partially_save_preferences_or_clear_existing_choices(self):
        before = self.state(self.owner)
        response = self.client.post(reverse("food-preferences"), self.preference_data(
            avoided_ingredients=[self.ingredient.pk, "DOES-NOT-EXIST"],
        ))
        self.assertEqual(response.status_code, 400)
        self.assertIn("avoided_ingredients", response.context["preference_form"].errors)
        self.assertEqual(self.state(self.owner), before)

    def test_missing_version_rejects_account_and_preference_writes_without_mutation(self):
        before = self.state(self.owner)
        for route, data, form_name in (
            ("modul3", self.account_data(), "account_form"),
            ("food-preferences", self.preference_data(), "preference_form"),
        ):
            with self.subTest(route=route):
                data.pop("version")
                response = self.client.post(reverse(route), data)
                self.assertEqual(response.status_code, 400)
                self.assertIn("version", response.context[form_name].errors)
                self.assertEqual(self.state(self.owner), before)

    def test_preference_post_requires_csrf_and_leaves_saved_choices_unchanged(self):
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.owner)
        before = self.state(self.owner)
        response = secure_client.post(reverse("food-preferences"), self.preference_data())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.state(self.owner), before)

    def test_unsupported_http_methods_cannot_modify_settings(self):
        before = self.state(self.owner)
        for route in self.settings_routes:
            for method in ("put", "patch", "delete"):
                with self.subTest(route=route, method=method):
                    response = getattr(self.client, method)(reverse(route), {}, content_type="application/json")
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response.headers["Allow"], "GET, POST")
        self.assertEqual(self.state(self.owner), before)

    def test_logout_revokes_settings_access_for_the_same_browser(self):
        self.client.post(reverse("logout"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        for route in self.settings_routes:
            with self.subTest(route=route):
                url = reverse(route)
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}",
                                     fetch_redirect_response=False)

    def test_signup_cannot_assign_privileged_flags_from_posted_fields(self):
        guest = Client()
        response = guest.post(reverse("signup"), {
            "full_name": "Pengguna Baru", "username": "pendaftar-baru",
            "email": "new@example.com", "password1": self.password,
            "password2": self.password, "is_staff": "true", "is_superuser": "true",
            "user_id": self.other.pk,
        })
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="pendaftar-baru")
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertNotEqual(created.pk, self.other.pk)
        self.assertEqual(int(guest.session[SESSION_KEY]), created.pk)
        self.assertTrue(UserProfile.objects.filter(user=created).exists())
        self.assertTrue(FoodPreference.objects.filter(user=created).exists())
