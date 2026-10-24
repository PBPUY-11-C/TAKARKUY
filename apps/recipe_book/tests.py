import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.preferences import profile_for
from apps.budget_planner.models import BudgetPlan, PlannedMeal
from apps.catalog.aggregation import expected_allergens
from apps.catalog.models import Ingredient, IngredientAlias, Recipe, RecipeIngredient, RecipeTag
from apps.pantry.models import PantryItem, PantryMovement, PantryOperation
from apps.pantry.services import StockError, plan_consumption

from .models import CookingHistory, RecipeFavorite, RecipeNote
from .services import cook, preview_cooking, recipe_query, stock_matches


class CookingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("cook", password="Demo1234!")
        self.other = get_user_model().objects.create_user("other-cook", password="Demo1234!")
        self.client.force_login(self.user)
        self.ingredient = Ingredient.objects.create(
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
        self.recipe = Recipe.objects.create(
            recipe_code="TEST-SUP",
            name="Sup bayam",
            base_servings=2,
            meal_type="makan_malam",
            is_plannable=True,
            instructions="Rebus air.\nMasukkan bayam.",
            instruction_status="authored_reviewed",
            instruction_review_note="Panduan tim diuji.",
            instruction_reviewed_on=timezone.localdate(),
            source_url="https://example.org",
        )
        self.link = RecipeIngredient.objects.create(
            recipe_ingredient_code="TEST-LINK",
            recipe=self.recipe,
            ingredient=self.ingredient,
            quantity=100,
            unit="g",
            quantity_status="verified",
        )
        RecipeTag.objects.create(recipe_tag_code="TEST-HALAL", recipe=self.recipe, tag="halal")
        self.payload = {"recipe_code": self.recipe.pk, "servings": 2, "operation_key": str(uuid4())}

    def batch(self, **fields):
        defaults = dict(
            user=self.user,
            name="Bayam",
            quantity=100,
            unit="g",
            grams_per_unit=1,
            ingredient=self.ingredient,
            session_id="test",
            expiry_source="manual",
            estimated_expires_on=timezone.localdate() + timedelta(days=3),
        )
        return PantryItem.objects.create(**{**defaults, **fields})

    def post(self, route, payload=None):
        return self.client.post(
            reverse(route), json.dumps(payload or self.payload), content_type="application/json"
        )

    def slot(self):
        plan = BudgetPlan.objects.create(
            user=self.user,
            status="saved",
            starts_on=timezone.localdate(),
            inputs={"servings": 2},
            snapshot={},
        )
        return PlannedMeal.objects.create(
            plan=plan,
            day=1,
            meal_type="makan_malam",
            scheduled_on=plan.starts_on,
            recipe=self.recipe,
            servings=2,
            snapshot={"name": self.recipe.name},
        )

    def test_page_filters_and_does_not_reduce_stock(self):
        batch = self.batch()
        response = self.client.get(reverse("modul4"))
        self.assertContains(response, "Sup bayam")
        self.assertContains(response, "Bahan utama lengkap")
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 100)
        self.assertFalse(CookingHistory.objects.exists())

    def test_recipe_search_matches_reviewed_ingredient_aliases_only(self):
        IngredientAlias.objects.create(
            alias_code="TEST-BAYAM-ALIAS",
            source="uji kurasi",
            raw_name="Sayur Bayem",
            ingredient=self.ingredient,
            mapping_status="reviewed",
        )
        IngredientAlias.objects.create(
            alias_code="TEST-BAYAM-CANDIDATE",
            source="uji belum ditinjau",
            raw_name="Kangkung",
            ingredient=self.ingredient,
            mapping_status="candidate",
        )

        response = self.client.get(reverse("modul4"), {"q": "bayem"})
        self.assertEqual(response.context["recipes"].paginator.count, 1)
        self.assertContains(response, "Sup bayam")
        response = self.client.get(reverse("modul4"), {"q": "kangkung"})
        self.assertEqual(response.context["recipes"].paginator.count, 0)

    def test_recipe_notes_are_private_editable_and_deletable(self):
        payload = {"recipe_code": self.recipe.pk, "content": "Kurangi cabai; masak 3 menit lebih lama."}
        response = self.post("modul4-note", payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertEqual(RecipeNote.objects.get(user=self.user).content, payload["content"])

        own_page = self.client.get(reverse("modul4"), {"recipe": self.recipe.pk})
        self.assertContains(own_page, payload["content"])
        self.client.force_login(self.other)
        other_page = self.client.get(reverse("modul4"), {"recipe": self.recipe.pk})
        self.assertNotContains(other_page, payload["content"])

        self.client.force_login(self.user)
        response = self.post("modul4-note", {**payload, "content": "Tambahkan jeruk nipis."})
        self.assertTrue(response.json()["saved"])
        self.assertEqual(RecipeNote.objects.get(user=self.user).content, "Tambahkan jeruk nipis.")
        response = self.post("modul4-note", {**payload, "content": "   "})
        self.assertFalse(response.json()["saved"])
        self.assertFalse(RecipeNote.objects.exists())

    def test_recipe_note_rejects_invalid_content(self):
        for content in (None, 12, "x" * 2001):
            self.assertEqual(
                self.post("modul4-note", {"recipe_code": self.recipe.pk, "content": content}).status_code,
                400,
            )

    @patch("apps.recipe_book.views.estimated_recipe_cost", return_value=12345)
    def test_serving_price_estimate_uses_selected_portion_count(self, estimate):
        response = self.post(
            "modul4-estimate", {"recipe_code": self.recipe.pk, "servings": 4}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"servings": 4, "cost": 12345})
        estimate.assert_called_once_with(self.recipe, 4)
        for servings in (True, 0, 11, "4"):
            self.assertEqual(
                self.post(
                    "modul4-estimate", {"recipe_code": self.recipe.pk, "servings": servings}
                ).status_code,
                400,
            )

    def test_preview_cook_and_replay_use_same_ledger(self):
        early = self.batch(
            quantity=40, estimated_expires_on=timezone.localdate() + timedelta(days=1)
        )
        late = self.batch(quantity=70)
        preview = self.post("modul4-preview").json()
        self.assertTrue(preview["complete"])
        self.assertEqual([b["id"] for b in preview["batches"]], [early.pk, late.pk])
        self.assertFalse(PantryMovement.objects.exists())
        first = self.post("modul4-cook")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(self.post("modul4-cook").json(), first.json())
        self.assertEqual(CookingHistory.objects.count(), 1)
        self.assertEqual(PantryOperation.objects.count(), 1)
        self.assertEqual(PantryMovement.objects.count(), 2)
        self.assertEqual(sum(m.consumed_grams for m in PantryMovement.objects.all()), 100)
        late.refresh_from_db()
        self.assertEqual(late.quantity, 10)

    def test_shortage_rolls_back_history_operation_and_stock(self):
        batch = self.batch(quantity=99)
        self.assertEqual(self.post("modul4-cook").status_code, 409)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 99)
        self.assertFalse(PantryOperation.objects.exists())
        self.assertFalse(CookingHistory.objects.exists())

    def test_preview_is_not_reservation_and_execution_can_use_another_batch(self):
        first = self.batch()
        self.assertTrue(preview_cooking(self.user, self.payload)["complete"])
        first.quantity = 0
        first.save()
        replacement = self.batch()
        result = cook(self.user, self.payload)
        self.assertEqual(result["consumed"][0]["batch_id"], replacement.pk)

    def test_manual_weight_is_explicit_and_version_required(self):
        batch = self.batch(quantity=1, unit="pack", grams_per_unit=None)
        preview = preview_cooking(self.user, self.payload)
        self.assertFalse(preview["complete"])
        self.assertEqual(preview["manual_batches"][0]["batch_id"], batch.pk)
        self.payload["manual"] = [
            {
                "batch_id": batch.pk,
                "version": batch.version,
                "quantity": "1",
                "grams_per_unit": "100",
            }
        ]
        self.assertTrue(preview_cooking(self.user, self.payload)["complete"])
        self.assertEqual(self.post("modul4-cook").status_code, 201)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 0)
        self.assertIsNone(batch.grams_per_unit)
        self.assertEqual(PantryMovement.objects.get().consumed_grams, 100)

    def test_stale_manual_batch_conflicts(self):
        batch = self.batch(quantity=1, unit="pack", grams_per_unit=None, version=2)
        self.payload["manual"] = [
            {"batch_id": batch.pk, "version": 1, "quantity": "1", "grams_per_unit": "100"}
        ]
        self.assertEqual(self.post("modul4-cook").status_code, 409)

    def test_foreign_batch_and_foreign_slot_cannot_be_used(self):
        batch = self.batch(user=self.other)
        self.payload["manual"] = [
            {"batch_id": batch.pk, "version": 1, "quantity": "100", "grams_per_unit": "1"}
        ]
        self.assertEqual(self.post("modul4-cook").status_code, 409)
        slot = self.slot()
        self.payload.pop("manual")
        self.payload.update(planned_meal=slot.pk, version=1)
        self.client.force_login(self.other)
        self.assertEqual(self.post("modul4-cook").status_code, 404)

    def test_unknown_expiry_requires_consent_expired_never_allowed(self):
        batch = self.batch(estimated_expires_on=None, expiry_source="unknown")
        self.assertFalse(preview_cooking(self.user, self.payload)["complete"])
        self.payload["allow_unknown_expiry"] = True
        self.assertTrue(preview_cooking(self.user, self.payload)["complete"])
        batch.estimated_expires_on = timezone.localdate() - timedelta(days=1)
        batch.save()
        self.assertFalse(preview_cooking(self.user, self.payload)["complete"])

    def test_slot_cook_updates_plan_version_and_blocks_new_key_double_cook(self):
        self.batch(quantity=300)
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=1)
        self.assertEqual(self.post("modul4-cook").status_code, 201)
        self.assertEqual(self.post("modul4-cook").status_code, 201)
        slot.refresh_from_db()
        slot.plan.refresh_from_db()
        self.assertEqual(slot.status, "cooked")
        self.assertEqual(slot.plan.version, 2)
        self.payload.update(operation_key=str(uuid4()), version=2)
        self.assertEqual(self.post("modul4-cook").status_code, 409)
        self.assertEqual(CookingHistory.objects.count(), 1)

    def test_slot_cook_rejects_stale_plan_version_without_consuming_stock(self):
        batch = self.batch(quantity=300)
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=slot.plan.version + 1)

        response = self.post("modul4-cook")

        self.assertEqual(response.status_code, 409)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 300)
        self.assertFalse(PantryMovement.objects.exists())
        self.assertFalse(CookingHistory.objects.exists())

    def test_slot_cook_rejects_portion_different_from_planner_slot(self):
        batch = self.batch(quantity=300)
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=slot.plan.version, servings=1)

        response = self.post("modul4-cook")

        self.assertEqual(response.status_code, 400)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 300)
        self.assertFalse(PantryMovement.objects.exists())
        self.assertFalse(CookingHistory.objects.exists())

    def test_missing_version_and_draft_cooking_rejected(self):
        self.batch()
        slot = self.slot()
        self.payload["planned_meal"] = slot.pk
        self.assertEqual(self.post("modul4-cook").status_code, 400)
        slot.plan.status = "draft"
        slot.plan.save()
        self.payload["version"] = 1
        self.assertEqual(self.post("modul4-cook").status_code, 409)

    def test_history_snapshots_survive_rename_deactivation_and_slot_deletion(self):
        self.batch()
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=1)
        cook(self.user, self.payload)
        self.recipe.name = "Nama baru"
        self.recipe.is_active = False
        self.recipe.save()
        slot.delete()
        history = CookingHistory.objects.get()
        self.assertEqual(history.recipe_name, "Sup bayam")
        self.assertIsNone(history.planned_meal)
        self.assertEqual(history.snapshot["ingredients"][0]["name"], "Bayam")
        self.recipe.delete()
        history.refresh_from_db()
        self.assertIsNone(history.recipe)

    def test_delete_cooked_plan_preserves_history_and_stock_ledger(self):
        batch = self.batch(quantity=150)
        slot = self.slot()
        plan_id = slot.plan_id
        self.payload.update(planned_meal=slot.pk, version=1)
        self.assertEqual(self.post("modul4-cook").status_code, 201)
        history = CookingHistory.objects.get()
        history_before = (
            history.recipe_name,
            history.snapshot,
            history.cooked_at,
            history.operation_id,
        )
        movements_before = list(PantryMovement.objects.order_by("pk").values())
        slot.plan.refresh_from_db()
        response = self.client.post(
            reverse("modul1-plan-delete", args=[plan_id]),
            json.dumps({"version": slot.plan.version}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BudgetPlan.objects.filter(pk=plan_id).exists())
        self.assertFalse(PlannedMeal.objects.filter(pk=slot.pk).exists())
        history.refresh_from_db()
        self.assertIsNone(history.planned_meal_id)
        self.assertEqual(
            (history.recipe_name, history.snapshot, history.cooked_at, history.operation_id),
            history_before,
        )
        self.assertTrue(PantryOperation.objects.filter(pk=history.operation_id).exists())
        self.assertEqual(list(PantryMovement.objects.order_by("pk").values()), movements_before)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, Decimal("50"))

    def test_favorites_are_idempotent_personal_and_inactive_visible(self):
        data = {"recipe_code": self.recipe.pk, "favorite": True}
        self.assertEqual(self.post("modul4-favorite", data).status_code, 200)
        self.post("modul4-favorite", data)
        self.assertEqual(RecipeFavorite.objects.count(), 1)
        self.recipe.is_active = False
        self.recipe.save()
        self.assertContains(self.client.get(reverse("modul4")), "Tidak tersedia")
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("modul4")), "Sup bayam")
        self.client.force_login(self.user)
        self.assertEqual(self.post("modul4-favorite", {**data, "favorite": False}).status_code, 200)

    def test_guidance_visible_by_default_with_optional_guidance_filter(self):
        self.recipe.instruction_status = "withheld"
        self.recipe.save()
        response = self.client.get(reverse("modul4"))
        self.assertContains(response, "Sup bayam")
        self.assertNotContains(response, "Rebus air.")
        self.assertContains(response, "1 resep belum memiliki panduan memasak")
        filtered = self.client.get(reverse("modul4"), {"guidance": "1"})
        self.assertNotContains(filtered, "Sup bayam")
        response = self.client.get(reverse("modul4"), {"recipe": self.recipe.pk})
        self.assertContains(response, "Panduan memasak belum tersedia")
        self.assertNotContains(response, "Rebus air")

    def test_allergen_index_changes_on_ingredient_link_tag_and_delete(self):
        self.recipe.refresh_from_db()
        self.assertTrue(self.recipe.allergen_reviewed)
        profile = profile_for(self.user)
        profile.allergens = ["kacang_pohon"]
        profile.save()
        self.ingredient.allergens = ["kacang_pohon"]
        self.ingredient.save()
        self.assertFalse(recipe_query(self.user).exists())
        self.assertContains(self.client.get(reverse("modul4")), "1 karena alergen")
        self.ingredient.allergens = []
        self.ingredient.save()
        self.assertTrue(recipe_query(self.user).exists())
        tag = RecipeTag.objects.create(
            recipe_tag_code="TEST-MINOR", recipe=self.recipe, tag="bumbu_minor_tidak_dihitung"
        )
        self.assertFalse(recipe_query(self.user).exists())
        tag.delete()
        self.assertTrue(recipe_query(self.user).exists())
        self.link.delete()
        self.recipe.refresh_from_db()
        self.assertFalse(self.recipe.allergen_reviewed)
        call_command("rebuild_recipe_allergens", check=True, verbosity=0)

    def test_stale_aggregate_does_not_bypass_execution_screening(self):
        self.batch()
        profile = profile_for(self.user)
        profile.allergens = ["telur"]
        profile.save()
        Ingredient.objects.filter(pk=self.ingredient.pk).update(allergens=["telur"])
        self.assertEqual(self.post("modul4-cook").status_code, 409)
        self.assertFalse(CookingHistory.objects.exists())
        self.assertNotEqual(
            expected_allergens(get_recipe_for_test(self.recipe.pk))[1],
            set(self.recipe.allergen_groups.values_list("group", flat=True)),
        )

    def test_api_guards_bad_inputs_csrf_and_guest(self):
        self.batch()
        for changes in (
            {"servings": True},
            {"servings": -1},
            {"manual": {}},
            {"recipe_code": {}},
            {"allow_unknown_expiry": "true"},
        ):
            self.assertEqual(self.post("modul4-cook", {**self.payload, **changes}).status_code, 400)
        deep = '{"manual":' + "[" * 1500 + "0" + "]" * 1500 + "}"
        self.assertEqual(
            self.client.post(
                reverse("modul4-cook"), deep, content_type="application/json"
            ).status_code,
            400,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(
                reverse("modul4-cook"), json.dumps(self.payload), content_type="application/json"
            ).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(
                reverse("modul4-note"),
                json.dumps({"recipe_code": self.recipe.pk, "content": "Catatan"}),
                content_type="application/json",
            ).status_code,
            403,
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse("modul4")).status_code, 302)
        self.assertEqual(self.post("modul4-cook").status_code, 403)
        self.assertEqual(
            self.post("modul4-note", {"recipe_code": self.recipe.pk, "content": "Catatan"}).status_code,
            403,
        )

    def test_manual_overuse_and_invalid_conversion_rejected(self):
        batch = self.batch(quantity=200)
        for weight, amount in (("2", "50"), ("1", "200"), ("NaN", "1"), ("0", "1")):
            with self.assertRaises(StockError):
                plan_consumption(
                    self.user,
                    {self.ingredient.pk: Decimal(100)},
                    manual=[
                        {
                            "batch_id": batch.pk,
                            "version": 1,
                            "quantity": amount,
                            "grams_per_unit": weight,
                        }
                    ],
                )

    def test_history_unique_constraint(self):
        self.batch(quantity=300)
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=1)
        cook(self.user, self.payload)
        old = CookingHistory.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CookingHistory.objects.create(
                user=self.user,
                planned_meal=slot,
                recipe=self.recipe,
                operation=old.operation,
                recipe_name="Duplikat",
                servings=2,
                snapshot={},
            )

    def test_account_deletion_cascades_own_history_without_touching_other_account(self):
        self.batch()
        cook(self.user, self.payload)
        self.user.delete()
        self.assertFalse(CookingHistory.objects.exists())
        self.assertFalse(PantryOperation.objects.exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())

    def test_renaming_plan_does_not_move_dates_or_actual_cooking_time(self):
        # Plans start on the day they are saved; renaming never moves meals.
        from apps.budget_planner.services import save_plan

        self.batch()
        slot = self.slot()
        slot.plan.snapshot = {"within_budget": True}
        slot.plan.save()
        self.payload.update(planned_meal=slot.pk, version=1)
        cook(self.user, self.payload)
        history = CookingHistory.objects.get()
        actual = history.cooked_at
        save_plan(self.user, slot.plan_id, 2, "Tanggal berubah")
        history.refresh_from_db()
        slot.refresh_from_db()
        self.assertEqual(history.cooked_at, actual)
        self.assertEqual(slot.scheduled_on, timezone.localdate())

    def test_stock_filters_are_read_only_and_portion_aware(self):
        batch = self.batch(
            quantity=99, estimated_expires_on=timezone.localdate() + timedelta(days=1)
        )
        self.assertNotContains(
            self.client.get(reverse("modul4"), {"stock": "complete"}), "Sup bayam"
        )
        self.assertContains(self.client.get(reverse("modul4"), {"stock": "soon"}), "Sup bayam")
        batch.quantity = 100
        batch.save()
        self.assertContains(self.client.get(reverse("modul4"), {"stock": "complete"}), "Sup bayam")
        self.assertFalse(PantryMovement.objects.exists())

    def test_best_stock_filter_ranks_recipes_and_explains_missing_ingredients(self):
        self.batch(quantity=40)
        better_match = Recipe.objects.create(
            recipe_code="TEST-SUP-ALT",
            name="Sup Bayam Lebih Cocok",
            base_servings=2,
            meal_type="makan_malam",
            is_plannable=True,
            instructions="Masak bayam.",
            instruction_status="authored_reviewed",
            instruction_review_note="Panduan tim diuji.",
            instruction_reviewed_on=timezone.localdate(),
            source_url="https://example.org",
        )
        RecipeTag.objects.create(recipe_tag_code="TEST-ALT-HALAL", recipe=better_match, tag="halal")
        RecipeIngredient.objects.create(
            recipe_ingredient_code="TEST-ALT-LINK",
            recipe=better_match,
            ingredient=self.ingredient,
            quantity=50,
            unit="g",
            quantity_status="verified",
        )

        response = self.client.get(reverse("modul4"), {"stock": "best"})
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        cards = content[content.index('class="recipe-cards"'):]
        self.assertLess(cards.index("Sup Bayam Lebih Cocok"), cards.index("Sup bayam"))
        self.assertContains(response, "Stok cocok 80%")
        self.assertContains(response, "Stok cocok 40%")
        self.assertContains(response, "Kurang: Bayam")
        self.assertFalse(PantryMovement.objects.exists())

    def test_best_stock_filter_explains_when_pantry_has_no_matching_stock(self):
        response = self.client.get(reverse("modul4"), {"stock": "best"})
        self.assertContains(response, "Belum ada kecocokan resep dengan bahan di Pantry")
        self.assertEqual(response.context["recipes"].paginator.count, 0)

    def test_stock_matches_counts_unknown_expiry_and_flags_it(self):
        self.batch(estimated_expires_on=None, expiry_source="unknown")
        [row] = stock_matches(self.user, 2)
        self.assertEqual(row["recipe_code"], self.recipe.pk)
        self.assertTrue(row["complete"])
        self.assertTrue(row["unknown_expiry"])
        self.assertFalse(row["soon"])
        self.assertEqual(row["coverage"], 1.0)

    def test_stock_matches_reports_partial_coverage_and_missing_grams(self):
        self.batch(quantity=40)
        [row] = stock_matches(self.user, 2)
        self.assertFalse(row["complete"])
        self.assertAlmostEqual(row["coverage"], 0.4)
        self.assertEqual(row["missing"], [{"ingredient_code": "TEST-BAYAM", "grams": "60"}])

    def test_pantry_and_book_agree_on_complete_recipes(self):
        # Undated stock is where the two modules used to disagree.
        self.batch(estimated_expires_on=None, expiry_source="unknown")
        servings = profile_for(self.user).servings
        pantry = self.client.get(reverse("modul2-recipes"), {"servings": servings}).json()
        complete = [row["recipe_code"] for row in pantry["recipes"] if row["complete"]]
        book = self.client.get(reverse("modul4"), {"stock": "complete"})
        self.assertEqual(complete, [recipe.pk for recipe in book.context["recipes"]])
        # The link from Modul 2 must land on a detail page that agrees.
        detail = self.client.get(reverse("modul4"), {"recipe": self.recipe.pk}).context["detail"]
        self.assertTrue(detail["complete"])
        self.assertTrue(detail["unknown_expiry"])

    def test_stock_matches_uses_dated_stock_before_unknown_source_stock(self):
        # A leftover date on an "unknown" batch must not jump ahead of a labelled batch.
        today = timezone.localdate()
        self.batch(expiry_source="unknown", estimated_expires_on=today + timedelta(days=1))
        self.batch(expiry_source="manual", estimated_expires_on=today + timedelta(days=2))
        [row] = stock_matches(self.user, 2)
        self.assertTrue(row["soon"])
        self.assertFalse(row["unknown_expiry"])

    def test_stock_matches_rejects_servings_over_10(self):
        with self.assertRaises(StockError):
            stock_matches(self.user, 11)


def get_recipe_for_test(code):
    return Recipe.objects.prefetch_related("recipeingredient_set__ingredient", "recipetag_set").get(
        pk=code
    )
