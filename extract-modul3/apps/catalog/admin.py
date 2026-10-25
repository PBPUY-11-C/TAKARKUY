from django.contrib import admin

from .models import Ingredient, Recipe, RecipeIngredient, RecipeTag


class IngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0


class TagInline(admin.TabularInline):
    model = RecipeTag
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("name", "meal_type", "instruction_status", "allergen_reviewed", "is_active")
    list_filter = ("instruction_status", "allergen_reviewed", "is_active")
    search_fields = ("name", "recipe_code")
    readonly_fields = ("allergen_reviewed",)
    inlines = (IngredientInline, TagInline)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "allergen_status")
    search_fields = ("name", "ingredient_code")
