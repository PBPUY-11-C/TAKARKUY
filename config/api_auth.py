"""Autentikasi API untuk aplikasi mobile (Flutter + pbp_django_auth)."""

from rest_framework.authentication import SessionAuthentication


class MobileSessionAuthentication(SessionAuthentication):
    """Login lewat cookie session yang sama dengan web, tanpa token CSRF karena pbp_django_auth tidak
    mengirimnya. Tetap aman dari CSRF: API hanya menerima body JSON (form lintas situs ditolak 415,
    fetch JSON lintas situs butuh izin CORS) dan cookie session memakai SameSite=Lax."""

    def enforce_csrf(self, request):
        """Lewati pemeriksaan token CSRF; perlindungannya dari aturan JSON-only dan SameSite."""
        return None
