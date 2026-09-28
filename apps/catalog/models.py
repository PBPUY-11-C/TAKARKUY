from django.db import models


class Ingredient(models.Model):
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
    calories_method = models.CharField(max_length=255, blank=True)
    nutrition_source_url = models.URLField(max_length=600, blank=True)


class IngredientPrice(models.Model):
    price_code = models.CharField(max_length=100, primary_key=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, db_column='ingredient_code')
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
        indexes = [models.Index(fields=['ingredient', 'region', 'recorded_at'])]


class IngredientShelfLife(models.Model):
    shelf_life_code = models.CharField(max_length=100, primary_key=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, db_column='ingredient_code')
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


class RecipeIngredient(models.Model):
    recipe_ingredient_code = models.CharField(max_length=100, primary_key=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, db_column='recipe_code')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, db_column='ingredient_code')
    quantity = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=30)
    is_optional = models.BooleanField(default=False)
    quantity_status = models.CharField(max_length=40)
    raw_text = models.TextField(blank=True)
    source = models.CharField(max_length=255)


class RecipeTag(models.Model):
    recipe_tag_code = models.CharField(max_length=100, primary_key=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, db_column='recipe_code')
    tag = models.CharField(max_length=100)
    source = models.CharField(max_length=255)


class IngredientAlias(models.Model):
    alias_code = models.CharField(max_length=100, primary_key=True)
    source = models.CharField(max_length=255)
    raw_name = models.CharField(max_length=255)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, db_column='ingredient_code')
    mapping_status = models.CharField(max_length=50)


class UnitConversion(models.Model):
    conversion_code = models.CharField(max_length=100, primary_key=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, db_column='ingredient_code')
    unit = models.CharField(max_length=30)
    gram_equivalent = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=255)
    source_url = models.URLField(max_length=600, blank=True)
    conversion_status = models.CharField(max_length=50)
    note = models.TextField(blank=True)
