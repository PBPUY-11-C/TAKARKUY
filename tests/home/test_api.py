import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Recipe
from apps.home.models import MapQuota, MyRecipe
from apps.home.services import JAKARTA
from apps.pantry.models import PantryItem, PantryOperation
from apps.planner.models import BudgetPlan, PlannedMeal
from apps.recipe.models import CookingHistory

User = get_user_model()

DATA_VALID = {
    "nama": "Nasi goreng telur",
    "waktu_makan": "pagi",
    "porsi": 2,
    "bahan": "Nasi\nTelur\nBawang putih",
    "langkah": "Tumis bawang\nMasukkan nasi",
    "estimasi_harga": 15000,
}


def buat_resep(user, **kwargs):
    return MyRecipe.objects.create(user=user, **{**DATA_VALID, **kwargs})


class HomeApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("aiko", password="rahasia123")
        self.lain = User.objects.create_user("budi", password="rahasia123")
        self.client.force_login(self.user)

    def post(self, url, data):
        return self.client.post(url, data=json.dumps(data), content_type="application/json")


class DashboardSummaryApiTests(HomeApiTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate(timezone=JAKARTA)
        self.recipe = Recipe.objects.create(
            recipe_code="RCP-API", name="Resep katalog", base_servings=2
        )

    def plan(self, user):
        plan = BudgetPlan.objects.create(
            user=user,
            title="Rencana A",
            status="saved",
            starts_on=self.today,
            inputs={"budget": 150000},
            snapshot={"total": 100000},
        )
        for day in range(1, 4):
            PlannedMeal.objects.create(
                plan=plan,
                day=day,
                meal_type="sarapan",
                scheduled_on=self.today + timedelta(days=day - 1),
                recipe=self.recipe,
                servings=2,
                snapshot={"name": "Nama snapshot"},
            )
        return plan

    def stock(self, user, name):
        return PantryItem.objects.create(
            user=user,
            session_id="api",
            name=name,
            quantity=100,
            unit="g",
            source="manual",
            expiry_source="estimate",
            estimated_expires_on=self.today + timedelta(days=1),
        )

    def history(self, user, name):
        event = PantryOperation.objects.create(
            user=user, key=uuid4(), kind="cook", payload_hash="test"
        )
        return CookingHistory.objects.create(
            user=user, recipe=self.recipe, operation=event, recipe_name=name, servings=2, snapshot={}
        )

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/dashboard/summary/").status_code, 403)

    def test_summary_matches_dashboard_services_and_only_own_data(self):
        plan = self.plan(self.user)
        self.plan(self.lain)
        self.stock(self.user, "Tempe")
        self.stock(self.lain, "Tahu tetangga")
        self.history(self.user, "Sup ayam")
        self.history(self.lain, "Sup tetangga")
        buat_resep(self.user)
        buat_resep(self.lain)

        response = self.client.get("/api/dashboard/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        body = response.json()
        self.assertEqual(body["today"], self.today.isoformat())
        self.assertEqual([p["id"] for p in body["plans"]], [str(plan.pk)])
        self.assertEqual(body["plans"][0]["remaining"], 50000)
        self.assertFalse(body["plans"][0]["over_budget"])
        meal = body["plans"][0]["today_meals"][0]
        self.assertEqual((meal["label"], meal["name"], meal["servings"]), ("Sarapan", "Nama snapshot", 2))
        self.assertEqual(len(body["week"]), 7)
        self.assertTrue(body["week_has_meals"])
        self.assertEqual(body["week"][0]["date"], (self.today + timedelta(days=1)).isoformat())
        self.assertEqual(body["week"][0]["meals"][0]["name"], "Nama snapshot")
        self.assertEqual(body["stock_counts"]["soon"], 1)
        self.assertEqual([b["name"] for b in body["stock_groups"]["soon"]], ["Tempe"])
        self.assertEqual(body["stock_groups"]["soon"][0]["days_left"], 1)
        self.assertEqual(body["cooking_count"], 1)
        self.assertEqual([e["recipe_name"] for e in body["recent_cooking"]], ["Sup ayam"])
        self.assertEqual(body["my_recipe_count"], 1)

    def test_summary_for_new_account_is_empty(self):
        body = self.client.get("/api/dashboard/summary/").json()
        self.assertEqual(body["plans"], [])
        self.assertFalse(body["week_has_meals"])
        self.assertIsNone(body["unsaved_draft"])
        self.assertEqual(body["stock_groups"], {"soon": [], "unknown": [], "expired": []})
        self.assertEqual((body["cooking_count"], body["my_recipe_count"]), (0, 0))


class MyRecipeApiTests(HomeApiTestCase):
    def test_requires_login(self):
        resep = buat_resep(self.user)
        self.client.logout()
        self.assertEqual(self.client.get("/api/dashboard/recipes/").status_code, 403)
        self.assertEqual(self.post("/api/dashboard/recipes/", DATA_VALID).status_code, 403)
        self.assertEqual(self.client.get(f"/api/dashboard/recipes/{resep.pk}/").status_code, 403)
        response = self.post(f"/api/dashboard/recipes/{resep.pk}/delete/", {})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(MyRecipe.objects.filter(pk=resep.pk).exists())

    def test_list_only_returns_own_recipes(self):
        mine = buat_resep(self.user, nama="Soto ayam")
        buat_resep(self.lain, nama="Rahasia budi")
        response = self.client.get("/api/dashboard/recipes/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual([r["id"] for r in response.json()], [mine.pk])

    def test_create_saves_for_logged_in_user(self):
        response = self.post("/api/dashboard/recipes/", DATA_VALID)
        self.assertEqual(response.status_code, 201)
        resep = MyRecipe.objects.get()
        self.assertEqual(resep.user, self.user)
        body = response.json()
        self.assertEqual(body["id"], resep.pk)
        self.assertEqual(body["daftar_bahan"], ["Nasi", "Telur", "Bawang putih"])
        self.assertEqual(body["daftar_langkah"], ["Tumis bawang", "Masukkan nasi"])

    def test_create_ignores_user_in_body(self):
        response = self.post("/api/dashboard/recipes/", {**DATA_VALID, "user": self.lain.pk})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(MyRecipe.objects.get().user, self.user)

    def test_create_rejects_invalid_input(self):
        for data in (
            {**DATA_VALID, "nama": ""},
            {**DATA_VALID, "porsi": 11},
            {**DATA_VALID, "waktu_makan": "subuh"},
            {**DATA_VALID, "nama": ["Nasi"]},
        ):
            with self.subTest(data=data):
                response = self.post("/api/dashboard/recipes/", data)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())
        self.assertEqual(self.post("/api/dashboard/recipes/", [DATA_VALID]).status_code, 400)
        self.assertFalse(MyRecipe.objects.exists())

    def test_create_reports_field_errors(self):
        response = self.post("/api/dashboard/recipes/", {**DATA_VALID, "nama": ""})
        self.assertIn("nama", response.json()["fields"])

    def test_detail_returns_own_recipe(self):
        resep = buat_resep(self.user)
        response = self.client.get(f"/api/dashboard/recipes/{resep.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nama"], "Nasi goreng telur")

    def test_other_users_recipe_is_not_found(self):
        resep = buat_resep(self.lain)
        self.assertEqual(self.client.get(f"/api/dashboard/recipes/{resep.pk}/").status_code, 404)
        response = self.post(f"/api/dashboard/recipes/{resep.pk}/update/", {**DATA_VALID, "nama": "Curian"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.post(f"/api/dashboard/recipes/{resep.pk}/delete/", {}).status_code, 404)
        resep.refresh_from_db()
        self.assertEqual(resep.nama, "Nasi goreng telur")

    def test_update_saves_changes(self):
        resep = buat_resep(self.user)
        response = self.post(
            f"/api/dashboard/recipes/{resep.pk}/update/", {**DATA_VALID, "nama": "Nasi goreng spesial", "porsi": 4}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nama"], "Nasi goreng spesial")
        resep.refresh_from_db()
        self.assertEqual((resep.nama, resep.porsi), ("Nasi goreng spesial", 4))

    def test_update_invalid_input_keeps_recipe(self):
        resep = buat_resep(self.user)
        response = self.post(f"/api/dashboard/recipes/{resep.pk}/update/", {**DATA_VALID, "nama": ""})
        self.assertEqual(response.status_code, 400)
        resep.refresh_from_db()
        self.assertEqual(resep.nama, "Nasi goreng telur")

    def test_delete_removes_recipe(self):
        resep = buat_resep(self.user)
        response = self.post(f"/api/dashboard/recipes/{resep.pk}/delete/", {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MyRecipe.objects.filter(pk=resep.pk).exists())

    def test_form_posts_are_rejected(self):
        # API tidak memakai token CSRF, jadi hanya body JSON yang diterima: form lintas situs ditolak.
        resep = buat_resep(self.user)
        self.assertEqual(self.client.post("/api/dashboard/recipes/", DATA_VALID).status_code, 415)
        response = self.client.post(f"/api/dashboard/recipes/{resep.pk}/update/", DATA_VALID)
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.client.post(f"/api/dashboard/recipes/{resep.pk}/delete/").status_code, 415)
        self.assertEqual(MyRecipe.objects.count(), 1)

    def test_action_urls_only_accept_post(self):
        resep = buat_resep(self.user)
        self.assertEqual(self.client.get(f"/api/dashboard/recipes/{resep.pk}/delete/").status_code, 405)
        self.assertTrue(MyRecipe.objects.filter(pk=resep.pk).exists())

    def test_post_works_without_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            "/api/dashboard/recipes/", data=json.dumps(DATA_VALID), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)


@patch("apps.home.maps.osm_markets")
class MarketLocatorApiTests(HomeApiTestCase):
    def test_requires_login(self, provider):
        self.client.logout()
        self.assertEqual(self.client.get("/api/dashboard/markets/?lat=-7.09&lon=107.9").status_code, 403)

    @override_settings(MAP_LOOKUP_ENABLED=False)
    def test_nearest_curated_markets_without_external_call(self, provider):
        response = self.client.get("/api/dashboard/markets/?lat=-7.09&lon=107.9")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        places = response.json()["places"]
        self.assertEqual(places[0]["name"], "Pasar Kadungora")
        self.assertEqual([p["distance_km"] for p in places], sorted(p["distance_km"] for p in places))
        provider.assert_not_called()

    def test_invalid_location_is_rejected(self, provider):
        for query in ("lat=51.5&lon=-0.12", "lat=-7.09", "lat=abc&lon=107.9", "lat=-7&lon=107&region=Garut"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/dashboard/markets/?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())
        provider.assert_not_called()

    @override_settings(MAP_LOOKUP_ENABLED=True)
    def test_exhausted_quota_is_rate_limited(self, provider):
        MapQuota.objects.create(user=self.user, window_started_at=timezone.now(), attempts=10)
        response = self.client.get("/api/dashboard/markets/?lat=-7.09&lon=107.9")
        self.assertEqual(response.status_code, 429)
        self.assertTrue(int(response["Retry-After"]) >= 1)
        provider.assert_not_called()
