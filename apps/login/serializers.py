from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import FoodPreference


class FoodPreferenceSerializer(serializers.ModelSerializer):
    """Preferensi makan tersimpan; bahan dihindari dikirim sebagai kode beserta namanya."""

    avoided_ingredients = serializers.SerializerMethodField()

    class Meta:
        model = FoodPreference
        fields = ["targets", "meal_types", "servings", "allergens", "avoided_ingredients", "halal_only"]

    def get_avoided_ingredients(self, preference):
        """Daftar {code, name} bahan yang dihindari, urut nama."""
        return [
            {"code": code, "name": name}
            for code, name in preference.avoided_ingredients.order_by("name").values_list(
                "ingredient_code", "name"
            )
        ]


class ProfileSerializer(serializers.ModelSerializer):
    """Detail akun untuk halaman profil: nama, username, email, avatar, version, dan preferensi makan."""

    full_name = serializers.SerializerMethodField()
    avatar = serializers.CharField(source="userprofile.avatar")
    version = serializers.IntegerField(source="userprofile.version")
    preferences = FoodPreferenceSerializer(source="foodpreference")

    class Meta:
        model = get_user_model()
        fields = ["username", "full_name", "email", "avatar", "version", "preferences"]

    def get_full_name(self, user):
        """Nama lengkap, atau username bila nama belum diisi (sama seperti form profil web)."""
        return user.get_full_name() or user.username
