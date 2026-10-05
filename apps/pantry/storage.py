"""Location-specific estimates; a location change never resets the item's age."""

from datetime import date, timedelta

from apps.catalog.models import IngredientShelfLife

DEFAULT_LOCATION = "suhu_ruang"
LOCATION_MAP = {
    "kulkas": ("chiller",),
    "freezer": ("freezer",),
    "suhu_ruang": ("suhu_ruang",),
}


def storage_options(ingredient_code):
    options = {}
    if not ingredient_code:
        return options
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
    return options


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
            f"Estimasi dari acuan {reference['min_days']}–{reference['max_days']} hari; "
            f"dihitung sejak {starting_on.strftime('%d/%m/%Y')}. Bukan jaminan keamanan bahan."
        ),
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
    if result["estimated_expires_on"] and item.estimated_expires_on:
        result["estimated_expires_on"] = min(
            date.fromisoformat(result["estimated_expires_on"]), item.estimated_expires_on
        ).isoformat()
        result["message"] += " Perpindahan tidak memperpanjang estimasi sebelumnya."
        result["shelf_life_days"] = shelf_life_duration(
            starting_on, date.fromisoformat(result["estimated_expires_on"])
        )
    return result
