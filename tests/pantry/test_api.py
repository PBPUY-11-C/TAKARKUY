import json
import os
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.pantry.models import PantryItem

ITEM = {
    "name": "Bayam Hijau",
    "category": "sayur_buah",
    "quantity": "2",
    "unit": "ikat",
    "location": "chiller",
    "shelf_life_days": 3,
}


# Tanpa provider Gemini agar estimasi masa simpan tidak memanggil API sungguhan.
@patch.dict(os.environ, {"PANTRY_LLM_PROVIDER": ""})
class PantryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user("pantry-api", password="Demo1234!")
        cls.other = users.create_user("pantry-other", password="Demo1234!")
        cls.today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))

    def setUp(self):
        self.client.force_login(self.user)

    def post(self, url, data, content_type="application/json"):
        return self.client.post(url, data=json.dumps(data), content_type=content_type)

    def create(self, items=None, key=None):
        return self.post(
            "/api/pantry/items/",
            {"source": "manual", "operation_key": key or str(uuid4()), "items": [ITEM] if items is None else items},
        )

    def item(self, user=None, **fields):
        return PantryItem.objects.create(
            user=user or self.user,
            session_id="test",
            source="manual",
            name=fields.pop("name", "Tahu Putih"),
            category="tahu_tempe_kacang",
            quantity=fields.pop("quantity", 1),
            unit="kotak",
            **fields,
        )

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/pantry/items/").status_code, 403)
        self.assertEqual(self.create().status_code, 403)
        self.assertFalse(PantryItem.objects.exists())

    def test_list_only_returns_own_active_items(self):
        mine = self.item()
        self.item(self.other)
        self.item(name="Habis", quantity=0)
        self.item(name="Dibuang", archived_at=timezone.now())
        response = self.client.get("/api/pantry/items/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [mine.pk])
        self.assertEqual(response.json()[0]["version"], 1)
        self.assertIn("no-store", response["Cache-Control"])

    def test_list_filters_by_expiry_like_web(self):
        expired = self.item(name="Lewat", estimated_expires_on=self.today - timedelta(days=1))
        soon = self.item(name="Segera", estimated_expires_on=self.today + timedelta(days=7))
        self.item(name="Lama", estimated_expires_on=self.today + timedelta(days=30))
        unknown = self.item(name="Tanpa tanggal")
        for value, expected in (("expired", expired), ("next7", soon), ("unknown", unknown)):
            rows = self.client.get(f"/api/pantry/items/?expiry={value}").json()
            self.assertEqual([row["id"] for row in rows], [expected.pk], value)
        self.assertEqual(len(self.client.get("/api/pantry/items/?expiry=all").json()), 4)
        self.assertEqual(self.client.get("/api/pantry/items/?expiry=besok").status_code, 400)

    def test_create_saves_items_and_records_movement(self):
        # Flutter (package http) menambahkan charset ke Content-Type body JSON.
        response = self.post(
            "/api/pantry/items/",
            {"source": "manual", "operation_key": str(uuid4()), "items": [ITEM]},
            content_type="application/json; charset=utf-8",
        )
        self.assertEqual(response.status_code, 201)
        item = PantryItem.objects.get(user=self.user)
        self.assertEqual(response.json(), {"saved": 1, "ids": [item.pk]})
        self.assertEqual(item.estimated_expires_on, self.today + timedelta(days=3))
        self.assertEqual(list(item.movements.values_list("kind", flat=True)), ["in"])

    def test_create_is_idempotent_per_operation_key(self):
        key = str(uuid4())
        self.assertEqual(self.create(key=key).status_code, 201)
        self.assertEqual(self.create(key=key).status_code, 201)
        self.assertEqual(PantryItem.objects.count(), 1)

    def test_create_rejects_invalid_rows(self):
        response = self.create([{**ITEM, "quantity": "-1"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.json())
        self.assertFalse(PantryItem.objects.exists())
        self.assertEqual(self.create([]).status_code, 400)

    def test_detail_includes_movement_history(self):
        self.create()
        item = PantryItem.objects.get()
        body = self.client.get(f"/api/pantry/items/{item.pk}/").json()
        self.assertEqual((body["id"], body["name"], body["version"]), (item.pk, "Bayam Hijau", 1))
        self.assertEqual([row["kind"] for row in body["movements"]], ["Masuk"])
        self.assertEqual(body["movements"][0]["after"], "2.000000")

    def test_update_changes_item_and_records_correction(self):
        self.create()
        item = PantryItem.objects.get()
        response = self.post(
            f"/api/pantry/items/{item.pk}/update/",
            {"version": item.version, "operation_key": str(uuid4()), "quantity": "5"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 2)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.movements.order_by("-pk").first().kind, "correction")

    def test_update_rejects_invalid_data(self):
        item = self.item()
        response = self.post(
            f"/api/pantry/items/{item.pk}/update/",
            {"version": item.version, "operation_key": str(uuid4()), "location": "atap"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
        missing_key = self.post(f"/api/pantry/items/{item.pk}/update/", {"version": 1})
        self.assertEqual(missing_key.status_code, 400)
        item.refresh_from_db()
        self.assertEqual((item.version, item.location), (1, "suhu_ruang"))

    def test_stale_version_is_a_conflict(self):
        item = self.item(version=2)
        response = self.post(
            f"/api/pantry/items/{item.pk}/update/",
            {"version": 1, "operation_key": str(uuid4()), "quantity": "9"},
        )
        self.assertEqual(response.status_code, 409)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_delete_archives_item(self):
        item = self.item()
        response = self.post(
            f"/api/pantry/items/{item.pk}/delete/",
            {"version": item.version, "operation_key": str(uuid4())},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True})
        item.refresh_from_db()
        self.assertIsNotNone(item.archived_at)
        self.assertEqual(item.quantity, 0)
        self.assertEqual(item.movements.get().kind, "discard")
        self.assertEqual(self.client.get("/api/pantry/items/").json(), [])

    def test_other_users_item_is_not_found(self):
        item = self.item(self.other)
        body = {"version": item.version, "operation_key": str(uuid4()), "quantity": "9"}
        self.assertEqual(self.client.get(f"/api/pantry/items/{item.pk}/").status_code, 404)
        self.assertEqual(self.post(f"/api/pantry/items/{item.pk}/update/", body).status_code, 404)
        self.assertEqual(self.post(f"/api/pantry/items/{item.pk}/delete/", body).status_code, 404)
        item.refresh_from_db()
        self.assertEqual((item.quantity, item.archived_at), (1, None))

    def test_form_posts_are_rejected(self):
        # API tidak memakai token CSRF, jadi hanya body JSON yang diterima: form lintas situs ditolak.
        item = self.item()
        body = {"version": item.version, "operation_key": str(uuid4())}
        for url in (
            "/api/pantry/items/",
            f"/api/pantry/items/{item.pk}/update/",
            f"/api/pantry/items/{item.pk}/delete/",
        ):
            self.assertEqual(self.client.post(url, body).status_code, 415, url)
        item.refresh_from_db()
        self.assertIsNone(item.archived_at)

    def test_post_works_without_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            "/api/pantry/items/",
            data=json.dumps({"source": "manual", "operation_key": str(uuid4()), "items": [ITEM]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

    def test_recipe_ideas_from_stock(self):
        response = self.client.get("/api/pantry/recipes/?servings=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"recipes": [], "servings": 2})
        self.assertEqual(self.client.get("/api/pantry/recipes/?servings=99").status_code, 400)
