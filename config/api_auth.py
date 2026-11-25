"""Autentikasi API untuk aplikasi mobile (Flutter + pbp_django_auth)."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication


class MobileSessionAuthentication(SessionAuthentication):
    """Login lewat cookie session yang sama dengan web, tanpa token CSRF karena pbp_django_auth tidak
    mengirimnya. Tetap aman dari CSRF: API hanya menerima body JSON (form lintas situs ditolak 415,
    fetch JSON lintas situs butuh izin CORS) dan cookie session memakai SameSite=Lax."""

    def enforce_csrf(self, request):
        """Lewati pemeriksaan token CSRF; perlindungannya dari aturan JSON-only dan SameSite."""
        return None


class MobileSessionScheme(OpenApiAuthenticationExtension):
    """Menjelaskan di dokumentasi Swagger bahwa API memakai cookie `sessionid` hasil login."""

    target_class = "config.api_auth.MobileSessionAuthentication"
    name = "sessionCookie"

    def get_security_definition(self, auto_schema):
        """Definisi keamanan OpenAPI: kunci API berupa cookie sessionid."""
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}
