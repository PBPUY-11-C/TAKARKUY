"""End-to-end coverage for the first promoted TheMealDB adaptation."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe, RecipeIngredient
from apps.pantry.models import PantryItem, PantryMovement

RECIPE_CODE = "RCP-TMDB-52998"
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "catalog_seed.json"


class TheMealDBCurationIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Import only this recipe and its fixture dependencies into the test DB."""
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        recipe = next(
            row for row in fixture if row["model"] == "catalog.recipe" and row["pk"] == RECIPE_CODE
        )
        links = [
            row
            for row in fixture
            if row["model"] == "catalog.recipeingredient" and row["fields"]["recipe"] == RECIPE_CODE
        ]
        ingredient_codes = {row["fields"]["ingredient"] for row in links}
        ingredients = [
            row
            for row in fixture
            if row["model"] == "catalog.ingredient" and row["pk"] in ingredient_codes
        ]
        prices = [
            row
            for row in fixture
            if row["model"] == "catalog.ingredientprice"
            and row["fields"]["ingredient"] in ingredient_codes
        ]
        tags = [
            row
            for row in fixture
            if row["model"] == "catalog.recipetag" and row["fields"]["recipe"] == RECIPE_CODE
        ]
        records = ingredients + prices + [recipe] + links + tags

        # Reuse the production importer so publication and allergen-index behavior
        # in this test follows the same path as a catalog refresh.
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "themealdb-recipe.json"
            fixture_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            call_command("import_catalog", str(fixture_path), verbosity=0)

        cls.recipe = Recipe.objects.get(pk=RECIPE_CODE)
        cls.links = list(
            RecipeIngredient.objects.filter(recipe=cls.recipe).select_related("ingredient")
        )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username=f"themealdb-{uuid4().hex[:10]}", password="Demo1234!"
        )
        self.client.force_login(self.user)

    def test_recipe_is_searchable_and_detail_shows_estimates_and_photo_placeholder(self):
        search = self.client.get(reverse("modul4"), {"q": "Sup Daging Sapi"})
        self.assertEqual(search.status_code, 200)
        self.assertContains(search, self.recipe.name)
        self.assertContains(search, "Foto belum tersedia")

        detail = self.client.get(reverse("modul4"), {"q": "Sup Daging Sapi", "recipe": RECIPE_CODE})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["selected"].pk, RECIPE_CODE)
        self.assertContains(detail, "Takaran estimasi")
        self.assertContains(detail, "Cara memasak")
        self.assertContains(detail, "https://www.themealdb.com/meal/52998")
        self.assertContains(detail, "Foto belum tersedia untuk resep ini.")
        self.assertFalse(detail.context["selected"].photo)
        self.assertGreater(detail.context["detail"]["cost"], 0)
        self.assertTrue(
            all(value is not None for value in detail.context["detail"]["nutrition"].values())
        )

    def test_serving_scale_changes_estimated_recipe_quantities(self):
        response = self.client.get(reverse("modul4"), {"recipe": RECIPE_CODE, "servings": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["detail"]["servings"], 2)
        ingredients = {
            item["ingredient_code"]: item for item in response.context["detail"]["ingredients"]
        }
        self.assertEqual(ingredients["ING-DAGING-SAPI"]["grams"], "300.0")
        self.assertTrue(all(item["estimated"] for item in ingredients.values()))

    def test_cook_preview_then_confirmation_consumes_tracked_stock_only(self):
        today = timezone.localdate()
        tracked_codes = {"ING-DAGING-SAPI", "ING-KENTANG", "ING-WORTEL", "ING-KUBIS"}
        for link in self.links:
            if link.ingredient_id not in tracked_codes:
                continue
            PantryItem.objects.create(
                user=self.user,
                session_id="themealdb-test",
                name=link.ingredient.name,
                quantity=link.quantity,
                unit="g",
                base_unit="g",
                grams_per_unit=1,
                ingredient=link.ingredient,
                source="manual",
                expiry_source="manual",
                estimated_expires_on=today.replace(year=today.year + 1),
            )

        payload = {
            "recipe_code": RECIPE_CODE,
            "servings": 4,
            "operation_key": str(uuid4()),
        }
        preview = self.client.post(
            reverse("modul4-preview"), json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertTrue(preview.json()["complete"])
        self.assertFalse(PantryMovement.objects.exists())

        cooked = self.client.post(
            reverse("modul4-cook"), json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(cooked.status_code, 201, cooked.content)
        self.assertEqual(
            {move.batch.ingredient_id for move in PantryMovement.objects.all()}, tracked_codes
        )
        self.assertEqual(sum(move.consumed_grams for move in PantryMovement.objects.all()), 1650)
