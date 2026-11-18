from django.contrib import admin

from .models import Ingredient, Recipe, RecipeIngredient, RecipeTag


class IngredientInline(admin.TabularInline):
    """Tabel inline bahan resep (RecipeIngredient) di halaman admin resep."""

    model = RecipeIngredient
    extra = 0


class TagInline(admin.TabularInline):
    """Tabel inline tag resep (RecipeTag) di halaman admin resep."""

    model = RecipeTag
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """Admin resep: status panduan dan alergen, plus ringkasan read-only takaran dan foto."""

    list_display = (
        "name",
        "meal_type",
        "instruction_status",
        "allergen_reviewed",
        "is_active",
    )
    list_filter = ("instruction_status", "allergen_reviewed", "is_active")
    search_fields = ("name", "recipe_code")
    readonly_fields = ("allergen_reviewed", "ingredient_quality", "photo_quality")
    inlines = (IngredientInline, TagInline)

    @admin.display(description="Kualitas takaran bahan")
    def ingredient_quality(self, obj):
        """Meringkas kelengkapan takaran: porsi dasar, takaran kosong/tanpa satuan, dan estimasi."""
        if obj is None:
            return "Simpan resep untuk melihat status takaran."
        links = list(obj.recipeingredient_set.all())
        if not links:
            return "Bahan belum tercatat"
        incomplete = sum(
            link.quantity is None or link.quantity <= 0 or not link.unit.strip()
            for link in links
        )
        estimated = sum(link.quantity_status == "estimated" for link in links)
        if not obj.base_servings:
            return f"{len(links)} bahan; porsi dasar belum tersedia"
        if incomplete:
            return f"{len(links)} bahan; {incomplete} takaran belum lengkap"
        if estimated:
            return f"{len(links)} bahan; {estimated} takaran estimasi"
        return f"{len(links)} bahan; takaran tercatat"

    @admin.display(description="Status foto")
    def photo_quality(self, obj):
        """Status foto resep: foto kurasi lebih dulu, lalu foto ulasan komunitas
        yang sudah diberi izin dan tidak disembunyikan."""
        if obj is None:
            return "Simpan resep untuk melihat status foto."
        from .recipe_images import recipe_image_index

        if obj.recipe_code in recipe_image_index():
            return "Foto kurasi tersedia"

        from apps.recipe.models import RecipeReview

        has_community_photo = RecipeReview.objects.filter(
            recipe=obj,
            photo__gt="",
            photo_is_hidden=False,
            is_hidden=False,
            photo_permission_granted=True,
            photo_consent_at__isnull=False,
        ).exists()
        return "Foto komunitas disetujui" if has_community_photo else "Foto belum tersedia"


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    """Admin bahan dengan kolom status alergen dan pencarian nama/kode."""

    list_display = ("name", "allergen_status")
    search_fields = ("name", "ingredient_code")
