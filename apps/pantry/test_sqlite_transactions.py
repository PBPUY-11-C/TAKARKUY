"""Two real file-backed Django SQLite writers; not a claim of row locks."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.test import SimpleTestCase


class SQLiteTransactionTests(SimpleTestCase):
    def test_immediate_transaction_serializes_read_then_write(self):
        from config.settings import DATABASES

        self.assertEqual(DATABASES["default"]["OPTIONS"]["transaction_mode"], "IMMEDIATE")
        config = deepcopy(connections["default"].settings_dict)
        config.update(
            ENGINE="django.db.backends.sqlite3",
            OPTIONS=DATABASES["default"]["OPTIONS"],
            AUTOCOMMIT=True,
        )
        acquired, attempting = Event(), Event()
        with TemporaryDirectory(prefix="takarkuy-sqlite-concurrency-") as directory:
            config["NAME"] = str(Path(directory) / "isolated.sqlite3")
            initial = DatabaseWrapper(config, alias="isolated")
            try:
                with initial.cursor() as cursor:
                    cursor.execute("CREATE TABLE stock (quantity integer CHECK (quantity >= 0))")
                    cursor.execute("INSERT INTO stock VALUES (100)")
            finally:
                initial.close()

            def worker(first):
                connection = DatabaseWrapper(deepcopy(config), alias="isolated")
                try:
                    connection.ensure_connection()
                    if not first:
                        if not acquired.wait(5):
                            raise AssertionError("First writer never acquired transaction")
                        attempting.set()
                    connection.set_autocommit(
                        False, force_begin_transaction_with_broken_autocommit=True
                    )
                    if first:
                        acquired.set()
                        if not attempting.wait(5):
                            raise AssertionError("Second writer never attempted transaction")
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT quantity FROM stock")
                        quantity = cursor.fetchone()[0]
                        if quantity >= 80:
                            cursor.execute("UPDATE stock SET quantity = quantity - 80")
                    connection.commit()
                    return quantity
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                one, two = pool.submit(worker, True), pool.submit(worker, False)
                self.assertEqual(one.result(timeout=10), 100)
                self.assertEqual(two.result(timeout=10), 20)
            final = DatabaseWrapper(config, alias="isolated")
            try:
                with final.cursor() as cursor:
                    cursor.execute("SELECT quantity FROM stock")
                    self.assertEqual(cursor.fetchone()[0], 20)
            finally:
                final.close()
