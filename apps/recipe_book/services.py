"""Recipe Book queries and transactional cooking. No stock reservations."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q

from apps.accounts.choices import ALLERGEN_KEYS
from apps.accounts.preferences import effective_allergens, profile_for
from apps.budget_planner.models import BudgetPlan, PlannedMeal
from apps.budget_planner.planner import purchase_grams
from apps.catalog.allergens import recipe_allowed
from apps.catalog.models import Recipe
from apps.pantry.services import StockError, execute_consumption, operation, plan_consumption

from .models import CookingHistory

# Curated by ingredient ID, not name matching. Never omitted from allergy screening.
# Oil is deliberately NOT a staple: larger amounts are meaningful recipe stock.
STAPLES = frozenset({"ING-GARAM", "ING-MERICA", "ING-AIR"})


def estimated_recipe_cost(recipe, servings):
    """Use the planner's basket quote, including whole-fruit rounding."""
    from apps.budget_planner.planner import _load_candidates, quote_schedule

    try:
        catalog = _load_candidates([recipe.meal_type], servings, [])
        quote = quote_schedule(
            [{recipe.meal_type: recipe.pk}], servings=servings, targets=[], catalog=catalog
        )
        return quote["total"]
    except ValueError:
        return None


def recipe_query(user, *, allergens=None):
    query = Recipe.objects.filter(
        is_active=True, is_plannable=True, recipetag__tag="halal"
    ).distinct()
    groups = effective_allergens(user) if allergens is None else allergens
    if not set(groups) <= ALLERGEN_KEYS:
        raise ValueError("Kelompok alergi tidak valid.")
    if groups:
        query = query.filter(allergen_reviewed=True).exclude(allergen_groups__group__in=groups)
    avoided = profile_for(user).avoided_ingredients.values_list("pk", flat=True)
    return query.exclude(recipeingredient__ingredient_id__in=avoided)


def with_guidance(query):
    return (
        query.filter(instruction_status__in=["source_ok", "authored_reviewed"])
        .exclude(instructions="")
        .exclude(Q(recipe_code__startswith="RCP-MDL-") & Q(instruction_review_note=""))
        .exclude(Q(instruction_status="authored_reviewed", instruction_reviewed_on__isnull=True))
        .exclude(Q(recipe_code__startswith="RCP-MDL-", instruction_reviewed_on__isnull=True))
    )


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


def recipe_requirements(recipe, servings, *, include_staples=False):
    if type(servings) is not int or not 1 <= servings <= 10:
        raise StockError("Porsi harus bilangan bulat 1–10.", 400)
    if not recipe.base_servings:
        raise StockError("Porsi dasar resep belum tersedia.", 400)
    needs, ingredients = {}, []
    nutrition = {key: Decimal(0) for key in ("calories", "protein", "carbs", "fat")}
    for link in recipe.recipeingredient_set.all():
        try:
            grams = purchase_grams(link) * Decimal(servings) / Decimal(recipe.base_servings)
            if link.unit != "g" or not grams.is_finite() or grams <= 0:
                raise ValueError
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise StockError("Takaran resep belum dapat dikonversi ke gram.", 400) from exc
        tracked = not link.is_optional and (include_staples or link.ingredient_id not in STAPLES)
        ingredients.append(
            {
                "ingredient_code": link.ingredient_id,
                "name": link.ingredient.name,
                "grams": str(grams),
                "tracked": tracked,
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
    for field in ("include_staples", "allow_unknown_expiry"):
        if type(payload.get(field, False)) is not bool:
            raise StockError("Pilihan konfirmasi tidak valid.", 400)
    recipe = get_recipe(user, code, inputs=plan.inputs if plan else None)
    needs, ingredients, nutrition = recipe_requirements(
        recipe, payload.get("servings"), include_staples=payload.get("include_staples", False)
    )
    return recipe, slot, needs, ingredients, nutrition


def preview_cooking(user, payload):
    recipe, slot, needs, ingredients, nutrition = cooking_inputs(user, payload)
    allocation = plan_consumption(
        user,
        needs,
        manual=payload.get("manual", []),
        allow_unknown_expiry=payload.get("allow_unknown_expiry", False),
    )
    return {
        "name": recipe.name,
        "ingredients": ingredients,
        "nutrition": nutrition,
        "complete": not allocation["missing"],
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
    response = execute_consumption(
        user,
        needs,
        event,
        manual=payload.get("manual", []),
        allow_unknown_expiry=payload.get("allow_unknown_expiry", False),
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
        },
    )
    if slot:
        slot.status = "cooked"
        slot.save(update_fields=["status"])
        # A clean, saved mirror has no unsaved content. Advance only its version
        # references; edited drafts stay untouched and must be resolved explicitly.
        mirror = (
            BudgetPlan.objects.select_for_update()
            .filter(
                user=user, status="draft", source_plan=slot.plan, source_version=slot.plan.version
            )
            .first()
        )
        if mirror and mirror.inputs == slot.plan.inputs and mirror.snapshot == slot.plan.snapshot:
            mirror.source_version = slot.plan.version + 1
            mirror.version += 1
            mirror.save(update_fields=["source_version", "version", "updated_at"])
        slot.plan.version += 1
        slot.plan.save(update_fields=["version", "updated_at"])
    event.response = {**response, "history_id": history.pk, "name": recipe.name}
    event.save(update_fields=["response"])
    return event.response
