import json
import secrets
from copy import deepcopy
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal
from functools import wraps
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from apps.accounts.preferences import (
    effective_allergens,
    effective_preferences,
    non_halal_schedule,
    planner_defaults,
)
from apps.catalog.allergens import unsafe_schedule
from apps.catalog.recipe_images import recipe_images_for

from .forms import PlanMetadataForm, PlannerForm
from .models import BudgetPlan, PlanPreview
from .planner import MEALS, build_plan, replacement_options
from .services import (
    JAKARTA,
    MAX_START_DAYS,
    PlanConflict,
    PreviewRateLimit,
    account_recent_recipe_codes,
    apply_preview,
    check_draft_state,
    check_version,
    clean_inputs,
    cooked_slots,
    expiring_stock_codes,
    make_preview,
    purchases_to_pantry,
    reserve_preview,
    save_plan,
    schedule_codes,
    stock_context,
    stored_inputs,
    write_draft,
)
from .shopping_pdf import shopping_list_pdf
from .snapshots import net_total, thaw

# BPOM Acuan Label Gizi (ALG) for the general population: the 100% mark of each
# ring in the "Gizi per hari" card.
NUTRITION_RINGS = (
    ("calories", "kkal", "", Decimal(2150), "energy"),
    ("protein", "protein", " g", Decimal(60), "protein"),
    ("carbs", "karbo", " g", Decimal(325), "carbs"),
    ("fat", "lemak", " g", Decimal(67), "fat"),
)


def nutrition_rings(nutrition):
    """Per-person daily values with their share of the ALG reference, capped at 100%."""
    return [
        {
            "key": key,
            "label": label,
            "value": f"{nutrition[field]}{unit}",
            "reference": f"{reference}{unit}",
            "percent": min(100, int(Decimal(str(nutrition[field])) * 100 / reference)),
        }
        for field, label, unit, reference, key in NUTRITION_RINGS
    ]


# Shopping categories on the planner card; bumbu, lemak and anything new fold into the last.
SHOPPING_SUMMARY = (
    ("protein", "Protein"),
    ("karbohidrat", "Karbohidrat"),
    ("sayur", "Sayur"),
    ("buah", "Buah"),
    ("lainnya", "Bumbu & Lainnya"),
)


def shopping_summary(groups):
    """Item count and subtotal per summary category, in SHOPPING_SUMMARY order."""
    keys = {key for key, _ in SHOPPING_SUMMARY}
    totals = {}
    for group in groups:
        key = group["name"].casefold()
        key = key if key in keys else "lainnya"
        count, subtotal = totals.get(key, (0, Decimal(0)))
        totals[key] = (count + len(group["items"]), subtotal + group["subtotal"])
    return [
        {"key": key, "label": label, "count": totals[key][0], "subtotal": totals[key][1]}
        for key, label in SHOPPING_SUMMARY
        if key in totals
    ]


def annotated_groups(user, plan, result, display_schedule):
    """Shopping groups with live pantry facts and a subtotal each."""
    groups, saving = pantry_annotations(user, plan, result, display_schedule)
    for group in groups:
        group["subtotal"] = sum(Decimal(str(item["cost"])) for item in group["items"])
    return groups, saving


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
        # Money still to spend after pantry stock, the figure the budget limits.
        # Baseline re-quoted with today's pantry when stock is involved (see make_preview).
        "before": int(result.get("previous_net_total", net_total(previous))),
        "after": int(net_total(result)),
        "delta": int(net_total(result) - result.get("previous_net_total", net_total(previous))),
        "budget": budget,
        "over_budget": max(0, int(net_total(result)) - budget),
        "days": preview.inputs["days"],
        "servings": preview.inputs["servings"],
        "schedule": result["schedule"],
        "shopping_groups": result["shopping_groups"],
        "nutrition": result["nutrition"],
        "nutrition_targets_set": bool(result.get("protein_floor") or result.get("calorie_cap")),
        "preference_notes": result.get("preference_notes", []),
    }


def pantry_annotations(user, plan, result, display_schedule):
    """Live pantry facts for display only; never written into the plan snapshot."""
    from apps.catalog.models import RecipeIngredient
    from apps.pantry.services import stock_for_planning

    # Same stock rule as the planner: undated stock counts, but is flagged, and
    # stock other saved plans still need is set aside.
    context = stock_context(user, plan) if plan is not None else None
    live = context["stock"] if context else stock_for_planning(user)
    stock, undated = {}, set()
    for code, grams, expires in live:
        stock[code] = stock.get(code, Decimal(0)) + grams
        if expires is None:
            undated.add(code)
    if plan is not None and live:
        # Allocate today's stock with the planner's rules (per day, FEFO, nothing used
        # after it expires), so a ✓ never covers a meal the stock will not last until.
        try:
            quote = build_plan(
                **clean_inputs(
                    {**plan.inputs, **effective_preferences(user, plan.inputs)}
                ).cleaned_data,
                fixed_schedule=schedule_codes(result),
                **context,
            )
            stock = {
                row["ingredient_code"]: Decimal(row["from_stock"])
                for group in quote["shopping_groups"]
                for row in group["items"]
            }
        except ValueError:
            pass  # catalog changed since the plan was made: fall back to plain totals
    added = {
        item.ingredient_id: item.added_to_pantry_at
        for item in (plan.shopping_items.all() if plan else ())
    }
    groups, saving = deepcopy(result["shopping_groups"]), 0
    for group in groups:
        for item in group["items"]:
            need = Decimal(str(item["quantity"]))
            have = min(stock.get(item["ingredient_code"], Decimal(0)), need)
            item["in_pantry"] = int(have)
            item["unknown_expiry"] = have > 0 and item["ingredient_code"] in undated
            item["to_buy"] = max(0, int((need - have).to_integral_value(rounding=ROUND_CEILING)))
            item["added_to_pantry"] = bool(added.get(item["ingredient_code"]))
            if have > 0 and need > 0:
                saving += int(Decimal(item["cost"]) * have / need)
    priority = expiring_stock_codes(user)
    codes = {meal["recipe_code"] for day in display_schedule for meal in day["meals"]}
    uses = {}
    for link in RecipeIngredient.objects.filter(
        recipe_id__in=codes, ingredient_id__in=priority
    ).select_related("ingredient"):
        uses.setdefault(link.recipe_id, []).append(link.ingredient.name)
    for day in display_schedule:
        for meal in day["meals"]:
            meal["expiring_stock"] = sorted(uses.get(meal["recipe_code"], []))
    return groups, saving // 100 * 100


def landing_prefill(query):
    """Budget, days, servings and meals carried from the landing calculator.

    The calculator shows the budget with thousands dots ("150.000").
    """
    raw = {key: query.get(key, "") for key in ("budget", "days", "servings")}
    raw["budget"] = raw["budget"].replace(".", "")
    values = {key: int(text) for key, text in raw.items() if text.isascii() and text.isdigit()}
    meals = [meal for meal in query.getlist("meal_types") if meal in MEALS]
    if meals:
        values["meal_types"] = meals
    return values


# The last plan shown is reopened on /planner/ until the browser closes or the user logs
# out: it is kept both in the login session (flushed on logout) and in a browser-session
# cookie (dropped when the browser closes), and both must agree.
REMEMBERED_PLAN = "planner_plan"


def remembered_plan(request):
    plan_id = request.session.get(REMEMBERED_PLAN)
    if not plan_id or request.COOKIES.get(REMEMBERED_PLAN) != plan_id:
        return None
    return BudgetPlan.objects.filter(pk=plan_id, user=request.user).first()


def remember_plan(request, response, plan):
    if plan is None:
        request.session.pop(REMEMBERED_PLAN, None)
        response.delete_cookie(REMEMBERED_PLAN)
        return
    request.session[REMEMBERED_PLAN] = str(plan.pk)
    response.set_cookie(
        REMEMBERED_PLAN,
        str(plan.pk),
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def account_page(request, builder):
    plan = None
    # Landing calculator values prefill a new plan; the form still validates on submit.
    prefill = landing_prefill(request.GET) if request.method == "GET" else {}
    requested = request.POST.get("plan_id") if request.method == "POST" else request.GET.get("plan")
    # "+ Rencana baru", the landing calculator and a missing-plan notice start empty.
    starts_fresh = request.GET.get("new") == "1" or prefill or request.GET.get("hilang") == "1"
    if request.method == "GET" and not requested and not starts_fresh:
        remembered = remembered_plan(request)
        if remembered is not None:
            return redirect(reverse("modul1") + f"?plan={remembered.pk}#hasil")
    if requested:
        try:
            plan = owned_plan(request, UUID(requested))
        except (ValueError, TypeError, Http404):
            # Deleted in another tab or an outdated link: start over with a notice.
            return redirect(reverse("modul1") + "?hilang=1")
    # Plans saved before the rice option existed were made without rice.
    plan_inputs = {"rice": "no", **plan.inputs} if plan else None
    initial = (
        plan_inputs
        if plan
        else {
            "budget": 150000,
            "days": 3,
            "servings": 2,
            "meal_types": ["sarapan", "makan_siang", "makan_malam"],
            "targets": ["seimbang"],
            **planner_defaults(request.user),
            **prefill,
        }
    )
    form = PlannerForm(
        request.POST if request.method == "POST" else plan_inputs,
        initial=initial,
    )
    result = thaw(plan.snapshot) if plan else None
    if result:
        result.setdefault("net_total", result["total"])  # plans saved before net costs
    if plan and request.method == "GET":
        form.is_valid()
    error, pending = None, None
    status, retry_after = 200, None
    if request.method == "POST" and form.is_valid():
        form.cleaned_data.update(
            effective_preferences(request.user, plan.inputs if plan else {}, form.cleaned_data)
        )
        try:
            expected = required_version(request.POST) if plan else None
            draft_id, draft_version, replace_draft = None, None, False
            if plan is None:
                raw_id = request.POST.get("replace_draft_id")
                if raw_id:
                    try:
                        draft_id = UUID(raw_id)
                    except ValueError:
                        raise PlanConflict(
                            "Draft sudah berubah. Muat ulang halaman sebelum melanjutkan."
                        ) from None
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
                # Generating is the most expensive request; it shares the preview quota.
                with transaction.atomic():
                    reserve_preview(request.user)
                candidate = builder(
                    **form.cleaned_data,
                    recent_recipe_codes=recent,
                    prior_slot_recipes={
                        meal: [slots.get(meal) for slots in prior]
                        for meal in form.cleaned_data["meal_types"]
                    },
                    seed=secrets.randbits(32),
                    **stock_context(request.user, plan),
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
    display_schedule = deepcopy(result["schedule"]) if result else []
    display_recipe_codes = [
        meal["recipe_code"]
        for day in display_schedule
        for meal in day["meals"]
    ]
    display_photos = recipe_images_for(display_recipe_codes)
    for day in display_schedule:
        for meal in day["meals"]:
            meal["photo"] = display_photos.get(meal["recipe_code"])
    if result and plan:
        for day in display_schedule:
            day["date"] = plan.starts_on + timedelta(days=day["number"] - 1)
        slots = {(item.day, item.meal_type): item for item in plan.meals.all()}
        cooked = {(item.day, item.meal_type) for item in cooked_slots(plan)}
        for day in display_schedule:
            for meal in day["meals"]:
                item = slots.get((day["number"], meal["type"]))
                if item:
                    meal["planned_meal_id"] = item.pk if plan.status == "saved" else None
                    meal["cooked"] = (item.day, item.meal_type) in cooked
                    meal["skipped"] = item.status == "skipped"
    shopping_groups, pantry_saving = (
        annotated_groups(request.user, plan, result, display_schedule)
        if result and result.get("within_budget")
        else (None, 0)
    )
    # Plans saved before the staple choice keep their stored value visible.
    rice_value = form["rice"].value() or "no"
    legacy_rice = dict(PlannerForm.LEGACY_RICE_CHOICES)
    staple_options = [
        *([(rice_value, legacy_rice[rice_value])] if rice_value in legacy_rice else []),
        *PlannerForm.STAPLE_CHOICES,
    ]
    avoid_terms = [
        term.strip() for term in str(form["exclude_ingredients"].value() or "").split(",")
    ]
    today = timezone.localdate(timezone=JAKARTA)
    response = render(
        request,
        "budget_planner/planner.html",
        {
            "form": form,
            "result": result,
            "display_schedule": display_schedule,
            "shopping_groups": shopping_groups,
            "pantry_saving": pantry_saving,
            "staple_options": staple_options,
            "rice_value": rice_value,
            "avoid_count": len([term for term in avoid_terms if term]),
            "item_count": sum(len(group["items"]) for group in shopping_groups or ()),
            # A changed start date lies within today .. MAX_START_DAYS; an older saved
            # date may stay as it is, and cooked meals pin the date.
            # A new draft's stored date can lie in the past; it is saved as today at the earliest.
            "start_value": plan.starts_on
            if plan and (plan.status == "saved" or plan.source_plan_id)
            else max(today, plan.starts_on if plan else today),
            "start_min": min(today, plan.starts_on) if plan else today,
            "plan_missing": request.GET.get("hilang") == "1",
            "start_max": today + timedelta(days=MAX_START_DAYS),
            "date_locked": bool(plan and cooked_slots(plan)),
            "shopping_summary": shopping_summary(shopping_groups or ()),
            "pantry_items": [
                item
                for group in shopping_groups or ()
                for item in group["items"]
                if not item["added_to_pantry"] and item["to_buy"] != 0
            ],
            "nutrition_rings": nutrition_rings(result["nutrition"])
            if result and result.get("within_budget")
            else [],
            "error": error,
            "plan": plan,
            "pending_preview": pending,
            "saved_plans": [
                setattr(saved, "net_total", net_total(thaw(saved.snapshot))) or saved
                for saved in BudgetPlan.objects.filter(user=request.user, status="saved")
            ],
            "active_draft": BudgetPlan.objects.filter(user=request.user, status="draft").first(),
            "allergy_warning": bool(
                result
                and unsafe_schedule(
                    schedule_codes(result),
                    effective_allergens(request.user, plan.inputs if plan else {}),
                )
            ),
            "halal_warning": bool(
                result
                and effective_preferences(request.user)["halal_only"]
                and non_halal_schedule(schedule_codes(result))
            ),
        },
        status=status,
    )
    patch_cache_control(response, private=True, no_store=True)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    if request.method == "GET":
        remember_plan(request, response, plan)
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
    if not isinstance(payload.get("title"), str):
        raise ValueError("Judul harus berupa teks.")
    form = PlanMetadataForm(payload)
    if not form.is_valid():
        return JsonResponse(
            {
                "error": next(iter(form.errors.values()))[0],
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
def add_plan_purchases(request, payload, plan_id):
    owned_plan(request, plan_id)
    response = purchases_to_pantry(
        request.user, plan_id, payload.get("version"), payload.get("items")
    )
    return JsonResponse({**response, "pantry_url": reverse("modul2")}, status=201)


@plan_api
def delete_account_plan(request, payload, plan_id):
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        plan = get_object_or_404(
            BudgetPlan.objects.select_for_update(), pk=plan_id, user=request.user
        )
        check_version(plan, payload.get("version"))
        plan.delete()
    return JsonResponse({"url": reverse("modul1") + "#rencana-saya"})


@login_required
@require_GET
def shopping_list_download(request, plan_id):
    plan = owned_plan(request, plan_id)
    result = thaw(plan.snapshot)
    if not result.get("within_budget"):
        raise Http404("Rencana belum memenuhi budget.")
    schedule = deepcopy(result["schedule"])
    groups, _ = annotated_groups(request.user, plan, result, schedule)
    response = HttpResponse(
        shopping_list_pdf(plan, result, groups, schedule), content_type="application/pdf"
    )
    filename = f"belanja-{slugify(plan.title) or 'rencana'}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    patch_cache_control(response, private=True, no_store=True)
    return response


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
        if any(item.day == day and item.meal_type == meal for item in cooked_slots(plan)):
            raise ValueError("Menu sudah dimasak.")
        with transaction.atomic():
            reserve_preview(request.user)  # quotes every alternative: shares the preview quota
        # The same basket quote as preview, including pooled fruit purchases.
        recipes = replacement_options(
            **clean_inputs(
                {**plan.inputs, **effective_preferences(request.user, plan.inputs)}
            ).cleaned_data,
            schedule=slots,
            day=day,
            meal=meal,
            current_total=net_total(snapshot),
            **stock_context(request.user, plan),
        )
        response = JsonResponse({"recipes": recipes, "version": plan.version})
    except PreviewRateLimit as exc:
        response = JsonResponse({"error": str(exc), "retry_after": exc.retry_after}, status=429)
        response["Retry-After"] = str(exc.retry_after)
    except Http404:
        response = JsonResponse({"error": NOT_FOUND_MESSAGE}, status=404)
    except ValueError as exc:
        response = JsonResponse({"error": str(exc)}, status=400)
    patch_cache_control(response, private=True, no_store=True)
    return response
