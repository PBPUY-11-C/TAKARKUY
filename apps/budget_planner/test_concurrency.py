"""Real concurrent transactions. Skipped on SQLite, exercised on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier, Event

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from .models import BudgetPlan, PlanPreview, PlanPreviewQuota
from .services import (
    PlanConflict,
    PreviewRateLimit,
    apply_preview,
    reserve_preview,
    save_plan,
    write_draft,
)
from .snapshots import freeze


@skipUnlessDBFeature("has_select_for_update")
class PlanConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("concurrency")
        self.inputs = {
            "budget": "100000",
            "days": 1,
            "servings": 1,
            "meal_types": ["sarapan"],
            "targets": ["seimbang"],
            "exclude_ingredients": "",
        }
        # No catalog fixture/search is needed to test write serialization itself.
        self.result = {
            "within_budget": True,
            "total": Decimal("0"),
            "schedule": [],
            "shopping_groups": [],
            "planned_recipe_codes": [],
        }

    def race(self, operation):
        ready = Barrier(2)

        def worker():
            close_old_connections()
            try:
                ready.wait(timeout=10)
                try:
                    return ("ok", operation())
                except PlanConflict:
                    return ("conflict", None)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            jobs = [executor.submit(worker) for _ in range(2)]
            return [job.result(timeout=30) for job in jobs]

    def draft(self):
        return write_draft(self.user, self.inputs, deepcopy(self.result))

    def test_first_draft_creation_is_serialized_and_cannot_clobber_winner(self):
        outcomes = self.race(lambda: self.draft().pk)
        self.assertCountEqual([x[0] for x in outcomes], ["ok", "conflict"])
        self.assertEqual(BudgetPlan.objects.filter(user=self.user, status="draft").count(), 1)
        self.assertEqual(BudgetPlan.objects.get(user=self.user).version, 1)

    def test_preview_quota_last_slot_is_reserved_only_once(self):
        PlanPreviewQuota.objects.create(
            user=self.user, window_started_at=timezone.now(), attempts=19
        )

        def attempt():
            try:
                reserve_preview(self.user)
                return "accepted"
            except PreviewRateLimit:
                return "limited"

        outcomes = self.race(attempt)
        self.assertCountEqual([value for _, value in outcomes], ["accepted", "limited"])
        self.assertEqual(PlanPreviewQuota.objects.get(user=self.user).attempts, 20)

    def test_same_version_update_only_one_request_wins(self):
        draft = self.draft()
        outcomes = self.race(
            lambda: (
                write_draft(
                    self.user,
                    self.inputs,
                    deepcopy(self.result),
                    previous=draft,
                    expected_version=1,
                ).pk
            )
        )
        self.assertCountEqual([x[0] for x in outcomes], ["ok", "conflict"])
        draft.refresh_from_db()
        self.assertEqual(draft.version, 2)

    def test_new_plan_consent_is_bound_to_exact_draft_version(self):
        draft = self.draft()
        outcomes = self.race(
            lambda: (
                write_draft(
                    self.user,
                    self.inputs,
                    deepcopy(self.result),
                    replace_draft=True,
                    expected_draft_id=draft.pk,
                    expected_draft_version=1,
                ).pk
            )
        )
        self.assertCountEqual([x[0] for x in outcomes], ["ok", "conflict"])
        draft.refresh_from_db()
        self.assertEqual(draft.version, 2)

    def test_double_save_is_idempotent_under_real_transactions(self):
        draft = self.draft()
        outcomes = self.race(
            lambda: (
                save_plan(
                    self.user,
                    draft.pk,
                    1,
                    "Minggu ini",
                    date(2026, 10, 5),
                ).pk
            )
        )
        self.assertEqual([x[0] for x in outcomes], ["ok", "ok"])
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        self.assertEqual(BudgetPlan.objects.filter(user=self.user, status="saved").count(), 1)

    def test_same_preview_can_only_be_applied_once(self):
        draft = self.draft()
        preview = PlanPreview.objects.create(
            plan=draft,
            version=1,
            draft_id=draft.pk,
            draft_version=1,
            inputs=self.inputs,
            snapshot=freeze(self.result),
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        outcomes = self.race(lambda: apply_preview(self.user, preview.pk).pk)
        self.assertCountEqual([x[0] for x in outcomes], ["ok", "conflict"])
        preview.refresh_from_db()
        self.assertIsNotNone(preview.used_at)
        draft.refresh_from_db()
        self.assertEqual(draft.version, 2)

    def test_user_row_lock_really_blocks_writes_until_commit(self):
        started = Event()

        def worker():
            close_old_connections()
            try:
                started.set()
                return self.draft().pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=self.user.pk)
                job = executor.submit(worker)
                self.assertTrue(started.wait(timeout=5))
                with self.assertRaises(TimeoutError):
                    job.result(timeout=0.2)
            self.assertIsNotNone(job.result(timeout=10))
        self.assertEqual(connection.vendor, "postgresql")
