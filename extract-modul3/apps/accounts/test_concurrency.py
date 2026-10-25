from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import RequestFactory, TransactionTestCase, skipUnlessDBFeature

from .models import AuthRateBucket
from .rate_limits import AuthLimited, reserve_auth_attempt


@skipUnlessDBFeature("has_select_for_update")
class AuthConcurrencyTests(TransactionTestCase):
    def race(self, action):
        ready = Barrier(2)

        def worker(number):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                try:
                    action(number)
                    return "ok"
                except (IntegrityError, AuthLimited):
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = [executor.submit(worker, number) for number in range(2)]
            return [task.result(timeout=30) for task in tasks]

    def test_simultaneous_signup_with_case_variant_username_has_one_winner(self):
        def action(number):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    "Penakar" if number else "PENAKAR", f"different{number}@example.com"
                )

        self.assertCountEqual(self.race(action), ["ok", "rejected"])
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_simultaneous_signup_with_case_variant_email_has_one_winner(self):
        def action(number):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    f"different{number}", "DINA@example.com" if number else "dina@example.com"
                )

        self.assertCountEqual(self.race(action), ["ok", "rejected"])
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_first_rate_bucket_creation_does_not_lose_increments(self):
        request = RequestFactory().post("/login/", REMOTE_ADDR="192.0.2.1")
        now = datetime(2026, 10, 5, 9, 1, tzinfo=UTC)
        self.assertEqual(
            self.race(lambda _: reserve_auth_attempt(request, "login", "same-identity", now=now)),
            ["ok", "ok"],
        )
        self.assertEqual(list(AuthRateBucket.objects.values_list("attempts", flat=True)), [2, 2])

    def test_parallel_requests_cannot_skip_last_identity_slot(self):
        request = RequestFactory().post("/login/", REMOTE_ADDR="192.0.2.1")
        now = datetime(2026, 10, 5, 9, 1, tzinfo=UTC)
        for _ in range(9):
            reserve_auth_attempt(request, "login", "same-identity", now=now)
        self.assertCountEqual(
            self.race(lambda _: reserve_auth_attempt(request, "login", "same-identity", now=now)),
            ["ok", "rejected"],
        )
        self.assertEqual(list(AuthRateBucket.objects.values_list("attempts", flat=True)), [10, 10])
