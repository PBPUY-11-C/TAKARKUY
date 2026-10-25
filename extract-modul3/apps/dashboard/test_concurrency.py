from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature

from .maps import MapLimited, _http, reserve_map
from .models import MapQuota


@skipUnlessDBFeature("has_select_for_update")
class MapConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("map-race")

    def race(self, fn):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return fn()
                except MapLimited:
                    return "limited"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(worker) for _ in range(2)]
            return [job.result(timeout=30) for job in jobs]

    def test_last_account_slot_cannot_be_taken_twice(self):
        from django.utils import timezone

        MapQuota.objects.create(user=self.user, window_started_at=timezone.now(), attempts=9)
        results = self.race(lambda: reserve_map(self.user))
        self.assertEqual(results.count("limited"), 1)
        self.assertEqual(MapQuota.objects.get().attempts, 10)

    @override_settings(MAP_USER_AGENT="TAKARKUY/1.0 (+https://github.com/PBPUY-11-C/TAKARKUY)")
    @patch(
        "apps.dashboard.maps.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=b"[]"),
    )
    def test_provider_gate_is_shared_not_per_user_or_worker(self, run):
        results = self.race(
            lambda: _http("nominatim", "https://nominatim.openstreetmap.org/search")
        )
        self.assertEqual(results.count("limited"), 1)
        self.assertEqual(run.call_count, 1)
