"""Deployment-wide maintenance gate, before body parsing and application views."""

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import Resolver404, resolve, reverse
from django.utils.cache import patch_cache_control, patch_vary_headers

from .rate_limits import AuthLimited, reserve_auth_attempt


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
        try:
            name = resolve(request.path_info).url_name or ""
        except Resolver404:
            name = ""
        return (
            name.startswith(("modul1-", "modul2-", "modul4-", "modul5-"))
            or request.content_type == "application/json"
            or (request.accepts("application/json") and not request.accepts("text/html"))
        )


class AuthRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST":
            return None
        action = request.resolver_match.url_name
        if action == "password-change" and request.user.is_authenticated:
            action = "password"
            identity = f"account:{request.user.pk}"
        elif action in {"login", "signup"}:
            identity = request.POST.get("username" if action == "login" else "email", "")
        else:
            return None
        try:
            reserve_auth_attempt(request, action, identity)
        except AuthLimited as error:
            response = render(
                request, "login/rate_limited.html", {"error": str(error)}, status=429
            )
            response["Retry-After"] = str(error.retry_after)
            patch_cache_control(response, private=True, no_store=True)
            return response
        return None
