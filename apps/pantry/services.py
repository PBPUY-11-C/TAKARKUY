"""Transactional stock services. User lock precedes operation and batch locks."""

import hashlib
import json
from datetime import timedelta
from decimal import ROUND_UP, Decimal, InvalidOperation
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import UnitConversion

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


def movement(item, operation, kind, before, *, consumed_grams=None):
    PantryMovement.objects.create(
        batch=item,
        operation=operation,
        kind=kind,
        quantity_before=Decimal(before.get("quantity") or "0"),
        quantity_after=item.quantity,
        consumed_grams=consumed_grams,
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


def plan_consumption(
    user, requirements, *, manual=None, allow_unknown_expiry=False, lock=False, preview_batches=None
):
    """One allocation algorithm for previews and execution; previews reserve nothing.

    Manual rows identify a batch/version and declare grams per native unit when
    no conversion exists. Known conversions cannot be overridden. Expired stock
    is never eligible, even with consent to unknown expiry dates.
    """
    if not isinstance(requirements, dict) or len(requirements) > 100:
        raise StockError("Kebutuhan bahan tidak valid.", 400)
    try:
        needs = {code: Decimal(str(value)) for code, value in requirements.items()}
        if any(
            not isinstance(code, str) or not n.is_finite() or not 0 < n <= 100000000
            for code, n in needs.items()
        ):
            raise ValueError
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise StockError("Kebutuhan gram tidak valid.", 400) from exc
    manual = manual if manual is not None else []
    if not isinstance(manual, list) or len(manual) > 100:
        raise StockError("Pilihan batch tidak valid.", 400)
    query = PantryItem.objects.filter(
        user=user, archived_at__isnull=True, quantity__gt=0, ingredient_id__in=needs
    ).exclude(estimated_expires_on__lt=timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")))
    if not allow_unknown_expiry:
        query = query.filter(estimated_expires_on__isnull=False).exclude(expiry_source="unknown")
    query = query.order_by(F("estimated_expires_on").asc(nulls_last=True), "pk")
    if lock:
        query = query.select_for_update()
    if preview_batches is not None:
        if lock:
            raise ValueError("Eksekusi wajib membaca ulang stok terkunci.")
        today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
        batches = [
            b
            for b in preview_batches
            if (
                b.user_id == user.pk
                and b.ingredient_id in needs
                and b.archived_at is None
                and b.quantity > 0
                and (b.estimated_expires_on is None or b.estimated_expires_on >= today)
                and (
                    allow_unknown_expiry
                    or (b.estimated_expires_on is not None and b.expiry_source != "unknown")
                )
            )
        ]
    else:
        batches = list(query)
    by_id = {batch.pk: batch for batch in batches}
    allocations, selected = [], set()
    for row in manual:
        if not isinstance(row, dict) or type(row.get("batch_id")) is not int:
            raise StockError("Pilihan batch tidak valid.", 400)
        batch = by_id.get(row["batch_id"])
        if batch is None or batch.pk in selected:
            raise StockError("Batch pilihan sudah berubah/tidak tersedia. Muat ulang.")
        check_version(batch, row.get("version"))
        try:
            taken = Decimal(str(row.get("quantity")))
            weight = Decimal(str(row.get("grams_per_unit")))
            if (
                not taken.is_finite()
                or not weight.is_finite()
                or not Decimal("0.000001") <= weight <= 1000000
                or not 0 < taken <= batch.quantity
                or taken.as_tuple().exponent < -6
            ):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise StockError(
                "Jumlah/berat batch manual tidak valid (maksimal 6 desimal).", 400
            ) from exc
        if batch.grams_per_unit and weight != batch.grams_per_unit:
            raise StockError("Konversi katalog tidak boleh ditimpa saat memasak.", 400)
        grams = taken * weight
        # Permit only the rounding of one native-unit microstep, not arbitrary overuse.
        if grams > needs[batch.ingredient_id] + weight * Decimal("0.000001"):
            raise StockError("Pemakaian manual melebihi kebutuhan resep.", 400)
        needs[batch.ingredient_id] -= grams
        selected.add(batch.pk)
        allocations.append({"batch": batch, "quantity": taken, "grams": grams, "manual": True})
    for batch in batches:
        remaining = needs[batch.ingredient_id]
        if batch.pk in selected or remaining <= 0 or not batch.grams_per_unit:
            continue
        taken = min(
            batch.quantity,
            (remaining / batch.grams_per_unit).quantize(Decimal("0.000001"), rounding=ROUND_UP),
        )
        grams = taken * batch.grams_per_unit
        needs[batch.ingredient_id] -= grams
        allocations.append({"batch": batch, "quantity": taken, "grams": grams, "manual": False})
    return {
        "allocations": allocations,
        "missing": {code: grams for code, grams in needs.items() if grams > 0},
        "manual_batches": [batch for batch in batches if not batch.grams_per_unit],
    }


def execute_consumption(user, requirements, event, *, manual=None, allow_unknown_expiry=False):
    """Caller holds the account lock and transaction, then we lock FEFO batches."""
    plan = plan_consumption(
        user, requirements, manual=manual, allow_unknown_expiry=allow_unknown_expiry, lock=True
    )
    if plan["missing"]:
        raise StockError("Stok terkonversi yang belum kedaluwarsa tidak cukup.")
    changes = []
    for row in plan["allocations"]:
        batch = row["batch"]
        before = snapshot(batch)
        batch.quantity -= row["quantity"]
        batch.version += 1
        batch.save(update_fields=["quantity", "version", "updated_at"])
        movement(batch, event, "consume", before, consumed_grams=row["grams"])
        changes.append(
            {
                "batch_id": batch.pk,
                "quantity": str(row["quantity"]),
                "grams": str(row["grams"]),
                "manual": row["manual"],
            }
        )
    return {"consumed": changes}


def recipe_matches(user, servings=1):
    """Read-only bridge to Recipe Book; matching does not reserve/deduct stock."""
    from apps.catalog.content_policy import protect_recipe_instructions
    from apps.recipe_book.services import recipe_query, recipe_requirements

    totals = available_grams(user)
    matches = []
    if not totals:
        return matches
    recipes = recipe_query(user).prefetch_related(
        "recipeingredient_set__ingredient", "recipetag_set"
    )
    for recipe in recipes:
        if not recipe.base_servings or not any(
            tag.tag == "halal" for tag in recipe.recipetag_set.all()
        ):
            continue
        try:
            required, _, _ = recipe_requirements(recipe, servings)
        except StockError:
            continue
        if not required:
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
    event.response = execute_consumption(
        user, needs, event, allow_unknown_expiry=allow_unknown_expiry
    )
    event.save(update_fields=["response"])
    return event.response


def session_scope(user):
    """Compatibility session column for a user's batches; authorization uses the FK."""
    return uuid5(NAMESPACE_URL, f"takarkuy:pantry-user:{user.pk}").hex


# Catalog category -> pantry category, and the storage tried first for it.
PURCHASE_CATEGORY = {
    "sayur": "sayur_buah",
    "buah": "sayur_buah",
    "karbohidrat": "beras_karbohidrat",
    "bumbu": "bumbu_minyak",
    "lemak": "bumbu_minyak",
}
FRESH_LOCATIONS = ("chiller", "freezer", "suhu_ruang")


def purchase_category(ingredient):
    if ingredient.category == "protein":
        code = ingredient.pk
        if any(word in code for word in ("TAHU", "TEMPE", "KACANG")):
            return "tahu_tempe_kacang"
        return "lainnya" if "TELUR" in code else "daging_seafood"
    return PURCHASE_CATEGORY.get(ingredient.category, "lainnya")


def add_purchases(user, rows, event):
    """Create one batch per bought catalog ingredient (grams), like manual input.

    Must be called inside atomic after operation(). Expiry comes from the local
    shelf-life reference for the first location that has one; fresh food tries
    the fridge first. Without a reference the date stays unknown, never guessed.
    """
    from .catalog_context import everyday_ingredient_name
    from .storage import DEFAULT_LOCATION, expiry_estimate, shelf_life_duration, storage_options

    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
    items = []
    for ingredient, grams in rows:
        options = storage_options(ingredient.pk)
        order = (
            FRESH_LOCATIONS
            if ingredient.category in {"protein", "sayur", "buah"}
            else (DEFAULT_LOCATION, "chiller", "freezer")
        )
        location = next((place for place in order if place in options), DEFAULT_LOCATION)
        days = expiry_estimate(options, location, today)["shelf_life_days"]
        expires_on = today + timedelta(days=days) if days is not None else None
        item = PantryItem(
            user=user,
            session_id=session_scope(user),
            source="manual",
            name=everyday_ingredient_name(ingredient.name),
            category=purchase_category(ingredient),
            quantity=grams,
            unit="g",
            location=location,
            ingredient_id=ingredient.pk,
            starting_on=today,
            estimated_expires_on=expires_on,
            expiry_source="estimate" if expires_on else "unknown",
            shelf_life_days=shelf_life_duration(today, expires_on),
        )
        refresh_conversion(item)
        item.save()
        movement(item, event, "in", {})
        items.append(item)
    return items
