"""Recipe Book queries and transactional cooking. No stock reservations."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.choices import ALLERGEN_KEYS
from apps.accounts.preferences import effective_allergens, preferences_for
from apps.budget_planner.models import BudgetPlan, PlannedMeal
from apps.budget_planner.planner import RICE_CODE, RICE_GRAMS_PER_SERVING, purchase_grams
from apps.catalog.allergens import recipe_allowed
from apps.catalog.models import Ingredient, Recipe
from apps.pantry.services import (
    StockError,
    eligible_stock,
    execute_consumption,
    operation,
    plan_consumption,
)

from .models import CookingHistory
from .staples import ALL_STAPLE_CODES, tracked_staple_codes

JAKARTA = ZoneInfo("Asia/Jakarta")

def estimated_recipe_cost(recipe, servings):
    """Use the planner's basket quote, including whole-fruit rounding."""
    from apps.budget_planner.planner import _load_candidates, quote_schedule

    try:
        catalog = _load_candidates([recipe.meal_type], servings, [], halal_only=False)
        quote = quote_schedule(
            [{recipe.meal_type: recipe.pk}], servings=servings, targets=[], catalog=catalog
        )
        return quote["total"]
    except ValueError:
        return None


def recipe_costs(servings, codes):
    """Basket quote per recipe for many recipes with one catalog load."""
    from apps.budget_planner.planner import MEALS, _load_candidates, quote_schedule

    try:
        catalog = _load_candidates(MEALS, servings, [], halal_only=False)
    except ValueError:
        return {}  # no price snapshot imported yet: nothing can be priced
    costs = {}
    for meal, items in catalog[5].items():
        # quote_schedule requires each schedule row to contain every meal in
        # its catalog. A recipe price is a single-meal quote, so give it a
        # catalog whose available candidates contain only that meal.
        meal_catalog = catalog[:5] + ({meal: items},) + catalog[6:]
        for item in items:
            code = item["recipe"].pk
            if code in codes:
                quote = quote_schedule(
                    [{meal: code}], servings=servings, targets=[], catalog=meal_catalog
                )
                costs[code] = quote["total"]
    return costs


def recipe_query(user, *, allergens=None):
    query = Recipe.objects.filter(
        is_active=True, is_plannable=True
    ).distinct()
    if preferences_for(user).halal_only:
        query = query.filter(recipetag__tag="halal")
    groups = effective_allergens(user) if allergens is None else allergens
    if not set(groups) <= ALLERGEN_KEYS:
        raise ValueError("Kelompok alergi tidak valid.")
    if groups:
        query = query.filter(allergen_reviewed=True).exclude(allergen_groups__group__in=groups)
    avoided = preferences_for(user).avoided_ingredients.values_list("pk", flat=True)
    return query.exclude(recipeingredient__ingredient_id__in=avoided)


def with_guidance(query):
    return (
        query.filter(instruction_status__in=["source_ok", "authored_reviewed"])
        .exclude(instructions="")
        .exclude(Q(recipe_code__startswith="RCP-MDL-") & Q(instruction_review_note=""))
        .exclude(Q(instruction_status="authored_reviewed", instruction_reviewed_on__isnull=True))
        .exclude(Q(recipe_code__startswith="RCP-MDL-", instruction_reviewed_on__isnull=True))
    )


def stock_matches(user, servings, *, query=None):
    """Recipes the user's pantry covers; one rule for Modul 2 and Modul 4. Reserves nothing.

    Stock with an unknown date counts (it is physically there) but is flagged,
    because cooking it later asks for explicit confirmation.
    """
    if type(servings) is not int or not 1 <= servings <= 10:
        raise StockError("Porsi harus bilangan bulat 1–10.", 400)
    # FEFO over trusted dates first; "unknown" batches go last even if a date is stored.
    inventory = sorted(
        eligible_stock(user, allow_unknown_expiry=True),
        key=lambda b: (
            b.estimated_expires_on is None or b.expiry_source == "unknown",
            b.estimated_expires_on or date.max,
            b.pk,
        ),
    )
    if not inventory:
        return []
    configured_staples = tracked_staple_codes(user)
    available_grams = {}
    for batch in inventory:
        available_grams[batch.ingredient_id] = available_grams.get(
            batch.ingredient_id, Decimal(0)
        ) + Decimal(batch.quantity) * Decimal(batch.grams_per_unit)
    query = with_guidance(recipe_query(user)) if query is None else query
    soon = timezone.localdate(timezone=JAKARTA) + timedelta(days=2)
    rows = []
    for recipe in (
        query.filter(recipeingredient__ingredient_id__in={b.ingredient_id for b in inventory})
        .distinct()
        .prefetch_related("recipeingredient_set__ingredient")
    ):
        try:
            needs, ingredients, _ = recipe_requirements(
                recipe, servings, tracked_staples=configured_staples
            )
            allocation = plan_consumption(
                user, needs, allow_unknown_expiry=True, preview_batches=inventory
            )
        except StockError:
            continue
        if not needs:
            continue
        missing = allocation["missing"]
        coverage = sum((grams - missing.get(code, 0)) / grams for code, grams in needs.items())
        if coverage <= 0:
            continue
        ingredient_names = {
            item["ingredient_code"]: item["name"]
            for item in ingredients
            if item["tracked"]
        }
        available = [
            {
                "ingredient_code": code,
                "name": ingredient_names.get(code, code),
                "grams": format((grams - missing.get(code, Decimal(0))).normalize(), "f"),
                "required_grams": format(grams.normalize(), "f"),
            }
            for code, grams in needs.items()
            if grams - missing.get(code, Decimal(0)) > 0
        ]
        missing_ingredients = [
            {
                "ingredient_code": code,
                "name": ingredient_names.get(code, code),
                "grams": format(grams.normalize(), "f"),
            }
            for code, grams in missing.items()
        ]
        max_servings = 10
        for code, grams in needs.items():
            per_serving = grams / Decimal(servings)
            possible = int(
                (available_grams.get(code, Decimal(0)) / per_serving).to_integral_value(
                    rounding=ROUND_FLOOR
                )
            )
            max_servings = min(max_servings, possible)
        if not missing:
            max_servings = max(max_servings, servings)
        used = [row["batch"] for row in allocation["allocations"]]
        undated = [
            b for b in used if b.estimated_expires_on is None or b.expiry_source == "unknown"
        ]
        rows.append(
            {
                "recipe_code": recipe.pk,
                "name": recipe.name,
                "complete": not missing,
                "max_servings": max(0, max_servings),
                "soon": any(b.estimated_expires_on <= soon for b in used if b not in undated),
                "coverage": float(coverage / len(needs)),
                "available": available,
                "missing_ingredients": missing_ingredients,
                "missing": [
                    {"ingredient_code": code, "grams": format(grams.normalize(), "f")}
                    for code, grams in missing.items()
                ],
                "unknown_expiry": bool(undated),
            }
        )
    return sorted(rows, key=lambda row: (-row["coverage"], row["name"]))


def get_recipe(user, code, *, inputs=None):
    groups = effective_allergens(user, inputs or {})
    recipe = (
        recipe_query(user, allergens=groups)
        .prefetch_related("recipeingredient_set__ingredient", "recipetag_set")
        .filter(pk=code)
        .first()
    )
    if recipe is None:
        raise StockError("Resep tidak tersedia atau tidak sesuai preferensi/alergi.", 404)
    # Recheck actual ingredients at execution; stale derived index must fail closed.
    if not recipe_allowed(recipe, list(recipe.recipeingredient_set.all()), groups):
        raise StockError("Data alergen berubah atau belum lengkap. Periksa profil.")
    return recipe


def recipe_requirements(recipe, servings, *, tracked_staples=(), with_rice=False):
    """Stock needs per ingredient; selected staple groups are managed like other stock."""
    if type(servings) is not int or not 1 <= servings <= 10:
        raise StockError("Porsi harus bilangan bulat 1–10.", 400)
    if not recipe.base_servings:
        raise StockError("Porsi dasar resep belum tersedia.", 400)
    needs, ingredients = {}, []
    nutrition = {key: Decimal(0) for key in ("calories", "protein", "carbs", "fat")}
    rice = Ingredient.objects.filter(pk=RICE_CODE).first() if with_rice else None
    if rice is not None:
        grams = Decimal(RICE_GRAMS_PER_SERVING * servings)
        ingredients.append(
            {
                "ingredient_code": rice.pk,
                "name": f"{rice.name} (nasi pendamping)",
                "grams": str(grams),
                "tracked": True,
                "optional": False,
                "estimated": False,
            }
        )
        needs[rice.pk] = grams
        for key in nutrition:
            value = getattr(rice, f"{key}_per_100g")
            nutrition[key] = None if value is None else grams * Decimal(str(value)) / 100
    for link in recipe.recipeingredient_set.all():
        try:
            grams = purchase_grams(link) * Decimal(servings) / Decimal(recipe.base_servings)
            if link.unit != "g" or not grams.is_finite() or grams <= 0:
                raise ValueError
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise StockError("Takaran resep belum dapat dikonversi ke gram.", 400) from exc
        is_common_staple = link.ingredient_id in ALL_STAPLE_CODES
        tracked = not link.is_optional and (
            not is_common_staple or link.ingredient_id in tracked_staples
        )
        ingredients.append(
            {
                "ingredient_code": link.ingredient_id,
                "name": link.ingredient.name,
                "grams": str(grams),
                "tracked": tracked,
                "common_staple": is_common_staple,
                "optional": link.is_optional,
                "estimated": link.quantity_status == "estimated",
            }
        )
        if tracked:
            needs[link.ingredient_id] = needs.get(link.ingredient_id, Decimal(0)) + grams
        for key in nutrition:
            value = getattr(link.ingredient, f"{key}_per_100g")
            if value is None:
                nutrition[key] = None
            elif nutrition[key] is not None:
                # Nutrition uses edible mass, stock uses purchase mass.
                edible = Decimal(str(link.quantity)) * Decimal(servings) / recipe.base_servings
                nutrition[key] += edible * Decimal(str(value)) / 100
    return (
        needs,
        ingredients,
        {
            k: str(v.quantize(Decimal("0.1"))) if v is not None else None
            for k, v in nutrition.items()
        },
    )


def cooking_inputs(user, payload, *, lock=False):
    slot_id = payload.get("planned_meal")
    slot = None
    if slot_id is not None:
        if type(slot_id) is not int or slot_id < 1:
            raise StockError("Slot rencana tidak valid.", 400)
        stub = PlannedMeal.objects.filter(pk=slot_id, plan__user=user).first()
        if stub is None:
            raise StockError("Menu rencana tidak ditemukan.", 404)
        plans = BudgetPlan.objects.filter(pk=stub.plan_id, user=user)
        plan = (plans.select_for_update() if lock else plans).get()
        slots = PlannedMeal.objects.filter(pk=slot_id, plan=plan)
        slot = (slots.select_for_update() if lock else slots).get()
        if type(payload.get("version")) is not int:
            raise StockError("Versi rencana wajib diisi.", 400)
        if plan.version != payload["version"] or slot.status != "planned":
            raise StockError("Menu/rencana sudah berubah atau sudah dimasak. Muat ulang.")
        if payload.get("recipe_code") != slot.recipe_id or payload.get("servings") != slot.servings:
            raise StockError("Resep/porsi harus sesuai slot rencana.", 400)
        # Cooking drafts is disallowed: cloning a cooked draft would duplicate slots.
        if plan.status != "saved":
            raise StockError("Simpan rencana sebelum mencatat masak dari slot ini.")
    else:
        plan = None
    code = payload.get("recipe_code")
    if not isinstance(code, str) or not code or len(code) > 100:
        raise StockError("Kode resep tidak valid.", 400)
    for field in ("allow_unknown_expiry",):
        if type(payload.get(field, False)) is not bool:
            raise StockError("Pilihan konfirmasi tidak valid.", 400)
    recipe = get_recipe(user, code, inputs=plan.inputs if plan else None)
    needs, ingredients, nutrition = recipe_requirements(
        recipe,
        payload.get("servings"),
        tracked_staples=tracked_staple_codes(user),
        with_rice=slot_has_rice(slot),
    )
    return recipe, slot, needs, ingredients, nutrition


def slot_has_rice(slot):
    return bool(slot and isinstance(slot.snapshot, dict) and slot.snapshot.get("with_rice"))


def _apply_external_ingredients(payload, needs, ingredients, allocation):
    """Accept only ingredient amounts that are currently missing from Pantry."""
    raw = payload.get("external_ingredients", [])
    if not isinstance(raw, list) or len(raw) > 100:
        raise StockError("Daftar bahan di luar Pantry tidak valid.", 400)
    names = {
        item["ingredient_code"]: item["name"]
        for item in ingredients
        if item["tracked"]
    }
    external = []
    seen = set()
    for row in raw:
        if not isinstance(row, dict):
            raise StockError("Daftar bahan di luar Pantry tidak valid.", 400)
        code, value = row.get("ingredient_code"), row.get("grams")
        if not isinstance(code, str) or code not in needs or code in seen:
            raise StockError("Bahan di luar Pantry tidak cocok dengan resep.", 400)
        try:
            grams = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise StockError("Jumlah bahan di luar Pantry tidak valid.", 400) from exc
        if not grams.is_finite() or grams <= 0:
            raise StockError("Jumlah bahan di luar Pantry tidak valid.", 400)
        missing = allocation["missing"].get(code, Decimal(0))
        if grams > missing:
            raise StockError(
                "Kekurangan stok sudah berubah. Periksa ulang pemakaian stok.", 409
            )
        remainder = missing - grams
        if remainder:
            allocation["missing"][code] = remainder
        else:
            allocation["missing"].pop(code, None)
        seen.add(code)
        external.append(
            {
                "ingredient_code": code,
                "name": names.get(code, code),
                "grams": format(grams.normalize(), "f"),
            }
        )
    return external


def advance_plan_version(user, plan):
    """Bump a saved plan after a slot status change, and its clean draft mirror.

    A clean, saved mirror has no unsaved content. Advance only its version
    references; edited drafts stay untouched and must be resolved explicitly.
    """
    mirror = (
        BudgetPlan.objects.select_for_update()
        .filter(user=user, status="draft", source_plan=plan, source_version=plan.version)
        .first()
    )
    if mirror and mirror.inputs == plan.inputs and mirror.snapshot == plan.snapshot:
        mirror.source_version = plan.version + 1
        mirror.version += 1
        mirror.save(update_fields=["source_version", "version", "updated_at"])
    plan.version += 1
    plan.save(update_fields=["version", "updated_at"])


@transaction.atomic
def set_slot_status(user, payload):
    """Skip a planned menu or undo the skip. Cooked menus never change."""
    from django.contrib.auth import get_user_model

    slot_id, status = payload.get("planned_meal"), payload.get("status")
    if type(slot_id) is not int or slot_id < 1 or status not in {"skipped", "planned"}:
        raise StockError("Slot atau status tidak valid.", 400)
    if type(payload.get("version")) is not int:
        raise StockError("Versi rencana wajib diisi.", 400)
    # Same lock order as cooking: user, then plan, then slot.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    stub = PlannedMeal.objects.filter(pk=slot_id, plan__user=user).first()
    if stub is None:
        raise StockError("Menu rencana tidak ditemukan.", 404)
    plan = BudgetPlan.objects.select_for_update().get(pk=stub.plan_id, user=user)
    slot = PlannedMeal.objects.select_for_update().get(pk=slot_id, plan=plan)
    if plan.status != "saved":
        raise StockError("Simpan rencana sebelum mengubah status menu.")
    if plan.version != payload["version"]:
        raise StockError("Menu/rencana sudah berubah. Muat ulang.")
    expected = "planned" if status == "skipped" else "skipped"
    if slot.status != expected:
        raise StockError("Status menu sudah berubah atau sudah dimasak. Muat ulang.")
    slot.status = status
    slot.save(update_fields=["status"])
    advance_plan_version(user, plan)
    return {"status": status, "version": plan.version}


def preview_cooking(user, payload):
    recipe, slot, needs, ingredients, nutrition = cooking_inputs(user, payload)
    allocation = plan_consumption(
        user,
        needs,
        manual=payload.get("manual", []),
        allow_unknown_expiry=payload.get("allow_unknown_expiry", False),
    )
    external = _apply_external_ingredients(payload, needs, ingredients, allocation)
    return {
        "name": recipe.name,
        "ingredients": ingredients,
        "nutrition": nutrition,
        "complete": not allocation["missing"],
        "external_ingredients": external,
        "missing": [
            {"ingredient_code": code, "grams": str(grams)}
            for code, grams in allocation["missing"].items()
        ],
        "batches": [
            {
                "id": row["batch"].pk,
                "name": row["batch"].name,
                "quantity": str(row["quantity"]),
                "unit": row["batch"].unit,
                "grams": str(row["grams"]),
                "manual": row["manual"],
            }
            for row in allocation["allocations"]
        ],
        "manual_batches": [
            {
                "batch_id": b.pk,
                "version": b.version,
                "name": b.name,
                "quantity": str(b.quantity),
                "unit": b.unit,
            }
            for b in allocation["manual_batches"]
        ],
    }


@transaction.atomic
def cook(user, payload):
    # Lock user first, then plan/slot, then stock. Replay precedes stale-version checks.
    event, replay = operation(
        user,
        payload.get("operation_key"),
        "cook",
        {key: value for key, value in payload.items() if key != "operation_key"},
    )
    if replay:
        return event.response
    recipe, slot, needs, ingredients, nutrition = cooking_inputs(user, payload, lock=True)
    allocation = plan_consumption(
        user,
        needs,
        manual=payload.get("manual", []),
        allow_unknown_expiry=payload.get("allow_unknown_expiry", False),
        lock=True,
    )
    external = _apply_external_ingredients(payload, needs, ingredients, allocation)
    response = execute_consumption(
        user,
        needs,
        event,
        manual=payload.get("manual", []),
        allow_unknown_expiry=payload.get("allow_unknown_expiry", False),
        planned=allocation,
    )
    history = CookingHistory.objects.create(
        user=user,
        recipe=recipe,
        planned_meal=slot,
        operation=event,
        recipe_name=recipe.name,
        servings=payload["servings"],
        snapshot={
            "recipe_code": recipe.pk,
            "ingredients": ingredients,
            "nutrition": nutrition,
            "source_url": recipe.source_url,
            "allergens": effective_allergens(user, slot.plan.inputs if slot else {}),
            "allow_unknown_expiry": payload.get("allow_unknown_expiry", False),
            "external_ingredients": external,
        },
    )
    if slot:
        slot.status = "cooked"
        slot.save(update_fields=["status"])
        advance_plan_version(user, slot.plan)
    event.response = {
        **response,
        "history_id": history.pk,
        "name": recipe.name,
        "external_ingredients": external,
    }
    event.save(update_fields=["response"])
    return event.response
