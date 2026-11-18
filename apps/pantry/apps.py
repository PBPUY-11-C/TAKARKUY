from django.apps import AppConfig


class PantryConfig(AppConfig):
    """Konfigurasi app Django pantry, memakai BigAutoField sebagai primary key default."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pantry"
