"""Endpoint REST Modul 4 untuk aplikasi mobile; aturan resep, kuota, dan validasi memakai kode web.
Hanya GET dan POST karena pbp_django_auth di Flutter hanya mendukung dua method itu."""

from datetime import timedelta
from functools import wraps

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from django.utils.cache import patch_cache_control
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.catalog.models import IngredientAlias, Recipe
from apps.catalog.recipe_images import recipe_images_for
from apps.login.preferences import preferences_for
from apps.pantry.services import StockError, plan_consumption

from . import views as web
from .models import CookingHistory, RecipeFavorite, RecipeNote
from .serializers import (
    CookingHistorySerializer,
    RecipeCardSerializer,
    RecipeFavoriteSerializer,
    photo_data,
)
from .services import (
    RecipeBookRateLimit,
    cook,
    estimated_recipe_cost,
    get_recipe,
    preview_cooking,
    recipe_costs,
    recipe_query,
    recipe_requirements,
    reserve_recipe_book_preview,
    stock_matches,
    with_guidance,
)
from .staples import tracked_staple_codes

MEALS = {"sarapan", "makan_siang", "makan_malam"}
STOCK_FILTERS = {"complete", "soon", "best"}


def recipe_errors(view):
    """Mengubah error layanan resep menjadi respons JSON {"error": ...} dengan status yang sesuai,
    dan menandai respons agar tidak di-cache karena berisi data pribadi."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        """Menjalankan view lalu memetakan 429/StockError/400."""
        try:
            response = view(request, *args, **kwargs)
        except RecipeBookRateLimit as exc:
            response = Response({"error": str(exc), "retry_after": exc.retry_after}, status=429)
            response["Retry-After"] = str(exc.retry_after)
        except StockError as exc:
            response = Response({"error": str(exc)}, status=exc.status)
        except (ValueError, TypeError) as exc:
            response = Response(
                {"error": str(exc) if isinstance(exc, ValueError) else "Data tidak valid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


def json_object(request):
    """Body request harus objek JSON; list atau nilai lain ditolak 400."""
    if not isinstance(request.data, dict):
        raise ValueError("Format data tidak valid.")
    return request.data


def int_param(request, name, default, low, high):
    """Parameter query bilangan bulat dalam rentang [low, high]; tidak diisi berarti default."""
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or not low <= value <= high:
        raise ValueError(f"Parameter {name} harus bilangan bulat {low} sampai {high}.")
    return value


def paginate(request, query, default_limit):
    """Satu halaman hasil sesuai `page` dan `limit` (maks 50) beserta jumlah total dan penanda lanjut."""
    limit = int_param(request, "limit", default_limit, 1, 50)
    page = Paginator(query, limit).get_page(int_param(request, "page", 1, 1, 100000))
    return page, {"count": page.paginator.count, "page": page.number, "has_next": page.has_next()}


@api_view(["GET"])
@recipe_errors
def recipe_list(request):
    """Cari resep yang lolos preferensi halal, alergi, dan pantangan, dengan filter yang sama dengan
    web: q, meal, favorites=1, guidance=1, max_price, stock (complete/soon/best), plus page dan limit."""
    params = request.query_params
    profile = preferences_for(request.user)
    query = recipe_query(request.user, preference=profile)
    term = params.get("q", "").strip()[:100]
    if term:
        alias_ingredients = IngredientAlias.objects.filter(
            raw_name__icontains=term,
            mapping_status__in=["reviewed", "manual_curated"],
        ).values("ingredient_id")
        query = query.filter(
            Q(name__icontains=term)
            | Q(recipeingredient__ingredient__name__icontains=term)
            | Q(recipeingredient__ingredient_id__in=alias_ingredients)
        ).distinct()
    meal = params.get("meal", "")
    if meal and meal not in MEALS:
        raise ValueError("Waktu makan tidak valid.")
    if meal:
        query = query.filter(meal_type=meal)
    if params.get("favorites") == "1":
        query = query.filter(recipefavorite__user=request.user)
    if params.get("guidance") == "1":
        query = with_guidance(query)
    max_price = int_param(request, "max_price", None, 0, 10**9)
    if max_price is not None and max_price not in web.PRICE_LIMITS:
        raise ValueError("Harga maksimal tidak valid.")
    costs = None
    if max_price is not None:
        costs = recipe_costs(profile.servings, set(query.values_list("pk", flat=True)))
        query = query.filter(pk__in=[code for code, cost in costs.items() if cost <= max_price])
    stock_filter = params.get("stock", "")
    if stock_filter and stock_filter not in STOCK_FILTERS:
        raise ValueError("Filter stok tidak valid.")
    stock_rows = {}
    if stock_filter:
        rows = stock_matches(request.user, profile.servings, query=query)
        if stock_filter == "best":
            stock_rows = {row["recipe_code"]: row for row in rows}
            query = query.filter(pk__in=list(stock_rows)).order_by(
                Case(
                    *[When(pk=code, then=Value(rank)) for rank, code in enumerate(stock_rows)],
                    default=Value(len(stock_rows)),
                    output_field=IntegerField(),
                )
            )
        else:
            stock_rows = {row["recipe_code"]: row for row in rows if row[stock_filter]}
            query = query.filter(pk__in=list(stock_rows))
    if stock_filter != "best":
        query = query.order_by("name")
    page, meta = paginate(request, query, 12)
    codes = {recipe.pk for recipe in page.object_list}
    if costs is None:
        costs = recipe_costs(profile.servings, codes) if codes else {}
    context = {
        "request": request,
        "costs": costs,
        "photos": recipe_images_for(codes),
        "guided": set(with_guidance(Recipe.objects.filter(pk__in=codes)).values_list("pk", flat=True)),
        "stock_rows": stock_rows,
    }
    results = RecipeCardSerializer(page.object_list, many=True, context=context).data
    return Response({**meta, "servings": profile.servings, "results": results})


@api_view(["GET"])
@recipe_errors
def recipe_detail(request, code):
    """Detail resep untuk porsi `servings` (default porsi profil): bahan dan kekurangan stok, gizi,
    estimasi harga, favorit, catatan pribadi. Langkah dan sumber hanya dikirim bila panduan layak."""
    servings = int_param(request, "servings", preferences_for(request.user).servings, 1, 10)
    recipe = get_recipe(request.user, code)
    needs, ingredients, nutrition = recipe_requirements(
        recipe, servings, tracked_staples=tracked_staple_codes(request.user)
    )
    stock = plan_consumption(request.user, needs, allow_unknown_expiry=True)
    for row in ingredients:
        row["missing"] = str(stock["missing"].get(row["ingredient_code"], 0))
    guidance = with_guidance(Recipe.objects.filter(pk=recipe.pk)).exists()
    note = RecipeNote.objects.filter(user=request.user, recipe=recipe).first()
    return Response(
        {
            "recipe_code": recipe.pk,
            "name": recipe.name,
            "meal_type": recipe.meal_type,
            "photo": photo_data(request, recipe_images_for([recipe.pk]).get(recipe.pk)),
            "servings": servings,
            "cost": estimated_recipe_cost(recipe, servings),
            "ingredients": ingredients,
            "nutrition": nutrition,
            "complete": not stock["missing"],
            "unknown_expiry": any(
                row["batch"].estimated_expires_on is None or row["batch"].expiry_source == "unknown"
                for row in stock["allocations"]
            ),
            "guidance": guidance,
            "steps": [line.strip() for line in recipe.instructions.splitlines() if line.strip()]
            if guidance
            else [],
            "source_url": recipe.source_url
            if guidance and recipe.source_url.startswith(("https://", "http://"))
            else "",
            "favorite": RecipeFavorite.objects.filter(user=request.user, recipe=recipe).exists(),
            "note": {"content": note.content, "updated_at": note.updated_at} if note else None,
        }
    )


@api_view(["GET", "POST"])
@recipe_errors
def favorites(request):
    """GET: favorit milik user, terbaru dulu. POST {recipe_code, favorite}: menandai atau melepas
    favorit; menandai hanya untuk resep yang lolos preferensi dan alergi."""
    if request.method == "POST":
        # __wrapped__ melewati decorator `api` web (yang membaca body mentah) agar validasinya identik.
        return web.set_favorite.__wrapped__(request, json_object(request))
    rows = RecipeFavorite.objects.filter(user=request.user).select_related("recipe")
    rows = rows.order_by("-created_at")
    available = set(
        recipe_query(request.user)
        .filter(pk__in=[row.recipe_id for row in rows])
        .values_list("pk", flat=True)
    )
    return Response(RecipeFavoriteSerializer(rows, many=True, context={"available": available}).data)


@api_view(["POST"])
@recipe_errors
def save_note(request):
    """POST {recipe_code, content}: menyimpan catatan pribadi maks 2000 karakter; content kosong
    berarti menghapus catatan."""
    return web.save_recipe_note.__wrapped__(request, json_object(request))


@api_view(["GET"])
@recipe_errors
def cooking_history(request):
    """Riwayat Sudah Masak milik user (terbaru dulu, 7 per halaman bawaan) dan jumlah masak 7 hari."""
    entries = CookingHistory.objects.filter(user=request.user).prefetch_related(
        "operation__pantrymovement_set"
    )
    page, meta = paginate(request, entries, 7)
    week_count = entries.filter(cooked_at__gte=timezone.now() - timedelta(days=7)).count()
    results = CookingHistorySerializer(page.object_list, many=True).data
    return Response({**meta, "week_count": week_count, "results": results})


@api_view(["POST"])
@recipe_errors
def cooking_preview(request):
    """Pratinjau pemakaian stok sebelum Sudah Masak tanpa mengubah data; memakai kuota Buku Resep."""
    data = json_object(request)
    reserve_recipe_book_preview(request.user)
    return Response(preview_cooking(request.user, data))


@api_view(["POST"])
@recipe_errors
def record_cooking(request):
    """Sudah Masak: mencatat riwayat dan mengurangi stok pantry; operation_key mencegah catatan ganda."""
    return Response(cook(request.user, json_object(request)), status=status.HTTP_201_CREATED)
