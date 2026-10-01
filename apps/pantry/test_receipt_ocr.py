import io
import json
import os
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import PantryItem
from .receipt_ocr import clean_items, gemini_read_receipt, image_mime


class ReceiptOCRFallbackTests(TestCase):
    @patch.dict(os.environ, {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    def test_page_discloses_conditional_photo_fallback(self):
        response = self.client.get(reverse("modul2"))
        self.assertContains(response, 'data-gemini-fallback="true"')
        self.assertContains(response, "foto struk dikirim ke Gemini")

    @patch.dict(
        os.environ,
        {
            "PANTRY_LLM_PROVIDER": "gemini",
            "PANTRY_LLM_MODEL": "gemini-2.5-flash-lite",
            "GEMINI_API_KEY": "test-key",
        },
    )
    @patch("apps.pantry.gemini.urlopen")
    def test_gemini_receives_photo_and_returns_structured_rows(self, urlopen):
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "items": [
                                            {"name": "Bayam", "quantity": "1", "unit": "ikat"}
                                        ],
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        rows = gemini_read_receipt(b"\xff\xd8\xfftest", "image/jpeg")
        self.assertEqual(rows[0], {"name": "Bayam", "quantity": "1", "unit": "ikat"})
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")

    def test_response_items_are_review_only_and_invalid_values_removed(self):
        items = clean_items(
            {
                "items": [
                    {"name": "  Bayam   Hijau ", "quantity": "2", "unit": "ikat"},
                    {"name": "Tempe", "quantity": "?", "unit": "pack"},
                    {"name": "Tahu", "quantity": "1", "unit": "unknown"},
                    {"name": "X", "quantity": "1", "unit": "buah"},
                ]
            }
        )
        self.assertEqual(
            items,
            [
                {"name": "Bayam Hijau", "quantity": "2", "unit": "ikat"},
                {"name": "Tempe", "quantity": "", "unit": ""},
                {"name": "Tahu", "quantity": "1", "unit": ""},
            ],
        )
        self.assertEqual(image_mime(b"\xff\xd8\xfftest"), "image/jpeg")
        self.assertIsNone(image_mime(b"not an image"))

    @patch.dict(os.environ, {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch(
        "apps.pantry.views.gemini_read_receipt",
        return_value=[{"name": "Bayam", "quantity": "1", "unit": "ikat"}],
    )
    def test_image_fallback_returns_draft_without_saving(self, gemini):
        upload = SimpleUploadedFile("receipt.jpg", b"\xff\xd8\xfftest", content_type="image/jpeg")
        response = self.client.post(reverse("modul2-ocr-fallback"), {"image": upload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["name"], "Bayam")
        gemini.assert_called_once_with(b"\xff\xd8\xfftest", "image/jpeg")
        self.assertEqual(PantryItem.objects.count(), 0)

    @patch.dict(os.environ, {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch("apps.pantry.views.gemini_read_receipt")
    def test_invalid_image_never_calls_gemini(self, gemini):
        upload = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        response = self.client.post(reverse("modul2-ocr-fallback"), {"image": upload})
        self.assertEqual(response.status_code, 400)
        gemini.assert_not_called()

    @patch.dict(os.environ, {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    @patch("apps.pantry.views.gemini_read_receipt", return_value=[])
    def test_daily_limit_blocks_extra_image_requests(self, gemini):
        for _ in range(10):
            upload = SimpleUploadedFile(
                "receipt.jpg", b"\xff\xd8\xfftest", content_type="image/jpeg"
            )
            self.assertEqual(
                self.client.post(reverse("modul2-ocr-fallback"), {"image": upload}).status_code, 200
            )
        upload = SimpleUploadedFile("receipt.jpg", b"\xff\xd8\xfftest", content_type="image/jpeg")
        self.assertEqual(
            self.client.post(reverse("modul2-ocr-fallback"), {"image": upload}).status_code, 429
        )
        self.assertEqual(gemini.call_count, 10)

    @patch.dict(os.environ, {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    def test_fallback_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("modul2"))
        upload = SimpleUploadedFile("receipt.jpg", b"\xff\xd8\xfftest", content_type="image/jpeg")
        self.assertEqual(
            client.post(reverse("modul2-ocr-fallback"), {"image": upload}).status_code, 403
        )
