"""Continuously retry and audit community photo storage in a deployment worker."""

import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("apps.recipe_book.operations")


class Command(BaseCommand):
    help = "Run scheduled cleanup and audit jobs for community recipe photos."

    def add_arguments(self, parser):
        parser.add_argument("--cleanup-seconds", type=int, default=900)
        parser.add_argument("--audit-seconds", type=int, default=3600)
        parser.add_argument("--once", action="store_true", help="Run both jobs once and exit.")

    def handle(self, *args, **options):
        cleanup_seconds = options["cleanup_seconds"]
        audit_seconds = options["audit_seconds"]
        if cleanup_seconds < 1 or audit_seconds < 1:
            raise CommandError("Intervals must be positive numbers of seconds.")

        last_cleanup = 0.0
        last_audit = 0.0
        run_once = options["once"]
        while True:
            now = time.monotonic()
            failed = False
            if run_once or now - last_cleanup >= cleanup_seconds:
                failed |= not self._run_job("cleanup", "cleanup_recipe_review_photos")
                last_cleanup = time.monotonic()
            if run_once or now - last_audit >= audit_seconds:
                failed |= not self._run_job(
                    "audit",
                    "audit_recipe_review_photos",
                    fail_on_issues=True,
                )
                last_audit = time.monotonic()
            if run_once:
                if failed:
                    raise CommandError("At least one recipe photo operation failed; inspect worker logs.")
                return
            time.sleep(min(30, cleanup_seconds, audit_seconds))

    @staticmethod
    def _run_job(label, command, **options):
        try:
            call_command(command, **options)
        except Exception:
            logger.exception("Recipe photo %s operation failed", label)
            return False
        else:
            logger.info("Recipe photo %s operation finished", label)
            return True
