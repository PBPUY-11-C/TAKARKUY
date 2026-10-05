from django.core.management.base import BaseCommand

from apps.budget_planner.services import cleanup_previews


class Command(BaseCommand):
    help = "Delete only expired or used meal-plan previews, leaving plans intact."

    def handle(self, *args, **options):
        deleted = cleanup_previews()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} expired/used previews."))
