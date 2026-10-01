import json
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import PantryItem


class PantryFlowTests(TestCase):
    def setUp(self):
        self.client.get(reverse("modul2"))
        self.item = {
            "name": "  Bayam   Hijau ",
            "category": "sayuran",
            "quantity": "1",
            "unit": "ikat",
            "location": "chiller",
            "shelf_life_days": "3",
        }

    def post_items(self, items, source="ocr", client=None):
        return (client or self.client).post(
            reverse("modul2-items"),
            data=json.dumps({"source": source, "items": items}),
            content_type="application/json",
        )

    def test_ocr_rows_are_saved_only_after_explicit_post(self):
        self.assertEqual(PantryItem.objects.count(), 0)
        response = self.post_items([self.item])
        self.assertEqual(response.status_code, 201)
        item = PantryItem.objects.get()
        self.assertEqual(item.name, "Bayam Hijau")
        self.assertEqual(item.quantity, Decimal("1"))
        self.assertEqual(item.source, "ocr")
        self.assertEqual(
            item.estimated_expires_on,
            timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")) + timedelta(days=3),
        )
        self.assertContains(self.client.get(reverse("modul2")), "Bayam Hijau")

    def test_manual_item_uses_same_pantry_without_price_or_store(self):
        response = self.post_items([self.item], source="manual")
        self.assertEqual(response.status_code, 201)
        fields = {field.name for field in PantryItem._meta.fields}
        self.assertNotIn("price", fields)
        self.assertNotIn("store", fields)
        self.assertEqual(PantryItem.objects.get().source, "manual")

    def test_inventory_hides_source_and_places_small_information_under_expiry(self):
        self.post_items([self.item], source="manual")
        page = self.client.get(reverse("modul2"))
        self.assertNotContains(page, '<th scope="col">Sumber</th>')
        self.assertContains(page, 'class="pantry-actions"')
        self.assertContains(page, 'class="storage-feedback" data-storage-feedback')
        html = page.content.decode()
        expiry_cell = html.split("data-pantry-expiry", 1)[1].split("</td>", 1)[0]
        self.assertIn("data-storage-feedback", expiry_cell)
        self.assertEqual(PantryItem.objects.get().source, "manual")

    def test_ocr_can_save_without_category_location_or_expiry(self):
        simple_item = {"name": "Tahu Putih", "quantity": "2", "unit": "kotak"}
        response = self.post_items([simple_item])
        self.assertEqual(response.status_code, 201)
        item = PantryItem.objects.get()
        self.assertEqual(item.category, "")
        self.assertEqual(item.location, "suhu_ruang")
        self.assertIsNone(item.shelf_life_days)
        self.assertIsNone(item.estimated_expires_on)
        page = self.client.get(reverse("modul2"))
        self.assertContains(page, "Tahu Putih")
        self.assertContains(page, "Belum ditentukan", count=1)
        self.assertContains(page, "data-pantry-location")
        self.assertContains(page, "data-pantry-expiry")

    def test_manual_item_needs_category_but_not_location_or_expiry(self):
        simple_item = {"name": "Tahu Putih", "quantity": "2", "unit": "kotak"}
        response = self.post_items([simple_item], source="manual")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PantryItem.objects.count(), 0)
        response = self.post_items([{**simple_item, "category": "protein_nabati"}], source="manual")
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(PantryItem.objects.get().estimated_expires_on)

    def test_manual_pack_unit_is_accepted_and_legacy_ocr_units_remain(self):
        page = self.client.get(reverse("modul2"))
        manual_select = (
            page.content.decode()
            .split('<select id="ingredient-unit"', 1)[1]
            .split("</select>", 1)[0]
        )
        ocr_select = (
            page.content.decode()
            .split('<select id="ocr-unit-options"', 1)[1]
            .split("</select>", 1)[0]
        )
        self.assertIn('<option value="pack">pack / bungkus</option>', manual_select)
        self.assertNotIn('<option value="papan">', manual_select)
        self.assertEqual(ocr_select.count("<option value="), 10)  # placeholder + nine units
        self.assertIn('<option value="pack">pack / bungkus</option>', ocr_select)
        self.assertNotIn('<option value="papan">', ocr_select)
        self.assertNotIn('<option value="kotak">', ocr_select)
        response = self.post_items(
            [
                {
                    "name": "Roti",
                    "category": "bahan_pokok",
                    "quantity": "1",
                    "unit": "pack",
                }
            ],
            source="manual",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PantryItem.objects.get().unit, "pack")

    def test_manual_category_dropdown_has_six_clear_options(self):
        page = self.client.get(reverse("modul2"))
        category_select = (
            page.content.decode()
            .split('<select id="ingredient-category"', 1)[1]
            .split("</select>", 1)[0]
        )
        self.assertEqual(category_select.count("<option value="), 7)  # placeholder + six categories
        for label in (
            "Sayur &amp; Buah",
            "Daging &amp; Seafood",
            "Tahu, Tempe &amp; Kacang",
            "Beras &amp; Karbohidrat",
            "Bumbu &amp; Minyak",
            "Lainnya",
        ):
            self.assertIn(label, category_select)
        self.assertNotIn('value="protein_hewani"', category_select)
        response = self.post_items(
            [
                {
                    "name": "Bawang Merah",
                    "category": "bumbu_minyak",
                    "quantity": "1",
                    "unit": "kg",
                }
            ],
            source="manual",
        )
        self.assertEqual(response.status_code, 201)

    def test_location_and_expiry_can_be_set_after_saving(self):
        self.post_items([{"name": "Tahu Putih", "quantity": "2", "unit": "kotak"}])
        item = PantryItem.objects.get()
        response = self.client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            data=json.dumps(
                {
                    "location": "chiller",
                    "estimated_expires_on": "2026-10-02",
                    "expiry_mode": "manual",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.location, "chiller")
        self.assertEqual(item.estimated_expires_on.isoformat(), "2026-10-02")
        self.assertContains(self.client.get(reverse("modul2")), 'value="2026-10-02"')

    def test_invalid_details_do_not_change_item(self):
        self.post_items([self.item])
        item = PantryItem.objects.get()
        response = self.client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            data=json.dumps({"location": "unknown", "estimated_expires_on": "not-a-date"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.location, "chiller")

    def test_other_browser_cannot_edit_pantry_item(self):
        self.post_items([self.item])
        item = PantryItem.objects.get()
        other_client = Client()
        response = other_client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            data=json.dumps({"location": "freezer", "estimated_expires_on": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_pantry_item_can_be_deleted_by_its_browser_session(self):
        self.post_items([self.item])
        item = PantryItem.objects.get()
        response = self.client.delete(reverse("modul2-item-delete", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PantryItem.objects.count(), 0)

    def test_other_browser_cannot_delete_pantry_item(self):
        self.post_items([self.item])
        item = PantryItem.objects.get()
        response = Client().delete(reverse("modul2-item-delete", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PantryItem.objects.filter(pk=item.pk).exists())

    def test_invalid_batch_is_atomic(self):
        invalid = {**self.item, "quantity": "0", "unit": "unknown"}
        response = self.post_items([self.item, invalid])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PantryItem.objects.count(), 0)

    def test_pantry_items_are_private_to_browser_session(self):
        self.post_items([self.item])
        other_client = Client()
        response = other_client.get(reverse("modul2"))
        self.assertNotContains(response, "Bayam Hijau")
        self.assertEqual(self.post_items([self.item], client=other_client).status_code, 201)
        self.assertEqual(PantryItem.objects.count(), 2)

    def test_csrf_is_required_for_save(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("modul2"))
        response = self.post_items([self.item], client=client)
        self.assertEqual(response.status_code, 403)

    def test_csrf_is_required_for_edit_and_delete(self):
        self.post_items([self.item])
        item = PantryItem.objects.get()
        client = Client(enforce_csrf_checks=True)
        client.cookies = self.client.cookies.copy()
        response = client.patch(
            reverse("modul2-item-details", args=[item.pk]),
            data=json.dumps({"location": "freezer", "estimated_expires_on": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            client.delete(reverse("modul2-item-delete", args=[item.pk])).status_code, 403
        )

    def test_get_and_wrong_content_type_cannot_save(self):
        self.assertEqual(self.client.get(reverse("modul2-items")).status_code, 405)
        self.assertEqual(
            self.client.post(reverse("modul2-items"), data={"items": []}).status_code, 415
        )
