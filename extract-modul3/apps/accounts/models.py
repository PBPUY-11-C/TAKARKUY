from django.conf import settings
from django.db import models


def default_targets():
    return ["seimbang"]


def default_meals():
    return ["sarapan", "makan_siang", "makan_malam"]


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    targets = models.JSONField(default=default_targets)
    meal_types = models.JSONField(default=default_meals)
    servings = models.PositiveSmallIntegerField(default=2)
    allergens = models.JSONField(default=list)
    avoided_ingredients = models.ManyToManyField("catalog.Ingredient", blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(servings__gte=1, servings__lte=10), name="profile_servings_valid"
            )
        ]


class AuthRateBucket(models.Model):
    # HMAC: no raw email, username, password or IP is stored in this table.
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
