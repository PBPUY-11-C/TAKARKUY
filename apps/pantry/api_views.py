"""Endpoint REST Modul 2 (Smart Pantry) untuk aplikasi mobile.

Logika simpan, ubah, dan buang stok memakai view web yang sama (idempotency key, version, riwayat
movement tetap berlaku). Bedanya hanya di pintu masuk: autentikasi session tanpa token CSRF
(lihat config/api_auth.py) dan hanya GET/POST karena pbp_django_auth di Flutter tidak mendukung
PATCH maupun DELETE."""

from datetime import timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.cache import patch_cache_control
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import views as web
from .models import PantryItem
from .storage import DEFAULT_LOCATION

EXPIRY_FILTERS = {"all", "expired", "soon", "unknown"}
SOON_DAYS = 7


def today():
    """Tanggal hari ini menurut WIB, acuan semua hitungan kedaluwarsa."""
    return timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))


class PantryItemSerializer(serializers.ModelSerializer):
    """Satu batch stok untuk Virtual Pantry; `version` wajib dikirim balik saat mengubah atau membuang."""

    quantity = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    ingredient_code = serializers.CharField(source="ingredient_id", default=None)
    days_remaining = serializers.SerializerMethodField()
    expiry_status = serializers.SerializerMethodField()

    class Meta:
        model = PantryItem
        fields = [
            "id",
            "name",
            "category",
            "quantity",
            "unit",
            "location",
            "ingredient_code",
            "source",
            "starting_on",
            "estimated_expires_on",
            "expiry_source",
            "days_remaining",
            "expiry_status",
            "version",
            "updated_at",
        ]

    def get_quantity(self, item):
        """Jumlah sebagai angka biasa agar mudah dibaca Dart (bukan string desimal 6 digit)."""
        return float(item.quantity)

    def get_location(self, item):
        """Lokasi simpan; item lama tanpa lokasi dianggap suhu ruang seperti di web."""
        return item.location or DEFAULT_LOCATION

    def get_days_remaining(self, item):
        """Sisa hari sampai tanggal kedaluwarsa (negatif bila lewat); None bila belum diketahui."""
        if not item.estimated_expires_on:
            return None
        return (item.estimated_expires_on - today()).days

    def get_expiry_status(self, item):
        """expired, soon (0–7 hari), ok, atau unknown; dasar filter di layar Pantry."""
        days = self.get_days_remaining(item)
        if days is None:
            return "unknown"
        if days < 0:
            return "expired"
        return "soon" if days <= SOON_DAYS else "ok"


def active_items(request):
    """Stok aktif milik user: belum diarsipkan dan jumlahnya masih lebih dari nol."""
    return PantryItem.objects.filter(user=request.user, archived_at__isnull=True, quantity__gt=0)


def no_store(view):
    """Respons berisi data pribadi tidak boleh di-cache."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        """Menjalankan view lalu menandai respons private, no-store."""
        response = view(request, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


def delegate(web_view, request, *args, method=None, **kwargs):
    """Menjalankan view web pada HttpRequest asli (body belum dibaca DRF); `method` menggantikan
    method request sementara karena klien mobile hanya bisa GET/POST."""
    raw = request._request
    original = raw.method
    if method:
        raw.method = method
    try:
        return web_view(raw, *args, **kwargs)
    finally:
        raw.method = original


@api_view(["GET", "POST"])
@no_store
def item_list(request):
    """GET: stok aktif, opsional `?filter=expired|soon|unknown` (default semua). POST: menambah
    1–30 bahan; body `{"source": "manual"|"ocr", "operation_key": <uuid>, "items": [...]}`."""
    if request.method == "POST":
        return delegate(web.save_pantry_items, request)
    mode = request.query_params.get("filter", "all")
    if mode not in EXPIRY_FILTERS:
        return Response(
            {"error": "filter harus salah satu dari: all, expired, soon, unknown."}, status=400
        )
    items = active_items(request)
    if mode == "expired":
        items = items.filter(estimated_expires_on__lt=today())
    elif mode == "soon":
        items = items.filter(
            estimated_expires_on__gte=today(),
            estimated_expires_on__lte=today() + timedelta(days=SOON_DAYS),
        )
    elif mode == "unknown":
        items = items.filter(estimated_expires_on__isnull=True)
    return Response(PantryItemSerializer(items, many=True).data)


@api_view(["GET"])
@no_store
def item_detail(request, item_id):
    """Detail satu stok milik user; milik user lain diperlakukan sebagai tidak ditemukan."""
    item = active_items(request).filter(pk=item_id).first()
    if item is None:
        return Response({"error": "Stok tidak ditemukan."}, status=404)
    return Response(PantryItemSerializer(item).data)


@api_view(["POST"])
@no_store
def item_update(request, item_id):
    """Mengubah jumlah, satuan, lokasi, atau tanggal kedaluwarsa (setara PATCH di web).
    Body wajib memuat `version` dan `operation_key`."""
    return delegate(web.update_pantry_details, request, item_id, method="PATCH")


@api_view(["POST"])
@no_store
def item_delete(request, item_id):
    """Membuang stok (setara DELETE di web: diarsipkan dan dicatat). Body: `version`, `operation_key`."""
    return delegate(web.delete_pantry_item, request, item_id, method="DELETE")


@api_view(["GET"])
@no_store
def item_movements(request, item_id):
    """Riwayat perubahan stok (maksimal 100 terbaru)."""
    return delegate(web.pantry_movements, request, item_id)


@api_view(["GET"])
@no_store
def recipe_matches(request):
    """Ide menu dari stok yang belum kedaluwarsa; `?servings=1..10`, maksimal 20 resep."""
    return delegate(web.pantry_recipe_matches, request)


@api_view(["POST"])
@no_store
def receipt_scan(request):
    """Membaca foto struk (multipart, field `image`, maksimal 10 MB) lewat Gemini. Hasilnya belum
    tersimpan: periksa dulu, lalu kirim ke POST /api/pantry/items/ dengan source "ocr"."""
    return delegate(web.fallback_receipt_ocr, request)