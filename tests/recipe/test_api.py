import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Ingredient, Recipe, RecipeIngredient, RecipeTag
from apps.pantry.models import PantryItem
from apps.recipe.models import CookingHistory, RecipeBookPreviewQuota, RecipeFavorite, RecipeNote

API = "/api/recipes/"


class RecipeApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user("cook-api", password="Demo1234!")
        cls.other = users.create_user("other-api", password="Demo1234!")
        cls.bayam = Ingredient.objects.create(
            ingredient_code="TEST-BAYAM",
            name="Bayam",
            base_unit="g",
            category="sayur",
            allergen_status="reviewed",
            allergens=[],
            allergen_source_url="https://example.org",
            calories_per_100g=30,
            protein_per_100g=3,
            carbs_per_100g=5,
            fat_per_100g=1,
        )
        cls.soup = cls.recipe("TEST-SUP", "Sup bayam", guided=True)
        cls.stir_fry = cls.recipe("TEST-TUMIS", "Tumis bayam", guided=False)
        cls.pork = cls.recipe("TEST-BABI", "Bayam babi", guided=True, halal=False)

    @classmethod
    def recipe(cls, code, name, *, guided, halal=True):
        recipe = Recipe.objects.create(
            recipe_code=code,
            name=name,
            base_servings=2,
            meal_type="makan_malam",
            is_plannable=True,
            instructions="Rebus air.\n\nMasukkan bayam.",
            instruction_status="authored_reviewed" if guided else "withheld",
            instruction_review_note="Panduan tim diuji." if guided else "",
            instruction_reviewed_on=timezone.localdate() if guided else None,
            source_url="https://example.org/sup",
        )
        RecipeIngredient.objects.create(
            recipe_ingredient_code=f"{code}-LINK",
            recipe=recipe,
            ingredient=cls.bayam,
            quantity=100,
            unit="g",
            quantity_status="verified",
        )
        if halal:
            RecipeTag.objects.create(recipe_tag_code=f"{code}-HALAL", recipe=recipe, tag="halal")
        return recipe

    def setUp(self):
        self.client.force_login(self.user)

    def post(self, url, data):
        return self.client.post(API + url, data=json.dumps(data), content_type="application/json")

    def batch(self, user=None):
        return PantryItem.objects.create(
            user=user or self.user,
            name="Bayam",
            quantity=500,
            unit="g",
            grams_per_unit=1,
            ingredient=self.bayam,
            session_id="test",
            expiry_source="manual",
            estimated_expires_on=timezone.localdate() + timedelta(days=3),
        )

    def cook_payload(self, **extra):
        return {"recipe_code": self.soup.pk, "servings": 2, "operation_key": str(uuid4()), **extra}

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(API).status_code, 403)
        self.assertEqual(self.client.get(API + f"{self.soup.pk}/").status_code, 403)
        response = self.post("favorites/", {"recipe_code": self.soup.pk, "favorite": True})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(RecipeFavorite.objects.exists())

    def test_list_searches_with_profile_rules_and_limit(self):
        response = self.client.get(API, {"q": "bayam"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        body = response.json()
        # Resep tanpa tag halal tidak muncul karena profil default hanya halal.
        self.assertEqual([row["recipe_code"] for row in body["results"]], ["TEST-SUP", "TEST-TUMIS"])
        self.assertEqual(body["count"], 2)
        guidance = {row["recipe_code"]: row["guidance"] for row in body["results"]}
        self.assertEqual(guidance, {"TEST-SUP": True, "TEST-TUMIS": False})

        limited = self.client.get(API, {"q": "bayam", "limit": 1}).json()
        self.assertEqual(len(limited["results"]), 1)
        self.assertTrue(limited["has_next"])
        second = self.client.get(API, {"q": "bayam", "limit": 1, "page": 2}).json()
        self.assertEqual(second["results"][0]["recipe_code"], "TEST-TUMIS")
        self.assertFalse(second["has_next"])

        self.assertEqual(self.client.get(API, {"q": "sup"}).json()["count"], 1)
        self.assertEqual(self.client.get(API, {"guidance": "1"}).json()["count"], 1)
        self.assertEqual(self.client.get(API, {"meal": "sarapan"}).json()["count"], 0)

    def test_list_rejects_invalid_parameters(self):
        for params in ({"limit": 0}, {"limit": "abc"}, {"limit": 51}, {"max_price": 123}, {"stock": "x"}):
            response = self.client.get(API, params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIn("error", response.json())

    def test_list_filters_favorites_and_stock(self):
        RecipeFavorite.objects.create(user=self.user, recipe=self.stir_fry)
        RecipeFavorite.objects.create(user=self.other, recipe=self.soup)
        body = self.client.get(API, {"favorites": "1"}).json()
        self.assertEqual([row["recipe_code"] for row in body["results"]], ["TEST-TUMIS"])
        self.assertEqual(self.client.get(API, {"stock": "complete"}).json()["count"], 0)
        self.batch()
        body = self.client.get(API, {"stock": "complete"}).json()
        self.assertEqual(body["count"], 2)
        self.assertTrue(body["results"][0]["stock_match"]["complete"])

    def test_detail_returns_ingredients_nutrition_cost_and_steps(self):
        response = self.client.get(API + f"{self.soup.pk}/", {"servings": 4})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        body = response.json()
        self.assertEqual(body["name"], "Sup bayam")
        self.assertEqual(body["servings"], 4)
        self.assertEqual(body["ingredients"][0]["name"], "Bayam")
        self.assertEqual(body["ingredients"][0]["grams"], "200.0")
        self.assertEqual(body["ingredients"][0]["missing"], "200.0")
        self.assertFalse(body["complete"])
        self.assertEqual(body["nutrition"]["calories"], "60.0")
        self.assertIn("cost", body)
        self.assertTrue(body["guidance"])
        self.assertEqual(body["steps"], ["Rebus air.", "Masukkan bayam."])
        self.assertEqual(body["source_url"], "https://example.org/sup")
        self.assertFalse(body["favorite"])
        self.assertIsNone(body["note"])

    def test_detail_withholds_steps_without_guidance(self):
        body = self.client.get(API + f"{self.stir_fry.pk}/").json()
        self.assertFalse(body["guidance"])
        self.assertEqual(body["steps"], [])
        self.assertEqual(body["source_url"], "")

    def test_detail_rejects_invalid_servings(self):
        response = self.client.get(API + f"{self.soup.pk}/", {"servings": 11})
        self.assertEqual(response.status_code, 400)

    def test_detail_missing_or_disallowed_recipe_is_not_found(self):
        self.assertEqual(self.client.get(API + "TIDAK-ADA/").status_code, 404)
        response = self.client.get(API + f"{self.pork.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json())

    def test_favorite_add_list_and_remove(self):
        RecipeFavorite.objects.create(user=self.other, recipe=self.stir_fry)
        response = self.post("favorites/", {"recipe_code": self.soup.pk, "favorite": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"favorite": True})
        rows = self.client.get(API + "favorites/").json()
        self.assertEqual([(row["recipe_code"], row["available"]) for row in rows], [("TEST-SUP", True)])
        self.assertTrue(self.client.get(API + f"{self.soup.pk}/").json()["favorite"])

        response = self.post("favorites/", {"recipe_code": self.soup.pk, "favorite": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RecipeFavorite.objects.filter(user=self.user).exists())
        self.assertTrue(RecipeFavorite.objects.filter(user=self.other).exists())

    def test_favorite_validates_input(self):
        self.assertEqual(self.post("favorites/", {"recipe_code": self.soup.pk}).status_code, 400)
        self.assertEqual(self.post("favorites/", [self.soup.pk]).status_code, 400)
        response = self.post("favorites/", {"recipe_code": "TIDAK-ADA", "favorite": True})
        self.assertEqual(response.status_code, 404)
        response = self.post("favorites/", {"recipe_code": self.pork.pk, "favorite": True})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(RecipeFavorite.objects.exists())

    def test_note_save_and_delete_only_touch_own_note(self):
        RecipeNote.objects.create(user=self.other, recipe=self.soup, content="Milik orang lain")
        response = self.post("notes/", {"recipe_code": self.soup.pk, "content": "  Kurangi garam "})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        note = self.client.get(API + f"{self.soup.pk}/").json()["note"]
        self.assertEqual(note["content"], "Kurangi garam")

        response = self.post("notes/", {"recipe_code": self.soup.pk, "content": ""})
        self.assertEqual(response.json(), {"saved": False})
        self.assertFalse(RecipeNote.objects.filter(user=self.user).exists())
        self.assertEqual(RecipeNote.objects.get(user=self.other).content, "Milik orang lain")

    def test_note_validates_input(self):
        response = self.post("notes/", {"recipe_code": self.soup.pk, "content": "x" * 2001})
        self.assertEqual(response.status_code, 400)
        response = self.post("notes/", {"recipe_code": "TIDAK-ADA", "content": "Catatan"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(RecipeNote.objects.exists())

    def test_preview_then_cook_records_own_history(self):
        batch = self.batch()
        self.batch(self.other)
        response = self.post("cook/preview/", self.cook_payload())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["complete"])
        self.assertEqual(response.json()["batches"][0]["id"], batch.pk)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 500)

        response = self.post("cook/", self.cook_payload())
        self.assertEqual(response.status_code, 201)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 400)

        body = self.client.get(API + "history/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["week_count"], 1)
        entry = body["results"][0]
        self.assertEqual((entry["recipe_code"], entry["servings"]), ("TEST-SUP", 2))
        self.assertEqual(entry["used_ingredients"][0]["grams"], "100")

        self.client.force_login(self.other)
        self.assertEqual(self.client.get(API + "history/").json()["count"], 0)

    def test_cook_validates_input(self):
        self.batch()
        response = self.post("cook/", self.cook_payload(servings=0))
        self.assertEqual(response.status_code, 400)
        response = self.post("cook/", {"recipe_code": self.soup.pk, "servings": 2})
        self.assertEqual(response.status_code, 400)
        response = self.post("cook/", self.cook_payload(recipe_code=self.pork.pk))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CookingHistory.objects.exists())

    def test_preview_uses_recipe_book_quota(self):
        RecipeBookPreviewQuota.objects.create(
            user=self.user, window_started_at=timezone.now(), attempts=60
        )
        response = self.post("cook/preview/", self.cook_payload())
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_form_posts_are_rejected(self):
        # API tanpa token CSRF hanya menerima body JSON: form lintas situs ditolak.
        response = self.client.post(API + "favorites/", {"recipe_code": self.soup.pk, "favorite": "true"})
        self.assertEqual(response.status_code, 415)
        self.assertFalse(RecipeFavorite.objects.exists())

    def test_post_works_without_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            API + "favorites/",
            data=json.dumps({"recipe_code": self.soup.pk, "favorite": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
