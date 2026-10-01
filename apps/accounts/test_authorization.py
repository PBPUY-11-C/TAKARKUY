import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.catalog.models import Ingredient
from apps.pantry.models import PantryItem, PantryNameCorrection


class AuthorizationTests(TestCase):
    def setUp(self):
        no_live_gemini = patch("apps.pantry.recommendations.gemini_ready", return_value=False)
        no_live_gemini.start()
        self.addCleanup(no_live_gemini.stop)
        self.owner = get_user_model().objects.create_user(username="owner")
        self.other = get_user_model().objects.create_user(username="other")
        self.ingredient = Ingredient.objects.create(
            ingredient_code="ING-AUTH", name="Bayam", category="sayur", base_unit="g"
        )
        self.item = PantryItem.objects.create(
            user=self.owner,
            session_id="old-session",
            name="Stok Rahasia Pemilik",
            quantity=1,
            unit="g",
            source="manual",
        )

    def test_guest_can_only_open_public_pages_and_module_one(self):
        for name in ("landing", "signup", "login", "modul1"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        for name in ("modul2", "modul4", "modul5"):
            with self.subTest(page=name):
                self.assertRedirects(
                    self.client.get(reverse(name)), f"{reverse('login')}?next={reverse(name)}"
                )

    @patch("apps.pantry.views.gemini_read_receipt")
    @patch("apps.pantry.views.resolve_names")
    def test_every_pantry_api_rejects_guest_before_processing(self, resolver, gemini):
        calls = [
            ("post", reverse("modul2-items")),
            ("post", reverse("modul2-suggestions")),
            ("post", reverse("modul2-ocr-fallback")),
            ("patch", reverse("modul2-item-details", args=[self.item.pk])),
            ("delete", reverse("modul2-item-delete", args=[self.item.pk])),
        ]
        for method, url in calls:
            with self.subTest(url=url):
                response = getattr(self.client, method)(
                    url, data="{}", content_type="application/json"
                )
                self.assertEqual(response.status_code, 401)
                self.assertIn("login_url", response.json())
        gemini.assert_not_called()
        resolver.assert_not_called()
        self.assertTrue(PantryItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(PantryItem.objects.count(), 1)

    def test_same_account_can_read_update_delete_from_another_browser(self):
        device = Client()
        device.force_login(self.owner)
        page = device.get(reverse("modul2"))
        self.assertContains(page, self.item.name)
        response = device.patch(
            reverse("modul2-item-details", args=[self.item.pk]),
            data=json.dumps({"location": "freezer", "expiry_mode": "auto"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.location, "freezer")
        self.assertEqual(
            device.delete(reverse("modul2-item-delete", args=[self.item.pk])).status_code, 200
        )

    def test_other_account_cannot_access_ids_even_with_copied_pantry_scope(self):
        self.client.force_login(self.other)
        session = self.client.session
        session["pantry_session_id"] = self.item.session_id
        session.save()
        self.assertNotContains(self.client.get(reverse("modul2")), self.item.name)
        response = self.client.patch(
            reverse("modul2-item-details", args=[self.item.pk]),
            data=json.dumps({"location": "freezer", "expiry_mode": "auto"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.delete(reverse("modul2-item-delete", args=[self.item.pk])).status_code, 404
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.location, "suhu_ruang")

    def test_switching_accounts_in_same_browser_does_not_share_stock(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("modul2")), self.item.name)
        self.client.post(reverse("logout"))
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("modul2")), self.item.name)

    def test_legacy_unowned_data_is_preserved_without_automatic_claim(self):
        legacy = PantryItem.objects.create(
            session_id="legacy", name="Stok Anonim Lama", quantity=1, unit="g", source="ocr"
        )
        correction = PantryNameCorrection.objects.create(
            session_id="legacy", raw_name="BXYM", normalized_name="bxym", ingredient=self.ingredient
        )
        self.client.force_login(self.owner)
        session = self.client.session
        session["pantry_session_id"] = "legacy"
        session.save()
        self.assertNotContains(self.client.get(reverse("modul2")), legacy.name)
        self.assertEqual(
            self.client.delete(reverse("modul2-item-delete", args=[legacy.pk])).status_code, 404
        )
        legacy.refresh_from_db()
        correction.refresh_from_db()
        self.assertIsNone(legacy.user_id)
        self.assertIsNone(correction.user_id)

    def test_saving_stock_uses_logged_in_owner_not_payload_owner(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("modul2-items"),
            content_type="application/json",
            data=json.dumps(
                {
                    "source": "manual",
                    "user_id": self.other.pk,
                    "items": [
                        {
                            "name": "Bayam",
                            "category": "sayur_buah",
                            "quantity": "1",
                            "unit": "ikat",
                            "user_id": self.other.pk,
                            "session_id": "forged",
                        }
                    ],
                }
            ),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            PantryItem.objects.get(pk=response.json()["ids"][0]).user_id, self.owner.pk
        )

    def test_private_ocr_correction_follows_account_across_devices(self):
        PantryNameCorrection.objects.create(
            user=self.owner,
            session_id="old-session",
            raw_name="BXYM",
            normalized_name="bxym",
            ingredient=self.ingredient,
        )
        for user, expected in ((self.owner, "koreksi_anda"), (self.other, "tidak_cocok")):
            client = Client()
            client.force_login(user)
            response = client.post(
                reverse("modul2-suggestions"),
                content_type="application/json",
                data=json.dumps({"names": ["BXYM"]}),
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["suggestions"][0]["method"], expected)

    def test_legacy_anonymous_votes_do_not_count_as_community_accounts(self):
        for index in range(5):
            PantryNameCorrection.objects.create(
                session_id=f"legacy-{index}",
                raw_name="BXYM",
                normalized_name="bxym",
                ingredient=self.ingredient,
            )
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("modul2-suggestions"),
            content_type="application/json",
            data=json.dumps({"names": ["BXYM"]}),
        )
        self.assertNotEqual(response.json()["suggestions"][0]["method"], "koreksi_bersama")

    def test_nonstaff_cannot_enter_admin_and_staff_cannot_edit_other_stock_via_pantry(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
        self.other.is_staff = self.other.is_superuser = True
        self.other.save()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(
            self.client.delete(reverse("modul2-item-delete", args=[self.item.pk])).status_code, 404
        )

    def test_login_next_returns_to_requested_module_and_rejects_external_redirect(self):
        self.owner.set_password("Demodemo1.")
        self.owner.save()
        response = self.client.post(
            reverse("login"),
            {
                "username": "owner",
                "password": "Demodemo1.",
                "next": reverse("modul2"),
            },
        )
        self.assertRedirects(response, reverse("modul2"))
        self.client.post(reverse("logout"))
        response = self.client.post(
            reverse("login"),
            {
                "username": "owner",
                "password": "Demodemo1.",
                "next": "https://example.org/evil",
            },
        )
        self.assertRedirects(response, reverse("modul5"))
