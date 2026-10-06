"""Account-owned plans, immutable saved snapshots, and explicit preview approval."""

import json
import secrets
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from math import ceil

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.preferences import effective_allergens
from apps.catalog.allergens import unsafe_schedule
from apps.catalog.content_policy import protect_recipe_instructions
from apps.catalog.models import Ingredient, Recipe

from .forms import PlannerForm
from .models import BudgetPlan, PlannedMeal, PlanPreview, PlanPreviewQuota, ShoppingListItem
from .planner import budget_preference_notes, build_plan, meal_cost_cap, spend_floor
from .snapshots import decode_value, freeze, thaw


class PlanConflict(ValueError):
    pass


class PreviewRateLimit(ValueError):
    def __init__(self, retry_after):
        self.retry_after = max(1, retry_after)
        super().__init__(
            f"Batas 20 pratinjau per 10 menit tercapai. Coba lagi dalam {self.retry_after} detik."
        )


def account_recent_recipe_codes(user, *, today=None):
    today = today or timezone.localdate()
    return set(
        PlannedMeal.objects.filter(
            plan__user=user,
            scheduled_on__gte=today - timedelta(days=6),
            scheduled_on__lte=today,
        )
        .exclude(status="skipped")
        .values_list("recipe_id", flat=True)
        .distinct()
    )


def cleanup_previews(*, user=None, now=None):
    previews = PlanPreview.objects.filter(
        Q(used_at__isnull=False) | Q(expires_at__lte=now or timezone.now())
    )
    if user is not None:
        previews = previews.filter(plan__user=user)
    deleted, _ = previews.delete()
    return deleted


@transaction.atomic
def reserve_preview(user, *, now=None):
    """Reserve before expensive work; even failed searches consume the attempt.

    Lock the account first, including the first counter creation. Logout and
    parallel requests therefore cannot reset or oversubscribe this quota.
    """
    now = now or timezone.now()
    get_user_model().objects.select_for_update().get(pk=user.pk)
    quota, _ = PlanPreviewQuota.objects.get_or_create(
        user=user, defaults={"window_started_at": now}
    )
    end = quota.window_started_at + timedelta(minutes=10)
    if now >= end:
        quota.window_started_at, quota.attempts = now, 0
        end = now + timedelta(minutes=10)
    if quota.attempts >= 20:
        raise PreviewRateLimit(ceil((end - now).total_seconds()))
    quota.attempts += 1
    quota.save(update_fields=["window_started_at", "attempts"])


def clean_inputs(data):
    if not isinstance(data, Mapping):
        raise ValueError("Parameter rencana harus berupa objek.")
    form = PlannerForm(data)
    if not form.is_valid():
        raise ValueError("Periksa budget, durasi, porsi, waktu makan, target gizi, dan pantangan.")
    return form


def stored_inputs(form):
    values = form.cleaned_data
    return {
        "budget": str(int(values["budget"])),
        "days": values["days"],
        "servings": values["servings"],
        "meal_types": values["meal_types"],
        "targets": values["targets"],
        "exclude_ingredients": ", ".join(values["exclude_ingredients"]),
        "allergens": values.get("allergens", []),
    }


def schedule_codes(result):
    return [
        {meal["type"]: meal["recipe_code"] for meal in day["meals"]} for day in result["schedule"]
    ]


def check_version(plan, version):
    if isinstance(version, bool) or not isinstance(version, int) or version != plan.version:
        raise PlanConflict(
            "Rencana sudah berubah di tab/perangkat lain. Muat ulang sebelum melanjutkan."
        )


def check_draft_state(draft, expected_id, expected_version):
    """An ID as well as a version prevents delete/recreate (ABA) races."""
    if (
        (
            draft is not None
            and (isinstance(expected_version, bool) or not isinstance(expected_version, int))
        )
        or (draft.pk if draft else None) != expected_id
        or (draft.version if draft else None) != expected_version
    ):
        raise PlanConflict("Draft sudah berubah. Muat ulang halaman sebelum melanjutkan.")


def sync_children(plan):
    """Synchronize changed snapshots in batches, keeping stable row identities."""
    result = thaw(plan.snapshot)
    assert_cooked_preserved(plan, plan.inputs, result)
    existing = {(item.day, item.meal_type): item for item in plan.meals.all()}
    created, updated = [], []
    slots = set()
    for day in result["schedule"]:
        for meal in day["meals"]:
            key = (day["number"], meal["type"])
            slots.add(key)
            values = {
                "scheduled_on": plan.starts_on + timedelta(days=key[0] - 1),
                "recipe_id": meal["recipe_code"],
                "servings": plan.inputs["servings"],
                "snapshot": freeze(meal),
            }
            item = existing.get(key)
            if item is not None and item.status == "cooked":
                values["snapshot"] = item.snapshot
            if item is None:
                created.append(PlannedMeal(plan=plan, day=key[0], meal_type=key[1], **values))
            elif any(getattr(item, field) != value for field, value in values.items()):
                if item.recipe_id != values["recipe_id"]:
                    item.status = "planned"
                for field, value in values.items():
                    setattr(item, field, value)
                updated.append(item)
    plan.meals.filter(
        pk__in=[item.pk for key, item in existing.items() if key not in slots]
    ).delete()
    PlannedMeal.objects.bulk_create(created, batch_size=100)
    PlannedMeal.objects.bulk_update(
        updated, ["scheduled_on", "recipe", "servings", "snapshot", "status"], batch_size=100
    )
    existing = {item.ingredient_id: item for item in plan.shopping_items.all()}
    created, updated, ingredients = [], [], set()
    for group in result["shopping_groups"]:
        for row in group["items"]:
            code = row["ingredient_code"]
            ingredients.add(code)
            values = {
                "quantity_grams": Decimal(str(row["quantity"])),
                "estimated_cost": Decimal(str(row["cost"])),
                "snapshot": freeze(row),
            }
            item = existing.get(code)
            if item is None:
                created.append(ShoppingListItem(plan=plan, ingredient_id=code, **values))
            elif any(getattr(item, field) != value for field, value in values.items()):
                for field, value in values.items():
                    setattr(item, field, value)
                updated.append(item)
    plan.shopping_items.filter(
        pk__in=[item.pk for code, item in existing.items() if code not in ingredients]
    ).delete()
    ShoppingListItem.objects.bulk_create(created, batch_size=100)
    ShoppingListItem.objects.bulk_update(
        updated, ["quantity_grams", "estimated_cost", "snapshot"], batch_size=100
    )


def reschedule_meals(plan):
    changed = []
    for item in plan.meals.all():
        scheduled_on = plan.starts_on + timedelta(days=item.day - 1)
        if item.scheduled_on != scheduled_on:
            item.scheduled_on = scheduled_on
            changed.append(item)
    PlannedMeal.objects.bulk_update(changed, ["scheduled_on"], batch_size=100)


def cooked_slots(plan, *, include_source=True):
    slots = list(plan.meals.filter(status="cooked"))
    if include_source and plan.status == "draft" and plan.source_plan_id:
        slots.extend(plan.source_plan.meals.filter(status="cooked"))
    return slots


def assert_editable(plan, *, include_source=True):
    if cooked_slots(plan, include_source=include_source):
        raise PlanConflict(
            "Rencana ini sudah memiliki menu yang dimasak. Buat rencana baru agar riwayatnya tetap utuh."
        )


def assert_cooked_preserved(plan, inputs, result, *, include_source=True):
    """Only an uncooked slot may change; cooked content is immutable, dates are not."""
    slots = {
        (day["number"], meal["type"]): meal for day in result["schedule"] for meal in day["meals"]
    }
    for item in cooked_slots(plan, include_source=include_source):
        meal = slots.get((item.day, item.meal_type))
        if (
            meal is None
            or item.recipe_id != meal["recipe_code"]
            or item.servings != inputs["servings"]
            or freeze(protect_recipe_instructions(thaw(item.snapshot))) != freeze(meal)
        ):
            raise PlanConflict(
                "Menu yang sudah dimasak tidak boleh diubah/dihapus. Ganti slot lain."
            )


@transaction.atomic
def write_draft(
    user,
    inputs,
    result,
    *,
    previous=None,
    expected_version=None,
    source=None,
    replace_draft=False,
    expected_draft_id=None,
    expected_draft_version=None,
):
    # Serializes the first-draft creation as well as concurrent writes across devices.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    inputs = {
        **inputs,
        "allergens": effective_allergens(user, inputs, previous.inputs if previous else {}),
    }
    if unsafe_schedule(schedule_codes(result), inputs["allergens"]):
        raise PlanConflict(
            "Menu tidak sesuai alergi terbaru atau mengandung bahan belum ditinjau. Buat rencana baru."
        )
    draft = BudgetPlan.objects.select_for_update().filter(user=user, status="draft").first()
    if previous is not None:
        try:
            current = BudgetPlan.objects.select_for_update().get(pk=previous.pk, user=user)
        except BudgetPlan.DoesNotExist as exc:
            raise PlanConflict("Rencana sudah dihapus. Muat ulang halaman.") from exc
        check_version(current, expected_version)
        previous = current
        assert_cooked_preserved(previous, inputs, result)
    if previous is None:
        check_draft_state(draft, expected_draft_id, expected_draft_version)
        if draft and replace_draft is not True:
            raise PlanConflict(
                "Masih ada draft. Simpan draft atau setujui penggantian melalui Rencana Baru."
            )
    snapshot_changed = draft is None or draft.snapshot != freeze(result) or draft.inputs != inputs
    previous_date = draft.starts_on if draft else None
    if draft:
        if previous is not None and previous.status == "draft" and draft.pk != previous.pk:
            raise PlanConflict("Draft sudah diganti. Muat ulang halaman.")
        if (
            previous is not None
            and previous.status == "saved"
            and (
                draft.source_plan_id != previous.pk
                or draft.source_version != previous.version
                or draft.snapshot != previous.snapshot
                or draft.inputs != previous.inputs
            )
        ):
            raise PlanConflict(
                "Masih ada perubahan draft yang belum disimpan. Simpan atau hapus draft itu sebelum mengubah rencana tersimpan."
            )
        assert_cooked_preserved(draft, inputs, result, include_source=previous is not None)
        draft.version += 1
        draft.inputs, draft.snapshot = inputs, freeze(result)
        draft.source_plan = source
        draft.source_version = (
            previous.source_version
            if previous is not None
            and previous.status == "draft"
            and previous.source_plan_id == (source.pk if source else None)
            else source.version
            if source
            else None
        )
        if source:
            draft.title, draft.starts_on = source.title, source.starts_on
        elif previous is None:
            draft.title, draft.starts_on = "Rencana Makan Saya", timezone.localdate()
        draft.save()
    else:
        draft = BudgetPlan.objects.create(
            user=user,
            inputs=inputs,
            snapshot=freeze(result),
            starts_on=source.starts_on if source else timezone.localdate(),
            title=source.title if source else "Rencana Makan Saya",
            source_plan=source,
            source_version=source.version if source else None,
        )
    if snapshot_changed:
        sync_children(draft)
    elif previous_date != draft.starts_on:
        reschedule_meals(draft)
    return draft


def make_preview(plan, version, payload):
    check_version(plan, version)
    action = payload.get("action")
    if not isinstance(action, str):
        raise ValueError("Aksi pratinjau tidak valid.")
    old = thaw(plan.snapshot)
    inputs = {**plan.inputs, "allergens": effective_allergens(plan.user, plan.inputs)}
    form = clean_inputs(inputs)
    if action == "replace":
        day, meal_type, recipe = payload.get("day"), payload.get("meal"), payload.get("recipe")
        if (
            isinstance(day, bool)
            or not isinstance(day, int)
            or not 1 <= day <= len(old["schedule"])
        ):
            raise ValueError("Hari tidak valid.")
        slots = schedule_codes(old)
        if (
            not isinstance(meal_type, str)
            or meal_type not in slots[day - 1]
            or not isinstance(recipe, str)
        ):
            raise ValueError("Waktu makan atau resep tidak valid.")
        if recipe == slots[day - 1][meal_type]:
            raise ValueError("Pilih menu yang berbeda.")
        if any(item.day == day and item.meal_type == meal_type for item in cooked_slots(plan)):
            raise PlanConflict("Menu yang sudah dimasak tidak dapat diganti.")
        # Other menu codes are fixed, not regenerated by the optimizer.
        slots[day - 1][meal_type] = recipe
        reserve_preview(plan.user)
        cleanup_previews(user=plan.user)
        result = build_plan(**form.cleaned_data, fixed_schedule=slots)
    elif action in {"regenerate", "parameters"}:
        assert_editable(plan)
        if action == "parameters":
            form = clean_inputs(payload.get("inputs", {}))
            form.cleaned_data["allergens"] = effective_allergens(
                plan.user, plan.inputs, form.cleaned_data
            )
            inputs = stored_inputs(form)
        prior = {
            meal: [slots.get(meal) for slots in schedule_codes(old)]
            for meal in form.cleaned_data["meal_types"]
        }
        reserve_preview(plan.user)
        cleanup_previews(user=plan.user)
        result = build_plan(
            **form.cleaned_data,
            recent_recipe_codes=account_recent_recipe_codes(plan.user)
            | set(old["planned_recipe_codes"]),
            prior_slot_recipes=prior,
            seed=secrets.randbits(32),
        )
        if not result["within_budget"]:
            raise ValueError(
                "Belum ada susunan baru yang sesuai budget. Ubah parameter atau pilih menu lain."
            )
        if action == "regenerate" and schedule_codes(result) == schedule_codes(old):
            raise ValueError(
                "Belum ada susunan alternatif yang memenuhi syarat. Menu lama tetap dipertahankan."
            )
    else:
        raise ValueError("Aksi pratinjau tidak dikenal.")
    if action == "replace":
        # Re-quoting the schedule must not rewrite a cooked meal's historical
        # metadata merely because current catalog/review fields have changed.
        cooked = {(item.day, item.meal_type): item for item in cooked_slots(plan)}
        for day in result["schedule"]:
            for index, meal in enumerate(day["meals"]):
                item = cooked.get((day["number"], meal["type"]))
                if item:
                    day["meals"][index] = protect_recipe_instructions(thaw(item.snapshot))
    draft = BudgetPlan.objects.filter(user=plan.user, status="draft").first()
    return PlanPreview.objects.create(
        plan=plan,
        version=version,
        inputs=inputs,
        snapshot=freeze(result),
        draft_id=draft.pk if draft else None,
        draft_version=draft.version if draft else None,
        expires_at=timezone.now() + timedelta(minutes=15),
    )


@transaction.atomic
def apply_preview(user, preview_id, *, new_budget=None):
    # Use a consistent lock order: account -> plan -> preview.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    stub = PlanPreview.objects.get(pk=preview_id, plan__user=user)
    plan = BudgetPlan.objects.select_for_update().get(pk=stub.plan_id, user=user)
    preview = PlanPreview.objects.select_for_update().get(pk=preview_id)
    check_version(plan, preview.version)
    current_draft = BudgetPlan.objects.filter(user=user, status="draft").first()
    if plan.status == "saved":
        check_draft_state(current_draft, preview.draft_id, preview.draft_version)
    if preview.used_at or preview.expires_at <= timezone.now():
        raise PlanConflict("Pratinjau sudah digunakan atau kedaluwarsa. Buat pratinjau baru.")
    result = thaw(preview.snapshot)
    assert_cooked_preserved(plan, preview.inputs, result)
    inputs = preview.inputs.copy()
    inputs["allergens"] = effective_allergens(user, plan.inputs, inputs)
    if unsafe_schedule(schedule_codes(result), inputs["allergens"]):
        raise PlanConflict(
            "Pratinjau tidak sesuai alergi terbaru atau ada bahan belum ditinjau. Buat pratinjau baru; rencana lama tidak diubah."
        )
    if result["total"] > Decimal(inputs["budget"]):
        if new_budget is None:
            raise ValueError(
                "Estimasi melewati budget. Setujui kenaikan budget atau pilih menu lain."
            )
        form = clean_inputs({**inputs, "budget": str(new_budget)})
        if form.cleaned_data["budget"] < result["total"]:
            raise ValueError("Budget baru masih di bawah estimasi belanja.")
        inputs = stored_inputs(form)
        budget = form.cleaned_data["budget"]
        result.update(within_budget=True, difference=int(budget) - result["total"])
        cap = meal_cost_cap(budget, len(result["schedule"]), result["meal_count"])
        result.update(
            spend_floor=spend_floor(budget),
            spend_floor_relaxed=result["total"] < spend_floor(budget),
            meal_cost_cap=cap,
            meal_cost_cap_relaxed=any(
                meal["cost"] > cap for day in result["schedule"] for meal in day["meals"]
            ),
        )
        result["preference_notes"] = budget_preference_notes(
            result["schedule"], result["total"], budget
        )
    elif new_budget is not None:
        raise ValueError("Kenaikan budget tidak diperlukan untuk pratinjau ini.")
    draft = write_draft(
        user,
        inputs,
        result,
        previous=plan,
        expected_version=preview.version,
        source=plan if plan.status == "saved" else plan.source_plan,
    )
    preview.used_at = timezone.now()
    preview.save(update_fields=["used_at"])
    return draft


@transaction.atomic
def save_plan(user, plan_id, version, title, starts_on, *, replace_original=False):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    plan = BudgetPlan.objects.select_for_update().get(pk=plan_id, user=user)
    if (
        plan.status == "draft"
        and not isinstance(version, bool)
        and isinstance(version, int)
        and plan.last_saved_version == version
        and plan.version == version + 1
        and plan.last_saved_plan_id
        and plan.title == title
        and plan.starts_on == starts_on
    ):
        return plan.last_saved_plan
    check_version(plan, version)
    if not thaw(plan.snapshot)["within_budget"]:
        raise ValueError("Rencana belum memenuhi budget.")
    if plan.status == "saved":
        date_changed = starts_on != plan.starts_on
        plan.title, plan.starts_on = title, starts_on
        plan.version += 1
        plan.save()
        if date_changed:
            reschedule_meals(plan)
        return plan
    if replace_original:
        if not plan.source_plan_id:
            raise ValueError("Draft ini tidak berasal dari rencana tersimpan.")
        saved = BudgetPlan.objects.select_for_update().get(
            pk=plan.source_plan_id, user=user, status="saved"
        )
        check_version(saved, plan.source_version)
        assert_cooked_preserved(saved, plan.inputs, thaw(plan.snapshot))
        snapshot_changed = saved.snapshot != plan.snapshot or saved.inputs != plan.inputs
        date_changed = saved.starts_on != starts_on
        saved.inputs, saved.snapshot = plan.inputs, plan.snapshot
        saved.title, saved.starts_on = title, starts_on
        saved.version += 1
        saved.save()
        if snapshot_changed:
            sync_children(saved)
        elif date_changed:
            reschedule_meals(saved)
    else:
        assert_editable(plan)
        saved = BudgetPlan.objects.create(
            user=user,
            status="saved",
            title=title,
            starts_on=starts_on,
            inputs=plan.inputs,
            snapshot=plan.snapshot,
        )
        sync_children(saved)
    date_changed = plan.starts_on != starts_on
    plan.title, plan.starts_on = title, starts_on
    plan.last_saved_plan, plan.last_saved_version = saved, plan.version
    plan.version += 1
    plan.source_plan, plan.source_version = saved, saved.version
    plan.save()
    if date_changed:
        reschedule_meals(plan)
    return saved


@transaction.atomic
def adopt_guest_result(request):
    """Called only after successful login/signup; never auto-saves a permanent plan."""
    saved = request.session.get("guest_last_plan")
    if not saved:
        return
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    if not saved or BudgetPlan.objects.filter(user=request.user, status="draft").exists():
        return
    try:
        form = clean_inputs(saved["inputs"])
        form.cleaned_data["allergens"] = effective_allergens(request.user, form.cleaned_data)
        result = json.loads(saved["result"], object_hook=decode_value)
        if not isinstance(result, dict) or not isinstance(result.get("schedule"), list):
            return
    except (ValueError, TypeError, KeyError):
        # A stale/invalid guest snapshot must never prevent successful login.
        return
    if any(
        "ingredient_code" not in item
        for group in result.get("shopping_groups", [])
        for item in group["items"]
    ):
        # Upgrade older session snapshots without guessing ingredient identities.
        try:
            result = build_plan(**form.cleaned_data, fixed_schedule=schedule_codes(result))
        except ValueError:
            return
    if unsafe_schedule(schedule_codes(result), form.cleaned_data["allergens"]):
        return
    if result.get("within_budget"):
        recipe_codes = {code for slots in schedule_codes(result) for code in slots.values()}
        ingredient_codes = {
            item["ingredient_code"]
            for group in result["shopping_groups"]
            for item in group["items"]
        }
        if Recipe.objects.filter(pk__in=recipe_codes).count() != len(
            recipe_codes
        ) or Ingredient.objects.filter(pk__in=ingredient_codes).count() != len(ingredient_codes):
            return
        write_draft(request.user, stored_inputs(form), result)
    request.session.pop("guest_last_plan", None)
