import json
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Ingredient, IngredientAlias, IngredientShelfLife

from .models import PantryNameCorrection
from .recommendations import resolve_names
from .test_helpers import authenticate


class PantryRecommendationTests(TestCase):
    def setUp(self):
        self.user = authenticate(self.client)

    @classmethod
    def setUpTestData(cls):
        cls.bayam = Ingredient.objects.create(
            ingredient_code="ING-BAYAM", name="Bayam", category="sayur", base_unit="g"
        )
        cls.sawi = Ingredient.objects.create(
            ingredient_code="ING-SAWI", name="Sawi", category="sayur", base_unit="g"
        )
        IngredientAlias.objects.create(
            alias_code="ALS-BAYAM-HIJAU",
            source="test",
            raw_name="Bayam Hijau",
            ingredient=cls.bayam,
            mapping_status="reviewed",
        )
        IngredientShelfLife.objects.create(
            shelf_life_code="SHF-BAYAM",
            ingredient=cls.bayam,
            storage_location="kulkas",
            min_days=3,
            max_days=7,
            warning_days=1,
            starting_event="tanggal_pembelian",
            source="FoodKeeper test",
            source_url="https://example.org/bayam",
            source_duration="3-7 days",
            days_conversion_method="direct",
            shelf_life_status="referensi_perlu_verifikasi_lokal",
        )

    def post_suggestions(self, names):
        return self.client.post(
            reverse("modul2-suggestions"),
            data=json.dumps({"names": names}),
            content_type="application/json",
        )

    @patch("apps.pantry.recommendations._gemini_choices")
    def test_exact_alias_skips_llm_and_returns_source_based_storage(self, llm):
        response = self.post_suggestions(["Bayam Hijau"])
        self.assertEqual(response.status_code, 200)
        result = response.json()["suggestions"][0]
        self.assertEqual(result["ingredient_code"], "ING-BAYAM")
        self.assertEqual(result["method"], "katalog")
        # A refrigerated reference must never be reused for default room storage.
        self.assertIsNone(result["storage"])
        llm.assert_not_called()

    @patch("apps.pantry.recommendations._gemini_choices")
    def test_short_pantry_name_keeps_catalogue_match_and_can_be_saved(self, llm):
        Ingredient.objects.create(
            ingredient_code="ING-BERAS-SUPER",
            name="Beras Kualitas Super I",
            category="padi",
            base_unit="g",
        )
        result = self.post_suggestions(["Beras Kualitas Super I"]).json()["suggestions"][0]
        self.assertEqual(result["suggested_name"], "Beras")
        self.assertEqual(result["ingredient_code"], "ING-BERAS-SUPER")
        llm.assert_not_called()

        response = self.client.post(
            reverse("modul2-items"),
            data=json.dumps(
                {
                    "source": "ocr",
                    "operation_key": str(uuid4()),
                    "items": [
                        {
                            "name": result["suggested_name"],
                            "original_name": result["raw_name"],
                            "ingredient_code": result["ingredient_code"],
                            "quantity": "1",
                            "unit": "kg",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        from .models import PantryItem

        self.assertEqual(PantryItem.objects.get().name, "Beras")

    @patch("apps.pantry.recommendations._gemini_choices", return_value={"0": "ING-SAWI"})
    @patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    def test_llm_may_only_choose_offered_candidate(self, llm):
        results, attempted = resolve_names(["bayam hj"], "session", user=self.user, allow_llm=True)
        self.assertTrue(attempted)
        self.assertIsNone(results[0]["ingredient_code"])
        llm.assert_called_once()

    @patch("apps.pantry.recommendations._gemini_choices", return_value={})
    @patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
    def test_ambiguous_receipt_items_share_one_llm_request(self, llm):
        results, attempted = resolve_names(
            ["bayam hj", "sawi hj"], "session", user=self.user, allow_llm=True
        )
        self.assertTrue(attempted)
        self.assertEqual(len(results), 2)
        llm.assert_called_once()
        prompt_rows = llm.call_args.args[0]
        self.assertEqual([row["ocr"] for row in prompt_rows], ["bayam hj", "sawi hj"])

    @patch("apps.pantry.recommendations._gemini_choices")
    def test_accepted_correction_is_reused_without_llm(self, llm):
        self.client.get(reverse("modul2"))
        response = self.client.post(
            reverse("modul2-items"),
            data=json.dumps(
                {
                    "source": "ocr",
                    "operation_key": str(uuid4()),
                    "items": [
                        {
                            "name": "Bayam",
                            "original_name": "BYM HIJAU",
                            "accepted": True,
                            "ingredient_code": "ING-BAYAM",
                            "quantity": "1",
                            "unit": "ikat",
                            "location": "chiller",
                            "shelf_life_days": 3,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PantryNameCorrection.objects.count(), 1)
        result = self.post_suggestions(["BYM HIJAU"]).json()["suggestions"][0]
        self.assertEqual(result["ingredient_code"], "ING-BAYAM")
        self.assertEqual(result["method"], "koreksi_anda")
        llm.assert_not_called()

    @patch("apps.pantry.recommendations._gemini_choices", return_value={})
    def test_other_account_does_not_get_private_correction(self, llm):
        self.client.get(reverse("modul2"))
        session_id = self.client.session["pantry_session_id"]
        PantryNameCorrection.objects.create(
            user=self.user,
            session_id=session_id,
            raw_name="BXYM",
            normalized_name="bxym",
            ingredient=self.bayam,
            confirmed_by_user=True,
        )
        from django.test import Client

        other = Client()
        authenticate(other, "other")
        response = other.post(
            reverse("modul2-suggestions"),
            data=json.dumps({"names": ["BXYM"]}),
            content_type="application/json",
        )
        self.assertNotEqual(response.json()["suggestions"][0]["method"], "koreksi_anda")

    @patch("apps.pantry.recommendations._gemini_choices")
    def test_ten_mature_consistent_corrections_become_shared_suggestion(self, llm):
        for index in range(10):
            PantryNameCorrection.objects.create(
                session_id=f"session-{index}",
                user=get_user_model().objects.create_user(
                    username=f"voter-{index}", date_joined=timezone.now() - timedelta(days=8)
                ),
                raw_name="BXYM",
                normalized_name="bxym",
                ingredient=self.bayam,
                confirmed_by_user=True,
            )
        result, attempted = resolve_names(["BXYM"], "another-session")
        self.assertEqual(result[0]["ingredient_code"], "ING-BAYAM")
        self.assertEqual(result[0]["method"], "koreksi_bersama")
        self.assertFalse(attempted)
        llm.assert_not_called()

    def test_conflicting_community_corrections_are_not_trusted(self):
        for index in range(10):
            PantryNameCorrection.objects.create(
                session_id=f"session-{index}",
                user=get_user_model().objects.create_user(
                    username=f"voter-{index}", date_joined=timezone.now() - timedelta(days=8)
                ),
                raw_name="BXYM",
                normalized_name="bxym",
                ingredient=self.bayam,
                confirmed_by_user=True,
            )
        PantryNameCorrection.objects.create(
            session_id="conflicting",
            user=get_user_model().objects.create_user(
                username="conflicting", date_joined=timezone.now() - timedelta(days=8)
            ),
            raw_name="BXYM",
            normalized_name="bxym",
            ingredient=self.sawi,
            confirmed_by_user=True,
        )
        result, _ = resolve_names(["BXYM"], "another-session", allow_llm=False)
        self.assertNotEqual(result[0]["method"], "koreksi_bersama")

    def test_unrecognized_name_does_not_invent_storage(self):
        result = self.post_suggestions(["PRODUK XYZ 123"]).json()["suggestions"][0]
        self.assertIsNone(result["ingredient_code"])
        self.assertIsNone(result["storage"])

    def test_estimated_date_uses_supplied_purchase_date(self):
        response = self.client.post(
            reverse("modul2-items"),
            data=json.dumps(
                {
                    "source": "ocr",
                    "operation_key": str(uuid4()),
                    "items": [
                        {
                            "name": "Bayam",
                            "quantity": "1",
                            "unit": "ikat",
                            "location": "chiller",
                            "shelf_life_days": 3,
                            "starting_on": "2026-09-27",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        from .models import PantryItem

        self.assertEqual(PantryItem.objects.get().estimated_expires_on, date(2026, 9, 30))

    def test_suggestions_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(reverse("modul2"))
        response = client.post(
            reverse("modul2-suggestions"),
            data=json.dumps({"names": ["Bayam"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_suggestions_reject_oversized_batch(self):
        self.assertEqual(self.post_suggestions(["Bayam"] * 31).status_code, 400)
