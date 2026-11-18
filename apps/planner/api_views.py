"""Endpoint REST Modul 1 untuk aplikasi mobile; logikanya memakai services yang sama dengan web.
Hanya GET dan POST karena pbp_django_auth di Flutter hanya mendukung dua method itu."""

import secrets
from functools import wraps
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.login.preferences import effective_preferences

from .forms import PlanMetadataForm
from .models import BudgetPlan
from .plan_views import NOT_FOUND_MESSAGE
from .planner import build_plan
from .serializers import BudgetPlanDetailSerializer, BudgetPlanSerializer
from .services import (
    PlanConflict,
    PreviewRateLimit,
    account_recent_recipe_codes,
    check_draft_state,
    check_version,
    clean_inputs,
    reserve_preview,
    save_plan,
    stock_context,
    stored_inputs,
    write_draft,
)


def planner_errors(view):
    """Mengubah error layanan planner menjadi respons JSON {"error": ...} dengan status yang sesuai,
    dan menandai respons agar tidak di-cache karena berisi data pribadi."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        """Menjalankan view lalu memetakan 429/409/404/400."""
        try:
            response = view(request, *args, **kwargs)
        except PreviewRateLimit as exc:
            response = Response({"error": str(exc), "retry_after": exc.retry_after}, status=429)
            response["Retry-After"] = str(exc.retry_after)
        except PlanConflict as exc:
            response = Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        except (Http404, BudgetPlan.DoesNotExist):
            response = Response({"error": NOT_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            response = Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch_cache_control(response, private=True, no_store=True)
        return response

    return wrapped


def json_object(request):
    """Body request harus objek JSON; list atau nilai lain ditolak 400."""
    if not isinstance(request.data, dict):
        raise ValueError("Format data tidak valid.")
    return request.data


def owned_plan(request, plan_id):
    """Rencana milik user yang login; milik user lain diperlakukan sebagai 404."""
    return get_object_or_404(BudgetPlan, pk=plan_id, user=request.user)


@api_view(["GET", "POST"])
@planner_errors
def plan_list(request):
    """GET: daftar rencana milik user. POST: menyusun menu dari input planner lalu menyimpannya
    sebagai draft; draft lama hanya diganti bila `replace_draft` disetujui."""
    if request.method == "GET":
        plans = BudgetPlan.objects.filter(user=request.user)
        return Response(BudgetPlanSerializer(plans, many=True).data)

    data = json_object(request)
    form = clean_inputs(data)
    form.cleaned_data.update(effective_preferences(request.user, {}, form.cleaned_data))
    replace = data.get("replace_draft") is True
    try:
        draft_id = UUID(data["replace_draft_id"]) if data.get("replace_draft_id") else None
    except (TypeError, ValueError):
        raise PlanConflict("Draft sudah berubah. Muat ulang sebelum melanjutkan.") from None
    draft_version = data.get("replace_draft_version")
    existing = BudgetPlan.objects.filter(user=request.user, status="draft").first()
    if existing and not replace:
        raise PlanConflict("Setujui penggantian draft atau simpan draft terlebih dahulu.")
    check_draft_state(existing, draft_id, draft_version)

    recent = account_recent_recipe_codes(request.user)
    with transaction.atomic():
        reserve_preview(request.user)
    result = build_plan(
        **form.cleaned_data,
        recent_recipe_codes=recent,
        prior_slot_recipes={meal: [] for meal in form.cleaned_data["meal_types"]},
        seed=secrets.randbits(32),
        **stock_context(request.user),
    )
    if not result["within_budget"]:
        return Response(
            {"error": "Budget belum cukup untuk menu ini.", "result": result},
            status=status.HTTP_400_BAD_REQUEST,
        )
    plan = write_draft(
        request.user,
        stored_inputs(form),
        result,
        replace_draft=replace,
        expected_draft_id=draft_id,
        expected_draft_version=draft_version,
    )
    return Response(BudgetPlanDetailSerializer(plan).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@planner_errors
def plan_detail(request, plan_id):
    """Detail satu rencana milik user: input, jadwal menu, daftar belanja, dan gizi."""
    return Response(BudgetPlanDetailSerializer(owned_plan(request, plan_id)).data)


@api_view(["POST"])
@planner_errors
def plan_save(request, plan_id):
    """Menyimpan draft menjadi rencana, atau mengubah judul dan tanggal mulai rencana tersimpan;
    `version` wajib sama dengan versi terbaru agar perubahan perangkat lain tidak tertimpa."""
    data = json_object(request)
    owned_plan(request, plan_id)
    if not isinstance(data.get("title"), str):
        raise ValueError("Judul harus berupa teks.")
    form = PlanMetadataForm(data)
    if not form.is_valid():
        return Response(
            {"error": next(iter(form.errors.values()))[0], "fields": form.errors.get_json_data()},
            status=status.HTTP_400_BAD_REQUEST,
        )
    replace = data.get("replace_original", False)
    if not isinstance(replace, bool):
        raise ValueError("Pilihan penyimpanan tidak valid.")
    plan = save_plan(
        request.user, plan_id, data.get("version"), **form.cleaned_data, replace_original=replace
    )
    return Response(BudgetPlanDetailSerializer(plan).data)


@api_view(["POST"])
@planner_errors
def plan_delete(request, plan_id):
    """Menghapus rencana beserta jadwal dan daftar belanjanya setelah versi dicek; stok pantry tetap."""
    data = json_object(request)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        plan = get_object_or_404(
            BudgetPlan.objects.select_for_update(), pk=plan_id, user=request.user
        )
        check_version(plan, data.get("version"))
        plan.delete()
    return Response({"deleted": True})
