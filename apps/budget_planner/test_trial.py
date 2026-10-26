"""Compatibility checks for historical guest quota records."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import GuestTrial
from .trial import WINDOW, record_success, trial_state


class GuestTrialTests(TestCase):
    def test_atomic_claim_does_not_trust_stale_counter(self):
        stale = GuestTrial()
        now = timezone.now()
        for _ in range(3):
            self.assertTrue(record_success(GuestTrial(id=stale.pk), now=now))
        self.assertFalse(record_success(stale, now=now))
        self.assertEqual(trial_state(stale, now)["remaining"], 0)

    def test_window_resets_exactly_after_24_hours(self):
        trial = GuestTrial()
        now = timezone.now()
        for _ in range(3):
            self.assertTrue(record_success(trial, now=now))
        self.assertFalse(record_success(trial, now=now + WINDOW - timedelta(seconds=1)))
        self.assertTrue(record_success(trial, now=now + WINDOW))
        trial.refresh_from_db()
        self.assertEqual(trial.window_started_at, now + WINDOW)
        self.assertEqual(trial.successful_uses, 1)

    def test_database_constraint_rejects_invalid_usage(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GuestTrial.objects.create(successful_uses=4)
