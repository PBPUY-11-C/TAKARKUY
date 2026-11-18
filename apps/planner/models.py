import uuid

from django.conf import settings
from django.db import models


class BudgetPlan(models.Model):
    """Rencana makan milik user (draft atau tersimpan) beserta input, snapshot hasil, dan versinya;
    draft mencatat rencana asal agar konflik edit bisa dideteksi."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=10, choices=[("draft", "Draft"), ("saved", "Tersimpan")], default="draft"
    )
    title = models.CharField(max_length=100, default="Rencana Makan Saya")
    starts_on = models.DateField()
    inputs = models.JSONField()
    snapshot = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    source_plan = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="editing_drafts"
    )
    source_version = models.PositiveIntegerField(null=True, blank=True)
    last_saved_plan = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="saved_from_drafts"
    )
    last_saved_version = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Urut dari yang terakhir diubah; tiap user hanya boleh punya satu draft."""
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="draft"),
                name="one_planner_draft_per_user",
            )
        ]


class PlannedMeal(models.Model):
    """Satu jadwal makan dalam rencana (hari dan waktu makan) beserta resep, porsi, dan status masak."""
    plan = models.ForeignKey(BudgetPlan, on_delete=models.CASCADE, related_name="meals")
    day = models.PositiveSmallIntegerField()
    scheduled_on = models.DateField()
    meal_type = models.CharField(max_length=20)
    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.PROTECT)
    servings = models.PositiveSmallIntegerField()
    snapshot = models.JSONField()
    status = models.CharField(
        max_length=10,
        choices=[("planned", "Belum Masak"), ("cooked", "Sudah Masak"), ("skipped", "Dilewati")],
        default="planned",
    )

    class Meta:
        """Urut per hari lalu waktu makan; satu slot hari dan waktu makan hanya berisi satu menu."""
        ordering = ["day", "meal_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "day", "meal_type"], name="one_meal_per_plan_slot"
            )
        ]


class ShoppingListItem(models.Model):
    """Satu bahan di daftar belanja rencana: jumlah gram, estimasi biaya, dan kapan masuk pantry."""
    plan = models.ForeignKey(BudgetPlan, on_delete=models.CASCADE, related_name="shopping_items")
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.PROTECT)
    quantity_grams = models.DecimalField(max_digits=14, decimal_places=3)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2)
    snapshot = models.JSONField()
    added_to_pantry_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Satu bahan hanya muncul sekali per daftar belanja rencana."""
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "ingredient"], name="one_ingredient_per_plan_list"
            )
        ]


class PlanPreview(models.Model):
    """Usulan rencana berumur pendek yang dihitung server; hasil kiriman browser tidak pernah
    dipercaya."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(BudgetPlan, on_delete=models.CASCADE, related_name="previews")
    version = models.PositiveIntegerField()
    draft_id = models.UUIDField(null=True, blank=True)
    draft_version = models.PositiveIntegerField(null=True, blank=True)
    inputs = models.JSONField()
    snapshot = models.JSONField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class PlanPreviewQuota(models.Model):
    """Kuota preview per akun dengan jendela tetap sepuluh menit, tidak bergantung sesi login."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        """Database menolak percobaan lebih dari 20 dalam satu jendela."""
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempts__lte=20), name="preview_quota_max_20"
            )
        ]
