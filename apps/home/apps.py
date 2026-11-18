from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Konfigurasi app beranda; label lama "dashboard" dipertahankan agar tabel database tetap sama."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.home"
    label = "dashboard"  # database label from before the rename
