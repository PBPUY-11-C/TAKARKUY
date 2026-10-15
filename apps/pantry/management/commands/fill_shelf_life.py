"""Give old pantry items with an unknown expiry a date from a reference or an AI estimate."""

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import IngredientShelfLife
from apps.pantry.models import PantryItem, ShelfLifeEstimate
from apps.pantry.shelf_life_ai import estimate_shelf_life
from apps.pantry.storage import DEFAULT_LOCATION, expiry_estimate, shelf_key, storage_options


class Command(BaseCommand):
    help = (
        "Isi tanggal kedaluwarsa stok lama yang belum diketahui (acuan resmi, lalu perkiraan AI)."
    )

    def handle(self, *args, **options):
        items = list(
            PantryItem.objects.filter(
                archived_at__isnull=True, quantity__gt=0, estimated_expires_on__isnull=True
            ).select_related("user")
        )
        by_user = {}
        for item in items:
            if item.user_id and not storage_options(item.ingredient_id, item.name):
                key = shelf_key(item.ingredient_id, item.name)
                by_user.setdefault(item.user, []).append((key, item.name, item.ingredient_id))
        # Each owner's own daily AI quota pays for their items.
        for user, entries in by_user.items():
            estimate_shelf_life(user, entries)
        filled = 0
        for item in items:
            start = item.starting_on or timezone.localdate(item.added_at)
            location = item.location or DEFAULT_LOCATION
            estimate = expiry_estimate(
                storage_options(item.ingredient_id, item.name), location, start
            )
            if not estimate["estimated_expires_on"]:
                continue
            # Version bump makes any open edit form reload instead of overwriting this date.
            filled += PantryItem.objects.filter(
                pk=item.pk, version=item.version, estimated_expires_on__isnull=True
            ).update(
                estimated_expires_on=estimate["estimated_expires_on"],
                shelf_life_days=estimate["shelf_life_days"],
                expiry_source="estimate",
                starting_on=start,
                version=F("version") + 1,
            )
        self.stdout.write(f"{filled} stok mendapat perkiraan tanggal.")
        self.stdout.write(f"{self.refresh_ai_dates()} tanggal perkiraan AI diganti acuan resmi.")

    def refresh_ai_dates(self):
        """Items dated from an AI guess move to an official reference added later."""
        official = set(IngredientShelfLife.objects.values_list("ingredient_id", flat=True))
        guessed = set(ShelfLifeEstimate.objects.values_list("pk", flat=True))
        refreshed = 0
        for item in PantryItem.objects.filter(
            archived_at__isnull=True,
            quantity__gt=0,
            expiry_source="estimate",
            ingredient_id__in=official,
        ):
            if shelf_key(item.ingredient_id, item.name) not in guessed:
                continue  # dated from the official reference already
            start = item.starting_on or timezone.localdate(item.added_at)
            estimate = expiry_estimate(
                storage_options(item.ingredient_id, item.name),
                item.location or DEFAULT_LOCATION,
                start,
            )
            if not estimate["estimated_expires_on"]:
                continue
            refreshed += PantryItem.objects.filter(pk=item.pk, version=item.version).update(
                estimated_expires_on=estimate["estimated_expires_on"],
                shelf_life_days=estimate["shelf_life_days"],
                starting_on=start,
                version=F("version") + 1,
            )
        return refreshed
