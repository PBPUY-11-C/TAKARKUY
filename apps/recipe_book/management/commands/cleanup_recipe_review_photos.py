from django.core.management.base import BaseCommand

from apps.recipe_book.models import RecipePhotoCleanup
from apps.recipe_book.photo_storage import attempt_recipe_photo_cleanup


class Command(BaseCommand):
    help = "Retry deletion of recipe review photos that failed to remove from storage."

    def handle(self, *args, **options):
        cleanup_ids = list(RecipePhotoCleanup.objects.values_list("pk", flat=True))
        removed = sum(attempt_recipe_photo_cleanup(cleanup_id) for cleanup_id in cleanup_ids)
        remaining = RecipePhotoCleanup.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {removed} photo files; {remaining} cleanup job(s) remain for retry."
            )
        )
