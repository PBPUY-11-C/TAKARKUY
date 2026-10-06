from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .aggregation import changed
        from .models import Ingredient, Recipe, RecipeIngredient, RecipeTag

        for model in (Ingredient, Recipe, RecipeIngredient, RecipeTag):
            post_save.connect(
                changed, sender=model, dispatch_uid=f"allergens_save_{model.__name__}"
            )
        for model in (RecipeIngredient, RecipeTag):
            post_delete.connect(
                changed, sender=model, dispatch_uid=f"allergens_delete_{model.__name__}"
            )
