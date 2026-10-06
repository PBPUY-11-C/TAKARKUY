from django.contrib import admin

from .models import RecipeReview


@admin.register(RecipeReview)
class RecipeReviewAdmin(admin.ModelAdmin):
    list_display = ("recipe", "user", "rating", "is_hidden", "updated_at")
    list_filter = ("is_hidden", "rating")
    search_fields = ("recipe__name", "user__username", "comment")
    readonly_fields = ("user", "recipe", "rating", "comment", "version", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False
