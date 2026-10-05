from copy import deepcopy
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.catalog.allergens import recipe_allowed
from apps.catalog.models import Ingredient, IngredientPrice, Recipe, RecipeIngredient, RecipeTag

from .models import BudgetPlan
from .planner import _load_candidates, build_plan
from .services import (
    PlanConflict,
    apply_preview,
    clean_inputs,
    make_preview,
    schedule_codes,
    write_draft,
)


class AllergenPlannerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("allergy-user")
        cls.profile = UserProfile.objects.create(user=cls.user)
        cls.inputs = {
            "budget": "100000",
            "days": 1,
            "servings": 1,
            "meal_types": ["sarapan"],
            "targets": ["seimbang"],
            "exclude_ingredients": "",
        }
        for code, groups, status in (
            ("BASE", [], "reviewed"),
            ("EGG", ["telur"], "reviewed"),
            ("SOY", ["kedelai", "gluten"], "reviewed"),
            ("UNKNOWN", [], "unknown"),
        ):
            ingredient = Ingredient.objects.create(
                ingredient_code=code,
                name=code,
                category="sayur",
                base_unit="g",
                calories_per_100g=100,
                protein_per_100g=10,
                carbs_per_100g=15,
                fat_per_100g=3,
                allergen_status=status,
                allergens=groups,
            )
            IngredientPrice.objects.create(
                price_code="PRICE-" + code,
                ingredient=ingredient,
                price_rupiah=10000,
                quantity=1,
                unit="kg",
                region="Kabupaten Garut",
                recorded_at=date(2026, 9, 28),
                price_status="published",
            )
            recipe = Recipe.objects.create(
                recipe_code=code,
                name="Menu " + code,
                base_servings=1,
                meal_type="sarapan",
                is_plannable=True,
            )
            RecipeIngredient.objects.create(
                recipe_ingredient_code="LINK-" + code,
                recipe=recipe,
                ingredient=ingredient,
                quantity=100,
                unit="g",
                quantity_status="curated",
            )
            RecipeTag.objects.create(recipe_tag_code="HALAL-" + code, recipe=recipe, tag="halal")
        recipe = Recipe.objects.create(
            recipe_code="MINOR",
            name="Bumbu tak tercatat",
            base_servings=1,
            meal_type="sarapan",
            is_plannable=True,
        )
        RecipeIngredient.objects.create(
            recipe_ingredient_code="LINK-MINOR",
            recipe=recipe,
            ingredient_id="BASE",
            quantity=100,
            unit="g",
            quantity_status="curated",
        )
        for tag in ("halal", "bumbu_minor_tidak_dihitung"):
            RecipeTag.objects.create(recipe_tag_code=tag + "-MINOR", recipe=recipe, tag=tag)

    def result(self, code="BASE", allergens=()):
        data = {**self.inputs, "allergens": list(allergens)}
        return build_plan(**clean_inputs(data).cleaned_data, fixed_schedule=[{"sarapan": code}])

    def draft(self, code="BASE", allergens=()):
        return write_draft(
            self.user, {**self.inputs, "allergens": list(allergens)}, self.result(code, allergens)
        )

    def candidate_codes(self, allergens):
        return {
            row["recipe"].pk
            for row in _load_candidates(("sarapan",), 1, [], allergens)[5]["sarapan"]
        }

    def test_group_mapping_not_substrings_drives_screening(self):
        self.assertEqual(self.candidate_codes(["telur"]), {"BASE", "SOY"})
        self.assertEqual(self.candidate_codes(["gluten"]), {"BASE", "EGG"})
        self.assertEqual(self.candidate_codes(["kedelai", "telur"]), {"BASE"})
        self.assertIn("UNKNOWN", self.candidate_codes([]))
        self.assertIn("MINOR", self.candidate_codes([]))

    def test_optional_ingredients_are_not_ignored_for_allergens(self):
        link = RecipeIngredient.objects.get(recipe_id="EGG")
        link.is_optional = True
        link.save()
        self.assertNotIn("EGG", self.candidate_codes(["telur"]))

    def test_invalid_mapping_is_excluded_not_assumed_safe(self):
        Ingredient.objects.filter(pk="BASE").update(allergens=["not-a-group"])
        self.assertNotIn("BASE", self.candidate_codes(["telur"]))

    def test_snapshot_and_current_profile_allergies_are_unioned(self):
        draft = self.draft(allergens=["kedelai"])
        self.profile.allergens = ["telur"]
        self.profile.save()
        for code in ("EGG", "SOY", "UNKNOWN", "MINOR"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                make_preview(
                    draft,
                    draft.version,
                    {"action": "replace", "day": 1, "meal": "sarapan", "recipe": code},
                )
        preview = make_preview(
            draft,
            draft.version,
            {"action": "parameters", "inputs": {**self.inputs, "allergens": []}},
        )
        self.assertEqual(preview.inputs["allergens"], ["kedelai", "telur"])

    def test_regeneration_uses_current_profile_allergies(self):
        draft = self.draft("SOY")
        self.profile.allergens = ["kedelai", "telur"]
        self.profile.save()
        preview = make_preview(draft, draft.version, {"action": "regenerate"})
        self.assertEqual(preview.inputs["allergens"], ["kedelai", "telur"])
        self.assertEqual(schedule_codes(preview.snapshot), [{"sarapan": "BASE"}])

    def test_parameters_cannot_remove_profile_or_snapshot_allergies(self):
        draft = self.draft("SOY")
        self.profile.allergens = ["telur"]
        self.profile.save()
        preview = make_preview(
            draft,
            draft.version,
            {"action": "parameters", "inputs": {**self.inputs, "allergens": []}},
        )
        self.assertEqual(preview.inputs["allergens"], ["telur"])
        self.assertNotIn(
            "EGG", {code for row in schedule_codes(preview.snapshot) for code in row.values()}
        )

    def test_new_allergy_after_preview_blocks_apply_and_preserves_old_plan(self):
        draft = self.draft()
        before = deepcopy(draft.snapshot)
        preview = make_preview(
            draft,
            draft.version,
            {"action": "replace", "day": 1, "meal": "sarapan", "recipe": "EGG"},
        )
        self.profile.allergens = ["telur"]
        self.profile.save()
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)
        draft.refresh_from_db()
        preview.refresh_from_db()
        self.assertEqual(draft.snapshot, before)
        self.assertIsNone(preview.used_at)

    def test_new_allergy_before_draft_write_blocks_race(self):
        result = self.result("EGG")
        self.profile.allergens = ["telur"]
        self.profile.save()
        with self.assertRaises(PlanConflict):
            write_draft(self.user, self.inputs, result)
        self.assertFalse(BudgetPlan.objects.exists())

    def test_old_snapshot_is_not_mutated_and_get_shows_warning(self):
        draft = self.draft("EGG")
        before = deepcopy(draft.snapshot)
        self.profile.allergens = ["telur"]
        self.profile.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("modul1"), {"plan": str(draft.pk)})
        self.assertContains(response, "Rencana lama memiliki bahan")
        draft.refresh_from_db()
        self.assertEqual(draft.snapshot, before)

    def test_profile_defaults_only_apply_to_new_plan(self):
        self.profile.servings = 4
        self.profile.meal_types = ["sarapan"]
        self.profile.targets = ["rendah_kalori"]
        self.profile.save()
        self.profile.avoided_ingredients.add(Ingredient.objects.get(pk="UNKNOWN"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("modul1"), {"new": "1"})
        self.assertEqual(response.context["form"].initial["servings"], 4)
        self.assertEqual(response.context["form"].initial["targets"], ["rendah_kalori"])
        self.assertEqual(response.context["form"].initial["exclude_ingredients"], "UNKNOWN")
        draft = self.draft()
        response = self.client.get(reverse("modul1"), {"plan": str(draft.pk)})
        self.assertEqual(response.context["form"].initial["servings"], 1)

    def test_post_cannot_omit_profile_allergies_to_generate_unsafe_draft(self):
        self.profile.allergens = ["telur"]
        self.profile.save()
        self.client.force_login(self.user)
        response = self.client.post(reverse("modul1"), self.inputs)
        self.assertEqual(response.status_code, 302)
        draft = BudgetPlan.objects.get(user=self.user)
        self.assertEqual(draft.inputs["allergens"], ["telur"])
        for code in {code for row in schedule_codes(draft.snapshot) for code in row.values()}:
            recipe = Recipe.objects.get(pk=code)
            self.assertTrue(
                recipe_allowed(recipe, list(recipe.recipeingredient_set.all()), ["telur"])
            )
