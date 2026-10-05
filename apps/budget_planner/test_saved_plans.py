import json
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe, RecipeTag
from apps.pantry.models import PantryItem

from .models import BudgetPlan, PlannedMeal, PlanPreview, ShoppingListItem
from .planner import build_plan
from .services import (
    PlanConflict,
    apply_preview,
    clean_inputs,
    make_preview,
    save_plan,
    schedule_codes,
    write_draft,
)
from .snapshots import freeze, thaw


class SavedPlanTests(TestCase):
    fixtures = ["catalog_seed"]

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("planner", password="Demo1234!")
        cls.other = get_user_model().objects.create_user("other", password="Demo1234!")
        cls.inputs = {
            "budget": "1000000",
            "days": 1,
            "servings": 1,
            "meal_types": ["sarapan"],
            "targets": ["seimbang"],
            "exclude_ingredients": "",
        }
        cls.quotes = []
        for recipe in Recipe.objects.filter(meal_type="sarapan", is_active=True, is_plannable=True):
            try:
                quote = build_plan(
                    **clean_inputs(cls.inputs).cleaned_data, fixed_schedule=[{"sarapan": recipe.pk}]
                )
            except ValueError:
                continue
            cls.quotes.append((quote["total"], recipe.pk, quote))
        cls.quotes.sort(key=lambda row: (row[0], row[1]))
        assert len(cls.quotes) >= 2 and cls.quotes[0][0] < cls.quotes[-1][0]

    def setUp(self):
        self.client.force_login(self.user)
        self.inputs = deepcopy(self.inputs)
        self.draft = write_draft(self.user, self.inputs, self.quotes[0][2])

    def api(self, name, pk, data, client=None):
        return (client or self.client).post(
            reverse(name, args=[pk]), data=json.dumps(data), content_type="application/json"
        )

    def replacement(self, plan=None, code=None):
        plan = plan or self.draft
        return make_preview(
            plan,
            plan.version,
            {
                "action": "replace",
                "day": 1,
                "meal": "sarapan",
                "recipe": code or self.quotes[-1][1],
            },
        )

    def saved(self):
        return save_plan(
            self.user, self.draft.pk, self.draft.version, "Minggu Ini", date(2026, 10, 5)
        )

    def generation_data(self, **changes):
        return {
            **self.inputs,
            "plan_id": str(self.draft.pk),
            "version": self.draft.version,
            **changes,
        }

    def update_draft(self, inputs=None, result=None):
        self.draft.refresh_from_db()
        self.draft = write_draft(
            self.user,
            inputs or self.inputs,
            result or self.quotes[0][2],
            previous=self.draft,
            expected_version=self.draft.version,
        )
        return self.draft

    def test_generate_auto_persists_one_draft_and_no_saved_plan(self):
        response = self.client.post(reverse("modul1"), self.generation_data(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BudgetPlan.objects.filter(user=self.user, status="draft").count(), 1)
        self.assertFalse(BudgetPlan.objects.filter(status="saved").exists())
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 2)
        self.assertEqual(self.draft.meals.count(), 1)
        self.assertTrue(self.draft.shopping_items.exists())
        self.assertEqual(PantryItem.objects.count(), 0)
        self.assertContains(response, "Simpan Rencana")

    def test_generate_again_rejects_stale_version(self):
        response = self.client.post(
            reverse("modul1"), {**self.inputs, "plan_id": str(self.draft.pk), "version": 0}
        )
        self.assertEqual(response.status_code, 409)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 1)

    def test_generation_requires_version_and_never_mutates_on_missing_or_bad_version(self):
        before = deepcopy(self.draft.snapshot)
        for value in (None, "", "abc", "-1", "1.5"):
            data = {**self.inputs, "plan_id": str(self.draft.pk)}
            if value is not None:
                data["version"] = value
            with self.subTest(version=value):
                self.assertEqual(self.client.post(reverse("modul1"), data).status_code, 400)
        # Omitting both ID and version must not opt into the current draft's version.
        self.assertEqual(self.client.post(reverse("modul1"), self.inputs).status_code, 400)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 1)
        self.assertEqual(self.draft.snapshot, before)

    def test_new_plan_requires_explicit_consent_and_matching_draft_identity_version(self):
        data = {**self.inputs, "new_plan": "1"}
        self.assertEqual(self.client.post(reverse("modul1"), data).status_code, 409)
        data.update(replace_draft_id=str(self.draft.pk), replace_draft_version=1)
        self.assertEqual(self.client.post(reverse("modul1"), data).status_code, 409)
        data["replace_draft"] = "1"
        self.update_draft()
        self.assertEqual(self.client.post(reverse("modul1"), data).status_code, 409)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 2)
        page = self.client.get(reverse("modul1") + "?new=1")
        self.assertContains(page, 'name="replace_draft"')
        self.assertContains(page, 'name="replace_draft_id"')

    def test_first_draft_can_be_created_without_version_when_none_exists(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("modul1"), {**self.inputs, "new_plan": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BudgetPlan.objects.get(user=self.other, status="draft").version, 1)

    def test_services_refuse_blind_draft_overwrite(self):
        before = deepcopy(self.draft.snapshot)
        with self.assertRaises(PlanConflict):
            write_draft(self.user, self.inputs, self.quotes[-1][2])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.snapshot, before)

    def test_saved_preview_cannot_replace_draft_from_different_plan(self):
        saved = self.saved()
        # Make an independent, unsaved draft while retaining the saved plan.
        self.update_draft(result=self.quotes[0][2])
        original = deepcopy(self.draft.snapshot)
        for action in ("replace", "regenerate"):
            payload = {"action": action, "version": saved.version}
            if action == "replace":
                payload.update(day=1, meal="sarapan", recipe=self.quotes[-1][1])
            response = self.api("modul1-plan-preview", saved.pk, payload)
            self.assertEqual(response.status_code, 200)
            preview = PlanPreview.objects.get(pk=response.json()["id"])
            rejected = self.api("modul1-preview-apply", preview.pk, {})
            self.assertEqual(rejected.status_code, 409)
            preview.refresh_from_db()
            self.assertIsNone(preview.used_at)
        self.draft.refresh_from_db()
        saved.refresh_from_db()
        self.assertEqual(self.draft.snapshot, original)
        self.assertEqual(saved.version, 1)

    def test_preview_detects_recreated_draft_even_with_same_version(self):
        saved = self.saved()
        preview = self.replacement(saved)
        version = self.draft.version
        self.draft.delete()
        replacement = BudgetPlan.objects.create(
            user=self.user,
            starts_on=saved.starts_on,
            inputs=self.inputs,
            snapshot=saved.snapshot,
            source_plan=saved,
            version=version,
        )
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)
        replacement.refresh_from_db()
        self.assertEqual(replacement.version, version)

    def test_saved_plan_cannot_clobber_unsaved_changes_even_from_same_source(self):
        saved = self.saved()
        changed = apply_preview(self.user, self.replacement(saved).pk)
        snapshot = deepcopy(changed.snapshot)
        another = self.replacement(saved, code=self.quotes[1][1])
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, another.pk)
        changed.refresh_from_db()
        self.assertEqual(changed.snapshot, snapshot)

    def test_missing_versions_rejected_for_all_plan_mutation_apis(self):
        requests = (
            ("modul1-plan-preview", {"action": "regenerate"}),
            ("modul1-plan-save", {"title": "Judul", "starts_on": "2026-10-05"}),
            ("modul1-plan-delete", {}),
        )
        for endpoint, data in requests:
            self.assertEqual(self.api(endpoint, self.draft.pk, data).status_code, 409)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 1)

    def test_new_plan_clears_saved_source_without_modifying_saved_plan(self):
        saved = self.saved()
        self.draft.refresh_from_db()
        self.assertIsNone(self.client.get(reverse("modul1") + "?new=1").context["plan"])
        response = self.client.post(
            reverse("modul1"),
            {
                **self.inputs,
                "new_plan": "1",
                "replace_draft": "1",
                "replace_draft_id": str(self.draft.pk),
                "replace_draft_version": self.draft.version,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.source_plan_id)
        self.assertEqual(self.draft.title, "Rencana Makan Saya")
        saved.refresh_from_db()
        self.assertEqual(saved.title, "Minggu Ini")

    def test_numeric_budget_rejects_non_decimal_unicode_without_crashing(self):
        response = self.client.post(reverse("modul1"), {**self.inputs, "budget": "²"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("budget", response.context["form"].errors)

    def test_success_redirects_and_reload_preserves_generated_draft(self):
        response = self.client.post(reverse("modul1"), self.generation_data())
        self.assertEqual(response.status_code, 302)
        self.draft.refresh_from_db()
        before = deepcopy(self.draft.snapshot)
        version = self.draft.version
        self.client.get(response.url)
        self.client.get(response.url)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.snapshot, before)
        self.assertEqual(self.draft.version, version)

    def test_legacy_guest_snapshot_upgrades_ingredient_ids_on_login(self):
        guest = Client()
        old = deepcopy(self.quotes[0][2])
        for group in old["shopping_groups"]:
            for item in group["items"]:
                del item["ingredient_code"]
        session = guest.session
        session["guest_last_plan"] = {"inputs": self.inputs, "result": json.dumps(freeze(old))}
        session.save()
        response = guest.post(reverse("login"), {"username": "other", "password": "Demo1234!"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BudgetPlan.objects.get(user=self.other).shopping_items.exists())

    def test_replacement_preserves_other_meal_types_and_days(self):
        inputs = {**self.inputs, "days": 2, "meal_types": ["sarapan", "makan_siang", "makan_malam"]}
        result = build_plan(**clean_inputs(inputs).cleaned_data)
        draft = self.update_draft(inputs, result)
        old_slots = schedule_codes(result)
        alternative = next(row[1] for row in self.quotes if row[1] != old_slots[0]["sarapan"])
        preview = self.replacement(draft, alternative)
        expected = deepcopy(old_slots)
        expected[0]["sarapan"] = alternative
        self.assertEqual(schedule_codes(thaw(preview.snapshot)), expected)

    def test_failed_generation_keeps_previous_draft(self):
        original = self.draft.snapshot
        response = self.client.post(reverse("modul1"), self.generation_data(budget="1"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["result"]["within_budget"])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.snapshot, original)

    def test_draft_is_available_in_second_browser_only_to_owner(self):
        second = Client()
        second.force_login(self.user)
        response = second.get(reverse("modul1"))
        self.assertEqual(response.context["plan"].pk, self.draft.pk)
        second.force_login(self.other)
        self.assertEqual(second.get(reverse("modul1") + f"?plan={self.draft.pk}").status_code, 404)
        self.assertIsNone(second.get(reverse("modul1")).context["plan"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_unique_draft_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetPlan.objects.create(
                user=self.user,
                starts_on=date.today(),
                inputs=self.inputs,
                snapshot=self.draft.snapshot,
            )

    def test_save_copies_snapshot_and_children_with_start_date(self):
        saved = self.saved()
        self.assertEqual(saved.status, "saved")
        self.assertEqual(saved.meals.get().scheduled_on, date(2026, 10, 5))
        self.assertEqual(saved.meals.get().recipe_id, self.quotes[0][1])
        self.assertEqual(saved.shopping_items.count(), self.draft.shopping_items.count())
        self.assertEqual(saved.snapshot, self.draft.snapshot)
        self.assertFalse(PantryItem.objects.exists())
        self.assertEqual(
            saved.shopping_items.get(pk=saved.shopping_items.first().pk).snapshot[
                "ingredient_code"
            ],
            saved.shopping_items.first().ingredient_id,
        )

    def test_repeat_save_is_idempotent_and_invalidates_old_preview(self):
        preview = self.replacement()
        saved = self.saved()
        same = save_plan(self.user, self.draft.pk, 1, "Minggu Ini", date(2026, 10, 5))
        self.assertEqual(same.pk, saved.pk)
        self.assertEqual(BudgetPlan.objects.filter(status="saved").count(), 1)
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)

    def test_saved_snapshot_not_changed_by_catalog_rename_or_generation(self):
        saved = self.saved()
        before = deepcopy(saved.snapshot)
        Recipe.objects.filter(pk=self.quotes[0][1]).update(name="Nama berubah")
        self.client.post(reverse("modul1"), self.generation_data())
        saved.refresh_from_db()
        self.assertEqual(saved.snapshot, before)
        response = self.client.get(reverse("modul1") + f"?plan={saved.pk}")
        self.assertEqual(response.context["result"], thaw(before))
        self.assertContains(response, "Minggu Ini")

    def test_save_metadata_and_delete_with_ownership_and_versions(self):
        saved = self.saved()
        response = self.api(
            "modul1-plan-save",
            saved.pk,
            {"version": 1, "title": "  Bekal   Kantor ", "starts_on": "2026-10-06"},
        )
        self.assertEqual(response.status_code, 200)
        saved.refresh_from_db()
        self.assertEqual(saved.title, "Bekal Kantor")
        self.assertEqual(saved.meals.get().scheduled_on, date(2026, 10, 6))
        self.assertEqual(self.api("modul1-plan-delete", saved.pk, {"version": 1}).status_code, 409)
        self.assertEqual(self.api("modul1-plan-delete", saved.pk, {"version": 2}).status_code, 200)
        self.assertFalse(PlannedMeal.objects.filter(plan_id=saved.pk).exists())
        self.assertFalse(ShoppingListItem.objects.filter(plan_id=saved.pk).exists())
        self.assertTrue(Recipe.objects.filter(pk=self.quotes[0][1]).exists())

    def test_guests_cannot_access_mutations_or_alternatives(self):
        guest = Client()
        for name in ("modul1-plan-save", "modul1-plan-delete", "modul1-plan-preview"):
            self.assertEqual(self.api(name, self.draft.pk, {}, guest).status_code, 401)
        self.assertEqual(
            guest.get(reverse("modul1-plan-alternatives", args=[self.draft.pk])).status_code, 401
        )
        preview = self.replacement()
        self.assertEqual(self.api("modul1-preview-apply", preview.pk, {}, guest).status_code, 401)

    def test_foreign_owner_cannot_read_modify_delete_or_apply(self):
        other = Client()
        other.force_login(self.other)
        for name in ("modul1-plan-save", "modul1-plan-delete", "modul1-plan-preview"):
            self.assertEqual(self.api(name, self.draft.pk, {"version": 1}, other).status_code, 404)
        self.assertEqual(
            other.get(reverse("modul1-plan-alternatives", args=[self.draft.pk])).status_code, 404
        )
        preview = self.replacement()
        self.assertEqual(self.api("modul1-preview-apply", preview.pk, {}, other).status_code, 404)
        self.assertTrue(BudgetPlan.objects.filter(pk=self.draft.pk).exists())

    def test_csrf_required(self):
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.user)
        self.assertEqual(
            self.api("modul1-plan-delete", self.draft.pk, {"version": 1}, guarded).status_code, 403
        )

    def test_method_json_and_payload_validation(self):
        url = reverse("modul1-plan-preview", args=[self.draft.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {}).status_code, 415)
        for body in ("{", "[]", '"string"'):
            self.assertEqual(
                self.client.post(url, body, content_type="application/json").status_code, 400
            )
        self.assertEqual(
            self.client.post(url, " " * 8001, content_type="application/json").status_code, 413
        )
        for payload in (
            {"version": True, "action": "regenerate"},
            {"version": 1, "action": []},
            {"version": 1, "action": "parameters", "inputs": []},
            {"version": 1, "action": "replace", "day": 1, "meal": [], "recipe": "fake"},
        ):
            self.assertIn(
                self.api("modul1-plan-preview", self.draft.pk, payload).status_code, (400, 409)
            )

    def test_metadata_validation(self):
        for changes in (
            {"title": ""},
            {"title": "x" * 101},
            {"title": {}},
            {"starts_on": "invalid"},
        ):
            response = self.api(
                "modul1-plan-save",
                self.draft.pk,
                {"version": 1, "title": "Plan", "starts_on": "2026-10-05", **changes},
            )
            self.assertEqual(response.status_code, 400)

    def test_alternatives_same_meal_and_exclude_current(self):
        response = self.client.get(
            reverse("modul1-plan-alternatives", args=[self.draft.pk]), {"day": 1, "meal": "sarapan"}
        )
        self.assertEqual(response.status_code, 200)
        codes = {row["recipe_code"] for row in response.json()["recipes"]}
        self.assertNotIn(self.quotes[0][1], codes)
        self.assertTrue(codes)
        self.assertFalse(Recipe.objects.filter(pk__in=codes).exclude(meal_type="sarapan").exists())

    def test_missing_plan_returns_json_not_html(self):
        missing = "00000000-0000-0000-0000-000000000000"
        alternatives = self.client.get(
            reverse("modul1-plan-alternatives", args=[missing]), {"day": 1, "meal": "sarapan"}
        )
        preview = self.api("modul1-plan-preview", missing, {"action": "regenerate", "version": 1})
        for response in (alternatives, preview):
            self.assertEqual(response.status_code, 404)
            self.assertIn("tidak ditemukan", response.json()["error"])

    def test_alternatives_include_price_difference(self):
        response = self.client.get(
            reverse("modul1-plan-alternatives", args=[self.draft.pk]), {"day": 1, "meal": "sarapan"}
        )
        rows = response.json()["recipes"]
        self.assertTrue(rows)
        self.assertTrue(all(isinstance(row["delta"], int) for row in rows))

    def test_alternatives_offer_only_halal_recipes(self):
        hidden = self.quotes[-1][1]
        RecipeTag.objects.filter(recipe_id=hidden, tag="halal").delete()
        response = self.client.get(
            reverse("modul1-plan-alternatives", args=[self.draft.pk]), {"day": 1, "meal": "sarapan"}
        )
        codes = [row["recipe_code"] for row in response.json()["recipes"]]
        self.assertNotIn(hidden, codes)
        self.assertEqual(len(codes), len(set(codes)))

    def test_preview_is_non_mutating_and_server_calculated(self):
        original = deepcopy(self.draft.snapshot)
        response = self.api(
            "modul1-plan-preview",
            self.draft.pk,
            {
                "version": 1,
                "action": "replace",
                "day": 1,
                "meal": "sarapan",
                "recipe": self.quotes[-1][1],
                "total": 1,
                "user": self.other.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["after"], self.quotes[-1][0])
        self.assertEqual(response.json()["delta"], self.quotes[-1][0] - self.quotes[0][0])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.snapshot, original)
        self.assertEqual(self.draft.version, 1)

    def test_replace_only_one_slot_and_requotes_full_basket(self):
        inputs = {**self.inputs, "days": 2, "servings": 3}
        slots = [{"sarapan": self.quotes[0][1]}] * 2
        result = build_plan(**clean_inputs(inputs).cleaned_data, fixed_schedule=slots)
        draft = self.update_draft(inputs, result)
        preview = self.replacement(draft)
        expected_slots = [{"sarapan": self.quotes[-1][1]}, {"sarapan": self.quotes[0][1]}]
        quoted = build_plan(**clean_inputs(inputs).cleaned_data, fixed_schedule=expected_slots)
        self.assertEqual(schedule_codes(thaw(preview.snapshot)), expected_slots)
        self.assertEqual(thaw(preview.snapshot)["shopping_groups"], quoted["shopping_groups"])
        updated = apply_preview(self.user, preview.pk)
        self.assertEqual(updated.meals.count(), 2)
        self.assertEqual(updated.meals.get(day=2).recipe_id, self.quotes[0][1])

    def test_replace_rejects_invalid_day_slot_inactive_wrong_type_and_same_recipe(self):
        wrong = Recipe.objects.filter(meal_type="makan_siang", is_plannable=True).first()
        for changes in (
            {"day": 0},
            {"day": True},
            {"day": 2},
            {"meal": "makan_malam"},
            {"recipe": "missing"},
            {"recipe": wrong.pk},
            {"recipe": self.quotes[0][1]},
        ):
            with self.assertRaises(ValueError):
                make_preview(
                    self.draft,
                    1,
                    {
                        "action": "replace",
                        "day": 1,
                        "meal": "sarapan",
                        "recipe": self.quotes[-1][1],
                        **changes,
                    },
                )
        Recipe.objects.filter(pk=self.quotes[-1][1]).update(is_active=False)
        with self.assertRaises(ValueError):
            self.replacement()

    def test_replacement_checks_ingredient_exclusion(self):
        recipe = Recipe.objects.get(pk=self.quotes[-1][1])
        forbidden = recipe.recipeingredient_set.first().ingredient.name
        self.draft.inputs = {**self.inputs, "exclude_ingredients": forbidden}
        self.draft.save()
        with self.assertRaises(ValueError):
            self.replacement()

    def test_replacement_checks_nutrition_target(self):
        # The low-cost fruit/breakfast choices cannot meet 27 g protein alone.
        self.draft.inputs = {**self.inputs, "targets": ["tinggi_protein"]}
        self.draft.save()
        with self.assertRaises(ValueError):
            self.replacement(code=self.quotes[1][1])

    def test_budget_increase_is_explicit_and_minimum_is_enforced(self):
        self.draft.inputs = {**self.inputs, "budget": str(self.quotes[0][0])}
        self.draft.save()
        preview = self.replacement()
        self.assertFalse(thaw(preview.snapshot)["within_budget"])
        for budget in (None, str(self.quotes[0][0]), "abc"):
            with self.assertRaises(ValueError):
                apply_preview(self.user, preview.pk, new_budget=budget)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 1)
        preview.refresh_from_db()
        self.assertIsNone(preview.used_at)
        updated = apply_preview(self.user, preview.pk, new_budget=str(self.quotes[-1][0]))
        self.assertEqual(updated.inputs["budget"], str(self.quotes[-1][0]))
        self.assertTrue(thaw(updated.snapshot)["within_budget"])
        self.assertEqual(thaw(updated.snapshot)["difference"], 0)
        self.assertEqual(thaw(updated.snapshot)["meal_cost_cap"], int(self.quotes[-1][0]) * 2)
        self.assertFalse(thaw(updated.snapshot)["spend_floor_relaxed"])
        self.assertFalse(PantryItem.objects.exists())

    def test_unnecessary_budget_increase_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_preview(self.user, self.replacement().pk, new_budget="2000000")

    def test_preview_can_only_apply_once(self):
        preview = self.replacement()
        apply_preview(self.user, preview.pk)
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)

    def test_expired_and_stale_previews_are_rejected(self):
        preview = self.replacement()
        PlanPreview.objects.filter(pk=preview.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)
        stale = self.replacement()
        self.update_draft()
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, stale.pk)

    def test_saved_replacement_does_not_overwrite_original_until_explicit_save(self):
        saved = self.saved()
        before = deepcopy(saved.snapshot)
        draft = apply_preview(self.user, self.replacement(saved).pk)
        saved.refresh_from_db()
        self.assertEqual(saved.snapshot, before)
        self.assertEqual(draft.source_plan_id, saved.pk)
        updated = save_plan(
            self.user, draft.pk, draft.version, saved.title, saved.starts_on, replace_original=True
        )
        self.assertEqual(updated.pk, saved.pk)
        self.assertEqual(updated.meals.get().recipe_id, self.quotes[-1][1])
        self.assertEqual(BudgetPlan.objects.filter(status="saved").count(), 1)

    def test_edit_saved_can_save_as_new_instead(self):
        saved = self.saved()
        draft = apply_preview(self.user, self.replacement(saved).pk)
        copied = save_plan(self.user, draft.pk, draft.version, "Plan B", saved.starts_on)
        self.assertNotEqual(copied.pk, saved.pk)
        self.assertEqual(BudgetPlan.objects.filter(status="saved").count(), 2)
        saved.refresh_from_db()
        self.assertEqual(saved.meals.get().recipe_id, self.quotes[0][1])

    def test_original_changed_rejects_overwrite_and_preserves_source_version_on_regeneration(self):
        saved = self.saved()
        draft = apply_preview(self.user, self.replacement(saved).pk)
        save_plan(self.user, saved.pk, 1, "Renamed", saved.starts_on)
        draft = write_draft(
            self.user,
            draft.inputs,
            thaw(draft.snapshot),
            previous=draft,
            expected_version=draft.version,
            source=draft.source_plan,
        )
        self.assertEqual(draft.source_version, 1)
        with self.assertRaises(PlanConflict):
            save_plan(
                self.user,
                draft.pk,
                draft.version,
                draft.title,
                draft.starts_on,
                replace_original=True,
            )

    def test_saved_preview_rejects_overwriting_newer_draft(self):
        saved = self.saved()
        preview = self.replacement(saved)
        self.update_draft()
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)

    def test_regenerate_is_previewed_before_apply(self):
        old = deepcopy(self.draft.snapshot)
        preview = make_preview(self.draft, 1, {"action": "regenerate"})
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.snapshot, old)
        self.assertNotEqual(schedule_codes(thaw(preview.snapshot)), schedule_codes(thaw(old)))
        self.assertTrue(thaw(preview.snapshot)["within_budget"])

    def test_saved_parameter_post_only_previews_changes(self):
        saved = self.saved()
        response = self.client.post(
            reverse("modul1"),
            {**self.inputs, "days": 2, "plan_id": str(saved.pk), "version": saved.version},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_preview"]["days"], 2)
        saved.refresh_from_db()
        self.assertEqual(saved.inputs["days"], 1)
        self.assertContains(response, 'id="pending-plan-preview"')

    def test_cooked_slots_cannot_be_replaced_or_deleted(self):
        self.draft.meals.update(status="cooked")
        with self.assertRaises(PlanConflict):
            self.replacement()
        self.assertEqual(
            self.api("modul1-plan-delete", self.draft.pk, {"version": 1}).status_code, 409
        )

    def test_guest_result_adopted_after_login_without_permanent_save(self):
        guest = Client()
        session = guest.session
        session["guest_last_plan"] = {
            "inputs": self.inputs,
            "result": json.dumps(freeze(self.quotes[0][2])),
        }
        session.save()
        response = guest.post(reverse("login"), {"username": "other", "password": "Demo1234!"})
        self.assertEqual(response.status_code, 302)
        adopted = BudgetPlan.objects.get(user=self.other)
        self.assertEqual(adopted.status, "draft")
        self.assertEqual(adopted.meals.get().recipe_id, self.quotes[0][1])
        self.assertNotIn("guest_last_plan", guest.session)

    def test_guest_adoption_never_clobbers_existing_account_draft(self):
        session = self.client.session
        session["guest_last_plan"] = {
            "inputs": self.inputs,
            "result": json.dumps(freeze(self.quotes[-1][2])),
        }
        session.save()
        self.client.post(reverse("login"), {"username": "planner", "password": "Demo1234!"})
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.meals.get().recipe_id, self.quotes[0][1])

    def test_invalid_guest_snapshot_does_not_break_login(self):
        guest = Client()
        session = guest.session
        session["guest_last_plan"] = {"inputs": [], "result": "bad json"}
        session.save()
        response = guest.post(reverse("login"), {"username": "other", "password": "Demo1234!"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BudgetPlan.objects.filter(user=self.other).exists())

    def test_snapshot_roundtrip_preserves_decimal_and_date(self):
        values = {"date": date(2026, 10, 4), "cost": Decimal("1234.50"), "list": [Decimal("0.03")]}
        self.assertEqual(thaw(freeze(values)), values)
