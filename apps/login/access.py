"""Gerbang autentikasi untuk endpoint JSON; proteksi CSRF tetap aktif."""

from functools import wraps
from urllib.parse import urlencode

from django.http import JsonResponse
from django.urls import reverse


def api_login_required(view):
    """Decorator endpoint JSON: tamu dibalas 401 berisi pesan dan login_url, bukan redirect."""
    @wraps(view)
    def protected(request, *args, **kwargs):
        """Teruskan ke view bila sudah login; bila belum, kembalikan JSON 401 dengan next ke Pantry."""
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "error": "Masuk terlebih dahulu untuk menggunakan Smart Pantry.",
                    "login_url": reverse("login:login") + "?" + urlencode({"next": reverse("pantry:show_pantry")}),
                },
                status=401,
            )
        return view(request, *args, **kwargs)

    return protected
