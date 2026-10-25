"""Authentication gate for JSON endpoints; CSRF protection remains enabled."""

from functools import wraps
from urllib.parse import urlencode

from django.http import JsonResponse
from django.urls import reverse


def api_login_required(view):
    @wraps(view)
    def protected(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "error": "Masuk terlebih dahulu untuk menggunakan Smart Pantry.",
                    "login_url": reverse("login") + "?" + urlencode({"next": reverse("modul2")}),
                },
                status=401,
            )
        return view(request, *args, **kwargs)

    return protected
