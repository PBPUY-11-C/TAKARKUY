import json
import secrets
from functools import wraps
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_cache_control

from apps.accounts.preferences import effective_allergens, planner_defaults
from apps.catalog.allergens import unsafe_schedule

from .forms import PlanMetadataForm, PlannerForm
from .models import BudgetPlan, PlanPreview
from .planner import budget_preference_notes, replacement_options
from .services import (
    PlanConflict,
    PreviewRateLimit,
    account_recent_recipe_codes,
    apply_preview,
    assert_editable,
    check_draft_state,
    check_version,
    clean_inputs,
    make_preview,
    save_plan,
    schedule_codes,
    stored_inputs,
    write_draft,
)
from .snapshots import thaw

NOT_FOUND_MESSAGE = "Rencana tidak ditemukan atau sudah diganti. Muat ulang halaman."


def owned_plan(request, plan_id):
    return get_object_or_404(BudgetPlan, pk=plan_id, user=request.user)


def required_version(data, field="version"):
    value = data.get(field)
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError("Versi rencana wajib dikirim. Muat ulang halaman sebelum melanjutkan.")
    return int(value)


def preview_data(preview):
    previous, result = thaw(preview.plan.snapshot), thaw(preview.snapshot)
    budget = int(preview.inputs["budget"])
    return {
        "id": str(preview.pk),
        "apply_url": reverse("modul1-preview-apply", args=[preview.pk]),
        "before": int(previous["total"]),
        "after": int(result["total"]),
        "delta": int(result["total"] - previous["total"]),
        "budget": budget,
        "over_budget": max(0, int(result["total"]) - budget),
        "days": preview.inputs["days"],
        "servings": preview.inputs["servings"],
        "schedule": result["schedule"],
        "shopping_groups": result["shopping_groups"],
        "nutrition": result["nutrition"],
        "nutrition_targets_set": bool(result.get("protein_floor") or result.get("calorie_cap")),
        "preference_notes": result.get("preference_notes", []),
    }


def account_page(request, builder):
    plan = None
    requested = request.POST.get("plan_id") if request.method == "POST" else request.GET.get("plan")
    if requested:
        try:
            plan = owned_plan(request, UUID(requested))
        except (ValueError, TypeError):
            raise Http404("Rencana tidak ditemukan.") from None
    elif request.GET.get("new") != "1" and not (
        request.method == "POST" and request.POST.get("new_plan") == "1"
    ):
        plan = BudgetPlan.objects.filter(user=request.user, status="draft").first()
    initial = (
        plan.inputs
        if plan
        else {
            "budget": 150000,
            "days": 3,
            "servings": 2,
            "meal_types": ["sarapan", "makan_siang", "makan_malam"],
            "targets": ["seimbang"],
            **planner_defaults(request.user),
        }
    )
    form = PlannerForm(
        request.POST if request.method == "POST" else (plan.inputs if plan else None),
        initial=initial,
    )
    result = thaw(plan.snapshot) if plan else None
    if result:
        # Explain preferences for older immutable snapshots too, without
        # rewriting their menu, shopping list, or stored prices.
        result["preference_notes"] = budget_preference_notes(
            result["schedule"], result["total"], int(plan.inputs["budget"])
        )
    if plan and request.method == "GET":
        form.is_valid()
    error, pending = None, None
    status, retry_after = 200, None
    if request.method == "POST" and form.is_valid():
        form.cleaned_data["allergens"] = effective_allergens(
            request.user, plan.inputs if plan else {}, form.cleaned_data
        )
        try:
            expected = required_version(request.POST) if plan else None
            draft_id, draft_version, replace_draft = None, None, False
            if plan is None:
                raw_id = request.POST.get("replace_draft_id")
                if raw_id:
                    draft_id = UUID(raw_id)
                    draft_version = required_version(request.POST, "replace_draft_version")
                existing = BudgetPlan.objects.filter(user=request.user, status="draft").first()
                check_draft_state(existing, draft_id, draft_version)
                replace_draft = request.POST.get("replace_draft") == "1"
                if existing and not replace_draft:
                    raise PlanConflict(
                        "Setujui penggantian draft atau simpan draft terlebih dahulu."
                    )
            if plan:
                check_version(plan, expected)
            if plan and plan.status == "saved":
                pending = preview_data(
                    make_preview(
                        plan,
                        expected,
                        {
                            "action": "parameters",
                            "inputs": stored_inputs(form),
                        },
                    )
                )
                form = clean_inputs(plan.inputs)
            else:
                prior = schedule_codes(result) if result else []
                recent = account_recent_recipe_codes(request.user)
                candidate = builder(
                    **form.cleaned_data,
                    recent_recipe_codes=recent,
                    prior_slot_recipes={
                        meal: [slots.get(meal) for slots in prior]
                        for meal in form.cleaned_data["meal_types"]
                    },
                    seed=secrets.randbits(32),
                )
                result = candidate
                if candidate["within_budget"]:
                    plan = write_draft(
                        request.user,
                        stored_inputs(form),
                        candidate,
                        previous=plan,
                        expected_version=expected,
                        source=plan.source_plan if plan and plan.status == "draft" else None,
                        replace_draft=replace_draft,
                        expected_draft_id=draft_id,
                        expected_draft_version=draft_version,
                    )
                    # Post/Redirect/Get: refreshing a generated draft must not regenerate it.
                    response = redirect(reverse("modul1") + f"?plan={plan.pk}#hasil")
                    patch_cache_control(response, private=True, no_store=True)
                    return response
        except PreviewRateLimit as exc:
            error, status = str(exc), 429
            retry_after = exc.retry_after
        except PlanConflict as exc:
            error, status = str(exc), 409
        except ValueError as exc:
            error = str(exc)
            status = 400
    response = render(
        request,
        "budget_planner/planner.html",
        {
            "form": form,
            "result": result,
            "error": error,
            "plan": plan,
            "trial": None,
            "pending_preview": pending,
            "saved_plans": BudgetPlan.objects.filter(user=request.user, status="saved"),
            "active_draft": BudgetPlan.objects.filter(user=request.user, status="draft").first(),
            "allergy_warning": bool(
                result
                and unsafe_schedule(
                    schedule_codes(result),
                    effective_allergens(request.user, plan.inputs if plan else {}),
                )
            ),
            "allergy_active": effective_allergens(request.user, plan.inputs if plan else {}),
        },
        status=status,
    )
    patch_cache_control(response, private=True, no_store=True)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    return response


def plan_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "error": "Masuk untuk mengelola rencana makan.",
                    "login_url": reverse("login") + "?next=" + reverse("modul1"),
                },
                status=401,
            )
        if request.method != "POST":
            response = JsonResponse({"error": "Gunakan POST."}, status=405)
            response["Allow"] = "POST"
            return response
        if request.content_type != "application/json":
            return JsonResponse({"error": "Kirim sebagai JSON."}, status=415)
        if len(request.body) > 8000:
            return JsonResponse({"error": "Data terlalu besar."}, status=413)
        try:
            payload = json.loads(request.body)
            if not isinstance(payload, dict):
                raise ValueError("Format data tidak valid.")
            response = view(request, payload, *args, **kwargs)
        except PreviewRateLimit as exc:
            response = JsonResponse({"error": str(exc), "retry_after": exc.retry_after}, status=429)
            response["Retry-After"] = str(exc.retry_after)
        except PlanConflict as exc:
            response = JsonResponse({"error": str(exc)}, status=409)
        except (Http404, BudgetPlan.DoesNotExist, PlanPreview.DoesNotExist):
            # JSON, not the HTML 404 page, so the page can show what happened.
            response = JsonResponse({"error": NOT_FOUND_MESSAGE}, status=404)
        except (ValueError, UnicodeDecodeError) as exc:
            response = JsonResponse(
                {
                    "error": str(exc)
                    if not isinstance(exc, json.JSONDecodeError)
                    else "JSON tidak valid."
                },
                status=400,
            )
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


@plan_api
def preview_plan(request, payload, plan_id):
    plan = owned_plan(request, plan_id)
    preview = make_preview(plan, payload.get("version"), payload)
    return JsonResponse(preview_data(preview))


@plan_api
def apply_plan_preview(request, payload, preview_id):
    get_object_or_404(PlanPreview, pk=preview_id, plan__user=request.user)
    draft = apply_preview(request.user, preview_id, new_budget=payload.get("new_budget"))
    return JsonResponse({"url": reverse("modul1") + f"?plan={draft.pk}#hasil"})


@plan_api
def save_account_plan(request, payload, plan_id):
    owned_plan(request, plan_id)
    if not isinstance(payload.get("title"), str) or not isinstance(payload.get("starts_on"), str):
        raise ValueError("Judul dan tanggal mulai harus berupa teks.")
    form = PlanMetadataForm(payload)
    if not form.is_valid():
        return JsonResponse(
            {
                "error": "Isi judul maksimal 100 karakter dan tanggal mulai yang valid.",
                "fields": form.errors.get_json_data(),
            },
            status=400,
        )
    replace = payload.get("replace_original", False)
    if not isinstance(replace, bool):
        raise ValueError("Pilihan penyimpanan tidak valid.")
    plan = save_plan(
        request.user, plan_id, payload.get("version"), **form.cleaned_data, replace_original=replace
    )
    return JsonResponse({"url": reverse("modul1") + f"?plan={plan.pk}#hasil", "id": str(plan.pk)})


@plan_api
def delete_account_plan(request, payload, plan_id):
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        plan = get_object_or_404(
            BudgetPlan.objects.select_for_update(), pk=plan_id, user=request.user
        )
        check_version(plan, payload.get("version"))
        assert_editable(plan)
        plan.delete()
    return JsonResponse({"url": reverse("modul1") + "#rencana-saya"})


def recipe_alternatives(request, plan_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Masuk terlebih dahulu."}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "Gunakan GET."}, status=405)
    try:
        plan = owned_plan(request, plan_id)
        day = int(request.GET.get("day", "0"))
        meal = request.GET.get("meal", "")
        snapshot = thaw(plan.snapshot)
        slots = schedule_codes(snapshot)
        if not 1 <= day <= len(slots) or meal not in slots[day - 1]:
            raise ValueError("Slot menu tidak valid.")
        if plan.meals.filter(day=day, meal_type=meal, status="cooked").exists():
            raise ValueError("Menu sudah dimasak.")
        # The same basket quote as preview, including pooled fruit purchases.
        recipes = replacement_options(
            **clean_inputs(
                {**plan.inputs, "allergens": effective_allergens(request.user, plan.inputs)}
            ).cleaned_data,
            schedule=slots,
            day=day,
            meal=meal,
            current_total=snapshot["total"],
        )
        response = JsonResponse({"recipes": recipes, "version": plan.version})
    except Http404:
        response = JsonResponse({"error": NOT_FOUND_MESSAGE}, status=404)
    except ValueError as exc:
        response = JsonResponse({"error": str(exc)}, status=400)
    patch_cache_control(response, private=True, no_store=True)
    return response
