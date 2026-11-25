"""Endpoint REST Modul 5 (Dashboard, Resep Saya, Market Locator) untuk aplikasi mobile; logikanya
memakai services, form, dan maps yang sama dengan web. Hanya GET dan POST karena pbp_django_auth."""

from functools import wraps

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .forms import MyRecipeForm
from .maps import MapLimited, lookup_places
from .models import MyRecipe
from .serializers import DashboardSerializer, MyRecipeSerializer
from .services import dashboard_data

NOT_FOUND_MESSAGE = "Resep tidak ditemukan."
TEXT_FIELDS = ("nama", "waktu_makan", "bahan", "langkah")


def home_errors(view):
    """Mengubah error layanan menjadi respons JSON {"error": ...} dengan status yang sesuai,
    dan menandai respons agar tidak di-cache karena berisi data pribadi."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        """Menjalankan view lalu memetakan 429/404/400."""
        try:
            response = view(request, *args, **kwargs)
        except MapLimited as exc:
            response = Response({"error": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            response["Retry-After"] = str(exc.retry_after)
        except Http404:
            response = Response({"error": NOT_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            response = Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


def json_object(request):
    """Body request harus objek JSON; list atau nilai lain ditolak 400."""
    if not isinstance(request.data, dict):
        raise ValueError("Format data tidak valid.")
    return request.data


def owned_recipe(request, pk):
    """Resep pribadi milik user yang login; milik user lain diperlakukan sebagai 404."""
    return get_object_or_404(MyRecipe, pk=pk, user=request.user)


def save_recipe(request, instance=None, created=False):
    """Memvalidasi body JSON dengan MyRecipeForm (sama dengan web) lalu menyimpan resep milik user."""
    data = json_object(request)
    # Form Django mengubah list/objek menjadi teks "[...]" tanpa error, jadi tipe dicek di sini.
    for field in TEXT_FIELDS:
        if field in data and not isinstance(data[field], str):
            raise ValueError("Isian resep harus berupa teks.")
    form = MyRecipeForm(data, instance=instance)
    if not form.is_valid():
        return Response(
            {"error": next(iter(form.errors.values()))[0], "fields": form.errors.get_json_data()},
            status=status.HTTP_400_BAD_REQUEST,
        )
    recipe = form.save(commit=False)
    recipe.user = request.user
    recipe.save()
    return Response(
        MyRecipeSerializer(recipe).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@home_errors
def dashboard_summary(request):
    """Ringkasan dashboard yang sama dengan halaman web: menu hari ini, jadwal 7 hari, stok
    prioritas, riwayat masak terakhir, dan jumlah resep pribadi."""
    data = {
        **dashboard_data(request.user),
        "my_recipe_count": MyRecipe.objects.filter(user=request.user).count(),
    }
    return Response(DashboardSerializer(data).data)


@api_view(["GET", "POST"])
@home_errors
def recipe_list(request):
    """GET: daftar resep pribadi milik user, terbaru diubah lebih dulu. POST: menambah resep baru."""
    if request.method == "GET":
        recipes = MyRecipe.objects.filter(user=request.user)
        return Response(MyRecipeSerializer(recipes, many=True).data)
    return save_recipe(request, created=True)


@api_view(["GET"])
@home_errors
def recipe_detail(request, pk):
    """Detail satu resep pribadi milik user."""
    return Response(MyRecipeSerializer(owned_recipe(request, pk)).data)


@api_view(["POST"])
@home_errors
def recipe_update(request, pk):
    """Mengganti seluruh isian resep pribadi milik user, dengan validasi yang sama dengan form web."""
    return save_recipe(request, owned_recipe(request, pk))


@api_view(["POST"])
@home_errors
def recipe_delete(request, pk):
    """Menghapus resep pribadi milik user; body tetap wajib JSON (boleh {}) agar form lintas situs ditolak."""
    json_object(request)
    owned_recipe(request, pk).delete()
    return Response({"deleted": True})


@api_view(["GET"])
@home_errors
def market_list(request):
    """Pasar terdekat dari ?lat=&lon= (atau ?region=) lewat lookup_places yang sama dengan web;
    kuota pencarian daring yang habis dibalas 429 dengan Retry-After."""
    return Response(lookup_places(request.user, request.query_params.dict()))
