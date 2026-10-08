import uuid

from django.conf import settings
from django.db import models


class GuestTrial(models.Model):
    """Server-side trial usage; the browser only holds a signed opaque identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    window_started_at = models.DateTimeField(null=True, blank=True)
    successful_uses = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(successful_uses__lte=3), name="guest_trial_max_3"
            )
        ]


class BudgetPlan(models.Model):
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
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="draft"),
                name="one_planner_draft_per_user",
            )
        ]


class PlannedMeal(models.Model):
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
        ordering = ["day", "meal_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "day", "meal_type"], name="one_meal_per_plan_slot"
            )
        ]


class ShoppingListItem(models.Model):
    plan = models.ForeignKey(BudgetPlan, on_delete=models.CASCADE, related_name="shopping_items")
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.PROTECT)
    quantity_grams = models.DecimalField(max_digits=14, decimal_places=3)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2)
    snapshot = models.JSONField()
    # Set once the user moved this purchase into the pantry; never re-added.
    added_to_pantry_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "ingredient"], name="one_ingredient_per_plan_list"
            )
        ]


class PlanPreview(models.Model):
    """Short-lived server-calculated proposal; never trust a result sent by the browser."""

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
    """Account-wide fixed ten-minute window, independent of login sessions."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempts__lte=20), name="preview_quota_max_20"
            )
        ]
