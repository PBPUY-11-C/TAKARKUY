import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import Client, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Ingredient

from .ai_cache import claim
from .models import NameResolution, PantryItem, PantryLLMUsage, PantryMovement, PantryOperation
from .services import StockError, consume_stock, reserve_llm


@skipUnlessDBFeature("has_select_for_update")
class PantryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("race")
        self.ingredient = Ingredient.objects.create(
            ingredient_code="ING-RACE", name="Test", category="test", base_unit="g"
        )
        self.item = PantryItem.objects.create(
            user=self.user,
            session_id="test",
            name="Test",
            ingredient=self.ingredient,
            source="manual",
            quantity=100,
            unit="g",
            grams_per_unit=1,
            expiry_source="manual",
            estimated_expires_on=timezone.localdate() + timedelta(days=3),
        )

    def race(self, action):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return action()
                except StockError:
                    return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            jobs = [executor.submit(worker) for _ in range(2)]
            return [job.result(timeout=30) for job in jobs]

    def test_last_quota_slot_only_one_wins(self):
        PantryLLMUsage.objects.create(
            user=self.user,
            kind="photo",
            day=timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")),
            attempts=9,
        )
        outcomes = self.race(lambda: reserve_llm(self.user, "photo"))
        self.assertCountEqual(outcomes, [None, "conflict"])
        self.assertEqual(PantryLLMUsage.objects.get().attempts, 10)

    def test_different_consumption_keys_cannot_overdraw(self):
        outcomes = self.race(lambda: consume_stock(self.user, {self.ingredient.pk: 80}, uuid4()))
        self.assertEqual(outcomes.count("conflict"), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 20)
        self.assertEqual(PantryMovement.objects.count(), 1)

    def test_same_cooking_key_only_consumes_once(self):
        key = uuid4()
        outcomes = self.race(lambda: consume_stock(self.user, {self.ingredient.pk: 60}, key))
        self.assertEqual(outcomes[0], outcomes[1])
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 40)
        self.assertEqual(PantryMovement.objects.count(), 1)
        self.assertEqual(PantryOperation.objects.count(), 1)

    def test_global_cache_only_one_lease_is_owned(self):
        outcomes = self.race(lambda: claim("test", "test-version")[1])
        self.assertCountEqual(outcomes, [True, False])
        self.assertEqual(NameResolution.objects.count(), 1)

    def test_parallel_create_retries_write_one_batch(self):
        payload = {
            "operation_key": str(uuid4()),
            "source": "manual",
            "items": [{"name": "Test", "category": "lainnya", "quantity": 1, "unit": "g"}],
        }

        def action():
            client = Client()
            client.force_login(self.user)
            response = client.post(
                reverse("modul2-items"), data=json.dumps(payload), content_type="application/json"
            )
            return response.status_code, response.json()

        outcomes = self.race(action)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][0], 201)
        self.assertEqual(PantryMovement.objects.count(), 1)
        self.assertEqual(PantryItem.objects.count(), 2)  # includes setup stock

    def test_parallel_edits_with_same_version_only_one_wins(self):
        def action():
            client = Client()
            client.force_login(self.user)
            response = client.patch(
                reverse("modul2-item-details", args=[self.item.pk]),
                data=json.dumps({"operation_key": str(uuid4()), "version": 1, "quantity": 50}),
                content_type="application/json",
            )
            return response.status_code

        self.assertCountEqual(self.race(action), [200, 409])
        self.assertEqual(PantryMovement.objects.count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.version, 2)
