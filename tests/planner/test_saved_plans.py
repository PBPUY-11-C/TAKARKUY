import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe, RecipeTag
from apps.pantry.models import PantryItem
from apps.planner.models import (
    BudgetPlan,
    PlannedMeal,
    PlanPreview,
    PlanPreviewQuota,
    ShoppingListItem,
)
from apps.planner.plan_views import preview_data
from apps.planner.planner import build_plan
from apps.planner.services import (
    JAKARTA,
    MAX_START_DAYS,
    PlanConflict,
    apply_preview,
    clean_inputs,
    make_preview,
    save_plan,
    schedule_codes,
    stock_context,
    write_draft,
)
from apps.planner.snapshots import freeze, thaw


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
        return save_plan(self.user, self.draft.pk, self.draft.version, "Minggu Ini")

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

    def test_start_date_is_chosen_on_save_and_moves_the_schedule(self):
        today = timezone.localdate(timezone=JAKARTA)
        later = today + timedelta(days=3)
        response = self.api(
            "modul1-plan-save",
            self.draft.pk,
            {"version": self.draft.version, "title": "Minggu Depan", "starts_on": later.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        saved = BudgetPlan.objects.get(user=self.user, status="saved")
        self.assertEqual(saved.starts_on, later)
        self.assertEqual(saved.meals.get().scheduled_on, later)
        moved = today + timedelta(days=5)
        save_plan(self.user, saved.pk, saved.version, "Minggu Depan", moved)
        saved.refresh_from_db()
        self.assertEqual(saved.meals.get().scheduled_on, moved)
        save_plan(self.user, saved.pk, saved.version, "Judul Baru")
        saved.refresh_from_db()
        self.assertEqual((saved.title, saved.starts_on), ("Judul Baru", moved))

    def test_old_draft_date_saves_as_today(self):
        today = timezone.localdate(timezone=JAKARTA)
        stale = today - timedelta(days=2)
        BudgetPlan.objects.filter(pk=self.draft.pk).update(starts_on=stale)
        page = self.client.get(reverse("modul1") + f"?plan={self.draft.pk}")
        self.assertContains(page, f'value="{today:%Y-%m-%d}"')
        response = self.api(
            "modul1-plan-save",
            self.draft.pk,
            {"version": self.draft.version, "title": "Lama", "starts_on": stale.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BudgetPlan.objects.get(status="saved").starts_on, today)

    def test_deleted_plan_link_returns_to_planner_with_notice(self):
        saved = self.saved()
        url = reverse("modul1")
        self.api("modul1-plan-delete", saved.pk, {"version": saved.version})
        for response in (
            self.client.get(url, {"plan": str(saved.pk)}),
            self.client.post(url, {**self.inputs, "plan_id": str(saved.pk), "version": 1}),
            self.client.get(url, {"plan": "bukan-uuid"}),
        ):
            self.assertRedirects(response, url + "?hilang=1")
        self.assertContains(self.client.get(url + "?hilang=1"), "sudah dihapus atau tidak ditemukan")

    def test_start_date_must_be_today_to_sixty_days_unless_unchanged(self):
        today = timezone.localdate(timezone=JAKARTA)
        for bad in (today - timedelta(days=1), today + timedelta(days=MAX_START_DAYS + 1)):
            with self.subTest(day=bad):
                response = self.api(
                    "modul1-plan-save",
                    self.draft.pk,
                    {"version": self.draft.version, "title": "X", "starts_on": bad.isoformat()},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("Tanggal mulai harus", response.json()["error"])
        response = self.api(
            "modul1-plan-save",
            self.draft.pk,
            {"version": self.draft.version, "title": "X", "starts_on": "besok"},
        )
        self.assertEqual(response.json()["error"], "Format tanggal mulai tidak valid.")
        saved = self.saved()
        BudgetPlan.objects.filter(pk=saved.pk).update(starts_on=today - timedelta(days=10))
        saved.refresh_from_db()
        save_plan(self.user, saved.pk, saved.version, "Lama", saved.starts_on)
        saved.refresh_from_db()
        self.assertEqual(saved.title, "Lama")

    def test_cooked_meals_pin_the_start_date(self):
        saved = self.saved()
        saved.meals.update(status="cooked")
        later = timezone.localdate(timezone=JAKARTA) + timedelta(days=2)
        with self.assertRaises(PlanConflict):
            save_plan(self.user, saved.pk, saved.version, saved.title, later)
        page = self.client.get(reverse("modul1") + f"?plan={saved.pk}")
        self.assertContains(page, 'title="Sudah ada menu yang dimasak"')

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

    def test_planner_alias_reads_and_updates_the_same_owned_draft(self):
        response = self.client.get(reverse("planner"), {"plan": str(self.draft.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["plan"].pk, self.draft.pk)
        response = self.client.post(reverse("planner"), self.generation_data(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.version, 2)
        self.assertEqual(BudgetPlan.objects.filter(user=self.user, status="draft").count(), 1)

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
        self.assertEqual(self.client.post(reverse("modul1"), self.inputs).status_code, 409)
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

    def test_planner_opens_empty_and_a_new_plan_replaces_the_scratch_draft(self):
        page = self.client.get(reverse("modul1"))
        self.assertIsNone(page.context["plan"])
        self.assertNotContains(page, "Draft terakhir")
        self.assertContains(page, '<input type="hidden" name="replace_draft" value="1">')
        response = self.client.post(
            reverse("modul1"),
            {
                **self.inputs,
                "new_plan": "1",
                "replace_draft": "1",
                "replace_draft_id": str(self.draft.pk),
                "replace_draft_version": str(self.draft.version),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BudgetPlan.objects.filter(user=self.user, status="draft").count(), 1)

    def test_last_plan_is_offered_until_logout_or_new_plan(self):
        planner = reverse("modul1")
        opened = planner + f"?plan={self.draft.pk}#hasil"
        self.client.get(planner, {"plan": str(self.draft.pk)})
        page = self.client.get(planner)
        self.assertIsNone(page.context["plan"])
        self.assertEqual(page.context["remembered_url"], opened)
        self.assertContains(page, 'sessionStorage.getItem("takarkuy-planner")')
        self.client.post(reverse("logout"))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(planner).context["remembered_url"], "")
        self.client.get(planner, {"plan": str(self.draft.pk)})
        self.client.get(planner, {"new": "1"})
        self.assertEqual(self.client.get(planner).context["remembered_url"], "")

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
        self.update_draft(result=self.quotes[0][2])
        original = deepcopy(self.draft.snapshot)
        for action in ("replace", "parameters"):
            payload = {"action": action, "version": saved.version}
            if action == "replace":
                payload.update(day=1, meal="sarapan", recipe=self.quotes[-1][1])
            else:
                payload.update(inputs=self.inputs)
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

    def test_older_saved_plan_editable_when_draft_matches_its_own_saved_source(self):
        first = self.saved()
        self.draft.refresh_from_db()
        self.draft = write_draft(
            self.user,
            self.inputs,
            self.quotes[1][2],
            replace_draft=True,
            expected_draft_id=self.draft.pk,
            expected_draft_version=self.draft.version,
        )
        save_plan(self.user, self.draft.pk, self.draft.version, "Plan B")
        draft = apply_preview(self.user, self.replacement(first).pk)
        self.assertEqual(draft.source_plan_id, first.pk)

    def test_new_draft_starts_on_jakarta_date_not_utc(self):
        early_morning = datetime(2026, 10, 14, 23, 30, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=early_morning):
            draft = write_draft(self.other, self.inputs, self.quotes[0][2])
        self.assertEqual(draft.starts_on, date(2026, 10, 15))

    def test_save_without_date_starts_today(self):
        response = self.api(
            "modul1-plan-save", self.draft.pk, {"version": self.draft.version, "title": "Plan"}
        )
        self.assertEqual(response.status_code, 200)
        saved = BudgetPlan.objects.get(status="saved")
        today = timezone.localdate(timezone=JAKARTA)
        self.assertEqual((saved.starts_on, saved.meals.get().scheduled_on), (today, today))

    def test_renaming_without_date_keeps_saved_date(self):
        saved = self.saved()
        start = saved.starts_on
        saved = save_plan(self.user, saved.pk, saved.version, "Baru")
        self.assertEqual((saved.title, saved.starts_on), ("Baru", start))
        self.assertEqual(saved.meals.get().scheduled_on, start)

    def stocked_draft(self):
        """A draft that fits its budget only because the pantry covers part of it."""
        code = self.quotes[-1][1]
        quote = self.quotes[-1][2]
        inputs = {**self.inputs, "budget": str(quote["total"] - 1000)}
        stock = [
            (row["ingredient_code"], Decimal(row["quantity"]), None)
            for group in quote["shopping_groups"]
            for row in group["items"]
        ]
        result = build_plan(
            **clean_inputs(inputs).cleaned_data, fixed_schedule=[{"sarapan": code}], stock=stock
        )
        self.assertTrue(result["within_budget"])
        self.draft.refresh_from_db()
        draft = write_draft(
            self.user, inputs, result, previous=self.draft, expected_version=self.draft.version
        )
        return draft, stock

    def add_pantry(self, stock):
        for code, grams, _ in stock:
            PantryItem.objects.create(
                user=self.user,
                session_id="t",
                name=code,
                ingredient_id=code,
                quantity=grams,
                unit="g",
                grams_per_unit=1,
                expiry_source="unknown",
            )

    def test_stock_reserved_by_another_saved_plan_is_not_counted_again(self):
        draft, stock = self.stocked_draft()
        self.add_pantry(stock)
        saved = save_plan(self.user, draft.pk, draft.version, "Plan A")
        used = thaw(saved.snapshot)["stock_used"]
        self.assertTrue(used)
        available = {}
        for code, grams, _ in stock_context(self.user)["stock"]:
            available[code] = available.get(code, 0) + grams
        for code, grams in used.items():
            self.assertEqual(
                available.get(code, 0), dict((c, g) for c, g, _ in stock)[code] - grams
            )
        own = {c: g for c, g, _ in stock_context(self.user, saved)["stock"]}
        self.assertEqual(own, {c: g for c, g, _ in stock})
        saved.meals.update(status="cooked")
        released = {c: g for c, g, _ in stock_context(self.user)["stock"]}
        self.assertEqual(released, {c: g for c, g, _ in stock})

    def test_stock_saving_note_not_repeated_under_net_cost(self):
        draft, stock = self.stocked_draft()
        self.add_pantry(stock)
        page = self.client.get(reverse("modul1") + f"?plan={draft.pk}")
        self.assertContains(page, "Nilai menu")
        self.assertNotContains(page, "belanja bisa berkurang")

    def test_stock_context_for_new_draft_starts_today_without_past_days(self):
        self.draft.refresh_from_db()
        self.draft.starts_on = timezone.localdate() - timedelta(days=3)
        self.draft.save()
        context = stock_context(self.user, self.draft)
        self.assertEqual(context["starts_on"], timezone.localdate())
        self.assertEqual(context["frozen_days"], frozenset())

    def test_save_without_any_stock_does_not_requote(self):
        self.draft.refresh_from_db()
        minimal = {
            "within_budget": True,
            "total": Decimal("0"),
            "schedule": [],
            "shopping_groups": [],
            "planned_recipe_codes": [],
        }
        draft = write_draft(self.other, self.inputs, minimal)
        saved = save_plan(self.other, draft.pk, draft.version, "Kosong")
        self.assertEqual(saved.status, "saved")

    def test_save_rejects_when_stock_vanished_and_net_exceeds_budget(self):
        draft, _ = self.stocked_draft()
        with self.assertRaisesMessage(PlanConflict, "Stok Pantry atau harga katalog berubah"):
            save_plan(self.user, draft.pk, draft.version, "Plan")
        draft.refresh_from_db()
        self.assertEqual(draft.status, "draft")
        self.assertFalse(BudgetPlan.objects.filter(status="saved").exists())

    def test_save_requotes_with_current_stock_and_keeps_draft_clean(self):
        draft, stock = self.stocked_draft()
        for code, grams, _ in stock:
            PantryItem.objects.create(
                user=self.user,
                session_id="t",
                name=code,
                ingredient_id=code,
                quantity=grams,
                unit="g",
                grams_per_unit=1,
                expiry_source="unknown",
            )
        saved = save_plan(self.user, draft.pk, draft.version, "Plan")
        draft.refresh_from_db()
        self.assertEqual(draft.snapshot, saved.snapshot)
        self.assertLessEqual(thaw(saved.snapshot)["net_total"], int(draft.inputs["budget"]))

    def test_pages_show_net_shopping_cost_not_full_menu_value(self):
        draft, stock = self.stocked_draft()
        net = thaw(draft.snapshot)["net_total"]
        page = self.client.get(reverse("modul1") + f"?plan={draft.pk}")
        self.assertContains(page, f'<p class="big">Rp {net:,} <span>'.replace(",", "."))
        preview = preview_data(self.replacement(draft, code=self.quotes[0][1]))
        self.assertEqual(preview["before"], net)

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
            ("modul1-plan-preview", {"action": "parameters", "inputs": self.inputs}),
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
        self.assertIsNone(second.get(reverse("modul1")).context["plan"])
        response = second.get(reverse("modul1") + f"?plan={self.draft.pk}")
        self.assertEqual(response.context["plan"].pk, self.draft.pk)
        second.force_login(self.other)
        self.assertRedirects(
            second.get(reverse("modul1") + f"?plan={self.draft.pk}"),
            reverse("modul1") + "?hilang=1",
        )
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

    def test_save_copies_snapshot_and_children_starting_today(self):
        saved = self.saved()
        self.assertEqual(saved.status, "saved")
        self.assertEqual(saved.meals.get().scheduled_on, timezone.localdate())
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
        same = save_plan(self.user, self.draft.pk, 1, "Minggu Ini")
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
            {"version": 1, "title": "  Bekal   Kantor "},
        )
        self.assertEqual(response.status_code, 200)
        saved.refresh_from_db()
        self.assertEqual(saved.title, "Bekal Kantor")
        self.assertEqual(saved.meals.get().scheduled_on, timezone.localdate(timezone=JAKARTA))
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
            {"version": True, "action": "parameters", "inputs": self.inputs},
            {"version": 1, "action": []},
            {"version": 1, "action": "parameters", "inputs": []},
            {"version": 1, "action": "replace", "day": 1, "meal": [], "recipe": "fake"},
        ):
            self.assertIn(
                self.api("modul1-plan-preview", self.draft.pk, payload).status_code, (400, 409)
            )

    def test_malformed_draft_id_shows_friendly_conflict(self):
        response = self.client.post(
            reverse("modul1"),
            {
                **self.inputs,
                "new_plan": "1",
                "replace_draft": "1",
                "replace_draft_id": "bukan-uuid",
                "replace_draft_version": self.draft.version,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Draft sudah berubah", status_code=409)

    def test_metadata_validation(self):
        for changes in (
            {"title": ""},
            {"title": "x" * 101},
            {"title": {}},
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
        preview = self.api(
            "modul1-plan-preview",
            missing,
            {"action": "parameters", "inputs": self.inputs, "version": 1},
        )
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

    def exhaust_quota(self):
        PlanPreviewQuota.objects.create(
            user=self.user, window_started_at=timezone.now(), attempts=20
        )

    def test_generate_uses_the_preview_quota(self):
        self.exhaust_quota()
        with patch("apps.planner.views.build_plan") as builder:
            response = self.client.post(reverse("modul1"), self.generation_data())
        self.assertEqual(response.status_code, 429)
        builder.assert_not_called()

    def test_alternatives_use_the_preview_quota(self):
        self.exhaust_quota()
        response = self.client.get(
            reverse("modul1-plan-alternatives", args=[self.draft.pk]), {"day": 1, "meal": "sarapan"}
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_alternative_and_preview_deltas_compare_with_live_stock(self):
        draft, stock = self.stocked_draft()
        self.add_pantry(stock)
        snapshot = thaw(draft.snapshot)
        snapshot["net_total"] = snapshot["total"]
        draft.snapshot = freeze(snapshot)
        draft.save()
        response = self.client.get(
            reverse("modul1-plan-alternatives", args=[draft.pk]), {"day": 1, "meal": "sarapan"}
        )
        live = build_plan(
            **clean_inputs(draft.inputs).cleaned_data,
            fixed_schedule=schedule_codes(thaw(draft.snapshot)),
            stock=stock,
        )["net_total"]
        option = response.json()["recipes"][0]
        replaced = [dict(slots) for slots in schedule_codes(thaw(draft.snapshot))]
        replaced[0]["sarapan"] = option["recipe_code"]
        after = build_plan(
            **clean_inputs(draft.inputs).cleaned_data, fixed_schedule=replaced, stock=stock
        )["net_total"]
        self.assertEqual(option["delta"], after - live)
        preview = preview_data(self.replacement(draft, code=option["recipe_code"]))
        self.assertEqual(preview["before"], live)

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
        updated = save_plan(self.user, draft.pk, draft.version, saved.title, replace_original=True)
        self.assertEqual(updated.pk, saved.pk)
        self.assertEqual(updated.meals.get().recipe_id, self.quotes[-1][1])
        self.assertEqual(BudgetPlan.objects.filter(status="saved").count(), 1)

    def test_edit_saved_can_save_as_new_instead(self):
        saved = self.saved()
        draft = apply_preview(self.user, self.replacement(saved).pk)
        copied = save_plan(self.user, draft.pk, draft.version, "Plan B")
        self.assertNotEqual(copied.pk, saved.pk)
        self.assertEqual(BudgetPlan.objects.filter(status="saved").count(), 2)
        saved.refresh_from_db()
        self.assertEqual(saved.meals.get().recipe_id, self.quotes[0][1])

    def test_original_changed_rejects_overwrite_and_preserves_source_version_on_new_draft(self):
        saved = self.saved()
        draft = apply_preview(self.user, self.replacement(saved).pk)
        save_plan(self.user, saved.pk, 1, "Renamed")
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
                replace_original=True,
            )

    def test_saved_preview_rejects_overwriting_newer_draft(self):
        saved = self.saved()
        preview = self.replacement(saved)
        self.update_draft()
        with self.assertRaises(PlanConflict):
            apply_preview(self.user, preview.pk)

    def test_parameter_change_is_previewed_before_apply(self):
        old = deepcopy(self.draft.snapshot)
        preview = make_preview(
            self.draft, 1, {"action": "parameters", "inputs": {**self.inputs, "servings": 2}}
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.snapshot, old)
        self.assertEqual(preview.inputs["servings"], 2)
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
        self.assertContains(response, "Ganti semua menu")
        self.assertNotContains(response, "Pratinjau perubahan")
        preview = response.context["pending_preview"]
        self.assertEqual((preview["previous_days"], preview["days"]), (1, 2))
        self.assertEqual(preview["title"], saved.title)
        items = sum(len(group["items"]) for group in preview["shopping_groups"])
        self.assertEqual(sum(row["count"] for row in preview["summary"]), items)
        self.assertTrue({"key", "label", "count"} <= set(preview["summary"][0]))

    def test_cooked_slots_cannot_be_replaced_but_plan_can_be_deleted(self):
        self.draft.meals.update(status="cooked")
        with self.assertRaises(PlanConflict):
            self.replacement()
        self.assertEqual(
            self.api("modul1-plan-delete", self.draft.pk, {"version": 1}).status_code, 200
        )
        self.assertFalse(BudgetPlan.objects.filter(pk=self.draft.pk).exists())

    def test_uncooked_slot_can_change_after_other_slot_cooked(self):
        from apps.planner.services import sync_children

        self.draft.delete()
        inputs = {**self.inputs, "days": 2}
        result = build_plan(
            **clean_inputs(inputs).cleaned_data, fixed_schedule=[{"sarapan": self.quotes[0][1]}] * 2
        )
        draft = write_draft(self.user, inputs, result)
        saved = save_plan(self.user, draft.pk, draft.version, "Dua hari")
        first = saved.meals.get(day=1)
        first.status = "cooked"
        first.save()
        snapshot = deepcopy(first.snapshot)
        preview = make_preview(
            saved,
            saved.version,
            {"action": "replace", "day": 2, "meal": "sarapan", "recipe": self.quotes[-1][1]},
        )
        edited = apply_preview(self.user, preview.pk)
        with self.assertRaises(PlanConflict):
            make_preview(edited, edited.version, {"action": "parameters", "inputs": self.inputs})
        saved = save_plan(
            self.user,
            edited.pk,
            edited.version,
            saved.title,
            replace_original=True,
        )
        first.refresh_from_db()
        self.assertEqual(first.status, "cooked")
        self.assertEqual(first.snapshot, snapshot)
        self.assertEqual(saved.meals.get(day=2).recipe_id, self.quotes[-1][1])
        bad = thaw(saved.snapshot)
        bad["schedule"] = bad["schedule"][1:]
        saved.snapshot = freeze(bad)
        with self.assertRaises(PlanConflict):
            sync_children(saved)

    def test_snapshot_roundtrip_preserves_decimal_and_date(self):
        values = {"date": date(2026, 10, 4), "cost": Decimal("1234.50"), "list": [Decimal("0.03")]}
        self.assertEqual(thaw(freeze(values)), values)
