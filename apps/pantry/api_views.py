"""Endpoint REST Modul 2 untuk aplikasi mobile; aksi tulis memakai view JSON web yang sama.
Hanya GET dan POST karena pbp_django_auth di Flutter hanya mendukung dua method itu."""

import inspect
from datetime import timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.cache import patch_cache_control
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import views
from .models import PantryItem
from .serializers import PantryItemDetailSerializer, PantryItemSerializer

NOT_FOUND_MESSAGE = "Stok tidak ditemukan."


def pantry_errors(view):
    """Menolak POST yang bukan JSON (415), mengubah 404/400 menjadi JSON {"error": ...},
    dan menandai respons agar tidak di-cache karena berisi data pribadi."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        """Menjalankan view setelah cek Content-Type lalu memetakan 404/400."""
        # Perlindungan CSRF API bergantung pada aturan JSON-only; view hapus web tidak mengeceknya.
        if request.method == "POST" and request._request.content_type != "application/json":
            response = Response(
                {"error": "Kirim data sebagai JSON."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )
        else:
            try:
                response = view(request, *args, **kwargs)
            except Http404:
                response = Response({"error": NOT_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND)
            except ValueError as exc:
                response = Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


def web(view):
    """View JSON web tanpa decorator login dan method-nya; DRF sudah mengautentikasi user dan
    membatasi method, jadi validasi, penguncian, versi, dan riwayat tetap satu sumber."""
    return inspect.unwrap(view)


@api_view(["GET", "POST"])
@pantry_errors
def item_list(request):
    """GET: stok aktif milik user, bisa difilter `expiry` (all, expired, next7, unknown) seperti web.
    POST: menambah 1–30 bahan dengan body yang sama seperti web (`source`, `operation_key`, `items`)."""
    if request.method == "POST":
        return web(views.save_pantry_items)(request._request)

    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
    filters = {
        "all": {},
        "expired": {"estimated_expires_on__lt": today},
        "next7": {"estimated_expires_on__range": (today, today + timedelta(days=7))},
        "unknown": {"estimated_expires_on__isnull": True},
    }
    expiry = request.query_params.get("expiry", "all")
    if expiry not in filters:
        raise ValueError("Filter kedaluwarsa harus all, expired, next7, atau unknown.")
    items = PantryItem.objects.filter(
        user=request.user, archived_at__isnull=True, quantity__gt=0, **filters[expiry]
    )
    return Response(PantryItemSerializer(items, many=True).data)


@api_view(["GET"])
@pantry_errors
def item_detail(request, item_id):
    """Detail satu bahan milik user beserta riwayat perubahannya, termasuk bahan yang sudah dibuang."""
    item = get_object_or_404(PantryItem, pk=item_id, user=request.user)
    return Response(PantryItemDetailSerializer(item).data)


@api_view(["POST"])
@pantry_errors
def item_update(request, item_id):
    """Mengubah detail bahan seperti PATCH di web; `version` dan `operation_key` wajib."""
    return web(views.update_pantry_details)(request._request, item_id)


@api_view(["POST"])
@pantry_errors
def item_delete(request, item_id):
    """Membuang bahan (jumlah 0 dan diarsipkan) seperti DELETE di web; `version` dan `operation_key` wajib."""
    return web(views.delete_pantry_item)(request._request, item_id)


@api_view(["GET"])
@pantry_errors
def recipe_ideas(request):
    """Resep yang bisa dimasak dari stok, sama dengan pintasan web; `servings` 1–10."""
    return web(views.pantry_recipe_matches)(request._request)
