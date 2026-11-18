"""Gerbang maintenance untuk seluruh deployment, dijalankan sebelum parsing body dan view aplikasi."""

import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import Resolver404, resolve, reverse
from django.utils.cache import patch_cache_control, patch_vary_headers

from .rate_limits import AuthLimited, reserve_auth_attempt

JSON_APPS = {"planner", "pantry", "recipe", "home"}
AUTH_ACTIONS = {
    "login:login": "login",
    "admin:login": "login",
    "login:register": "signup",
    "login:change_password": "password",
    "auth_api:login": "login",
    "auth_api:register": "signup",
    "auth_api:change_password": "password",
}


class MaintenanceMiddleware:
    """Saat MAINTENANCE_MODE aktif, tutup situs untuk semua kecuali halaman admin dan staf aktif."""

    def __init__(self, get_response):
        """Simpan handler berikutnya dalam rantai middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Loloskan admin dan staf (respons no-store); lainnya dapat 503 HTML/JSON + Retry-After 3600."""
        if not settings.MAINTENANCE_MODE:
            return self.get_response(request)

        admin_root = reverse("admin:index")
        if request.path_info == admin_root.rstrip("/") or request.path_info.startswith(admin_root):
            return self.get_response(request)

        user = request.user
        if user.is_authenticated and user.is_active and user.is_staff:
            response = self.get_response(request)
            patch_cache_control(response, private=True, no_store=True)
            patch_vary_headers(response, ("Cookie",))
            return response

        message = "TAKARKUY sedang dalam pengembangan. Silakan coba lagi nanti."
        if self.wants_json(request):
            response = JsonResponse(
                {"error": message, "code": "maintenance", "retry_after": 3600}, status=503
            )
        else:
            response = render(request, "maintenance.html", status=503)
        response["Retry-After"] = "3600"
        response["X-Frame-Options"] = "DENY"
        patch_cache_control(response, private=True, no_store=True)
        patch_vary_headers(response, ("Cookie", "Accept"))
        return response

    @staticmethod
    def wants_json(request):
        """True bila request ke endpoint API (app JSON selain view show_*), mengirim JSON,
        atau hanya menerima JSON; menentukan format halaman maintenance."""
        try:
            match = resolve(request.path_info)
        except Resolver404:
            match = None
        return (
            request.path_info.startswith("/api/")
            or (match is not None and match.namespace in JSON_APPS and not match.url_name.startswith("show_"))
            or request.content_type == "application/json"
            or (request.accepts("application/json") and not request.accepts("text/html"))
        )


class AuthRateLimitMiddleware:
    """Rate limit untuk POST login, daftar, dan ganti kata sandi, dicek sebelum view berjalan."""

    def __init__(self, get_response):
        """Simpan handler berikutnya dalam rantai middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Teruskan request apa adanya; pembatasan dilakukan di process_view."""
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Catat percobaan POST per akun/identitas dan per IP; balas 429 + Retry-After bila lewat batas."""
        if request.method != "POST":
            return None
        action = AUTH_ACTIONS.get(request.resolver_match.view_name)
        if action == "password" and request.user.is_authenticated:
            identity = f"account:{request.user.pk}"
        elif action in {"login", "signup"}:
            identity = self.auth_data(request).get("username" if action == "login" else "email", "")
        else:
            return None
        try:
            reserve_auth_attempt(request, action, identity)
        except AuthLimited as error:
            if MaintenanceMiddleware.wants_json(request):
                response = JsonResponse(
                    {"status": False, "message": str(error), "retry_after": error.retry_after},
                    status=429,
                )
            else:
                response = render(
                    request, "login/rate_limited.html", {"error": str(error)}, status=429
                )
            response["Retry-After"] = str(error.retry_after)
            patch_cache_control(response, private=True, no_store=True)
            return response
        return None

    @staticmethod
    def auth_data(request):
        """Data POST form, atau objek JSON untuk API mobile; tanpa ini semua pendaftaran JSON berbagi
        satu kuota identitas kosong."""
        if request.content_type != "application/json":
            return request.POST
        try:
            data = json.loads(request.body)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
