import logging

from django.core.management.base import BaseCommand

from apps.recipe.models import RecipePhotoCleanup
from apps.recipe.photo_storage import attempt_recipe_photo_cleanup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Retry deletion of recipe review photos that failed to remove from storage."

    def handle(self, *args, **options):
        cleanup_ids = list(RecipePhotoCleanup.objects.values_list("pk", flat=True))
        removed = sum(attempt_recipe_photo_cleanup(cleanup_id) for cleanup_id in cleanup_ids)
        remaining = RecipePhotoCleanup.objects.count()
        oldest = RecipePhotoCleanup.objects.order_by("created_at").first()
        if remaining:
            logger.warning(
                "Recipe photo cleanup backlog remains removed=%d pending=%d oldest_created_at=%s",
                removed,
                remaining,
                oldest.created_at.isoformat() if oldest else "unknown",
            )
            style = self.style.WARNING
        else:
            logger.info("Recipe photo cleanup completed removed=%d pending=0", removed)
            style = self.style.SUCCESS
        self.stdout.write(style(f"Removed {removed} photo files; {remaining} cleanup job(s) remain for retry."))
