from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from apps.pantry.services import StockError

from . import tests as cooking_tests
from .models import RecipeReview, ReviewQuota
from .reviews import ReviewLimited, reserve_review, write_review
from .services import cook


@skipUnlessDBFeature("has_select_for_update")
class ReviewConcurrencyTests(TransactionTestCase):
    setUp = cooking_tests.CookingTests.setUp
    batch = cooking_tests.CookingTests.batch

    def race(self, fn):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return fn()
                except (StockError, ReviewLimited):
                    return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(worker) for _ in range(2)]
            return [job.result(timeout=30) for job in jobs]

    def test_parallel_first_review_creates_only_one(self):
        self.batch()
        cook(self.user, self.payload)
        payload = {"recipe_code": self.recipe.pk, "rating": 5, "comment": "Enak"}
        results = self.race(lambda: write_review(self.user, payload))
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(RecipeReview.objects.count(), 1)
        self.assertEqual(ReviewQuota.objects.get().attempts, 2)

    def test_last_quota_slot_is_atomic(self):
        ReviewQuota.objects.create(user=self.user, window_started_at=timezone.now(), attempts=9)
        results = self.race(lambda: reserve_review(self.user))
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(ReviewQuota.objects.get().attempts, 10)
