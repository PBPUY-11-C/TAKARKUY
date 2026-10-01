"""Location-specific estimates; a location change never resets the item's age."""

from datetime import timedelta

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
