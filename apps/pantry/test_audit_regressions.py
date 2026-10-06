"""Regressions for unconfirmed AI, malformed JSON and legacy dates."""

import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Ingredient, IngredientShelfLife

from .models import NameResolution, PantryItem, PantryNameCorrection
from .recommendations import resolve_names
from .services import available_grams
from .test_helpers import authenticate


class AuditRegressionTests(TestCase):
    def setUp(self):
        self.user = authenticate(self.client)
        self.today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
        self.ingredient = Ingredient.objects.create(
            ingredient_code="ING-AUDIT", name="Bayam", category="sayur", base_unit="g"
        )

    def create(self, **changes):
        return self.client.post(
            reverse("modul2-items"),
            data=json.dumps(
                {
                    "source": "ocr",
                    "operation_key": str(uuid4()),
                    "items": [
                        {
                            "name": "Bayam",
                            "original_name": "BYM",
                            "ingredient_code": self.ingredient.pk,
                            "quantity": 100,
                            "unit": "g",
                            **changes,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )

    def edit(self, item, **changes):
        return self.client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            data=json.dumps(
                {
                    "operation_key": str(uuid4()),
                    "version": item.version,
                    **changes,
                }
            ),
            content_type="application/json",
        )

    def test_autofill_and_cached_ai_do_not_record_corrections(self):
        for method in ("ai_perlu_periksa", "ai_cache_perlu_periksa", "katalog"):
            self.assertEqual(self.create(suggestion_method=method).status_code, 201)
        self.assertEqual(PantryItem.objects.count(), 3)
        self.assertFalse(PantryNameCorrection.objects.exists())

    def test_explicit_confirmation_and_actual_edit_record_corrections(self):
        self.assertEqual(self.create(accepted=True).status_code, 201)
        correction = PantryNameCorrection.objects.get()
        self.assertTrue(correction.confirmed_by_user)
        self.assertEqual(
            self.create(
                original_name="BAYAM HIJ", ingredient_code="", user_edited=True
            ).status_code,
            201,
        )
        self.assertEqual(PantryNameCorrection.objects.filter(confirmed_by_user=True).count(), 2)

    def test_false_or_string_confirmation_cannot_promote_autofill(self):
        self.assertEqual(self.create(accepted=False, user_edited=False).status_code, 201)
        self.assertEqual(self.create(original_name="Bayam", user_edited=True).status_code, 201)
        self.assertFalse(PantryNameCorrection.objects.exists())
        for flag in ("accepted", "user_edited"):
            self.assertEqual(self.create(**{flag: "true"}).status_code, 400)

    def test_old_unconfirmed_corrections_are_not_private_or_community_votes(self):
        for index in range(10):
            voter = (
                self.user if index == 0 else get_user_model().objects.create_user(f"voter{index}")
            )
            get_user_model().objects.filter(pk=voter.pk).update(
                date_joined=timezone.now() - timedelta(days=8)
            )
            PantryNameCorrection.objects.create(
                user=voter,
                session_id=str(index),
                raw_name="BXYM",
                normalized_name="bxym",
                ingredient=self.ingredient,
            )
        result, _ = resolve_names(["BXYM"], "test", user=self.user, allow_llm=False)
        self.assertNotIn(result[0]["method"], {"koreksi_anda", "koreksi_bersama"})

    def test_nested_json_returns_json_400_on_all_input_endpoints(self):
        self.create()
        item = PantryItem.objects.get()
        # 1,200 levels triggers Python's decoder recursion limit and fits every cap.
        for body in ("[" * 1200 + "0" + "]" * 1200, "[" * 30 + "0" + "]" * 30):
            # The edit/delete cap is 2 KB, so use 950 levels there.
            short_body = body if len(body) <= 2000 else "[" * 950 + "0" + "]" * 950
            cases = (
                (self.client.post, reverse("modul2-items"), body),
                (self.client.post, reverse("modul2-suggestions"), body),
                (self.client.patch, reverse("modul2-item-details", args=[item.pk]), short_body),
                (self.client.delete, reverse("modul2-item-delete", args=[item.pk]), short_body),
            )
            for request, url, raw in cases:
                with self.subTest(url=url, levels=len(raw)):
                    response = request(url, data=raw, content_type="application/json")
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("error", response.json())

    def test_non_finite_json_constants_are_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity", "1e999"):
            response = self.client.post(
                reverse("modul2-items"),
                data='{"items":' + constant + "}",
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.json())

    def test_text_fields_reject_objects_numbers_and_booleans(self):
        for field in (
            "name",
            "category",
            "unit",
            "location",
            "expiry_source",
            "starting_on",
            "estimated_expires_on",
            "ingredient_code",
            "original_name",
        ):
            for value in ({"bad": "value"}, ["bad"], 123, True):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.create(**{field: value}).status_code, 400)
        self.assertFalse(PantryItem.objects.exists())

    def test_edit_text_fields_are_strict_too(self):
        self.create()
        item = PantryItem.objects.get()
        for field in ("name", "ingredient_code", "estimated_expires_on", "expiry_mode"):
            self.assertEqual(self.edit(item, **{field: {"bad": "value"}}).status_code, 400)
        self.assertEqual(PantryItem.objects.get().version, 1)

    def test_invalid_source_is_json_400_not_type_error(self):
        response = self.client.post(
            reverse("modul2-items"),
            data=json.dumps({"source": {}, "items": [{}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_history_missing_or_other_owner_returns_json_404(self):
        self.create()
        item = PantryItem.objects.get()
        for pk in (item.pk, item.pk + 1000):
            if pk == item.pk:
                item.user = get_user_model().objects.create_user("other")
                item.save()
            response = self.client.get(reverse("modul2-item-movements", args=[pk]))
            self.assertEqual(response.status_code, 404)
            self.assertIn("error", response.json())

    def test_date_bounds_and_same_day_expiry(self):
        self.assert_date_bounds_and_same_day_expiry()

    def assert_date_bounds_and_same_day_expiry(self):
        for field in ("starting_on", "estimated_expires_on"):
            for value in ("0001-01-01", "9999-12-31"):
                self.assertEqual(self.create(**{field: value}).status_code, 400)
        self.assertEqual(
            self.create(starting_on=str(self.today + timedelta(days=1))).status_code, 400
        )
        self.assertEqual(self.create(estimated_expires_on=str(self.today)).status_code, 201)
        item = PantryItem.objects.get()
        self.assertEqual(item.shelf_life_days, 0)
        self.assertEqual(self.edit(item, quantity=50).status_code, 200)
        for value in ("0001-01-01", "9999-12-31"):
            item.refresh_from_db()
            self.assertEqual(
                self.edit(item, estimated_expires_on=value, expiry_mode="manual").status_code, 400
            )

    def test_bounded_historical_dates_remain_accepted(self):
        self.assertEqual(
            self.create(starting_on="2000-01-01", estimated_expires_on="2000-01-02").status_code,
            201,
        )
        self.assertEqual(PantryItem.objects.get().starting_on, date(2000, 1, 1))

    def test_legacy_dates_are_eligible_and_preserved_on_transfer(self):
        self.create(estimated_expires_on=str(self.today + timedelta(days=2)))
        item = PantryItem.objects.get()
        item.expiry_source = "legacy"
        item.save()
        chosen = item.estimated_expires_on
        self.assertEqual(available_grams(self.user)[self.ingredient.pk], 100)
        self.assertEqual(self.edit(item, location="freezer", expiry_mode="auto").status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, chosen)
        self.assertEqual(item.expiry_source, "legacy")

    def test_capped_freezer_date_and_duration_stay_consistent(self):
        self.assert_capped_freezer_date_and_duration()

    def assert_capped_freezer_date_and_duration(self):
        for location, days in (("suhu_ruang", 2), ("freezer", 20)):
            IngredientShelfLife.objects.create(
                shelf_life_code=f"SHF-{location}",
                ingredient=self.ingredient,
                storage_location=location,
                min_days=days,
                max_days=days,
                warning_days=1,
                starting_event="tanggal_pembelian",
                source="Synthetic test",
                source_url="https://example.org/test",
                source_duration="test",
                days_conversion_method="test",
                shelf_life_status="test",
            )
        self.create()
        item = PantryItem.objects.get()
        self.assertEqual(self.edit(item, location="freezer", expiry_mode="auto").status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, self.today + timedelta(days=2))
        self.assertEqual(item.shelf_life_days, 2)

    def test_date_validation_uses_jakarta_when_utc_is_previous_day(self):
        frozen = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=frozen), timezone.override("UTC"):
            self.today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
            self.assertEqual(timezone.localdate(), date(2026, 10, 5))
            self.assertEqual(self.today, date(2026, 10, 6))
            self.assert_date_bounds_and_same_day_expiry()

    def test_freezer_expiry_uses_jakarta_when_utc_is_previous_day(self):
        frozen = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=frozen), timezone.override("UTC"):
            self.today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
            self.assertEqual(timezone.localdate(), date(2026, 10, 5))
            self.assertEqual(self.today, date(2026, 10, 6))
            self.assert_capped_freezer_date_and_duration()

    @patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch(
        "apps.pantry.recommendations._gemini_choices",
        side_effect=RuntimeError("Unexpected provider failure"),
    )
    def test_unexpected_ai_error_releases_every_owned_cache_lease(self, llm):
        Ingredient.objects.create(
            ingredient_code="ING-SAWI", name="Sawi", category="sayur", base_unit="g"
        )
        with self.assertRaises(RuntimeError):
            resolve_names(["bayam hj", "sawi hj"], "test", user=self.user)
        self.assertEqual(NameResolution.objects.count(), 2)
        self.assertFalse(NameResolution.objects.filter(lease__isnull=False).exists())
        self.assertFalse(NameResolution.objects.filter(expires_at__gt=timezone.now()).exists())
