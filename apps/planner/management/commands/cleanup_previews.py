from django.core.management.base import BaseCommand

from apps.planner.services import cleanup_previews


class Command(BaseCommand):
    """Perintah manage.py untuk membersihkan preview rencana yang kedaluwarsa atau sudah dipakai."""
    help = "Delete only expired or used meal-plan previews, leaving plans intact."

    def handle(self, *args, **options):
        """Menghapus preview lama lewat cleanup_previews dan mencetak jumlah yang terhapus."""
        deleted = cleanup_previews()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} expired/used previews."))
