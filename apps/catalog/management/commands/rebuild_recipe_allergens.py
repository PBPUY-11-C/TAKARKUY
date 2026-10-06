from django.core.management.base import BaseCommand, CommandError

from apps.catalog.aggregation import expected_allergens, rebuild_allergens
from apps.catalog.models import Recipe


class Command(BaseCommand):
    help = "Rebuild derived recipe allergens, or --check for drift after bulk writes/loaddata."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        if not options["check"]:
            rebuild_allergens()
        for recipe in Recipe.objects.prefetch_related(
            "recipeingredient_set__ingredient", "recipetag_set", "allergen_groups"
        ):
            reviewed, groups = expected_allergens(recipe)
            if reviewed != recipe.allergen_reviewed or groups != {
                row.group for row in recipe.allergen_groups.all()
            }:
                raise CommandError(f"Agregasi tidak cocok: {recipe.pk}")
        self.stdout.write(self.style.SUCCESS("Agregasi alergen konsisten."))
