"""One provider call per scan route; shared untrusted photo/text cache."""

import json
import re
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Ingredient

from .ai_cache import claim, finish
from .catalog_context import catalog_snapshot
from .forms import PantryItemForm
from .models import NameResolution, PantryItem, PantryLLMUsage, PantryNameCorrection
from .receipt_ocr import clean_items
from .recommendations import _gemini_choices, resolve_names
from .test_helpers import authenticate


@patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
class SingleScanTests(TestCase):
    def setUp(self):
        self.user = authenticate(self.client)
        self.ingredient = Ingredient.objects.create(
            ingredient_code="ING-BAYAM", name="Bayam", category="sayur", base_unit="g"
        )

    def photo(self):
        return self.client.post(
            reverse("modul2-ocr-fallback"),
            {
                "image": SimpleUploadedFile(
                    "receipt.jpg", b"\xff\xd8\xfftest", content_type="image/jpeg"
                )
            },
        )

    @patch("apps.pantry.recommendations._gemini_choices")
    @patch(
        "apps.pantry.receipt_ocr.generate_json",
        return_value={
            "items": [
                {
                    "raw": "bayam hj",
                    "name": "Bayam",
                    "code": "ING-BAYAM",
                    "quantity": "1",
                    "unit": "ikat",
                }
            ]
        },
    )
    def test_photo_reads_and_matches_once_then_text_reuses_same_cache(self, photo_ai, text_ai):
        response = self.photo()
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["raw"], "bayam hj")
        self.assertEqual(item["ingredient_code"], self.ingredient.pk)
        self.assertEqual(item["method"], "ai_foto_perlu_periksa")
        results, attempted = resolve_names(["bayam hj"], "next-day", user=self.user)
        self.assertFalse(attempted)
        self.assertEqual(results[0]["method"], "ai_cache_perlu_periksa")
        self.assertEqual(results[0]["ingredient_code"], self.ingredient.pk)
        photo_ai.assert_called_once()
        text_ai.assert_not_called()
        self.assertEqual(PantryLLMUsage.objects.get(kind="photo").attempts, 1)
        self.assertFalse(PantryLLMUsage.objects.filter(kind="names").exists())
        self.assertFalse(PantryItem.objects.exists())
        payload = {
            "source": "ocr",
            "operation_key": str(uuid4()),
            "items": [
                {
                    "name": item["name"],
                    "original_name": item["raw"],
                    "ingredient_code": item["ingredient_code"],
                    "quantity": "1",
                    "unit": "g",
                }
            ],
        }
        self.assertEqual(
            self.client.post(
                reverse("modul2-items"), data=json.dumps(payload), content_type="application/json"
            ).status_code,
            201,
        )
        self.assertFalse(PantryNameCorrection.objects.exists())
        prompt = photo_ai.call_args.args[0][0]["text"]
        self.assertIn("ING-BAYAM|Bayam", prompt)
        schema = photo_ai.call_args.kwargs["generation_config"]["responseSchema"]
        self.assertTrue(schema["properties"]["items"]["items"]["properties"]["code"]["nullable"])

    @patch("apps.pantry.recommendations._gemini_choices")
    @patch(
        "apps.pantry.receipt_ocr.generate_json",
        return_value={
            "items": [
                {
                    "raw": "Bayam",
                    "name": "Bayam",
                    "code": "NOT-A-CODE",
                    "quantity": "?",
                    "unit": "ikat",
                }
            ]
        },
    )
    def test_invalid_photo_code_is_null_then_resolved_locally(self, photo_ai, text_ai):
        self.assertIsNone(
            clean_items(
                {
                    "items": [
                        {"raw": "Bayam", "name": "Bayam", "code": {}, "quantity": "1", "unit": "g"}
                    ]
                }
            )[0]["ingredient_code"]
        )
        row = self.photo().json()["items"][0]
        self.assertEqual(row["ingredient_code"], self.ingredient.pk)
        self.assertEqual(row["quantity"], "")
        self.assertEqual(row["unit"], "")
        self.assertFalse(NameResolution.objects.exists())
        photo_ai.assert_called_once()
        text_ai.assert_not_called()

    def test_bad_raw_is_rejected_and_empty_raw_uses_name(self):
        rows = clean_items(
            {
                "items": [
                    {"raw": value, "name": "Bayam", "quantity": "1", "unit": "g"}
                    for value in ({}, "x" * 256, "")
                ]
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["raw"], "Bayam")

    @patch("apps.pantry.recommendations._gemini_choices")
    @patch("apps.pantry.receipt_ocr.generate_json")
    def test_photo_failure_followed_by_local_suggestions_never_calls_text(self, photo_ai, text_ai):
        from .gemini import GeminiUnavailable

        photo_ai.side_effect = GeminiUnavailable("Unavailable")
        self.assertEqual(self.photo().status_code, 502)
        response = self.client.post(
            reverse("modul2-suggestions"),
            data=json.dumps({"names": ["bayam hj"], "allow_llm": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        photo_ai.assert_called_once()
        text_ai.assert_not_called()
        self.assertFalse(PantryLLMUsage.objects.filter(kind="names").exists())

    @patch("apps.pantry.recommendations._gemini_choices")
    def test_thirty_unresolved_names_are_one_call_and_one_quota_attempt(self, text_ai):
        text_ai.return_value = {str(i): self.ingredient.pk for i in range(30)}
        names = [f"bayam x{i:02d}" for i in range(30)]
        results, attempted = resolve_names(names, "test", user=self.user)
        self.assertTrue(attempted)
        self.assertEqual(len(text_ai.call_args.args[0]), 30)
        self.assertTrue(all(row["ingredient_code"] == self.ingredient.pk for row in results))
        text_ai.assert_called_once()
        self.assertEqual(PantryLLMUsage.objects.get(kind="names").attempts, 1)

    @patch("apps.pantry.recommendations.generate_json")
    def test_structured_text_matches_are_validated_and_budgeted(self, generate):
        rows = [
            {
                "index": str(i),
                "ocr": "B",
                "candidates": [{"ingredient_code": self.ingredient.pk, "name": "Bayam"}],
            }
            for i in range(30)
        ]
        generate.return_value = {
            "matches": [
                {"i": 0, "code": self.ingredient.pk},
                {"i": 1, "code": "INVALID"},
                {"i": 2, "code": {}},
                {"i": True, "code": self.ingredient.pk},
                {"i": 99, "code": self.ingredient.pk},
            ]
        }
        self.assertEqual(_gemini_choices(rows), {"0": self.ingredient.pk, "1": None, "2": None})
        config = generate.call_args.kwargs["generation_config"]
        self.assertEqual(config["maxOutputTokens"], 1450)
        self.assertIn("matches", config["responseSchema"]["properties"])
        generate.return_value = {
            "matches": [{"i": 0, "code": self.ingredient.pk}, {"i": 0, "code": self.ingredient.pk}]
        }
        self.assertIsNone(_gemini_choices(rows)["0"])

    def test_catalogue_changes_invalidate_cache_and_prompt_order_is_stable(self):
        first = catalog_snapshot()
        record, _ = claim("bayam hj", first["version"])
        finish(record, self.ingredient.pk)
        self.assertEqual(catalog_snapshot()["version"], first["version"])
        self.ingredient.name = "Bayam Merah"
        self.ingredient.save()
        self.assertNotEqual(catalog_snapshot()["version"], first["version"])
        results, _ = resolve_names(["bayam hj"], "test", user=self.user, allow_llm=False)
        self.assertNotEqual(results[0]["method"], "ai_cache_perlu_periksa")

    @patch("apps.pantry.recommendations._gemini_choices", return_value={"0": "ING-BAYAM"})
    def test_cached_photo_code_outside_local_candidates_is_refreshed(self, text_ai):
        other = Ingredient.objects.create(
            ingredient_code="ING-SAWI", name="Sawi", category="sayur", base_unit="g"
        )
        record, _ = claim("bayam hj", catalog_snapshot()["version"])
        finish(record, other.pk)
        result, attempted = resolve_names(["bayam hj"], "test", user=self.user)
        self.assertTrue(attempted)
        self.assertEqual(result[0]["ingredient_code"], self.ingredient.pk)
        self.assertEqual(NameResolution.objects.get().ingredient_id, self.ingredient.pk)

    def test_default_django_errors_are_indonesian(self):
        form = PantryItemForm(
            {"name": "Bayam", "category": "INVALID", "quantity": "123456789012345", "unit": "g"}
        )
        self.assertFalse(form.is_valid())
        self.assertNotIn("Select a valid choice", str(form.errors))
        self.assertNotIn("Ensure that", str(form.errors))
        self.assertIn("pilihan", str(form.errors).lower())

    def test_indonesian_locale_keeps_machine_decimal_inputs_valid(self):
        PantryItem.objects.create(
            user=self.user,
            session_id="test",
            name="Bayam",
            quantity="1.25",
            unit="pack",
            source="manual",
            pack_weight_g="250.5",
        )
        page = self.client.get(reverse("modul2"))
        html = page.content.decode()
        quantity = re.search(r'data-edit-quantity[^>]*value="([^"]*)"', html).group(1)
        weight = re.search(r'data-edit-weight[^>]*value="([^"]*)"', html).group(1)
        self.assertNotIn(",", quantity + weight)
        self.assertEqual(Decimal(quantity), Decimal("1.25"))
        self.assertEqual(Decimal(weight), Decimal("250.5"))
