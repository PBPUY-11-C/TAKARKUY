from django.conf import settings
from django.db import models

from .avatars import AVATAR_CHOICES, AVATAR_KEYS


def default_targets():
    return ["seimbang"]


def default_meals():
    return ["sarapan", "makan_siang", "makan_malam"]


def default_tracked_staples():
    return ["cooking_oil"]


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.PositiveIntegerField(default=1)
    avatar = models.CharField(max_length=16, choices=AVATAR_CHOICES, default="initials")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(avatar__in=AVATAR_KEYS), name="accounts_avatar_valid")
        ]


class FoodPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    targets = models.JSONField(default=default_targets)
    meal_types = models.JSONField(default=default_meals)
    servings = models.PositiveSmallIntegerField(default=2)
    allergens = models.JSONField(default=list)
    tracked_staples = models.JSONField(default=default_tracked_staples)
    avoided_ingredients = models.ManyToManyField("catalog.Ingredient", blank=True)
    halal_only = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(servings__gte=1, servings__lte=10), name="preference_servings_valid"
            )
        ]


class AuthRateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
