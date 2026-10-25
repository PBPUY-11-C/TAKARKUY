import json
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe

from .models import BudgetPlan, PlanPreview, PlanPreviewQuota
from .planner import _load_candidates, build_plan, quote_schedule, replacement_options
from .services import (
    PreviewRateLimit,
    account_recent_recipe_codes,
    clean_inputs,
    make_preview,
    reserve_preview,
    save_plan,
    schedule_codes,
    write_draft,
)
from .snapshots import freeze, thaw


class PlannerRefinementTests(TestCase):
    fixtures = ["catalog_seed"]

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("refinements")
        cls.other = get_user_model().objects.create_user("other-refinements")
        cls.inputs = {
            "budget": "1000000",
            "days": 3,
            "servings": 1,
            "meal_types": ["sarapan"],
            "targets": ["seimbang"],
            "exclude_ingredients": "",
        }
        cls.fruit = Recipe.objects.get(name__iexact="Pisang dan Jeruk").pk
        cls.replacement = Recipe.objects.get(name__iexact="Nasi Kuning", is_plannable=True).pk
        cls.args = clean_inputs(cls.inputs).cleaned_data
        cls.result = build_plan(**cls.args, fixed_schedule=[{"sarapan": cls.fruit}] * 3)

    def setUp(self):
        self.draft = write_draft(self.user, deepcopy(self.inputs), deepcopy(self.result))
        self.client.force_login(self.user)

    def preview(self, plan=None):
        plan = plan or self.draft
        return make_preview(
            plan,
            plan.version,
            {
                "action": "replace",
                "day": 1,
                "meal": "sarapan",
                "recipe": self.replacement,
            },
        )

    def saved(self):
        return save_plan(
            self.user, self.draft.pk, self.draft.version, "Rencana", timezone.localdate()
        )

    def test_quote_is_database_free_and_same_as_build_for_shared_fruit(self):
        catalog = _load_candidates(("sarapan",), 1, [])
        with self.assertNumQueries(0):
            quote = quote_schedule(
                schedule_codes(self.result), servings=1, targets=["seimbang"], catalog=catalog
            )
        for field in ("total", "shopping_groups", "schedule", "nutrition", "rounding_adjustment"):
            self.assertEqual(quote[field], self.result[field])

    def test_every_dropdown_delta_matches_full_preview_and_excludes_over_budget(self):
        slots = schedule_codes(self.result)
        catalog = _load_candidates(("sarapan",), 1, [])
        with patch("apps.budget_planner.planner._load_candidates", return_value=catalog):
            with self.assertNumQueries(0):
                options = replacement_options(
                    **self.args,
                    schedule=slots,
                    day=1,
                    meal="sarapan",
                    current_total=self.result["total"],
                )
            self.assertGreater(len(options), 10)
            for option in options:
                changed = deepcopy(slots)
                changed[0]["sarapan"] = option["recipe_code"]
                result = build_plan(**self.args, fixed_schedule=changed)
                self.assertEqual(option["delta"], result["total"] - self.result["total"])
            constrained = replacement_options(
                **{**self.args, "budget": self.result["total"]},
                schedule=slots,
                day=1,
                meal="sarapan",
                current_total=self.result["total"],
            )
        # Regression: old dropdown called this cheaper, while pooled fruit makes it dearer.
        nasi = next(item for item in options if item["recipe_code"] == self.replacement)
        self.assertGreater(nasi["delta"], 0)
        self.assertNotIn(self.replacement, [item["recipe_code"] for item in constrained])
        preview = self.preview()
        self.assertEqual(nasi["delta"], thaw(preview.snapshot)["total"] - self.result["total"])

    def test_soft_spend_preference_is_explained_in_result_and_preview(self):
        self.assertTrue(self.result["within_budget"])
        self.assertTrue(self.result["spend_floor_relaxed"])
        self.assertIn("60%", self.result["preference_notes"][0])
        self.assertContains(self.client.get(reverse("modul1")), self.result["preference_notes"][0])
        response = self.client.post(
            reverse("modul1-plan-preview", args=[self.draft.pk]),
            json.dumps(
                {
                    "version": 1,
                    "action": "replace",
                    "day": 1,
                    "meal": "sarapan",
                    "recipe": self.replacement,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["preference_notes"])
        self.assertFalse(response.json()["nutrition_targets_set"])
        candidates = _load_candidates(("sarapan",), 1, [])[5]["sarapan"]
        cheapest = min(candidates, key=lambda item: item["cost"])["recipe"].pk
        dearest = max(candidates, key=lambda item: item["cost"])["recipe"].pk
        slots = [{"sarapan": dearest}, {"sarapan": cheapest}, {"sarapan": cheapest}]
        preview = build_plan(**self.args, fixed_schedule=slots)
        tightened = build_plan(
            **{**self.args, "budget": preview["total"]},
            fixed_schedule=schedule_codes(preview),
        )
        self.assertTrue(tightened["within_budget"])
        self.assertTrue(tightened["meal_cost_cap_relaxed"])
        self.assertTrue(any("2×" in note for note in tightened["preference_notes"]))

    def test_recent_history_owned_and_calendar_window_is_cross_session(self):
        today = timezone.localdate()
        saved = self.saved()
        saved.meals.update(scheduled_on=today - timedelta(days=6))
        self.assertEqual(account_recent_recipe_codes(self.user), {self.fruit})
        self.assertEqual(account_recent_recipe_codes(self.other), set())
        # Draft dates in the future and older saved menus must not pollute history.
        self.draft.meals.update(scheduled_on=today + timedelta(days=1))
        saved.meals.update(scheduled_on=today - timedelta(days=7))
        self.assertEqual(account_recent_recipe_codes(self.user), set())
        saved.meals.update(scheduled_on=today)
        browser = Client()
        browser.force_login(self.user)
        with patch(
            "apps.budget_planner.views.build_plan", return_value=deepcopy(self.result)
        ) as builder:
            response = browser.post(
                reverse("modul1"), {**self.inputs, "plan_id": str(self.draft.pk), "version": 2}
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(builder.call_args.kwargs["recent_recipe_codes"], {self.fruit})

    def test_metadata_title_does_not_write_children_and_date_only_reschedules(self):
        saved = self.saved()
        meal_ids = list(saved.meals.values_list("pk", flat=True))
        shopping_ids = list(saved.shopping_items.values_list("pk", flat=True))
        with CaptureQueriesContext(connection) as queries:
            saved = save_plan(self.user, saved.pk, saved.version, "Judul Baru", saved.starts_on)
        children = ("budget_planner_plannedmeal", "budget_planner_shoppinglistitem")
        writes = [
            row["sql"]
            for row in queries
            if row["sql"].startswith(("UPDATE", "INSERT", "DELETE"))
            and any(table in row["sql"] for table in children)
        ]
        self.assertEqual(writes, [])
        with patch("apps.budget_planner.services.sync_children") as sync:
            saved = save_plan(
                self.user,
                saved.pk,
                saved.version,
                "Tanggal Baru",
                saved.starts_on + timedelta(days=2),
            )
            sync.assert_not_called()
        self.assertEqual(meal_ids, list(saved.meals.values_list("pk", flat=True)))
        self.assertEqual(shopping_ids, list(saved.shopping_items.values_list("pk", flat=True)))
        self.assertEqual(saved.meals.first().scheduled_on, saved.starts_on)

    def test_same_snapshot_draft_save_does_not_resync_and_changed_snapshot_uses_batches(self):
        with patch("apps.budget_planner.services.sync_children") as sync:
            self.draft = write_draft(
                self.user, self.inputs, self.result, previous=self.draft, expected_version=1
            )
            sync.assert_not_called()
        ids = list(self.draft.meals.values_list("pk", flat=True))
        self.draft.meals.filter(day=1).update(status="skipped")
        changed = build_plan(
            **self.args,
            fixed_schedule=[
                {"sarapan": self.replacement},
                {"sarapan": self.fruit},
                {"sarapan": self.fruit},
            ],
        )
        with CaptureQueriesContext(connection) as queries:
            self.draft = write_draft(
                self.user, self.inputs, changed, previous=self.draft, expected_version=2
            )
        self.assertLess(len(queries), 20)
        self.assertEqual(ids, list(self.draft.meals.values_list("pk", flat=True)))
        self.assertEqual(self.draft.meals.get(day=1).status, "planned")
        # A full seven-day, three-slot plan still uses batched writes, not 21
        # update_or_create calls (and does not change this user's draft).
        full_inputs = {
            **self.inputs,
            "days": 7,
            "meal_types": ["sarapan", "makan_siang", "makan_malam"],
        }
        full_result = build_plan(**clean_inputs(full_inputs).cleaned_data, seed=7)
        with CaptureQueriesContext(connection) as queries:
            full = write_draft(self.other, full_inputs, full_result)
        self.assertEqual(full.meals.count(), 21)
        self.assertLess(len(queries), 20)

    def test_new_preview_cleans_used_expired_but_not_live_or_other_accounts(self):
        now = timezone.now()
        first = self.preview()
        expired = PlanPreview.objects.create(
            plan=self.draft,
            version=1,
            inputs=self.inputs,
            snapshot=freeze(self.result),
            expires_at=now - timedelta(seconds=1),
        )
        used = PlanPreview.objects.create(
            plan=self.draft,
            version=1,
            inputs=self.inputs,
            snapshot=freeze(self.result),
            expires_at=now + timedelta(hours=1),
            used_at=now,
        )
        other = BudgetPlan.objects.create(
            user=self.other,
            starts_on=timezone.localdate(),
            inputs=self.inputs,
            snapshot=freeze(self.result),
        )
        other_expired = PlanPreview.objects.create(
            plan=other, version=1, inputs=self.inputs, snapshot=freeze(self.result), expires_at=now
        )
        second = self.preview()
        self.assertFalse(PlanPreview.objects.filter(pk__in=[expired.pk, used.pk]).exists())
        self.assertTrue(PlanPreview.objects.filter(pk=first.pk).exists())
        self.assertTrue(PlanPreview.objects.filter(pk=second.pk).exists())
        self.assertTrue(PlanPreview.objects.filter(pk=other_expired.pk).exists())
        call_command("cleanup_previews", stdout=StringIO())
        self.assertFalse(PlanPreview.objects.filter(pk=other_expired.pk).exists())
        self.assertEqual(BudgetPlan.objects.count(), 2)

    def test_quota_persists_across_sessions_429_and_resets_at_boundary(self):
        now = timezone.now()
        for _ in range(20):
            reserve_preview(self.user, now=now)
        browser = Client()
        browser.force_login(self.user)
        with patch("apps.budget_planner.services.build_plan") as expensive:
            response = browser.post(
                reverse("modul1-plan-preview", args=[self.draft.pk]),
                json.dumps(
                    {
                        "version": 1,
                        "action": "replace",
                        "day": 1,
                        "meal": "sarapan",
                        "recipe": self.replacement,
                    }
                ),
                content_type="application/json",
            )
            expensive.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        saved = self.saved()
        response = browser.post(
            reverse("modul1"),
            {**self.inputs, "plan_id": str(saved.pk), "version": saved.version},
        )
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        with self.assertRaises(PreviewRateLimit):
            reserve_preview(self.user, now=now + timedelta(minutes=9, seconds=59))
        reserve_preview(self.user, now=now + timedelta(minutes=10))
        self.assertEqual(PlanPreviewQuota.objects.get(user=self.user).attempts, 1)
        reserve_preview(self.other, now=now)
        self.assertEqual(PlanPreviewQuota.objects.get(user=self.other).attempts, 1)

    def test_bad_payload_not_reserved_but_failed_expensive_attempt_is_reserved(self):
        with self.assertRaises(ValueError):
            make_preview(self.draft, 1, {"action": "replace", "day": True})
        self.assertFalse(PlanPreviewQuota.objects.filter(user=self.user).exists())
        with patch("apps.budget_planner.services.build_plan", side_effect=ValueError("no result")):
            with self.assertRaises(ValueError):
                self.preview()
        self.assertEqual(PlanPreviewQuota.objects.get(user=self.user).attempts, 1)
