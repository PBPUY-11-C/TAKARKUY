from django.core.exceptions import ValidationError
from django.db import models


class Ingredient(models.Model):
    """Bahan makanan: gizi per 100 g beserta sumbernya, dan status tinjauan alergen."""

    ingredient_code = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=40)
    base_unit = models.CharField(max_length=20)
    calories_per_100g = models.FloatField(null=True, blank=True)
    protein_per_100g = models.FloatField(null=True, blank=True)
    carbs_per_100g = models.FloatField(null=True, blank=True)
    fat_per_100g = models.FloatField(null=True, blank=True)
    nutrition_source = models.CharField(max_length=255, blank=True)
    nutrition_source_id = models.CharField(max_length=100, blank=True)
    nutrition_verified = models.BooleanField(default=False)
    calories_method = models.TextField(blank=True)
    nutrition_source_url = models.URLField(max_length=600, blank=True)
    allergen_status = models.CharField(
        max_length=20,
        default="unknown",
        choices=[("unknown", "Belum ditinjau"), ("reviewed", "Ditinjau berdasarkan jenis bahan")],
    )
    allergens = models.JSONField(default=list)
    allergen_source_url = models.URLField(max_length=600, blank=True)
    allergen_note = models.TextField(blank=True)

    def clean(self):
        """Alergen harus daftar kunci yang dikenal; status reviewed wajib punya URL sumber tinjauan."""
        from apps.login.choices import ALLERGEN_KEYS

        if not isinstance(self.allergens, list) or any(
            not isinstance(value, str) or value not in ALLERGEN_KEYS for value in self.allergens
        ):
            raise ValidationError({"allergens": "Kelompok alergen tidak valid."})
        if self.allergen_status == "reviewed" and not self.allergen_source_url:
            raise ValidationError({"allergen_source_url": "Sumber peninjauan wajib diisi."})


class IngredientPrice(models.Model):
    """Catatan harga bahan per wilayah dan tanggal, lengkap dengan sumber dan lisensinya."""

    price_code = models.CharField(max_length=100, primary_key=True)
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, db_column="ingredient_code"
    )
    price_rupiah = models.DecimalField(max_digits=14, decimal_places=2)
    quantity = models.FloatField()
    unit = models.CharField(max_length=30)
    region = models.CharField(max_length=100)
    recorded_at = models.DateField()
    source = models.CharField(max_length=255)
    source_url = models.URLField(max_length=600)
    source_recorded_at = models.DateField(null=True, blank=True)
    source_license = models.CharField(max_length=255, blank=True)
    source_commodity_name = models.CharField(max_length=255)
    price_status = models.CharField(max_length=50)

    class Meta:
        """Indeks gabungan (bahan, wilayah, tanggal catat) untuk mempercepat pencarian harga."""

        indexes =[models.Index(fields=["ingredient", "region", "recorded_at"])]


class IngredientShelfLife(models.Model):
    """Perkiraan daya simpan bahan per lokasi penyimpanan (hari minimum, maksimum, peringatan)."""

    shelf_life_code = models.CharField(max_length=100, primary_key=True)
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, db_column="ingredient_code"
    )
    storage_location = models.CharField(max_length=30)
    min_days = models.PositiveIntegerField()
    max_days = models.PositiveIntegerField()
    warning_days = models.PositiveIntegerField()
    starting_event = models.CharField(max_length=50)
    source = models.CharField(max_length=255)
    source_record_id = models.CharField(max_length=100, blank=True)
    source_url = models.URLField(max_length=600)
    source_recorded_at = models.DateField(null=True, blank=True)
    source_license = models.CharField(max_length=255, blank=True)
    source_duration = models.CharField(max_length=100)
    days_conversion_method = models.CharField(max_length=255)
    shelf_life_status = models.CharField(max_length=100)
    mapping_note = models.TextField(blank=True)


class Recipe(models.Model):
    """Resep katalog dengan status tinjauan panduan memasak dan penanda alergen sudah ditinjau."""

    recipe_code = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    base_servings = models.PositiveIntegerField(null=True, blank=True)
    meal_type = models.CharField(max_length=40, blank=True)
    instructions = models.TextField(blank=True)
    is_plannable = models.BooleanField(default=False)
    missing_data_reason = models.TextField(blank=True)
    source = models.CharField(max_length=255)
    source_url = models.URLField(max_length=600)
    raw_ingredients = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    instruction_status = models.CharField(
        max_length=20,
        default="withheld",
        db_index=True,
        choices=[
            ("source_ok", "Sumber disetujui"),
            ("authored_reviewed", "Panduan tim ditinjau"),
            ("withheld", "Ditahan"),
        ],
    )
    instruction_review_note = models.TextField(blank=True)
    instruction_reviewed_on = models.DateField(null=True, blank=True)
    allergen_reviewed = models.BooleanField(default=False, db_index=True)

    def clean(self):
        """Panduan yang tidak ditahan wajib punya teks dan catatan tinjauan; panduan tim dan resep
        Mendeley yang dipublikasikan wajib punya tanggal tinjauan."""
        if self.instruction_status != "withheld" and (
            not self.instructions.strip() or not self.instruction_review_note.strip()
        ):
            raise ValidationError(
                {"instruction_review_note": "Panduan dan bukti/catatan tinjauan wajib diisi."}
            )
        if (
            self.instruction_status == "authored_reviewed"
            or (self.pk.startswith("RCP-MDL-") and self.instruction_status != "withheld")
        ) and not self.instruction_reviewed_on:
            raise ValidationError(
                {"instruction_reviewed_on": "Tanggal tinjauan panduan tim wajib diisi."}
            )


class RecipeAllergen(models.Model):
    """Kelompok alergen turunan per resep; diisi ulang oleh rebuild_allergens, bukan manual."""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="allergen_groups")
    group = models.CharField(max_length=30, db_index=True)

    class Meta:
        """Satu kelompok alergen hanya boleh tercatat sekali per resep."""

        constraints = [
            models.UniqueConstraint(fields=["recipe", "group"], name="recipe_allergen_unique")
        ]


class RecipeIngredient(models.Model):
    """Bahan dalam resep beserta takaran, satuan, status takaran, dan teks mentahnya."""

    recipe_ingredient_code = models.CharField(max_length=100, primary_key=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, db_column="recipe_code")
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, db_column="ingredient_code"
    )
    quantity = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=30)
    is_optional = models.BooleanField(default=False)
    quantity_status = models.CharField(max_length=40)
    raw_text = models.TextField(blank=True)
    source = models.CharField(max_length=255)


class RecipeTag(models.Model):
    """Tag resep (misal slot saran atau bumbu minor) beserta sumber pembuatnya."""

    recipe_tag_code = models.CharField(max_length=100, primary_key=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, db_column="recipe_code")
    tag = models.CharField(max_length=100)
    source = models.CharField(max_length=255)


class IngredientAlias(models.Model):
    """Pemetaan nama bahan mentah dari suatu sumber ke bahan katalog."""

    alias_code = models.CharField(max_length=100, primary_key=True)
    source = models.CharField(max_length=255)
    raw_name = models.CharField(max_length=255)
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, db_column="ingredient_code"
    )
    mapping_status = models.CharField(max_length=50)


class UnitConversion(models.Model):
    """Konversi satuan bahan ke ekuivalen gram, dengan sumber dan status konversinya."""

    conversion_code = models.CharField(max_length=100, primary_key=True)
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, db_column="ingredient_code"
    )
    unit = models.CharField(max_length=30)
    gram_equivalent = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=255)
    source_url = models.URLField(max_length=600, blank=True)
    conversion_status = models.CharField(max_length=50)
    note = models.TextField(blank=True)
