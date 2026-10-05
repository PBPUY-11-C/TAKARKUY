from .choices import ALLERGEN_KEYS
from .models import UserProfile


def profile_for(user):
    return UserProfile.objects.get_or_create(user=user)[0]


def planner_defaults(user):
    profile = profile_for(user)
    return {
        "targets": profile.targets,
        "meal_types": profile.meal_types,
        "servings": profile.servings,
        "allergens": profile.allergens,
        "exclude_ingredients": ", ".join(
            profile.avoided_ingredients.values_list("name", flat=True)
        ),
    }


def effective_allergens(user, *inputs):
    groups = set()
    for values in [profile_for(user).allergens, *(data.get("allergens", []) for data in inputs)]:
        if not isinstance(values, list) or any(
            not isinstance(value, str) or value not in ALLERGEN_KEYS for value in values
        ):
            raise ValueError("Data alergi tidak valid. Periksa profil atau rencana.")
        groups.update(values)
    return sorted(groups)
