import json
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.cache import patch_cache_control

from apps.accounts.preferences import effective_allergens, profile_for
from apps.budget_planner.models import PlannedMeal
from apps.budget_planner.services import PreviewRateLimit, reserve_preview
from apps.catalog.models import Ingredient, IngredientAlias, Recipe
from apps.catalog.recipe_images import recipe_image_for, recipe_images_for
from apps.pantry.services import StockError, plan_consumption

from .models import CookingHistory, RecipeDataReport, RecipeFavorite, RecipeNote, RecipeReview
from .reviews import (
    ReviewLimited,
    attach_review_photo,
    delete_review_photo,
    review_context,
    write_review,
)
from .services import (
    cook,
    estimated_recipe_cost,
    get_recipe,
    preview_cooking,
    recipe_costs,
    recipe_query,
    recipe_requirements,
    slot_has_rice,
    stock_matches,
    with_guidance,
)
from .services import set_slot_status as change_slot_status

# Price ceilings offered in the filter, for the profile's servings.
PRICE_LIMITS = (10000, 15000, 25000, 50000)


def api(view):
    @wraps(view)
    def wrapped(request):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Silakan masuk kembali."}, status=403)
        if request.method != "POST":
            response = JsonResponse({"error": "Gunakan POST."}, status=405)
            response["Allow"] = "POST"
            return response
        if len(request.body) > 40000:
            return JsonResponse({"error": "Data terlalu besar."}, status=413)
        try:
            if request.content_type != "application/json":
                raise ValueError("Kirim data dalam format JSON.")
            data = json.loads(request.body)
            if not isinstance(data, dict):
                raise ValueError("Data harus berupa objek.")
            response = view(request, data)
        except StockError as exc:
            response = JsonResponse({"error": str(exc)}, status=exc.status)
        except PreviewRateLimit as exc:
            response = JsonResponse({"error": str(exc)}, status=429)
            response["Retry-After"] = str(exc.retry_after)
        except (ValueError, TypeError, RecursionError) as exc:
            response = JsonResponse(
                {"error": str(exc) if isinstance(exc, ValueError) else "Data tidak valid."},
                status=400,
            )
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


@api
@transaction.atomic
def set_favorite(request, data):
    from django.contrib.auth import get_user_model

    if not isinstance(data.get("recipe_code"), str) or type(data.get("favorite")) is not bool:
        raise ValueError("Kode resep dan pilihan favorit wajib diisi.")
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    recipe = Recipe.objects.filter(pk=data["recipe_code"]).first()
    if recipe is None:
        raise StockError("Resep tidak ditemukan.", 404)
    if data["favorite"]:
        get_recipe(request.user, recipe.pk)
        RecipeFavorite.objects.get_or_create(user=request.user, recipe=recipe)
    else:
        RecipeFavorite.objects.filter(user=request.user, recipe=recipe).delete()
    return JsonResponse({"favorite": data["favorite"]})


@api
@transaction.atomic
def save_recipe_note(request, data):
    from django.contrib.auth import get_user_model

    code = data.get("recipe_code")
    content = data.get("content")
    if not isinstance(code, str) or not 1 <= len(code) <= 100:
        raise ValueError("Kode resep tidak valid.")
    if not isinstance(content, str) or len(content) > 2000:
        raise ValueError("Catatan maksimal 2000 karakter.")
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    recipe = get_recipe(request.user, code)
    content = content.strip()
    if content:
        note, _ = RecipeNote.objects.update_or_create(
            user=request.user, recipe=recipe, defaults={"content": content}
        )
        return JsonResponse({"saved": True, "updated_at": note.updated_at.isoformat()})
    RecipeNote.objects.filter(user=request.user, recipe=recipe).delete()
    return JsonResponse({"saved": False})


@api
def cooking_preview(request, data):
    reserve_preview(request.user)
    return JsonResponse(preview_cooking(request.user, data))


@api
def record_cooking(request, data):
    return JsonResponse(cook(request.user, data), status=201)


@api
def set_slot_status(request, data):
    return JsonResponse(change_slot_status(request.user, data))


@api
@transaction.atomic
def report_recipe_data(request, data):
    from django.contrib.auth import get_user_model

    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    code = data.get("recipe_code")
    category = data.get("category")
    details = data.get("details", "")
    allowed_categories = {choice[0] for choice in RecipeDataReport.CATEGORY_CHOICES}
    if not isinstance(code, str) or not 1 <= len(code) <= 100:
        raise ValueError("Resep yang dilaporkan tidak valid.")
    if category not in allowed_categories:
        raise ValueError("Pilih bagian resep yang perlu diperiksa.")
    if not isinstance(details, str) or len(details.strip()) < 5 or len(details) > 1000:
        raise ValueError("Jelaskan masalah dalam 5 sampai 1000 karakter.")
    recipe = get_recipe(request.user, code)
    recent_reports = RecipeDataReport.objects.filter(
        reporter=request.user, created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    if recent_reports >= 5:
        raise StockError("Batas 5 laporan per jam tercapai. Coba lagi nanti.", 429)
    report = RecipeDataReport.objects.create(
        recipe=recipe, reporter=request.user, category=category, details=details.strip()
    )
    return JsonResponse({"submitted": True, "report_id": report.pk}, status=201)


@api
def recipe_review(request, data):
    return JsonResponse(write_review(request.user, data))


@api
def recipe_review_photo_delete(request, data):
    return JsonResponse(
        delete_review_photo(request.user, data.get("recipe_code"), data.get("version"))
    )


@login_required
@require_POST
def recipe_review_photo(request):
    try:
        request_size = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return JsonResponse({"error": "Ukuran unggahan tidak valid."}, status=400)
    if request_size > 7 * 1024 * 1024:
        return JsonResponse({"error": "Ukuran foto maksimal 6 MB."}, status=413)
    upload = request.FILES.get("photo")
    if upload is None:
        return JsonResponse({"error": "Pilih foto sebelum mengunggah."}, status=400)
    try:
        version = int(request.POST.get("version", ""))
        result = attach_review_photo(
            request.user,
            request.POST.get("recipe_code", ""),
            version,
            upload,
            permission_granted=request.POST.get("photo_permission") == "on",
        )
    except StockError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    except ReviewLimited as exc:
        response = JsonResponse({"error": str(exc)}, status=429)
        response["Retry-After"] = str(exc.retry_after)
        return response
    except (ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    response = JsonResponse(result)
    patch_cache_control(response, private=True, no_store=True)
    return response


@login_required
def recipe_review_photo_file(request, review_id):
    review = get_object_or_404(RecipeReview, pk=review_id)
    if not review.photo:
        return JsonResponse({"error": "Foto tidak tersedia."}, status=404)
    if (
        (
            not review.photo_permission_granted
            or review.photo_consent_at is None
            or review.is_hidden
            or review.photo_is_hidden
        )
        and review.user_id != request.user.pk
        and not request.user.is_staff
    ):
        return JsonResponse({"error": "Foto belum tersedia untuk publik."}, status=404)
    try:
        response = FileResponse(review.photo.open("rb"), content_type="image/jpeg")
    except OSError:
        return JsonResponse({"error": "Berkas foto tidak ditemukan."}, status=404)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _recipe_quality(recipe, guidance_available):
    links = list(recipe.recipeingredient_set.all())
    if not links:
        ingredients = "Bahan belum tercatat"
    else:
        try:
            if not recipe.base_servings:
                raise StockError("Porsi dasar belum tersedia.")
            recipe_requirements(recipe, 1)
            ingredients = (
                "Takaran lengkap · sebagian estimasi"
                if any(link.quantity_status == "estimated" for link in links)
                else "Takaran bahan lengkap"
            )
        except StockError:
            ingredients = "Takaran bahan perlu dilengkapi"
    return {
        "guidance": "Panduan ditinjau" if guidance_available else "Panduan belum tersedia",
        "ingredients": ingredients,
        # Curated mapping entries and approved community photos are reviewed
        # before being selected for display by recipe_images_for().
        "photo": "Foto ditinjau" if getattr(recipe, "photo", None) else "Foto belum tersedia",
    }


@login_required
def book_page(request):
    profile = profile_for(request.user)
    groups = effective_allergens(request.user)
    baseline = Recipe.objects.filter(
        is_active=True, is_plannable=True, recipetag__tag="halal"
    ).distinct()
    unknown_count = baseline.filter(allergen_reviewed=False).count() if groups else 0
    allergen_count = (
        baseline.filter(allergen_reviewed=True, allergen_groups__group__in=groups)
        .distinct()
        .count()
        if groups
        else 0
    )
    query = recipe_query(request.user)
    term = request.GET.get("q", "").strip()[:100]
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
    meal = request.GET.get("meal", "")
    if meal in {"sarapan", "makan_siang", "makan_malam"}:
        query = query.filter(meal_type=meal)
    if request.GET.get("favorites") == "1":
        query = query.filter(recipefavorite__user=request.user)
    held_count = query.count() - with_guidance(query).count()
    if request.GET.get("guidance") == "1":
        query = with_guidance(query)
    try:
        max_price = int(request.GET.get("max_price", ""))
    except ValueError:
        max_price = None
    if max_price in PRICE_LIMITS:
        codes = set(query.values_list("pk", flat=True))
        costs = recipe_costs(profile.servings, codes)
        query = query.filter(pk__in=[code for code, cost in costs.items() if cost <= max_price])
    else:
        max_price = None
    stock_filter = request.GET.get("stock", "")
    stock_rows = {}
    if stock_filter in {"complete", "soon", "best"}:
        rows = stock_matches(request.user, profile.servings, query=query)
        if stock_filter == "best":
            stock_rows = {row["recipe_code"]: row for row in rows}
            ranked_codes = list(stock_rows)
            query = query.filter(pk__in=ranked_codes).order_by(
                Case(
                    *[When(pk=code, then=Value(rank)) for rank, code in enumerate(ranked_codes)],
                    default=Value(len(ranked_codes)),
                    output_field=IntegerField(),
                )
            )
        else:
            query = query.filter(pk__in=[row["recipe_code"] for row in rows if row[stock_filter]])
    ordered_query = query if stock_filter == "best" else query.order_by("name")
    page = Paginator(
        ordered_query.prefetch_related("recipeingredient_set__ingredient"), 12
    ).get_page(request.GET.get("page"))
    photos = recipe_images_for([recipe.pk for recipe in page.object_list])
    page_codes = [recipe.pk for recipe in page.object_list]
    missing_codes = {
        item["ingredient_code"]
        for code in page_codes
        for item in stock_rows.get(code, {}).get("missing", [])
    }
    missing_names = {
        code: ingredient.name for code, ingredient in Ingredient.objects.in_bulk(missing_codes).items()
    }
    guidance_codes = set(
        with_guidance(Recipe.objects.filter(pk__in=page_codes)).values_list("pk", flat=True)
    )
    for recipe in page.object_list:
        recipe.photo = photos.get(recipe.pk)
        recipe.quality = _recipe_quality(recipe, recipe.pk in guidance_codes)
        match = stock_rows.get(recipe.pk)
        if match:
            recipe.stock_match = {
                **match,
                "coverage_percent": round(match["coverage"] * 100),
                "missing_names": [
                    missing_names.get(item["ingredient_code"], item["ingredient_code"])
                    for item in match["missing"]
                ],
            }
    selection_error = None
    selected = None
    slot = None
    code = request.GET.get("recipe")
    if request.GET.get("slot"):
        try:
            slot = (
                PlannedMeal.objects.select_related("plan")
                .filter(pk=int(request.GET["slot"]), plan__user=request.user, plan__status="saved")
                .first()
            )
        except (ValueError, OverflowError):
            slot = None
        if slot:
            code = slot.recipe_id
        else:
            selection_error = "Menu rencana tidak ditemukan."
    if not code and page.object_list and not selection_error:
        code = page.object_list[0].pk
    detail, stock = None, None
    if code and not selection_error:
        try:
            selected = get_recipe(request.user, code, inputs=slot.plan.inputs if slot else None)
            selected.photo = recipe_images_for([selected.pk]).get(selected.pk)
            selected.quality = _recipe_quality(
                selected, with_guidance(Recipe.objects.filter(pk=selected.pk)).exists()
            )
            servings = slot.servings if slot else profile.servings
            needs, ingredients, nutrition = recipe_requirements(
                selected, servings, with_rice=slot_has_rice(slot)
            )
            # Same stock rule as stock_matches: undated stock counts, but is flagged.
            stock = plan_consumption(request.user, needs, allow_unknown_expiry=True)
            detail = {
                "unknown_expiry": any(
                    row["batch"].estimated_expires_on is None
                    or row["batch"].expiry_source == "unknown"
                    for row in stock["allocations"]
                ),
                "ingredients": ingredients,
                "nutrition": nutrition,
                "servings": servings,
                "cost": estimated_recipe_cost(selected, servings),
                "source_url": selected.source_url
                if selected.source_url.startswith(("https://", "http://"))
                else "",
                "guidance": with_guidance(Recipe.objects.filter(pk=selected.pk)).exists(),
                "complete": not stock["missing"],
                "favorite": RecipeFavorite.objects.filter(
                    user=request.user, recipe=selected
                ).exists(),
                "steps": [
                    line.strip() for line in selected.instructions.splitlines() if line.strip()
                ],
                "quality": selected.quality,
            }
            for row in ingredients:
                row["missing"] = str(stock["missing"].get(row["ingredient_code"], 0))
        except StockError as exc:
            selection_error = str(exc)
    personal_note = (
        RecipeNote.objects.filter(user=request.user, recipe=selected).first() if selected else None
    )
    favorites = list(
        RecipeFavorite.objects.filter(user=request.user)
        .select_related("recipe")
        .order_by("-created_at")[:20]
    )
    available_favorites = set(
        recipe_query(request.user)
        .filter(pk__in=[favorite.recipe_id for favorite in favorites])
        .values_list("pk", flat=True)
    )
    for favorite in favorites:
        favorite.available = favorite.recipe_id in available_favorites
    history = Paginator(
        CookingHistory.objects.filter(user=request.user).prefetch_related(
            "operation__pantrymovement_set"
        ),
        7,
    ).get_page(request.GET.get("history_page"))
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("slot", None)
    params.pop("recipe", None)
    params.pop("held", None)
    history_params = request.GET.copy()
    history_params.pop("history_page", None)
    review_params = request.GET.copy()
    review_params.pop("review_page", None)
    response = render(
        request,
        "modul4.html",
        {
            "recipes": page,
            "selected": selected,
            "detail": detail,
            "personal_note": personal_note,
            "slot": slot,
            "selection_error": selection_error,
            "favorites": favorites,
            "history": history,
            "week_count": CookingHistory.objects.filter(
                user=request.user, cooked_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
            "unknown_count": unknown_count,
            "allergen_count": allergen_count,
            "held_count": held_count,
            "guidance_only": request.GET.get("guidance") == "1",
            "q": term,
            "meal": meal,
            "max_price": max_price,
            "price_limits": PRICE_LIMITS,
            "with_rice": slot_has_rice(slot),
            "filters": request.GET,
            "query_params": urlencode(params, doseq=True),
            "history_params": urlencode(history_params, doseq=True),
            "review_params": urlencode(review_params, doseq=True),
            **(
                review_context(request.user, selected, request.GET.get("review_page"))
                if selected and not selection_error
                else {}
            ),
        },
    )
    patch_cache_control(response, private=True, no_store=True)
    return response
