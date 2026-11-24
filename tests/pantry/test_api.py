import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.pantry.models import PantryItem, PantryMovement

BASE = "/api/pantry/items/"


def wib_today():
    return timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))


class PantryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user("pantry-api", password="Demo1234!")
        cls.other = users.create_user("pantry-other", password="Demo1234!")

    def setUp(self):
        # Klien mobile tidak mengirim token CSRF, jadi pemeriksaannya dibiarkan aktif di tes.
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def post(self, url, data):
        return self.client.post(url, data=json.dumps(data), content_type="application/json")

    def item(self, name="Bayam", days=None, user=None, **extra):
        expires = wib_today() + timedelta(days=days) if days is not None else None
        return PantryItem.objects.create(
            user=user or self.user,
            session_id="s",
            name=name,
            quantity=1,
            unit="ikat",
            location="chiller",
            source="manual",
            estimated_expires_on=expires,
            expiry_source="manual" if expires else "unknown",
            **extra,
        )

    def create_payload(self, **fields):
        row = {"name": "Tahu Putih", "category": "tahu_tempe_kacang", "quantity": "2", "unit": "kotak"}
        return {"source": "manual", "operation_key": str(uuid4()), "items": [{**row, **fields}]}

    def test_requires_login(self):
        self.client.logout()
        for method, url in [
            ("get", BASE),
            ("post", BASE),
            ("get", f"{BASE}1/"),
            ("post", f"{BASE}1/update/"),
            ("post", f"{BASE}1/delete/"),
            ("get", f"{BASE}1/movements/"),
            ("get", "/api/pantry/recipes/"),
            ("post", "/api/pantry/receipt/scan/"),
        ]:
            self.assertEqual(getattr(self.client, method)(url).status_code, 403, url)

    def test_list_only_returns_own_active_items(self):
        mine = self.item("Bayam", days=3)
        self.item("Milik lain", days=3, user=self.other)
        self.item("Sudah habis", days=3).__class__.objects.filter(name="Sudah habis").update(quantity=0)
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual([row["id"] for row in rows], [mine.pk])
        self.assertEqual(rows[0]["quantity"], 1.0)
        self.assertEqual(rows[0]["days_remaining"], 3)
        self.assertEqual(rows[0]["expiry_status"], "soon")
        self.assertEqual(rows[0]["version"], 1)
        self.assertIn("no-store", response["Cache-Control"])

    def test_list_filters_by_expiry(self):
        expired = self.item("Lewat", days=-1)
        soon = self.item("Segera", days=7)
        later = self.item("Nanti", days=30)
        unknown = self.item("Tanpa tanggal")

        def ids(mode):
            return {row["id"] for row in self.client.get(BASE, {"filter": mode}).json()}

        self.assertEqual(ids("expired"), {expired.pk})
        self.assertEqual(ids("soon"), {soon.pk})
        self.assertEqual(ids("unknown"), {unknown.pk})
        self.assertEqual(ids("all"), {expired.pk, soon.pk, later.pk, unknown.pk})
        self.assertEqual(self.client.get(BASE, {"filter": "salah"}).status_code, 400)

    def test_detail_hides_other_users_item(self):
        mine, theirs = self.item(), self.item(user=self.other)
        self.assertEqual(self.client.get(f"{BASE}{mine.pk}/").json()["name"], "Bayam")
        self.assertEqual(self.client.get(f"{BASE}{theirs.pk}/").status_code, 404)

    def test_create_item_without_csrf_token(self):
        response = self.post(BASE, self.create_payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["saved"], 1)
        item = PantryItem.objects.get(user=self.user)
        self.assertEqual((item.name, item.source), ("Tahu Putih", "manual"))
        self.assertEqual(self.client.get(BASE).json()[0]["id"], item.pk)

    def test_create_is_idempotent_and_validates(self):
        payload = self.create_payload()
        self.assertEqual(self.post(BASE, payload).status_code, 201)
        self.assertEqual(self.post(BASE, payload).status_code, 201)
        self.assertEqual(PantryItem.objects.filter(user=self.user).count(), 1)
        invalid = self.post(BASE, self.create_payload(unit="tidak-ada"))
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("rows", invalid.json())
        missing_key = {**self.create_payload()}
        del missing_key["operation_key"]
        self.assertEqual(self.post(BASE, missing_key).status_code, 400)

    def test_update_uses_post_and_checks_version(self):
        item = self.item(days=3)
        body = {"version": 1, "operation_key": str(uuid4()), "quantity": "5", "location": "freezer"}
        response = self.post(f"{BASE}{item.pk}/update/", body)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["version"], 2)
        item.refresh_from_db()
        self.assertEqual((float(item.quantity), item.location, item.version), (5.0, "freezer", 2))
        stale = self.post(f"{BASE}{item.pk}/update/", {**body, "operation_key": str(uuid4())})
        self.assertEqual(stale.status_code, 409)

    def test_update_other_users_item_is_not_found(self):
        theirs = self.item(user=self.other)
        body = {"version": 1, "operation_key": str(uuid4()), "quantity": "9"}
        self.assertEqual(self.post(f"{BASE}{theirs.pk}/update/", body).status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(float(theirs.quantity), 1.0)

    def test_delete_archives_item_and_hides_it(self):
        item = self.item()
        response = self.post(
            f"{BASE}{item.pk}/delete/", {"version": 1, "operation_key": str(uuid4())}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"deleted": True})
        item.refresh_from_db()
        self.assertIsNotNone(item.archived_at)
        self.assertEqual(self.client.get(BASE).json(), [])
        self.assertEqual(PantryMovement.objects.filter(batch=item, kind="discard").count(), 1)

    def test_delete_other_users_item_is_not_found(self):
        theirs = self.item(user=self.other)
        body = {"version": 1, "operation_key": str(uuid4())}
        self.assertEqual(self.post(f"{BASE}{theirs.pk}/delete/", body).status_code, 404)

    def test_web_endpoints_keep_their_methods(self):
        item = self.item()
        self.assertEqual(
            self.client.get(f"/pantry/items/{item.pk}/").status_code, 405
        )
        self.assertEqual(self.client.get(f"{BASE}{item.pk}/update/").status_code, 405)

    def test_movements_show_history(self):
        self.post(BASE, self.create_payload())
        item = PantryItem.objects.get(user=self.user)
        rows = self.client.get(f"{BASE}{item.pk}/movements/").json()["movements"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "Masuk")

    def test_recipe_matches_validates_servings(self):
        self.assertEqual(self.client.get("/api/pantry/recipes/").status_code, 200)
        self.assertEqual(self.client.get("/api/pantry/recipes/?servings=99").status_code, 400)

    def test_receipt_scan_is_unavailable_without_gemini(self):
        response = self.client.post("/api/pantry/receipt/scan/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())

    def test_receipt_scan_reads_uploaded_photo_in_memory(self):
        from unittest import mock

        from django.core.files.uploadedfile import SimpleUploadedFile

        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        found = [{"name": "Bayam", "quantity": "1", "unit": "ikat"}]
        with (
            mock.patch("apps.pantry.views.gemini_ready", return_value=True),
            mock.patch("apps.pantry.views.gemini_read_receipt", return_value=found),
            mock.patch("apps.pantry.views.complete_photo_items", return_value=found),
        ):
            response = self.client.post(
                "/api/pantry/receipt/scan/",
                {"image": SimpleUploadedFile("struk.png", png, content_type="image/png")},
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["items"], found)

    def test_receipt_scan_rejects_oversized_upload(self):
        from unittest import mock

        from django.core.files.uploadedfile import SimpleUploadedFile

        big = SimpleUploadedFile("besar.png", b"0" * (11 * 1024 * 1024), content_type="image/png")
        with mock.patch("apps.pantry.views.gemini_ready", return_value=True):
            response = self.client.post("/api/pantry/receipt/scan/", {"image": big})
        self.assertEqual(response.status_code, 413)