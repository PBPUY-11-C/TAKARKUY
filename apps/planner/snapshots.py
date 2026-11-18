import json
from datetime import date
from decimal import Decimal

from apps.catalog.content_policy import protect_plan_instructions


def encode_value(value):
    """Hook json.dumps: Decimal dan date dibungkus jadi dict bertanda; tipe lain ditolak."""
    if isinstance(value, Decimal):
        return {"_decimal": str(value)}
    if isinstance(value, date):
        return {"_date": value.isoformat()}
    raise TypeError(f"Unsupported planner result type: {type(value).__name__}")


def decode_value(value):
    """Hook json.loads: mengembalikan dict bertanda `_decimal`/`_date` ke Decimal atau date."""
    if set(value) == {"_decimal"}:
        return Decimal(value["_decimal"])
    if set(value) == {"_date"}:
        return date.fromisoformat(value["_date"])
    return value


def freeze(result):
    """Mengubah hasil planner menjadi data JSON murni agar bisa disimpan di JSONField."""
    return json.loads(json.dumps(result, default=encode_value))


def thaw(snapshot):
    """Memulihkan snapshot (Decimal dan date) lalu menerapkan protect_plan_instructions pada
    instruksi resepnya."""
    return protect_plan_instructions(json.loads(json.dumps(snapshot), object_hook=decode_value))


def net_total(result):
    """Uang yang masih perlu dibelanjakan; snapshot lama sebelum hitungan pantry hanya punya `total`."""
    return result.get("net_total", result["total"])
