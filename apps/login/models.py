from django.conf import settings
from django.db import models

from .avatars import AVATAR_CHOICES, AVATAR_KEYS


def default_targets():
    """Default target makan: hanya "seimbang"."""
    return ["seimbang"]


def default_meals():
    """Default waktu makan: sarapan, makan siang, dan makan malam."""
    return ["sarapan", "makan_siang", "makan_malam"]


def default_tracked_staples():
    """Default bahan pokok yang dilacak: minyak goreng."""
    return ["cooking_oil"]


class UserProfile(models.Model):
    """Profil akun: avatar dan nomor versi untuk mendeteksi penyimpanan bentrok dari tab lain."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.PositiveIntegerField(default=1)
    avatar = models.CharField(max_length=16, choices=AVATAR_CHOICES, default="initials")

    class Meta:
        """Constraint database: avatar wajib salah satu dari AVATAR_KEYS."""

        constraints = [
            models.CheckConstraint(condition=models.Q(avatar__in=AVATAR_KEYS), name="accounts_avatar_valid")
        ]


class FoodPreference(models.Model):
    """Preferensi makan tersimpan per akun, dipakai sebagai default planner dan filter alergi/halal."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    targets = models.JSONField(default=default_targets)
    meal_types = models.JSONField(default=default_meals)
    servings = models.PositiveSmallIntegerField(default=2)
    allergens = models.JSONField(default=list)
    tracked_staples = models.JSONField(default=default_tracked_staples)
    avoided_ingredients = models.ManyToManyField("catalog.Ingredient", blank=True)
    halal_only = models.BooleanField(default=True)

    class Meta:
        """Constraint database: jumlah porsi harus 1 sampai 10."""

        constraints = [
            models.CheckConstraint(
                condition=models.Q(servings__gte=1, servings__lte=10), name="preference_servings_valid"
            )
        ]


class AuthRateBucket(models.Model):
    """Penghitung percobaan auth per jendela waktu; key berupa HMAC agar identitas tak disimpan mentah."""

    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
