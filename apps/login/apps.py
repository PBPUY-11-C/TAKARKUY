from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Konfigurasi app login; label "accounts" dipertahankan agar tabel dan migrasi lama tetap cocok."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.login"
    label = "accounts"  # database label from before the rename
