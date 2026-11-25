from rest_framework import serializers

from apps.catalog.models import Recipe

from .models import CookingHistory, RecipeFavorite


def photo_data(request, photo):
    """Foto resep (kurasi atau komunitas) beserta atribusinya, dengan URL absolut untuk aplikasi."""
    if not photo:
        return None
    return {
        "image_url": request.build_absolute_uri(photo["image_url"]),
        "creator": photo.get("creator", ""),
        "license_name": photo.get("license_name", ""),
        "license_url": photo.get("license_url", ""),
    }


class RecipeCardSerializer(serializers.ModelSerializer):
    """Kartu hasil pencarian resep: biaya untuk porsi profil, foto, status panduan, dan kecocokan stok.
    Nilai hitungan dikirim lewat context agar dihitung sekali per halaman."""

    guidance = serializers.SerializerMethodField()
    cost = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    stock_match = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ["recipe_code", "name", "meal_type", "guidance", "cost", "photo", "stock_match"]

    def get_guidance(self, recipe):
        """True bila panduan memasak resep layak ditampilkan."""
        return recipe.pk in self.context["guided"]

    def get_cost(self, recipe):
        """Estimasi belanja untuk porsi profil, atau None bila data harga tidak tersedia."""
        return self.context["costs"].get(recipe.pk)

    def get_photo(self, recipe):
        """Foto resep beserta atribusi, atau None."""
        return photo_data(self.context["request"], self.context["photos"].get(recipe.pk))

    def get_stock_match(self, recipe):
        """Hasil kecocokan stok pantry bila filter stok aktif, selain itu None."""
        return self.context["stock_rows"].get(recipe.pk)


class RecipeFavoriteSerializer(serializers.ModelSerializer):
    """Resep favorit milik user; `available` False bila resep kini tidak sesuai preferensi/alergi."""

    recipe_code = serializers.CharField(source="recipe_id")
    name = serializers.CharField(source="recipe.name")
    available = serializers.SerializerMethodField()

    class Meta:
        model = RecipeFavorite
        fields = ["recipe_code", "name", "available", "created_at"]

    def get_available(self, favorite):
        """Resep masih lolos aturan halal, alergi, dan pantangan user."""
        return favorite.recipe_id in self.context["available"]


class CookingHistorySerializer(serializers.ModelSerializer):
    """Satu catatan Sudah Masak: resep, porsi, waktu, stok pantry terpakai, dan bahan dari luar Pantry."""

    recipe_code = serializers.CharField(source="recipe_id", allow_null=True)
    used_ingredients = serializers.SerializerMethodField()
    external_ingredients = serializers.SerializerMethodField()

    class Meta:
        model = CookingHistory
        fields = [
            "id",
            "recipe_code",
            "recipe_name",
            "servings",
            "planned_meal",
            "cooked_at",
            "used_ingredients",
            "external_ingredients",
        ]

    def get_used_ingredients(self, entry):
        """Batch pantry yang dikurangi saat masak, sama dengan rincian riwayat di web."""
        return [
            {
                "name": move.snapshot.get("before", {}).get("name", ""),
                "unit": move.snapshot.get("before", {}).get("unit", ""),
                "grams": format(move.consumed_grams.normalize(), "f") if move.consumed_grams else "0",
                "quantity_before": format(move.quantity_before.normalize(), "f"),
                "quantity_after": format(move.quantity_after.normalize(), "f"),
            }
            for move in entry.operation.pantrymovement_set.all()
        ]

    def get_external_ingredients(self, entry):
        """Bahan yang dipakai dari luar Pantry, tersimpan di snapshot riwayat."""
        return entry.snapshot.get("external_ingredients", [])
