"""Bentuk error seragam untuk seluruh API: {"error": pesan, "code": kode}, plus "fields" untuk
validasi. Aplikasi Flutter cukup membaca satu bentuk ini dari modul mana pun."""

from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def _first_message(detail):
    """Pesan pertama dari detail validasi yang bisa berupa dict, list, atau teks."""
    while isinstance(detail, (dict, list)) and detail:
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail) if detail else "Data tidak valid."


def api_exception_handler(exc, context):
    """Membungkus error bawaan DRF (403, 404, 405, 415, 400, 429, dsb.) ke bentuk seragam;
    header seperti Retry-After tetap dipertahankan."""
    response = exception_handler(exc, context)
    if response is None:
        return None
    detail = response.data
    if isinstance(exc, ValidationError):
        response.data = {"error": _first_message(detail), "code": "invalid", "fields": detail}
    else:
        message = detail.get("detail", detail) if isinstance(detail, dict) else detail
        response.data = {
            "error": str(message),
            "code": getattr(message, "code", None) or getattr(exc, "default_code", "error"),
        }
    return response
