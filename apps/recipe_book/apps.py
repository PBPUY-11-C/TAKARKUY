from django.apps import AppConfig


class RecipeBookConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recipe_book"

    def ready(self):
        from . import signals  # noqa: F401
