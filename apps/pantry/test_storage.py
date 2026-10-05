import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Ingredient, IngredientShelfLife

from .models import PantryItem
from .storage import storage_options
from .test_helpers import authenticate


class PantryStorageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ingredient = Ingredient.objects.create(
            ingredient_code="ING-STORAGE-TEST", name="Bahan Uji", category="test", base_unit="g"
        )
        # Synthetic references for testing the calculation, not food guidance.
        for location, days in (("suhu_ruang", 2), ("kulkas", 5), ("freezer", 20)):
            IngredientShelfLife.objects.create(
                shelf_life_code=f"SHF-TEST-{location}",
                ingredient=cls.ingredient,
                storage_location=location,
                min_days=days,
                max_days=days + 1,
                warning_days=1,
                starting_event="tanggal_pembelian",
                source="Test only",
                source_url="https://example.org/test",
                source_duration="test",
                days_conversion_method="test",
                shelf_life_status="test",
            )

    def setUp(self):
        self.user = authenticate(self.client)
        self.today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
        self.client.get(reverse("modul2"))

    def add(self, source="manual", **changes):
        return self.client.post(
            reverse("modul2-items"),
            content_type="application/json",
            data=json.dumps(
                {
                    "source": source,
                    "operation_key": str(uuid4()),
                    "items": [
                        {
                            "name": "Bahan Uji",
                            "category": "lainnya",
                            "quantity": "1",
                            "unit": "pack",
                            **changes,
                        }
                    ],
                }
            ),
        )

    def update(self, item, **changes):
        return self.client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            content_type="application/json",
            data=json.dumps({**changes, "version": item.version, "operation_key": str(uuid4())}),
        )

    @patch("apps.pantry.recommendations._gemini_choices")
    def test_manual_and_ocr_default_to_room_and_get_same_date_without_llm(self, llm):
        for source in ("manual", "ocr"):
            self.assertEqual(self.add(source).status_code, 201)
        for item in PantryItem.objects.all():
            self.assertEqual(item.location, "suhu_ruang")
            self.assertEqual(item.ingredient_id, self.ingredient.pk)
            self.assertEqual(item.starting_on, self.today)
            self.assertEqual(item.estimated_expires_on, self.today + timedelta(days=2))
        llm.assert_not_called()

    def test_purchase_date_is_preserved_when_location_changes_repeatedly(self):
        start = self.today - timedelta(days=1)
        self.add("ocr", starting_on=start.isoformat())
        item = PantryItem.objects.get()
        for location, days in (("chiller", 5), ("freezer", 20), ("suhu_ruang", 2)):
            # A stale date sent by the client must not override automatic recalculation.
            response = self.update(
                item,
                location=location,
                expiry_mode="auto",
                estimated_expires_on=self.today.isoformat(),
            )
            self.assertEqual(response.status_code, 200)
            item.refresh_from_db()
            self.assertEqual(item.starting_on, start)
            self.assertEqual(item.estimated_expires_on, start + timedelta(days=2))
            self.assertEqual(
                response.json()["estimated_expires_on"], item.estimated_expires_on.isoformat()
            )

    def test_unknown_ingredient_is_saved_without_invented_expiry(self):
        self.add(name="Bahan Yang Tidak Ada XYZ")
        item = PantryItem.objects.get()
        self.assertEqual(item.location, "suhu_ruang")
        self.assertIsNone(item.ingredient_id)
        self.assertIsNone(item.estimated_expires_on)
        page = self.client.get(reverse("modul2"))
        self.assertContains(page, "Acuan masa simpan untuk lokasi ini belum tersedia")

    def test_no_room_reference_does_not_borrow_fridge_and_switch_clears_old_date(self):
        IngredientShelfLife.objects.filter(storage_location="suhu_ruang").delete()
        self.add()
        item = PantryItem.objects.get()
        self.assertIsNone(item.estimated_expires_on)
        self.update(item, location="chiller")
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, self.today + timedelta(days=5))
        self.update(item, location="suhu_ruang")
        item.refresh_from_db()
        self.assertIsNone(item.estimated_expires_on)
        self.assertIsNone(item.shelf_life_days)

    def test_manual_date_override_is_allowed_and_kept_on_same_location(self):
        self.add()
        item = PantryItem.objects.get()
        chosen = self.today + timedelta(days=1)
        self.update(
            item, location="chiller", estimated_expires_on=chosen.isoformat(), expiry_mode="manual"
        )
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, chosen)
        self.update(item, location="chiller", estimated_expires_on=chosen.isoformat())
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, chosen)

    def test_expired_item_is_not_refreshed_from_today(self):
        start = self.today - timedelta(days=10)
        self.add(starting_on=start.isoformat())
        item = PantryItem.objects.get()
        self.update(item, location="chiller", expiry_mode="auto")
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, start + timedelta(days=2))
        self.assertLess(item.estimated_expires_on, self.today)

    def test_legacy_item_uses_added_date_without_writing_on_get(self):
        session_id = self.client.session["pantry_session_id"]
        item = PantryItem.objects.create(
            user=self.user,
            session_id=session_id,
            name="Bahan Uji",
            category="lainnya",
            quantity=1,
            unit="g",
            location="",
            source="manual",
        )
        start = self.today - timedelta(days=4)
        PantryItem.objects.filter(pk=item.pk).update(added_at=timezone.now() - timedelta(days=4))
        page = self.client.get(reverse("modul2"))
        self.assertContains(page, "pantry-storage-data")
        preview = page.context["pantry_storage"][str(item.pk)]
        self.assertEqual(preview["location"], "suhu_ruang")
        self.assertEqual(
            preview["options"]["chiller"]["estimated_expires_on"],
            (start + timedelta(days=5)).isoformat(),
        )
        item.refresh_from_db()
        self.assertEqual(item.location, "")
        self.assertIsNone(item.ingredient_id)
        self.update(item, location="chiller", expiry_mode="auto")
        item.refresh_from_db()
        self.assertEqual(item.starting_on, start)
        self.assertEqual(item.ingredient_id, self.ingredient.pk)
        self.assertEqual(item.estimated_expires_on, start + timedelta(days=5))

    def test_storage_options_use_only_three_locations(self):
        options = storage_options(self.ingredient.pk)
        self.assertEqual(options["freezer"]["min_days"], 20)
        self.assertEqual(options["suhu_ruang"]["min_days"], 2)
        self.assertEqual(set(options), {"chiller", "freezer", "suhu_ruang"})
        self.assertEqual(
            PantryItem.LOCATION_CHOICES,
            [
                ("chiller", "Kulkas"),
                ("freezer", "Freezer"),
                ("suhu_ruang", "Suhu Ruang"),
            ],
        )
        self.add()
        page = self.client.get(reverse("modul2"))
        self.assertContains(page, '<option value="chiller">Kulkas</option>')
        self.assertNotContains(page, "Lemari Kering")
        self.assertNotContains(page, "Kulkas Bawah")

    def test_legacy_dry_cabinet_migration_preserves_stock_and_expiry(self):
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps
        from django.db import connection

        self.add()
        item = PantryItem.objects.get()
        expiry = item.estimated_expires_on
        PantryItem.objects.filter(pk=item.pk).update(location="lemari_kering")
        migration = import_module("apps.pantry.migrations.0007_simplify_storage_locations")
        migration.normalize_legacy_locations(apps, SimpleNamespace(connection=connection))
        item.refresh_from_db()
        self.assertEqual(item.location, "suhu_ruang")
        self.assertEqual(item.estimated_expires_on, expiry)
        self.assertEqual(PantryItem.objects.count(), 1)

    def test_other_account_cannot_trigger_recalculation(self):
        self.add()
        item = PantryItem.objects.get()
        other = Client()
        authenticate(other, "other")
        response = other.patch(
            reverse("modul2-item-details", args=[item.pk]),
            content_type="application/json",
            data=json.dumps(
                {
                    "version": item.version,
                    "operation_key": str(uuid4()),
                    "location": "chiller",
                    "expiry_mode": "auto",
                }
            ),
        )
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.location, "suhu_ruang")


class PantryStorageCatalogTests(TestCase):
    fixtures = ["catalog_seed.json"]

    def test_tempe_matches_local_catalogue_and_has_no_room_estimate(self):
        client = Client()
        authenticate(client)
        response = client.post(
            reverse("modul2-items"),
            content_type="application/json",
            data=json.dumps(
                {
                    "source": "manual",
                    "operation_key": str(uuid4()),
                    "items": [
                        {
                            "name": "tempe",
                            "category": "tahu_tempe_kacang",
                            "quantity": "1",
                            "unit": "pack",
                        }
                    ],
                }
            ),
        )
        self.assertEqual(response.status_code, 201)
        item = PantryItem.objects.get()
        self.assertEqual(item.ingredient_id, "ING-TEMPE")
        self.assertEqual(item.location, "suhu_ruang")
        self.assertIsNone(item.estimated_expires_on)
        response = client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            content_type="application/json",
            data=json.dumps(
                {
                    "version": item.version,
                    "operation_key": str(uuid4()),
                    "location": "chiller",
                    "expiry_mode": "auto",
                }
            ),
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.estimated_expires_on, item.starting_on + timedelta(days=3))
