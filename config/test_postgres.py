"""Isolated PostgreSQL test settings; never reads PWS DB_* credentials.

Use only with `manage.py test --settings=config.test_postgres --noinput`.
The runner creates/drops TEST.NAME, not the development/production database.
"""

import os

# Set before importing the base settings: dotenv does not override this value.
# This test-only module must never activate the production database branch.
os.environ["PRODUCTION"] = "false"

from .settings import *  # noqa: F403

DEBUG = True
PRODUCTION = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
test_name = os.getenv("TEST_PG_DATABASE", "test_takarkuy_planner")
test_host = os.getenv("TEST_PG_HOST", "127.0.0.1")
if not test_name.startswith("test_takarkuy_") or test_host not in {"localhost", "127.0.0.1", "::1"}:
    raise ValueError("Tes PostgreSQL hanya boleh memakai database test_takarkuy_* di loopback.")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": os.getenv("TEST_PG_USER", "postgres"),
        "PASSWORD": os.getenv("TEST_PG_PASSWORD", ""),
        "HOST": test_host,
        "PORT": os.getenv("TEST_PG_PORT", "55432"),
        "OPTIONS": {
            "options": "-c search_path=public -c lock_timeout=10000 -c statement_timeout=60000"
        },
        "TEST": {"NAME": test_name},
    }
}
