"""Conservative ingredient-based screening, not an allergen-free guarantee."""

from apps.accounts.choices import ALLERGEN_KEYS


def recipe_allowed(recipe, links, allergens):
    groups = set(allergens)
    if not groups:
        return True
    if not groups <= ALLERGEN_KEYS:
        return False
    tags = {tag.tag for tag in recipe.recipetag_set.all()}
    if "bumbu_minor_tidak_dihitung" in tags:
        return False
    if not links:
        return False
    for link in links:
        ingredient = link.ingredient
        if ingredient.allergen_status != "reviewed" or not isinstance(ingredient.allergens, list):
            return False
        values = ingredient.allergens
        if any(not isinstance(value, str) or value not in ALLERGEN_KEYS for value in values):
            return False
        if groups.intersection(values):
            return False
    return True


def unsafe_schedule(schedule, allergens):
    from .models import Recipe

    if not allergens:
        return False
    codes = {code for row in schedule for code in row.values()}
    recipes = list(
        Recipe.objects.filter(pk__in=codes).prefetch_related(
            "recipeingredient_set__ingredient", "recipetag_set"
        )
    )
    return len(recipes) != len(codes) or any(
        not recipe_allowed(recipe, list(recipe.recipeingredient_set.all()), allergens)
        for recipe in recipes
    )
