from .choices import ALLERGEN_KEYS
from .models import FoodPreference, UserProfile


def profile_for(user):
    return UserProfile.objects.get_or_create(user=user)[0]


def preferences_for(user):
    return FoodPreference.objects.get_or_create(user=user)[0]


def effective_preferences(user, *inputs):
    """Current halal policy and the union of saved/current allergies, from the account."""
    return {
        "allergens": effective_allergens(user, *inputs),
        "halal_only": preferences_for(user).halal_only,
    }


def non_halal_schedule(schedule):
    from apps.catalog.models import Recipe

    codes = {code for day in schedule for code in day.values()}
    halal = set(
        Recipe.objects.filter(pk__in=codes, recipetag__tag="halal").values_list("pk", flat=True)
    )
    return bool(codes - halal)


def planner_defaults(user):
    profile = preferences_for(user)
    return {
        "targets": profile.targets,
        "meal_types": profile.meal_types,
        "servings": profile.servings,
        "allergens": profile.allergens,
        "halal_only": profile.halal_only,
        # The planner field is comma-separated, so names keep their words but lose commas.
        "exclude_ingredients": ", ".join(
            name.replace(",", "")
            for name in profile.avoided_ingredients.values_list("name", flat=True)
        ),
    }


def effective_allergens(user, *inputs, preference=None):
    groups = set()
    saved_allergens = (preference or preferences_for(user)).allergens
    for values in [saved_allergens, *(data.get("allergens", []) for data in inputs)]:
        if not isinstance(values, list) or any(
            not isinstance(value, str) or value not in ALLERGEN_KEYS for value in values
        ):
            raise ValueError("Data alergi tidak valid. Periksa profil atau rencana.")
        groups.update(values)
    return sorted(groups)
