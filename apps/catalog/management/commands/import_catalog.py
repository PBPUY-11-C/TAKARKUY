"""Controlled fixture refresh using stable primary keys."""

import json
from pathlib import Path

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = "Update catalog rows from a fixture and optionally deactivate missing recipes."

    def add_arguments(self, parser):
        parser.add_argument("fixture", type=Path)
        parser.add_argument("--deactivate-missing-recipes", action="store_true")
        parser.add_argument(
            "--sync-generated-relations",
            action="store_true",
            help="Remove obsolete generated ingredient/tag links on imported catalog recipes only; preserve user-source rows.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = options["fixture"]
        if not path.is_file():
            raise CommandError(f"Fixture tidak ditemukan: {path}")
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Fixture tidak dapat dibaca: {exc}") from exc
        if not isinstance(records, list):
            raise CommandError("Fixture harus berupa daftar JSON.")
        allowed = {
            "catalog.ingredient",
            "catalog.ingredientprice",
            "catalog.ingredientshelflife",
            "catalog.recipe",
            "catalog.recipeingredient",
            "catalog.recipetag",
            "catalog.ingredientalias",
            "catalog.unitconversion",
        }
        # Reject conflicting duplicates BEFORE any database write. Identical
        # repeated records are harmless and processed once (idempotent import).
        unique = {}
        for item in records:
            if (
                not isinstance(item, dict)
                or item.get("model") not in allowed
                or not item.get("pk")
                or not isinstance(item.get("fields"), dict)
            ):
                raise CommandError(
                    "Record fixture harus memiliki model katalog, pk, dan fields yang valid."
                )
            key = (item["model"], str(item["pk"]))
            if key in unique and unique[key] != item:
                raise CommandError(f"ID duplikat dengan data berbeda: {key[0]} / {key[1]}")
            unique.setdefault(key, item)
        records = list(unique.values())
        # SQLite does not enforce varchar lengths; reject incompatible records
        # before writing so local imports behave consistently with PostgreSQL.
        for item in records:
            model = apps.get_model(item["model"])
            for name, value in item["fields"].items():
                try:
                    field = model._meta.get_field(name)
                except FieldDoesNotExist as exc:
                    raise CommandError(f"Field tidak dikenal: {item['model']}.{name}") from exc
                if isinstance(value, str) and field.max_length and len(value) > field.max_length:
                    raise CommandError(
                        f"Field terlalu panjang: {item['model']} / {item['pk']} / "
                        f"{name} (maksimal {field.max_length} karakter)."
                    )
        seen_recipes, promoted_recipes = set(), set()
        for item in records:
            label = item.get("model")
            if label not in allowed:
                raise CommandError(f"Model tidak dikenal: {label}")
            model = apps.get_model(label)
            values = item["fields"].copy()
            for key in ("ingredient", "recipe"):
                if key in values:
                    values[key + "_id"] = values.pop(key)
            model.objects.update_or_create(pk=item["pk"], defaults=values)
            if label == "catalog.recipe":
                seen_recipes.add(item["pk"])
                if item["fields"].get("is_plannable") is True:
                    promoted_recipes.add(item["pk"])
        # Remove ONLY obsolete discovery badges on recipes just promoted by this
        # fixture. Preserve user tags, unrelated recipes and historical plans.
        tag_model = apps.get_model("catalog.recipetag")
        generated = (
            Q(source__startswith="TAKARKUY")
            | Q(source__startswith="TheMealDB API")
            | Q(source__startswith="Kaggle")
        )
        discovery_tags = tag_model.objects.filter(
            generated | Q(source=""),
            recipe_id__in=promoted_recipes,
        )
        discovery_tags.filter(tag="kandidat_belum_dikurasi").delete()
        discovery_tags.filter(tag__startswith="slot_saran_").delete()
        if options["sync_generated_relations"]:
            for label in ("catalog.recipeingredient", "catalog.recipetag"):
                desired = {item["pk"] for item in records if item["model"] == label}
                apps.get_model(label).objects.filter(generated, recipe_id__in=seen_recipes).exclude(
                    pk__in=desired
                ).delete()
        if options["deactivate_missing_recipes"]:
            apps.get_model("catalog.recipe").objects.exclude(pk__in=seen_recipes).update(
                is_active=False
            )
        self.stdout.write(self.style.SUCCESS(f"{len(records)} baris fixture diproses."))
