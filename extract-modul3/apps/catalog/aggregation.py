"""Derived allergen index. Bulk writers must rebuild explicitly before commit."""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction

from apps.accounts.choices import ALLERGEN_KEYS

from .models import Recipe, RecipeAllergen

_suspended = ContextVar("catalog_aggregation_suspended", default=False)


@contextmanager
def suspend_aggregation():
    token = _suspended.set(True)
    try:
        yield
    finally:
        _suspended.reset(token)


def expected_allergens(recipe):
    links = list(recipe.recipeingredient_set.all())
    reviewed = bool(links) and not any(
        tag.tag == "bumbu_minor_tidak_dihitung" for tag in recipe.recipetag_set.all()
    )
    groups = set()
    for link in links:
        ingredient = link.ingredient
        values = ingredient.allergens
        valid = isinstance(values, list) and all(
            isinstance(value, str) and value in ALLERGEN_KEYS for value in values
        )
        reviewed = reviewed and ingredient.allergen_status == "reviewed" and valid
        if valid:
            groups.update(values)
    return bool(reviewed), groups


@transaction.atomic
def rebuild_allergens(codes=None):
    query = Recipe.objects.order_by("pk")
    if codes is not None:
        query = query.filter(pk__in=codes)
    # Serializes index refreshes for the same recipe, including Admin edits.
    recipes = list(
        query.select_for_update().prefetch_related(
            "recipeingredient_set__ingredient", "recipetag_set"
        )
    )
    rows = []
    for recipe in recipes:
        recipe.allergen_reviewed, groups = expected_allergens(recipe)
        rows.extend(RecipeAllergen(recipe=recipe, group=value) for value in sorted(groups))
    RecipeAllergen.objects.filter(recipe_id__in=[r.pk for r in recipes]).delete()
    RecipeAllergen.objects.bulk_create(rows, batch_size=500)
    Recipe.objects.bulk_update(recipes, ["allergen_reviewed"], batch_size=500)


def changed(sender, instance, raw=False, **kwargs):
    if raw or _suspended.get():
        return
    if sender._meta.model_name == "ingredient":
        codes = instance.recipeingredient_set.values_list("recipe_id", flat=True)
    elif sender._meta.model_name == "recipe":
        codes = [instance.pk]
    else:
        codes = [instance.recipe_id]
    rebuild_allergens(codes)
