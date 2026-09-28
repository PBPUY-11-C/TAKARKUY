"""Controlled fixture refresh using stable primary keys."""
import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Update catalog rows from a fixture and optionally deactivate missing recipes.'

    def add_arguments(self, parser):
        parser.add_argument('fixture', type=Path)
        parser.add_argument('--deactivate-missing-recipes', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        path = options['fixture']
        if not path.is_file():
            raise CommandError(f'Fixture tidak ditemukan: {path}')
        try:
            records = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError(f'Fixture tidak dapat dibaca: {exc}') from exc
        if not isinstance(records, list):
            raise CommandError('Fixture harus berupa daftar JSON.')
        allowed = {
            'catalog.ingredient', 'catalog.ingredientprice', 'catalog.ingredientshelflife',
            'catalog.recipe', 'catalog.recipeingredient', 'catalog.recipetag',
            'catalog.ingredientalias', 'catalog.unitconversion',
        }
        seen_recipes = set()
        for item in records:
            label = item.get('model')
            if label not in allowed:
                raise CommandError(f'Model tidak dikenal: {label}')
            model = apps.get_model(label)
            values = item['fields'].copy()
            for key in ('ingredient', 'recipe'):
                if key in values:
                    values[key + '_id'] = values.pop(key)
            model.objects.update_or_create(pk=item['pk'], defaults=values)
            if label == 'catalog.recipe':
                seen_recipes.add(item['pk'])
        if options['deactivate_missing_recipes']:
            apps.get_model('catalog.recipe').objects.exclude(pk__in=seen_recipes).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f'{len(records)} baris fixture diproses.'))
