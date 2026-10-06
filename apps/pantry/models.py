from django.conf import settings
from django.db import models


class PantryItem(models.Model):
    """One purchase batch. Archive rather than delete to preserve its stock ledger."""

    EXPIRY_CHOICES = [
        ("legacy", "Tanggal lama (periksa label)"),
        ("label", "Label kemasan"),
        ("manual", "Manual"),
        ("estimate", "Estimasi"),
        ("unknown", "Belum diketahui"),
    ]
    MANUAL_CATEGORY_CHOICES = [
        ("sayur_buah", "Sayur & Buah"),
        ("daging_seafood", "Daging & Seafood"),
        ("tahu_tempe_kacang", "Tahu, Tempe & Kacang"),
        ("beras_karbohidrat", "Beras & Karbohidrat"),
        ("bumbu_minyak", "Bumbu & Minyak"),
        ("lainnya", "Lainnya"),
    ]
    CATEGORY_CHOICES = MANUAL_CATEGORY_CHOICES + [
        ("sayuran", "Sayuran (kategori lama)"),
        ("buah", "Buah (kategori lama)"),
        ("protein_hewani", "Protein Hewani (kategori lama)"),
        ("protein_nabati", "Protein Nabati (kategori lama)"),
        ("bahan_pokok", "Bahan Pokok (kategori lama)"),
    ]
    UNIT_CHOICES = [
        ("g", "g"),
        ("kg", "kg"),
        ("ml", "ml"),
        ("liter", "liter"),
        ("buah", "buah"),
        ("ikat", "ikat"),
        ("butir", "butir"),
        ("papan", "papan"),
        ("kotak", "kotak"),
        ("bungkus", "bungkus"),
        ("botol", "botol"),
        ("pak", "pak"),
        ("pack", "pack / bungkus"),
    ]
    MANUAL_UNIT_CHOICES = [
        ("g", "gram (g)"),
        ("kg", "kilogram (kg)"),
        ("ml", "milliliter (ml)"),
        ("liter", "liter"),
        ("buah", "buah"),
        ("butir", "butir"),
        ("ikat", "ikat"),
        ("pack", "pack / bungkus"),
        ("botol", "botol"),
    ]
    LOCATION_CHOICES = [
        ("chiller", "Kulkas"),
        ("freezer", "Freezer"),
        ("suhu_ruang", "Suhu Ruang"),
    ]
    SOURCE_CHOICES = [("ocr", "Struk"), ("manual", "Manual")]

    # Null is reserved for preserved legacy stock whose owner cannot be established.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE
    )
    session_id = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, blank=True, default="")
    quantity = models.DecimalField(max_digits=14, decimal_places=6)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    location = models.CharField(
        max_length=20, choices=LOCATION_CHOICES, blank=True, default="suhu_ruang"
    )
    ingredient = models.ForeignKey(
        "catalog.Ingredient", null=True, blank=True, on_delete=models.PROTECT
    )
    starting_on = models.DateField(null=True, blank=True)
    shelf_life_days = models.PositiveSmallIntegerField(null=True, blank=True)
    estimated_expires_on = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)
    base_unit = models.CharField(
        max_length=3, default="pcs", choices=[("g", "g"), ("ml", "ml"), ("pcs", "pcs")]
    )
    pack_weight_g = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    grams_per_unit = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    conversion_note = models.CharField(max_length=255, blank=True)
    expiry_source = models.CharField(max_length=10, choices=EXPIRY_CHOICES, default="unknown")
    archived_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["estimated_expires_on", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0), name="pantry_quantity_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(pack_weight_g__isnull=True) | models.Q(pack_weight_g__gt=0),
                name="pantry_pack_weight_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(grams_per_unit__isnull=True) | models.Q(grams_per_unit__gt=0),
                name="pantry_conversion_positive",
            ),
        ]


class PantryOperation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.UUIDField()
    kind = models.CharField(max_length=20)
    payload_hash = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="pantry_operation_unique")
        ]


class PantryMovement(models.Model):
    batch = models.ForeignKey(PantryItem, on_delete=models.CASCADE, related_name="movements")
    operation = models.ForeignKey(PantryOperation, null=True, on_delete=models.RESTRICT)
    kind = models.CharField(
        max_length=20,
        choices=[
            ("in", "Masuk"),
            ("correction", "Koreksi"),
            ("move", "Pindah"),
            ("discard", "Dibuang"),
            ("consume", "Dipakai"),
        ],
    )
    quantity_before = models.DecimalField(max_digits=14, decimal_places=6)
    quantity_after = models.DecimalField(max_digits=14, decimal_places=6)
    consumed_grams = models.DecimalField(max_digits=26, decimal_places=12, null=True, blank=True)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(consumed_grams__isnull=True) | models.Q(consumed_grams__gte=0),
                name="pantry_consumed_grams_nonnegative",
            )
        ]


class PantryLLMUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.DateField()
    kind = models.CharField(max_length=10, choices=[("photo", "Photo"), ("names", "Names")])
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day", "kind"], name="pantry_daily_usage_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(attempts__lte=10), name="pantry_daily_usage_limit"
            ),
        ]


class NameResolution(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    normalized_name = models.CharField(max_length=255)
    ingredient = models.ForeignKey("catalog.Ingredient", null=True, on_delete=models.SET_NULL)
    lease = models.UUIDField(null=True)
    expires_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)


class PantryNameCorrection(models.Model):
    """An OCR spelling explicitly corrected by one account."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE
    )
    session_id = models.CharField(max_length=32, db_index=True)
    raw_name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255)
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_by_user = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_name"], name="pantry_user_ocr_name_unique"
            ),
            models.UniqueConstraint(
                fields=["session_id", "normalized_name"], name="pantry_session_ocr_name_unique"
            ),
        ]
