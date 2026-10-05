"""Batch accounting, ownership, idempotency, conservative dates and conversions."""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Ingredient, Recipe, RecipeIngredient, RecipeTag, UnitConversion

from .ai_cache import claim, finish
from .models import NameResolution, PantryItem, PantryLLMUsage, PantryMovement, PantryOperation
from .recommendations import resolve_names
from .services import (
    StockError,
    available_grams,
    consume_stock,
    conversion,
    recipe_matches,
    reserve_llm,
)
from .test_helpers import authenticate


class BatchTests(TestCase):
    def setUp(self):
        self.user = authenticate(self.client)
        self.today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
        self.ingredient = Ingredient.objects.create(
            ingredient_code="ING-TEST", name="Bayam", category="sayur", base_unit="g"
        )

    def create(self, **changes):
        payload = {
            "operation_key": str(uuid4()),
            "source": "manual",
            "items": [
                {
                    "name": "Bayam",
                    "category": "sayur_buah",
                    "quantity": "100",
                    "unit": "g",
                    **changes,
                }
            ],
        }
        return self.client.post(
            reverse("modul2-items"), data=json.dumps(payload), content_type="application/json"
        ), payload

    def batch(self, **changes):
        return PantryItem.objects.create(
            user=self.user,
            session_id="test",
            name="Bayam",
            ingredient=self.ingredient,
            source="manual",
            unit="g",
            quantity=100,
            grams_per_unit=1,
            expiry_source="manual",
            estimated_expires_on=self.today + timedelta(days=2),
            **changes,
        )

    def edit(self, item, **changes):
        return self.client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            data=json.dumps({"operation_key": str(uuid4()), "version": item.version, **changes}),
            content_type="application/json",
        )

    def test_create_replay_writes_one_batch_and_one_movement(self):
        response, payload = self.create()
        self.assertEqual(response.status_code, 201)
        again = self.client.post(
            reverse("modul2-items"), data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(again.json(), response.json())
        self.assertEqual(PantryItem.objects.count(), 1)
        self.assertEqual(PantryMovement.objects.count(), 1)
        payload["items"][0]["quantity"] = "200"
        self.assertEqual(
            self.client.post(
                reverse("modul2-items"), data=json.dumps(payload), content_type="application/json"
            ).status_code,
            409,
        )

    def test_create_requires_operation_key(self):
        response = self.client.post(
            reverse("modul2-items"),
            data=json.dumps(
                {
                    "source": "manual",
                    "items": [
                        {"name": "Bayam", "category": "sayur_buah", "quantity": 1, "unit": "g"}
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PantryItem.objects.exists())

    def test_numeric_ocr_name_cannot_crash(self):
        response = self.client.post(
            reverse("modul2-items"),
            data=json.dumps(
                {
                    "operation_key": str(uuid4()),
                    "source": "ocr",
                    "items": [
                        {
                            "name": 123,
                            "original_name": "BYM",
                            "ingredient_code": self.ingredient.pk,
                            "quantity": 1,
                            "unit": "g",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_edit_all_fields_journals_and_checks_version(self):
        response, _ = self.create()
        item = PantryItem.objects.get(pk=response.json()["ids"][0])
        edited = self.edit(
            item,
            name="Bayam Merah",
            quantity="2",
            category="lainnya",
            unit="pack",
            pack_weight_g="250",
            ingredient_code=self.ingredient.pk,
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(self.edit(item, quantity="3").status_code, 409)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.grams_per_unit, 250)
        self.assertEqual(item.movements.count(), 2)
        self.assertEqual(item.movements.last().snapshot["before"]["quantity"], "100.000000")

    def test_missing_version_and_invalid_edit_do_not_leave_operations(self):
        item = self.batch()
        for changes in ({"version": None}, {"quantity": "-1"}, {"ingredient_code": "UNKNOWN"}):
            self.assertEqual(self.edit(item, **changes).status_code, 400)
        self.assertFalse(PantryOperation.objects.exists())
        self.assertFalse(PantryMovement.objects.exists())

    def test_label_and_manual_dates_survive_location_changes(self):
        for source in ("label", "manual"):
            response, _ = self.create(
                estimated_expires_on=str(self.today + timedelta(days=3)), expiry_source=source
            )
            item = PantryItem.objects.get(pk=response.json()["ids"][0])
            chosen = item.estimated_expires_on
            self.assertEqual(
                self.edit(item, location="freezer", expiry_mode="auto").status_code, 200
            )
            item.refresh_from_db()
            self.assertEqual(item.estimated_expires_on, chosen)
            self.assertEqual(item.expiry_source, source)

    def test_archive_keeps_ledger_and_owner_only_history(self):
        response, _ = self.create()
        item = PantryItem.objects.get(pk=response.json()["ids"][0])
        payload = {"operation_key": str(uuid4()), "version": 1}
        url = reverse("modul2-item-delete", args=[item.pk])
        for _ in range(2):
            self.assertEqual(
                self.client.delete(
                    url, data=json.dumps(payload), content_type="application/json"
                ).status_code,
                200,
            )
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)
        self.assertIsNotNone(item.archived_at)
        self.assertEqual(item.movements.count(), 2)
        history = reverse("modul2-item-movements", args=[item.pk])
        self.assertEqual(len(self.client.get(history).json()["movements"]), 2)
        other = Client()
        authenticate(other, "other")
        self.assertEqual(other.get(history).status_code, 404)
        self.assertEqual(Client().get(history).status_code, 401)

    def test_database_rejects_negative_quantity(self):
        item = self.batch()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PantryItem.objects.filter(pk=item.pk).update(quantity=-1)

    def test_units_do_not_assume_volume_equals_mass(self):
        self.assertEqual(conversion("kg", None)[1], 1000)
        self.assertIsNone(conversion("ml", self.ingredient.pk)[1])
        self.assertIsNone(conversion("pack", self.ingredient.pk)[1])
        self.assertEqual(conversion("pack", self.ingredient.pk, Decimal(250))[1], 250)
        UnitConversion.objects.create(
            conversion_code="CNV-TEST",
            ingredient=self.ingredient,
            unit="butir",
            gram_equivalent=50,
            source="Test",
            conversion_status="size_specific",
        )
        self.assertEqual(conversion("butir", self.ingredient.pk)[1], 50)

    def test_fefo_and_replay_across_multiple_batches(self):
        first = self.batch()
        second = self.batch()
        PantryItem.objects.filter(pk=second.pk).update(
            estimated_expires_on=self.today + timedelta(days=1)
        )
        key = uuid4()
        answer = consume_stock(self.user, {self.ingredient.pk: 150}, key)
        self.assertEqual([row["batch_id"] for row in answer["consumed"]], [second.pk, first.pk])
        self.assertEqual(consume_stock(self.user, {self.ingredient.pk: 150}, key), answer)
        self.assertEqual(PantryMovement.objects.count(), 2)
        self.assertEqual(available_grams(self.user)[self.ingredient.pk], 50)
        with self.assertRaises(StockError):
            consume_stock(self.user, {self.ingredient.pk: 10}, key)

    def test_insufficient_second_ingredient_rolls_back_everything(self):
        item = self.batch()
        with self.assertRaises(StockError):
            consume_stock(self.user, {self.ingredient.pk: 50, "ING-MISSING": 10}, uuid4())
        item.refresh_from_db()
        self.assertEqual(item.quantity, 100)
        self.assertFalse(PantryMovement.objects.exists())
        self.assertFalse(PantryOperation.objects.exists())

    def test_unknown_expired_and_unmapped_stock_are_not_implicitly_consumed(self):
        self.batch()
        PantryItem.objects.update(expiry_source="unknown")
        self.assertEqual(available_grams(self.user), {})
        self.assertEqual(
            available_grams(self.user, allow_unknown_expiry=True)[self.ingredient.pk], 100
        )
        PantryItem.objects.update(estimated_expires_on=self.today - timedelta(days=1))
        self.assertEqual(available_grams(self.user, allow_unknown_expiry=True), {})
        PantryItem.objects.update(estimated_expires_on=self.today, ingredient=None)
        self.assertEqual(available_grams(self.user, allow_unknown_expiry=True), {})

    def test_conversion_snapshot_does_not_follow_catalogue_edits(self):
        row = UnitConversion.objects.create(
            conversion_code="CNV-TEST",
            ingredient=self.ingredient,
            unit="butir",
            gram_equivalent=50,
            source="test",
            conversion_status="reviewed",
        )
        response, _ = self.create(quantity="2", unit="butir", estimated_expires_on=str(self.today))
        row.gram_equivalent = 100
        row.save()
        self.assertEqual(available_grams(self.user)[self.ingredient.pk], 100)
        self.assertEqual(response.status_code, 201)
        item = PantryItem.objects.get()
        self.assertEqual(self.edit(item, location="freezer").status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.grams_per_unit, 50)

    def test_deleting_account_can_cascade_its_batches_and_operations(self):
        self.create()
        self.user.delete()
        self.assertFalse(PantryItem.objects.exists())
        self.assertFalse(PantryMovement.objects.exists())

    def test_quota_survives_sessions_and_counts_failed_attempts(self):
        for _ in range(10):
            reserve_llm(self.user, "photo")
        self.client.logout()
        self.client.force_login(self.user)
        with self.assertRaises(StockError) as error:
            reserve_llm(self.user, "photo")
        self.assertEqual(error.exception.status, 429)
        reserve_llm(self.user, "names")
        self.assertEqual(PantryLLMUsage.objects.get(kind="photo").attempts, 10)

    def test_cache_lease_expires_and_old_writer_cannot_overwrite(self):
        old, owned = claim("bym", "test-version")
        self.assertTrue(owned)
        current, owned = claim("bym", "test-version")
        self.assertFalse(owned)
        NameResolution.objects.filter(pk=old.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        current, owned = claim("bym", "test-version")
        self.assertTrue(owned)
        finish(current, self.ingredient.pk)
        finish(old, None)
        self.assertEqual(NameResolution.objects.get().ingredient_id, self.ingredient.pk)

    @patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch("apps.pantry.recommendations._gemini_choices", return_value={"0": "ING-TEST"})
    def test_ai_cache_reuses_guess_across_accounts_without_quota(self, llm):
        first, attempted = resolve_names(["bayam hj"], "one", user=self.user)
        self.assertTrue(attempted)
        other = get_user_model().objects.create_user("other")
        second, attempted = resolve_names(["bayam hj"], "two", user=other)
        self.assertFalse(attempted)
        self.assertEqual(first[0]["ingredient_code"], second[0]["ingredient_code"])
        self.assertEqual(second[0]["method"], "ai_cache_perlu_periksa")
        self.assertFalse(PantryLLMUsage.objects.filter(user=other).exists())
        llm.assert_called_once()

    def test_recipe_matching_checks_servings_and_does_not_consume_stock(self):
        self.batch()
        recipe = Recipe.objects.create(
            recipe_code="RCP-MDL-TEST", name="Sayur", base_servings=1, is_plannable=True
        )
        RecipeTag.objects.create(
            recipe_tag_code="TAG-TEST", recipe=recipe, tag="halal", source="test"
        )
        RecipeIngredient.objects.create(
            recipe_ingredient_code="RI-TEST",
            recipe=recipe,
            ingredient=self.ingredient,
            quantity=60,
            unit="g",
            quantity_status="test",
            source="test",
        )
        self.assertTrue(recipe_matches(self.user, 1)[0]["complete"])
        self.assertFalse(recipe_matches(self.user, 2)[0]["complete"])
        self.assertTrue(recipe_matches(self.user)[0]["instructions_pending_review"])
        self.assertEqual(PantryItem.objects.get().quantity, 100)
        self.assertFalse(PantryMovement.objects.exists())
        self.assertEqual(Client().get(reverse("modul2-recipes")).status_code, 401)
        self.assertEqual(
            self.client.get(reverse("modul2-recipes"), {"servings": "nan"}).status_code, 400
        )

    def test_young_accounts_cannot_promote_shared_corrections(self):
        from .models import PantryNameCorrection

        for index in range(10):
            user = get_user_model().objects.create_user(f"young-{index}")
            PantryNameCorrection.objects.create(
                user=user,
                session_id=str(index),
                raw_name="BXYM",
                normalized_name="bxym",
                ingredient=self.ingredient,
                confirmed_by_user=True,
            )
        results, _ = resolve_names(["BXYM"], "test", user=self.user, allow_llm=False)
        self.assertNotEqual(results[0]["method"], "koreksi_bersama")

    @patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch("apps.pantry.recommendations._gemini_choices", return_value={"0": "ING-TEST"})
    def test_duplicate_names_share_one_prompt_and_apply_to_both_rows(self, llm):
        results, attempted = resolve_names(["bayam hj", "bayam hj"], "test", user=self.user)
        self.assertTrue(attempted)
        self.assertEqual(
            [row["ingredient_code"] for row in results], [self.ingredient.pk, self.ingredient.pk]
        )
        self.assertEqual(len(llm.call_args.args[0]), 1)

    @patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch("apps.pantry.recommendations._gemini_choices", return_value={"0": "ING-TEST"})
    def test_account_quota_cannot_poison_shared_cache(self, llm):
        for _ in range(10):
            reserve_llm(self.user, "names")
        _, attempted = resolve_names(["bayam hj"], "test", user=self.user)
        self.assertFalse(attempted)
        llm.assert_not_called()
        other = get_user_model().objects.create_user("other")
        results, attempted = resolve_names(["bayam hj"], "other", user=other)
        self.assertTrue(attempted)
        self.assertEqual(results[0]["ingredient_code"], self.ingredient.pk)
