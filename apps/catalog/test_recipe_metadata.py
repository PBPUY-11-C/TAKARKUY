import json
from tempfile import NamedTemporaryFile

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.catalog.aggregation import rebuild_allergens
from apps.catalog.content_policy import protect_recipe_instructions
from apps.catalog.models import Ingredient, Recipe, RecipeIngredient


class RecipeMetadataTests(TestCase):
    def setUp(self):
        self.ingredient = Ingredient.objects.create(
            ingredient_code="TEST-MILK",
            name="Susu",
            category="lainnya",
            base_unit="g",
            allergens=["susu"],
            allergen_status="reviewed",
            allergen_source_url="https://example.org",
        )
        self.recipe = Recipe.objects.create(
            recipe_code="TEST-RECIPE", name="Sup", base_servings=1, source_url="https://example.org"
        )
        RecipeIngredient.objects.create(
            recipe_ingredient_code="TEST-LINK",
            recipe=self.recipe,
            ingredient=self.ingredient,
            quantity=100,
            unit="g",
        )

    def import_records(self, records):
        with NamedTemporaryFile(mode="w+", suffix=".json", encoding="utf-8") as stream:
            json.dump(records, stream)
            stream.flush()
            call_command("import_catalog", stream.name, verbosity=0)

    def test_import_updates_derived_groups_even_when_signals_suspended(self):
        self.import_records(
            [
                {
                    "model": "catalog.ingredient",
                    "pk": self.ingredient.pk,
                    "fields": {"allergens": ["kacang_pohon"], "allergen_status": "reviewed"},
                }
            ]
        )
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.allergen_reviewed)
        self.assertEqual(
            list(self.recipe.allergen_groups.values_list("group", flat=True)), ["kacang_pohon"]
        )
        call_command("rebuild_recipe_allergens", check=True, verbosity=0)

    def test_authored_guidance_survives_legacy_import_but_source_change_is_withheld(self):
        self.recipe.instruction_status = "authored_reviewed"
        self.recipe.instructions = "Panduan tim"
        self.recipe.save()
        self.import_records(
            [
                {
                    "model": "catalog.recipe",
                    "pk": self.recipe.pk,
                    "fields": {"instructions": "Teks sumber"},
                }
            ]
        )
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.instructions, "Panduan tim")
        self.recipe.instruction_status = "source_ok"
        self.recipe.save()
        self.import_records(
            [
                {
                    "model": "catalog.recipe",
                    "pk": self.recipe.pk,
                    "fields": {"instructions": "Sumber baru"},
                }
            ]
        )
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.instruction_status, "withheld")

    def test_admin_model_validation_requires_review_evidence(self):
        self.recipe.instruction_status = "authored_reviewed"
        with self.assertRaises(ValidationError):
            self.recipe.clean()
        self.ingredient.allergens = ["invalid"]
        with self.assertRaises(ValidationError):
            self.ingredient.clean()

    def test_bulk_drift_is_detected_and_repairable(self):
        Ingredient.objects.filter(pk=self.ingredient.pk).update(allergen_status="unknown")
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("rebuild_recipe_allergens", check=True, verbosity=0)
        rebuild_allergens()
        call_command("rebuild_recipe_allergens", check=True, verbosity=0)

    def test_publication_guard_handles_all_sources_and_reviewed_mendeley(self):
        withheld = protect_recipe_instructions(
            {"recipe_code": "TEST", "instructions": "Rahasia", "instruction_status": "withheld"}
        )
        self.assertEqual(withheld["instructions"], "")
        reviewed = protect_recipe_instructions(
            {
                "recipe_code": "RCP-MDL-TEST",
                "instructions": "Panduan tim",
                "instruction_status": "authored_reviewed",
                "instruction_review_note": "Reviewer: tim, panduan diuji",
                "instruction_reviewed_on": "2026-10-06",
            }
        )
        self.assertEqual(reviewed["instructions"], "Panduan tim")
        self.assertNotIn("instructions_pending_review", reviewed)
