"""Location-specific estimates; a location change never resets the item's age."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.catalog.models import IngredientShelfLife

from .models import ShelfLifeEstimate

JAKARTA = ZoneInfo("Asia/Jakarta")
DEFAULT_LOCATION = "suhu_ruang"
LOCATION_MAP = {
    "kulkas": ("chiller",),
    "freezer": ("freezer",),
    "suhu_ruang": ("suhu_ruang",),
}


AI_LOCATIONS = ("suhu_ruang", "chiller", "freezer")


def shelf_key(ingredient_code, name):
    """Cache key for an AI estimate: per catalog ingredient, else per normalized name."""
    from .catalog_context import normalize_name

    if ingredient_code:
        return f"ing:{ingredient_code}"
    name = normalize_name(name)
    return f"name:{name}" if name else None


def storage_options(ingredient_code, name=None):
    if not ingredient_code:
        return _ai_options(None, name)
    options = {}
    records = IngredientShelfLife.objects.filter(ingredient_id=ingredient_code).order_by(
        "min_days", "max_days", "shelf_life_code"
    )
    for record in records:
        if not 1 <= record.min_days <= record.max_days <= 3650:
            continue
        if record.starting_event not in {"tanggal_pembelian", "mulai_disimpan"}:
            continue
        for location in LOCATION_MAP.get(record.storage_location, ()):
            options.setdefault(
                location,
                {
                    "location": location,
                    "min_days": record.min_days,
                    "max_days": record.max_days,
                    "starting_event": record.starting_event,
                    "source": record.source,
                    "source_url": record.source_url,
                    "status": record.shelf_life_status,
                },
            )
    # Official references always win; the AI guess only fills a gap.
    return options or _ai_options(ingredient_code, name)


def _ai_options(ingredient_code, name):
    key = shelf_key(ingredient_code, name)
    estimate = ShelfLifeEstimate.objects.filter(pk=key).first() if key else None
    if estimate is None:
        return {}
    return {
        location: {
            "location": location,
            "min_days": days,
            "max_days": days,
            "starting_event": "mulai_disimpan",
            "source": "Perkiraan AI",
            "source_url": "",
            "status": "ai_estimate",
        }
        for location in AI_LOCATIONS
        if (days := getattr(estimate, f"{location}_days"))
    }


def expiry_estimate(options, location, starting_on):
    reference = options.get(location)
    if reference is None:
        return {
            "estimated_expires_on": "",
            "shelf_life_days": None,
            "message": "Acuan masa simpan untuk lokasi ini belum tersedia. Isi manual bila diketahui.",
        }
    return {
        "estimated_expires_on": (starting_on + timedelta(days=reference["min_days"])).isoformat(),
        "shelf_life_days": reference["min_days"],
        "message": (
            f"Perkiraan AI sekitar {reference['min_days']} hari"
            if reference["status"] == "ai_estimate"
            else f"Estimasi dari acuan {reference['min_days']}–{reference['max_days']} hari"
        )
        + f"; dihitung sejak {starting_on.strftime('%d/%m/%Y')}. Bukan jaminan keamanan bahan.",
        "source_url": reference["source_url"],
    }


def shelf_life_duration(starting_on, expires_on):
    days = (expires_on - starting_on).days if expires_on and starting_on else -1
    return days if 0 <= days <= 3650 else None


def transfer_estimate(item, options, location, starting_on):
    if item.expiry_source in {"label", "manual", "legacy", "unknown"} and item.estimated_expires_on:
        return {
            "estimated_expires_on": item.estimated_expires_on.isoformat(),
            "shelf_life_days": shelf_life_duration(starting_on, item.estimated_expires_on),
            "message": "Tanggal label/manual/lama dipertahankan; pindah lokasi tidak mereset umur.",
        }
    result = expiry_estimate(options, location, starting_on)
    # Items enter as room temperature; a move on the day storage started is the real
    # first placement, so it is not capped. Later moves can shorten but never extend.
    placed_today = starting_on and starting_on >= timezone.localdate(timezone=JAKARTA)
    if result["estimated_expires_on"] and item.estimated_expires_on and not placed_today:
        result["estimated_expires_on"] = min(
            date.fromisoformat(result["estimated_expires_on"]), item.estimated_expires_on
        ).isoformat()
        result["message"] += " Perpindahan tidak memperpanjang estimasi sebelumnya."
        result["shelf_life_days"] = shelf_life_duration(
            starting_on, date.fromisoformat(result["estimated_expires_on"])
        )
    return result
