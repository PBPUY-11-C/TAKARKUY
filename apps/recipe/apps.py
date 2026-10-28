from django.apps import AppConfig


class RecipeBookConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recipe"
    label = "recipe_book"  # database label from before the rename

    def ready(self):
        from . import signals  # noqa: F401
