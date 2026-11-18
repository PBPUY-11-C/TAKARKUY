from django.apps import AppConfig


class RecipeBookConfig(AppConfig):
    """Konfigurasi app resep; label lama recipe_book dipertahankan agar tabel database tetap cocok."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recipe"
    label = "recipe_book"  # database label from before the rename

    def ready(self):
        """Mengimpor modul signals agar receiver pembersihan foto ulasan terdaftar."""
        from . import signals  # noqa: F401
