"""Autentikasi token untuk API aplikasi mobile."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated


class MobileTokenAuthentication(TokenAuthentication):
    """Token DRF stateless dengan respons unauthenticated 403 seragam."""

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed as exc:
            raise NotAuthenticated("Token tidak valid atau sudah dicabut.", code="not_authenticated") from exc

    def authenticate_header(self, request):
        return None


class MobileTokenScheme(OpenApiAuthenticationExtension):
    """Skema header token untuk dokumentasi OpenAPI."""

    target_class = "config.api_auth.MobileTokenAuthentication"
    name = "mobileToken"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "Authorization", "description": "Token <token>"}
