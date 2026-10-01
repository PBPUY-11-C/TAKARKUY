from django.conf import settings
from django.db import models


class PantryItem(models.Model):
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
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
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

    class Meta:
        ordering = ["estimated_expires_on", "id"]


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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_name"], name="pantry_user_ocr_name_unique"
            ),
            models.UniqueConstraint(
                fields=["session_id", "normalized_name"], name="pantry_session_ocr_name_unique"
            ),
        ]
