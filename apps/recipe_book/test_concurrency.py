from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from apps.pantry.models import PantryMovement
from apps.pantry.services import StockError

from . import tests as cooking_tests
from .models import CookingHistory
from .services import cook


@skipUnlessDBFeature("has_select_for_update")
class CookingConcurrencyTests(TransactionTestCase):
    setUp = cooking_tests.CookingTests.setUp
    batch = cooking_tests.CookingTests.batch
    slot = cooking_tests.CookingTests.slot

    def race(self, fn):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return fn()
                except StockError:
                    return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(worker) for _ in range(2)]
            return [job.result(timeout=30) for job in jobs]

    def test_same_key_writes_one_history_and_movement(self):
        batch = self.batch(quantity=300)
        results = self.race(lambda: cook(self.user, self.payload))
        self.assertEqual(results[0], results[1])
        self.assertEqual(CookingHistory.objects.count(), 1)
        self.assertEqual(PantryMovement.objects.count(), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 200)

    def test_different_keys_same_slot_only_one_wins(self):
        self.batch(quantity=300)
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=1)
        results = self.race(
            lambda: cook(self.user, {**self.payload, "operation_key": str(uuid4())})
        )
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(CookingHistory.objects.count(), 1)
        self.assertEqual(PantryMovement.objects.count(), 1)

    def test_two_recipes_cannot_overdraw_shared_inventory(self):
        batch = self.batch()
        results = self.race(
            lambda: cook(self.user, {**self.payload, "operation_key": str(uuid4())})
        )
        self.assertEqual(results.count("conflict"), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 0)
