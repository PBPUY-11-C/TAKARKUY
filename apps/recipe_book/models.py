from django.conf import settings
from django.db import models


class RecipeFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "recipe"], name="recipe_favorite_unique")
        ]


class CookingHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("catalog.Recipe", null=True, on_delete=models.SET_NULL)
    planned_meal = models.ForeignKey(
        "budget_planner.PlannedMeal", null=True, blank=True, on_delete=models.SET_NULL
    )
    operation = models.OneToOneField("pantry.PantryOperation", on_delete=models.RESTRICT)
    recipe_name = models.CharField(max_length=255)
    servings = models.PositiveSmallIntegerField()
    snapshot = models.JSONField()
    cooked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-cooked_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["planned_meal"],
                condition=models.Q(planned_meal__isnull=False),
                name="one_cooking_per_planned_meal",
            ),
            models.CheckConstraint(
                condition=models.Q(servings__gte=1, servings__lte=10), name="cooking_servings_valid"
            ),
        ]


class RecipeReview(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=500, blank=True)
    is_hidden = models.BooleanField(default=False, db_index=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["user", "recipe"], name="one_recipe_review_per_user"),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5), name="recipe_review_rating_valid"
            ),
        ]


class ReviewQuota(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(attempts__lte=10), name="review_quota_max_10")
        ]
