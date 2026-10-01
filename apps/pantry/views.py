import json
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalog.models import Ingredient

from .forms import PantryDetailsForm, PantryItemForm, PantryOCRItemForm
from .gemini import gemini_ready
from .models import PantryItem, PantryNameCorrection
from .receipt_ocr import MAX_IMAGE_BYTES, ReceiptOCRUnavailable, gemini_read_receipt, image_mime
from .recommendations import (
    everyday_ingredient_name,
    exact_ingredient_code,
    normalize_name,
    resolve_names,
)


def _session_id(request):
    if "pantry_session_id" not in request.session:
        request.session["pantry_session_id"] = uuid4().hex
    return request.session["pantry_session_id"]


def pantry_page(request):
    session_id = _session_id(request)
    return render(
        request,
        "modul2.html",
        {
            "pantry_items": PantryItem.objects.filter(session_id=session_id),
            "category_choices": PantryItem.MANUAL_CATEGORY_CHOICES,
            "manual_unit_choices": PantryItem.MANUAL_UNIT_CHOICES,
            "location_choices": PantryItem.LOCATION_CHOICES,
            "today": timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")),
            "gemini_receipt_fallback": gemini_ready(),
        },
    )


@require_POST
def fallback_receipt_ocr(request):
    if not gemini_ready():
        return JsonResponse({"error": "Pemindaian cadangan belum tersedia."}, status=503)
    upload = request.FILES.get("image")
    if upload is None or upload.size < 1 or upload.size > MAX_IMAGE_BYTES:
        return JsonResponse(
            {"error": "Unggah foto struk JPG, PNG, atau WebP maksimal 10 MB."}, status=400
        )
    image = upload.read(MAX_IMAGE_BYTES + 1)
    mime = image_mime(image)
    if len(image) > MAX_IMAGE_BYTES or not mime:
        return JsonResponse({"error": "Foto struk tidak valid."}, status=400)
    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")).isoformat()
    count = (
        request.session.get("pantry_ocr_llm_count", 0)
        if request.session.get("pantry_ocr_llm_date") == today
        else 0
    )
    if count >= 10:
        return JsonResponse(
            {"error": "Batas pemindaian cadangan hari ini tercapai. Coba lagi besok."}, status=429
        )
    request.session["pantry_ocr_llm_date"] = today
    request.session["pantry_ocr_llm_count"] = count + 1
    try:
        items = gemini_read_receipt(image, mime)
    except ReceiptOCRUnavailable:
        return JsonResponse(
            {
                "error": "Pemindaian cadangan belum berhasil. Periksa hasil OCR atau tambah baris manual."
            },
            status=502,
        )
    return JsonResponse({"items": items})


@require_POST
def suggest_receipt_items(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=415)
    if len(request.body) > 8000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    names = payload.get("names") if isinstance(payload, dict) else None
    if (
        not isinstance(names, list)
        or not 1 <= len(names) <= 30
        or any(not isinstance(name, str) or not 2 <= len(name.strip()) <= 255 for name in names)
    ):
        return JsonResponse({"error": "Kirim 1–30 nama bahan yang valid."}, status=400)

    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")).isoformat()
    llm_date = request.session.get("pantry_llm_date")
    llm_count = request.session.get("pantry_llm_count", 0) if llm_date == today else 0
    allow_llm = llm_count < 10
    suggestions, llm_attempted = resolve_names(names, _session_id(request), allow_llm=allow_llm)
    if llm_attempted:
        request.session["pantry_llm_date"] = today
        request.session["pantry_llm_count"] = llm_count + 1
    return JsonResponse({"suggestions": suggestions})


@require_POST
def save_pantry_items(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=415)
    if len(request.body) > 50000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    rows = payload.get("items") if isinstance(payload, dict) else None
    source = payload.get("source") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30 or source not in {"ocr", "manual"}:
        return JsonResponse({"error": "Kirim 1–30 bahan dari struk atau input manual."}, status=400)

    form_class = PantryOCRItemForm if source == "ocr" else PantryItemForm
    forms = [form_class(row if isinstance(row, dict) else {}) for row in rows]
    errors = {
        str(index + 1): form.errors.get_json_data()
        for index, form in enumerate(forms)
        if not form.is_valid()
    }
    if errors:
        return JsonResponse({"error": "Periksa kembali data bahan.", "rows": errors}, status=400)

    accepted = []
    if source == "ocr":
        for row in rows:
            raw = row.get("original_name", "") if isinstance(row, dict) else ""
            code = row.get("ingredient_code", "") if isinstance(row, dict) else ""
            if not isinstance(raw, str) or len(raw) > 255 or not isinstance(code, str):
                return JsonResponse({"error": "Data koreksi nama tidak valid."}, status=400)
            if code:
                ingredient = Ingredient.objects.filter(pk=code).first()
                if not ingredient or normalize_name(row.get("name", "")) not in {
                    normalize_name(ingredient.name),
                    normalize_name(everyday_ingredient_name(ingredient.name)),
                }:
                    return JsonResponse(
                        {"error": "Nama bahan berubah. Periksa kembali sebelum menyimpan."},
                        status=400,
                    )
                accepted.append((raw, ingredient.ingredient_code))
            elif raw and normalize_name(raw) != normalize_name(row.get("name", "")):
                accepted.append((raw, exact_ingredient_code(row.get("name", ""))))
            else:
                accepted.append(("", None))
    session_id = _session_id(request)
    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
    with transaction.atomic():
        items = [
            PantryItem.objects.create(
                session_id=session_id,
                source=source,
                estimated_expires_on=(
                    (form.cleaned_data["starting_on"] or today)
                    + timedelta(days=form.cleaned_data["shelf_life_days"])
                    if form.cleaned_data["shelf_life_days"] is not None
                    else None
                ),
                **{key: value for key, value in form.cleaned_data.items() if key != "starting_on"},
            )
            for form in forms
        ]
        if source == "ocr":
            for raw, code in accepted:
                if raw and code and normalize_name(raw):
                    PantryNameCorrection.objects.update_or_create(
                        session_id=session_id,
                        normalized_name=normalize_name(raw),
                        defaults={"raw_name": raw, "ingredient_id": code},
                    )
    return JsonResponse({"saved": len(items), "ids": [item.pk for item in items]}, status=201)


@require_http_methods(["PATCH"])
def update_pantry_details(request, item_id):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=415)
    if len(request.body) > 2000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Data bahan tidak valid."}, status=400)

    item = get_object_or_404(PantryItem, pk=item_id, session_id=_session_id(request))
    form = PantryDetailsForm(payload)
    if not form.is_valid():
        return JsonResponse(
            {
                "error": "Periksa lokasi dan tanggal kedaluwarsa.",
                "fields": form.errors.get_json_data(),
            },
            status=400,
        )

    item.location = form.cleaned_data["location"]
    item.estimated_expires_on = form.cleaned_data["estimated_expires_on"]
    if item.estimated_expires_on:
        today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
        days = (item.estimated_expires_on - today).days
        item.shelf_life_days = days if 1 <= days <= 3650 else None
    else:
        item.shelf_life_days = None
    item.save(update_fields=["location", "estimated_expires_on", "shelf_life_days"])
    return JsonResponse({"saved": True})


@require_http_methods(["DELETE"])
def delete_pantry_item(request, item_id):
    item = get_object_or_404(PantryItem, pk=item_id, session_id=_session_id(request))
    item.delete()
    return JsonResponse({"deleted": True})
