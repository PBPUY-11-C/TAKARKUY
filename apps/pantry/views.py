from datetime import date, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.access import api_login_required
from apps.catalog.models import Ingredient

from .ai_usage import collect_usage
from .forms import PantryDetailsForm, PantryItemForm, PantryOCRItemForm
from .gemini import gemini_ready
from .json_input import load_payload
from .models import PantryItem, PantryNameCorrection
from .receipt_ocr import (
    MAX_IMAGE_BYTES,
    ReceiptOCRUnavailable,
    complete_photo_items,
    gemini_read_receipt,
    image_mime,
)
from .recommendations import (
    everyday_ingredient_name,
    exact_ingredient_code,
    normalize_name,
    resolve_names,
)
from .services import (
    StockError,
    check_version,
    movement,
    operation,
    recipe_matches,
    refresh_conversion,
    reserve_llm,
    snapshot,
)
from .storage import (
    DEFAULT_LOCATION,
    expiry_estimate,
    shelf_life_duration,
    storage_options,
    transfer_estimate,
)


def _local_codes(names, session_id, user):
    if not names:
        return []
    suggestions, _ = resolve_names(names, session_id, user=user, allow_llm=False)
    return [suggestion["ingredient_code"] for suggestion in suggestions]


def _starting_on(item):
    return item.starting_on or timezone.localdate(item.added_at, timezone=ZoneInfo("Asia/Jakarta"))


def _session_id(request):
    # Compatibility column only: all authorization queries use the user FK.
    scope = uuid5(NAMESPACE_URL, f"takarkuy:pantry-user:{request.user.pk}").hex
    if request.session.get("pantry_session_id") != scope:
        request.session["pantry_session_id"] = scope
    return scope


@login_required
def pantry_page(request):
    session_id = _session_id(request)
    items = list(PantryItem.objects.filter(user=request.user, archived_at__isnull=True))
    unmatched = [item for item in items if not item.ingredient_id]
    legacy_codes = dict(
        zip(
            (item.pk for item in unmatched),
            _local_codes([item.name for item in unmatched], session_id, request.user),
        )
    )
    references = {}
    estimates = {}
    for item in items:
        code = item.ingredient_id or legacy_codes.get(item.pk)
        if code not in references:
            references[code] = storage_options(code)
        options = references[code]
        location = item.location or DEFAULT_LOCATION
        item.display_location = location
        state = transfer_estimate(item, options, location, _starting_on(item))
        item.storage_message = state["message"]
        expiry = item.estimated_expires_on
        remaining = (
            (expiry - timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))).days
            if expiry
            else None
        )
        item.expiry_status = (
            "Tanggal sudah lewat"
            if remaining is not None and remaining < 0
            else "Mendekati tanggal kedaluwarsa"
            if remaining is not None and remaining <= 2
            else ""
        )
        estimates[str(item.pk)] = {
            "location": location,
            "options": {
                key: transfer_estimate(item, options, key, _starting_on(item))
                for key, _ in PantryItem.LOCATION_CHOICES
            },
        }
    return render(
        request,
        "modul2.html",
        {
            "pantry_items": items,
            "pantry_storage": estimates,
            "category_choices": PantryItem.MANUAL_CATEGORY_CHOICES,
            "manual_unit_choices": PantryItem.MANUAL_UNIT_CHOICES,
            "location_choices": PantryItem.LOCATION_CHOICES,
            "expiry_choices": PantryItem.EXPIRY_CHOICES,
            "ingredients": Ingredient.objects.order_by("name"),
            "today": timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")),
            "gemini_receipt_fallback": gemini_ready(),
        },
    )


@api_login_required
@require_POST
def fallback_receipt_ocr(request):
    if not gemini_ready():
        return JsonResponse({"error": "Pemindaian cadangan belum tersedia."}, status=503)
    upload = request.FILES.get("image")
    if getattr(request, "receipt_too_large", False):
        if upload is not None:
            upload.close()
        return JsonResponse({"error": "Foto maksimal 10 MB."}, status=413)
    if upload is None or upload.size < 1 or upload.size > MAX_IMAGE_BYTES:
        return JsonResponse(
            {"error": "Unggah foto struk JPG, PNG, atau WebP maksimal 10 MB."}, status=400
        )
    image = upload.read(MAX_IMAGE_BYTES + 1)
    upload.close()
    mime = image_mime(image)
    if len(image) > MAX_IMAGE_BYTES or not mime:
        return JsonResponse({"error": "Foto struk tidak valid."}, status=400)
    try:
        reserve_llm(request.user, "photo")
        with collect_usage() as calls:
            items = gemini_read_receipt(image, mime)
        items = complete_photo_items(items, request.user, _session_id(request))
    except StockError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    except ReceiptOCRUnavailable:
        return JsonResponse(
            {
                "error": "Pemindaian cadangan belum berhasil. Periksa hasil OCR atau tambah baris manual.",
                "ai_usage": calls,
            },
            status=502,
        )
    finally:
        upload.close()
    return JsonResponse({"items": items, "ai_usage": calls})


@api_login_required
@require_POST
def suggest_receipt_items(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=415)
    if len(request.body) > 8000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = load_payload(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    names = payload.get("names") if isinstance(payload, dict) else None
    if (
        not isinstance(names, list)
        or not 1 <= len(names) <= 30
        or any(not isinstance(name, str) or not 2 <= len(name.strip()) <= 255 for name in names)
    ):
        return JsonResponse({"error": "Kirim 1–30 nama bahan yang valid."}, status=400)

    allow_llm = payload.get("allow_llm", True)
    if type(allow_llm) is not bool:
        return JsonResponse({"error": "allow_llm harus berupa boolean."}, status=400)
    with collect_usage() as calls:
        suggestions, _ = resolve_names(
            names, _session_id(request), user=request.user, allow_llm=allow_llm
        )
    return JsonResponse({"suggestions": suggestions, "ai_usage": calls})


@api_login_required
@require_POST
def save_pantry_items(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=415)
    if len(request.body) > 50000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = load_payload(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    rows = payload.get("items") if isinstance(payload, dict) else None
    source = payload.get("source") if isinstance(payload, dict) else None
    if (
        not isinstance(rows, list)
        or not 1 <= len(rows) <= 30
        or not isinstance(source, str)
        or source not in {"ocr", "manual"}
    ):
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
        for row, form in zip(rows, forms):
            raw = row.get("original_name", "") if isinstance(row, dict) else ""
            code = row.get("ingredient_code", "") if isinstance(row, dict) else ""
            if not isinstance(raw, str) or len(raw) > 255 or not isinstance(code, str):
                return JsonResponse({"error": "Data koreksi nama tidak valid."}, status=400)
            for flag in ("accepted", "user_edited"):
                if flag in row and type(row[flag]) is not bool:
                    return JsonResponse(
                        {"error": "Konfirmasi nama harus berupa boolean."}, status=400
                    )
            confirmed = row.get("accepted") is True or (
                row.get("user_edited") is True
                and normalize_name(raw) != normalize_name(form.cleaned_data["name"])
            )
            if code:
                ingredient = Ingredient.objects.filter(pk=code).first()
                if not ingredient or normalize_name(form.cleaned_data["name"]) not in {
                    normalize_name(ingredient.name),
                    normalize_name(everyday_ingredient_name(ingredient.name)),
                }:
                    return JsonResponse(
                        {"error": "Nama bahan berubah. Periksa kembali sebelum menyimpan."},
                        status=400,
                    )
                accepted.append((raw, ingredient.ingredient_code, confirmed))
            elif raw and normalize_name(raw) != normalize_name(form.cleaned_data["name"]):
                accepted.append((raw, exact_ingredient_code(form.cleaned_data["name"]), confirmed))
            else:
                accepted.append(("", None, False))
    session_id = _session_id(request)
    today = timezone.localdate(timezone=ZoneInfo("Asia/Jakarta"))
    local_codes = _local_codes(
        [form.cleaned_data["name"] for form in forms], session_id, request.user
    )
    references = {}
    try:
        with transaction.atomic():
            event, replay = operation(request.user, payload.get("operation_key"), "create", payload)
            if replay:
                return JsonResponse(event.response, status=201)
            items = []
            for index, form in enumerate(forms):
                fields = form.cleaned_data.copy()
                starting_on = fields.pop("starting_on") or today
                fields["location"] = fields["location"] or DEFAULT_LOCATION
                code = (accepted[index][1] if source == "ocr" else None) or local_codes[index]
                if code not in references:
                    references[code] = storage_options(code)
                estimate = expiry_estimate(references[code], fields["location"], starting_on)
                explicit_date = fields.pop("estimated_expires_on")
                expiry_source = fields.pop("expiry_source")
                manual_days = fields["shelf_life_days"]
                fields["shelf_life_days"] = (
                    manual_days if manual_days is not None else estimate["shelf_life_days"]
                )
                expires_on = explicit_date or (
                    starting_on + timedelta(days=fields["shelf_life_days"])
                    if fields["shelf_life_days"] is not None
                    else None
                )
                if explicit_date:
                    expiry_source = "label" if expiry_source == "label" else "manual"
                elif manual_days is not None:
                    expiry_source = "manual"
                else:
                    expiry_source = "estimate" if expires_on else "unknown"
                fields["shelf_life_days"] = shelf_life_duration(starting_on, expires_on)
                item = PantryItem(
                    user=request.user,
                    session_id=session_id,
                    source=source,
                    ingredient_id=code,
                    starting_on=starting_on,
                    estimated_expires_on=expires_on,
                    expiry_source=expiry_source,
                    **fields,
                )
                refresh_conversion(item)
                item.save()
                movement(item, event, "in", {})
                items.append(item)
            if source == "ocr":
                for raw, code, confirmed in accepted:
                    if confirmed and raw and code and normalize_name(raw):
                        PantryNameCorrection.objects.update_or_create(
                            user=request.user,
                            normalized_name=normalize_name(raw),
                            defaults={
                                "session_id": session_id,
                                "raw_name": raw,
                                "ingredient_id": code,
                                "confirmed_by_user": True,
                            },
                        )
            event.response = {"saved": len(items), "ids": [item.pk for item in items]}
            event.save(update_fields=["response"])
    except StockError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    return JsonResponse(event.response, status=201)


@api_login_required
@require_http_methods(["PATCH"])
def update_pantry_details(request, item_id):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=415)
    if len(request.body) > 2000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = load_payload(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Data bahan tidak valid."}, status=400)

    if not PantryItem.objects.filter(pk=item_id, user=request.user).exists():
        return JsonResponse({"error": "Stok tidak ditemukan."}, status=404)
    try:
        with transaction.atomic():
            event, replay = operation(
                request.user, payload.get("operation_key"), "edit", {**payload, "id": item_id}
            )
            if replay:
                return JsonResponse(event.response)
            item = PantryItem.objects.select_for_update().get(pk=item_id, user=request.user)
            check_version(item, payload.get("version"))
            if item.archived_at:
                raise StockError("Stok sudah dihapus.")
            before = snapshot(item)
            previous_conversion = (item.unit, item.ingredient_id, item.pack_weight_g)
            initial = {
                key: getattr(item, key)
                for key in PantryDetailsForm.base_fields
                if hasattr(item, key)
            }
            initial["ingredient_code"] = item.ingredient_id or ""
            form = PantryDetailsForm({**initial, **payload})
            if not form.is_valid():
                raise StockError("Periksa kembali data bahan.", 400)
            fields = form.cleaned_data
            code = fields.pop("ingredient_code")
            if code and not Ingredient.objects.filter(pk=code).exists():
                raise StockError("Bahan katalog tidak ditemukan.", 400)
            if item.name != fields["name"] and "ingredient_code" not in payload:
                code = _local_codes([fields["name"]], item.session_id, request.user)[0]
            if not code and "ingredient_code" not in payload:
                code = _local_codes([fields["name"]], item.session_id, request.user)[0]
            item.ingredient_id = code or None
            mode = fields.pop("expiry_mode")
            expiry_source = fields.pop("expiry_source") or item.expiry_source
            entered_date = fields.pop("estimated_expires_on")
            for key, value in fields.items():
                setattr(item, key, value)
            item.location = item.location or DEFAULT_LOCATION
            item.starting_on = item.starting_on or _starting_on(item)
            options = storage_options(item.ingredient_id)
            explicit = mode == "manual" or (
                "estimated_expires_on" in payload
                and mode != "auto"
                and str(entered_date or "") != before["estimated_expires_on"]
            )
            if explicit:
                item.estimated_expires_on = entered_date
                item.expiry_source = (
                    (
                        expiry_source
                        if expiry_source == "label"
                        or (
                            expiry_source == "unknown" and payload.get("expiry_source") == "unknown"
                        )
                        else "manual"
                    )
                    if entered_date
                    else "unknown"
                )
                estimate = {"message": "Tanggal pengguna/label tidak diubah otomatis."}
            else:
                # Preserve authoritative dates; estimates can shorten but never extend.
                estimate = transfer_estimate(item, options, item.location, item.starting_on)
                item.estimated_expires_on = (
                    date.fromisoformat(estimate["estimated_expires_on"])
                    if estimate["estimated_expires_on"]
                    else None
                )
                if not item.estimated_expires_on:
                    item.expiry_source = "unknown"
                elif item.expiry_source == "unknown" and not before["estimated_expires_on"]:
                    item.expiry_source = "estimate"
                item.shelf_life_days = estimate.get("shelf_life_days")
            item.shelf_life_days = shelf_life_duration(item.starting_on, item.estimated_expires_on)
            if (
                previous_conversion != (item.unit, item.ingredient_id, item.pack_weight_g)
                or item.grams_per_unit is None
            ):
                refresh_conversion(item)
            item.version += 1
            item.save()
            movement(
                item,
                event,
                "move"
                if before["location"] != item.location and before["quantity"] == str(item.quantity)
                else "correction",
                before,
            )
            event.response = {
                "saved": True,
                "version": item.version,
                "location": item.location,
                "estimated_expires_on": str(item.estimated_expires_on or ""),
                "expiry_source": item.expiry_source,
                "message": estimate["message"],
            }
            event.save(update_fields=["response"])
    except StockError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    return JsonResponse(event.response)


@api_login_required
@require_http_methods(["DELETE"])
def delete_pantry_item(request, item_id):
    if not PantryItem.objects.filter(pk=item_id, user=request.user).exists():
        return JsonResponse({"error": "Stok tidak ditemukan."}, status=404)
    if len(request.body) > 2000:
        return JsonResponse({"error": "Data terlalu besar."}, status=413)
    try:
        payload = load_payload(request.body)
        if not isinstance(payload, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Kirim data sebagai JSON."}, status=400)
    try:
        with transaction.atomic():
            event, replay = operation(
                request.user, payload.get("operation_key"), "discard", {**payload, "id": item_id}
            )
            if replay:
                return JsonResponse(event.response)
            item = PantryItem.objects.select_for_update().get(pk=item_id, user=request.user)
            check_version(item, payload.get("version"))
            if item.archived_at:
                raise StockError("Stok sudah dihapus.")
            before = snapshot(item)
            item.quantity = 0
            item.archived_at = timezone.now()
            item.version += 1
            item.save()
            movement(item, event, "discard", before)
            event.response = {"deleted": True}
            event.save(update_fields=["response"])
    except StockError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    return JsonResponse(event.response)


@api_login_required
@require_http_methods(["GET"])
def pantry_movements(request, item_id):
    item = PantryItem.objects.filter(pk=item_id, user=request.user).first()
    if item is None:
        return JsonResponse({"error": "Stok tidak ditemukan."}, status=404)
    return JsonResponse(
        {
            "movements": [
                {
                    "kind": row.get_kind_display(),
                    "before": str(row.quantity_before),
                    "after": str(row.quantity_after),
                    "created_at": row.created_at.isoformat(),
                    "snapshot": row.snapshot,
                }
                for row in item.movements.order_by("-pk")[:100]
            ]
        }
    )


@api_login_required
@require_http_methods(["GET"])
def pantry_recipe_matches(request):
    try:
        servings = int(request.GET.get("servings", "1"))
        if not 1 <= servings <= 20:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({"error": "Porsi harus 1–20."}, status=400)
    return JsonResponse({"recipes": recipe_matches(request.user, servings), "servings": servings})
