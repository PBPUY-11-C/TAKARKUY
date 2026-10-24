"""Report missing, orphaned, and queued recipe review photo files."""

import logging
from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.recipe_book.models import RecipePhotoCleanup, RecipeReview

logger = logging.getLogger(__name__)


def _stored_review_photos(storage, directory="recipe-reviews"):
    """Yield names recursively; return None when the backend cannot list files."""
    try:
        directories, files = storage.listdir(directory)
    except FileNotFoundError:
        return set()
    except Exception as exc:
        logger.warning(
            "Recipe photo storage listing unavailable directory=%s error=%s",
            directory,
            type(exc).__name__,
        )
        return None
    names = {f"{directory}/{name}" for name in files}
    for child in directories:
        nested = _stored_review_photos(storage, f"{directory}/{child}")
        if nested is None:
            return None
        names.update(nested)
    return names


class Command(BaseCommand):
    help = "Report missing and orphaned community review photos and pending deletions."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-issues", action="store_true")
        parser.add_argument("--stale-minutes", type=int, default=30)

    def handle(self, *args, **options):
        if options["stale_minutes"] < 0:
            raise CommandError("--stale-minutes tidak boleh negatif.")
        referenced = set(
            RecipeReview.objects.exclude(photo="").values_list("photo", flat=True)
        )
        missing = []
        check_errors = 0
        for review in RecipeReview.objects.exclude(photo="").only("pk", "photo"):
            try:
                if not default_storage.exists(review.photo.name):
                    missing.append(review.pk)
            except Exception as exc:
                check_errors += 1
                logger.exception(
                    "Could not check recipe review photo review_id=%s error=%s",
                    review.pk,
                    type(exc).__name__,
                )
                missing.append(review.pk)

        pending = RecipePhotoCleanup.objects.order_by("created_at")
        queued_names = set(pending.values_list("storage_name", flat=True))
        oldest = pending.first()
        oldest_minutes = (
            max(0, int((timezone.now() - oldest.created_at).total_seconds() // 60))
            if oldest
            else 0
        )
        stale_pending = bool(oldest and oldest_minutes >= options["stale_minutes"])
        stored = _stored_review_photos(default_storage)
        orphan_names = (
            stored - referenced - queued_names if stored is not None else None
        )

        report = (
            f"Referenced={len(referenced)}; missing={len(missing)}; storage_check_errors={check_errors}; "
            f"cleanup_pending={pending.count()}; oldest_pending_minutes={oldest_minutes}; "
            f"orphaned={len(orphan_names) if orphan_names is not None else 'unsupported'}"
        )
        self.stdout.write(report)
        if missing or check_errors or (orphan_names and len(orphan_names)) or stale_pending:
            logger.warning("Recipe review photo audit found issues: %s", report)
        elif stored is None:
            logger.info("Recipe photo storage does not support listing; orphan scan skipped.")
        else:
            logger.info("Recipe review photo audit passed: %s", report)

        has_issues = bool(
            missing or check_errors or orphan_names or stale_pending
        )
        if options["fail_on_issues"] and has_issues:
            raise CommandError(report)
