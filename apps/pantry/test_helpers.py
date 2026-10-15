from decimal import Decimal

from django.contrib.auth import get_user_model

from .services import eligible_stock


def authenticate(client, username="pantry-test"):
    user = get_user_model().objects.create_user(username=username)
    client.force_login(user)
    return user


def available_grams(user, *, allow_unknown_expiry=False):
    """Grams per ingredient of stock the app treats as usable (test convenience)."""
    totals = {}
    for batch in eligible_stock(user, allow_unknown_expiry=allow_unknown_expiry):
        totals[batch.ingredient_id] = (
            totals.get(batch.ingredient_id, Decimal(0)) + batch.quantity * batch.grams_per_unit
        )
    return totals
