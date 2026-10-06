import json
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import patch_cache_control

from apps.accounts.preferences import effective_allergens, profile_for
from apps.budget_planner.models import PlannedMeal
from apps.budget_planner.services import PreviewRateLimit, reserve_preview
from apps.catalog.models import Recipe
from apps.pantry.models import PantryItem
from apps.pantry.services import StockError, plan_consumption

from .models import CookingHistory, RecipeFavorite
from .services import (
    cook,
    estimated_recipe_cost,
    get_recipe,
    preview_cooking,
    recipe_query,
    recipe_requirements,
    with_guidance,
)


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
def cooking_preview(request, data):
    reserve_preview(request.user)
    return JsonResponse(preview_cooking(request.user, data))


@api
def record_cooking(request, data):
    return JsonResponse(cook(request.user, data), status=201)


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
    held_count = query.count() - with_guidance(query).count()
    term = request.GET.get("q", "").strip()[:100]
    if term:
        query = query.filter(
            Q(name__icontains=term) | Q(recipeingredient__ingredient__name__icontains=term)
        ).distinct()
    meal = request.GET.get("meal", "")
    if meal in {"sarapan", "makan_siang", "makan_malam"}:
        query = query.filter(meal_type=meal)
    if request.GET.get("favorites") == "1":
        query = query.filter(recipefavorite__user=request.user)
    if request.GET.get("held") != "1":
        query = with_guidance(query)
    stock_filter = request.GET.get("stock", "")
    if stock_filter in {"complete", "soon"}:
        inventory = list(
            PantryItem.objects.filter(
                user=request.user,
                archived_at__isnull=True,
                quantity__gt=0,
                estimated_expires_on__gte=timezone.localdate(),
            )
            .exclude(expiry_source="unknown")
            .order_by("estimated_expires_on", "pk")
        )
        allowed = []
        for recipe in query.prefetch_related("recipeingredient_set__ingredient"):
            try:
                needs, _, _ = recipe_requirements(recipe, profile.servings)
                allocation = plan_consumption(request.user, needs, preview_batches=inventory)
            except StockError:
                continue
            if stock_filter == "complete" and not allocation["missing"]:
                allowed.append(recipe.pk)
            elif stock_filter == "soon" and any(
                row["batch"].estimated_expires_on <= timezone.localdate() + timedelta(days=2)
                for row in allocation["allocations"]
            ):
                allowed.append(recipe.pk)
        query = query.filter(pk__in=allowed)
    page = Paginator(query.order_by("name"), 12).get_page(request.GET.get("page"))
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
            servings = slot.servings if slot else profile.servings
            needs, ingredients, nutrition = recipe_requirements(selected, servings)
            stock = plan_consumption(request.user, needs)
            detail = {
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
            }
            for row in ingredients:
                row["missing"] = str(stock["missing"].get(row["ingredient_code"], 0))
        except StockError as exc:
            selection_error = str(exc)
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
    history_params = request.GET.copy()
    history_params.pop("history_page", None)
    response = render(
        request,
        "modul4.html",
        {
            "recipes": page,
            "selected": selected,
            "detail": detail,
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
            "q": term,
            "meal": meal,
            "filters": request.GET,
            "query_params": urlencode(params, doseq=True),
            "history_params": urlencode(history_params, doseq=True),
        },
    )
    patch_cache_control(response, private=True, no_store=True)
    return response
