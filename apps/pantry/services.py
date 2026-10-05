"""Transactional stock services. User lock precedes operation and batch locks."""

import hashlib
import json
from decimal import ROUND_UP, Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import Recipe, UnitConversion

from .models import PantryItem, PantryLLMUsage, PantryMovement, PantryOperation


class StockError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def reserve_llm(user, kind):
    """Count paid attempts, including errors, across devices before making the call."""
    if user is None or kind not in {"photo", "names"}:
        raise StockError("Akun diperlukan untuk AI.", 400)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        usage, _ = PantryLLMUsage.objects.get_or_create(
            user=user, kind=kind, day=timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
        )
        updated = PantryLLMUsage.objects.filter(pk=usage.pk, attempts__lt=10).update(
            attempts=F("attempts") + 1
        )
        if not updated:
            raise StockError("Batas AI hari ini tercapai. Coba lagi besok.", 429)


def conversion(unit, ingredient_id, pack_weight_g=None):
    base = "g" if unit in {"g", "kg"} else "ml" if unit in {"ml", "liter"} else "pcs"
    if unit in {"g", "kg"}:
        return base, Decimal(1 if unit == "g" else 1000), "Satuan berat."
    if pack_weight_g is not None and base == "pcs":
        return base, pack_weight_g, "Berat per unit diisi pengguna."
    records = (
        UnitConversion.objects.filter(ingredient_id=ingredient_id, unit=unit).order_by(
            "conversion_code"
        )
        if ingredient_id
        else []
    )
    for record in records:
        if record.conversion_status not in {
            "standard",
            "size_specific",
            "manual_curated",
            "reviewed",
        }:
            continue
        weight = Decimal(str(record.gram_equivalent or 0))
        if weight.is_finite() and 0 < weight < Decimal("1000000"):
            return base, weight, (record.note or f"Konversi katalog: {record.source}")[:255]
    return base, None, "Belum ada konversi berat; tidak dihitung untuk resep."


def refresh_conversion(item):
    item.base_unit, item.grams_per_unit, item.conversion_note = conversion(
        item.unit, item.ingredient_id, item.pack_weight_g
    )


def snapshot(item):
    return {
        field: str(getattr(item, field)) if getattr(item, field) is not None else ""
        for field in (
            "name",
            "category",
            "source",
            "quantity",
            "unit",
            "base_unit",
            "ingredient_id",
            "location",
            "starting_on",
            "estimated_expires_on",
            "expiry_source",
            "pack_weight_g",
            "grams_per_unit",
            "conversion_note",
            "archived_at",
            "version",
        )
    }


def movement(item, operation, kind, before):
    PantryMovement.objects.create(
        batch=item,
        operation=operation,
        kind=kind,
        quantity_before=Decimal(before.get("quantity") or "0"),
        quantity_after=item.quantity,
        snapshot={"before": before, "after": snapshot(item)},
    )


def operation(user, key, kind, payload):
    """Must be called inside atomic. Same key + different payload is a conflict."""
    try:
        key = UUID(str(key))
    except (ValueError, TypeError, AttributeError) as exc:
        raise StockError("operation_key UUID wajib diisi.", 400) from exc
    get_user_model().objects.select_for_update().get(pk=user.pk)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    event, created = PantryOperation.objects.get_or_create(
        user=user, key=key, defaults={"kind": kind, "payload_hash": digest}
    )
    if event.kind != kind or event.payload_hash != digest:
        raise StockError("Kunci aksi telah dipakai untuk perubahan berbeda.")
    return event, not created


def check_version(item, version):
    if type(version) is not int or version < 1:
        raise StockError("version wajib diisi sebagai bilangan bulat.", 400)
    if item.version != version:
        raise StockError("Stok sudah berubah di tab lain. Muat ulang sebelum mengedit.")


def eligible_stock(user, *, allow_unknown_expiry=False):
    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
    query = PantryItem.objects.filter(
        user=user,
        archived_at__isnull=True,
        quantity__gt=0,
        ingredient__isnull=False,
        grams_per_unit__gt=0,
    ).exclude(estimated_expires_on__lt=today)
    if not allow_unknown_expiry:
        query = query.filter(estimated_expires_on__isnull=False).exclude(expiry_source="unknown")
    return query


def available_grams(user, *, allow_unknown_expiry=False):
    totals = {}
    for batch in eligible_stock(user, allow_unknown_expiry=allow_unknown_expiry):
        totals[batch.ingredient_id] = (
            totals.get(batch.ingredient_id, Decimal(0)) + batch.quantity * batch.grams_per_unit
        )
    return totals


def recipe_matches(user, servings=1):
    """Read-only bridge to Recipe Book; matching does not reserve/deduct stock."""
    from apps.budget_planner.planner import purchase_grams
    from apps.catalog.content_policy import protect_recipe_instructions

    totals = available_grams(user)
    matches = []
    if not totals:
        return matches
    recipes = Recipe.objects.filter(is_active=True, is_plannable=True).prefetch_related(
        "recipeingredient_set", "recipetag_set"
    )
    for recipe in recipes:
        if not recipe.base_servings or not any(
            tag.tag == "halal" for tag in recipe.recipetag_set.all()
        ):
            continue
        required = {}
        valid = True
        for link in recipe.recipeingredient_set.all():
            if link.is_optional:
                continue
            if link.unit != "g" or link.quantity is None or link.quantity <= 0:
                valid = False
                break
            grams = purchase_grams(link) * Decimal(servings) / Decimal(recipe.base_servings)
            if not grams.is_finite() or grams <= 0:
                valid = False
                break
            required[link.ingredient_id] = required.get(link.ingredient_id, Decimal(0)) + grams
        if not valid or not required:
            continue
        covered = sum(
            min(totals.get(code, 0), grams) / grams for code, grams in required.items()
        ) / len(required)
        if covered == 0:
            continue
        result = protect_recipe_instructions({"recipe_code": recipe.pk})
        result.update(
            name=recipe.name,
            complete=all(totals.get(code, 0) >= grams for code, grams in required.items()),
            coverage=float(covered),
            missing=[
                {"ingredient_code": code, "grams": str(grams - totals.get(code, 0))}
                for code, grams in required.items()
                if grams > totals.get(code, 0)
            ],
        )
        matches.append(result)
    return sorted(matches, key=lambda row: (-row["coverage"], row["name"]))[:20]


@transaction.atomic
def consume_stock(user, requirements, consumption_key, *, allow_unknown_expiry=False):
    """Internal cooking integration: all-or-nothing FEFO, idempotent across batches.

    Unknown dates require explicit caller confirmation. This is not a food-safety check.
    """
    if not isinstance(requirements, dict) or not requirements or len(requirements) > 100:
        raise StockError("Kebutuhan bahan tidak valid.", 400)
    try:
        needs = {code: Decimal(str(value)) for code, value in requirements.items()}
        if any(
            not isinstance(code, str) or not value.is_finite() or value <= 0 or value > 100000000
            for code, value in needs.items()
        ):
            raise ValueError
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise StockError("Kebutuhan gram harus positif dan valid.", 400) from exc
    event, replay = operation(
        user, consumption_key, "consume", {"needs": needs, "allow_unknown": allow_unknown_expiry}
    )
    if replay:
        return event.response
    batches = list(
        eligible_stock(user, allow_unknown_expiry=allow_unknown_expiry)
        .filter(ingredient_id__in=needs)
        .order_by(F("estimated_expires_on").asc(nulls_last=True), "pk")
        .select_for_update()
    )
    totals = {}
    for batch in batches:
        totals[batch.ingredient_id] = (
            totals.get(batch.ingredient_id, Decimal(0)) + batch.quantity * batch.grams_per_unit
        )
    if any(totals.get(code, 0) < grams for code, grams in needs.items()):
        raise StockError("Stok terkonversi yang belum kedaluwarsa tidak cukup.")
    changes = []
    for batch in batches:
        required = needs[batch.ingredient_id]
        if required <= 0:
            continue
        before = snapshot(batch)
        taken = min(
            batch.quantity,
            (required / batch.grams_per_unit).quantize(Decimal("0.000001"), rounding=ROUND_UP),
        )
        batch.quantity -= taken
        batch.version += 1
        batch.save(update_fields=["quantity", "version", "updated_at"])
        movement(batch, event, "consume", before)
        grams = taken * batch.grams_per_unit
        needs[batch.ingredient_id] -= grams
        changes.append({"batch_id": batch.pk, "quantity": str(taken), "grams": str(grams)})
    event.response = {"consumed": changes}
    event.save(update_fields=["response"])
    return event.response
