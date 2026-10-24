from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import RecipeReview


@admin.register(RecipeReview)
class RecipeReviewAdmin(admin.ModelAdmin):
    list_display = ("recipe", "user", "rating", "is_hidden", "photo_moderation", "updated_at")
    list_filter = ("is_hidden", "photo_is_hidden", "rating")
    search_fields = ("recipe__name", "user__username", "comment")
    readonly_fields = ("user", "recipe", "rating", "comment", "photo", "version", "created_at", "updated_at")

    @admin.display(description="Foto")
    def photo_moderation(self, obj):
        if not obj.photo:
            return "—"
        return format_html('<a href="{}">Lihat foto</a> · {}', reverse("modul4-review-photo", args=[obj.pk]), "Menunggu" if obj.photo_is_hidden else "Tampil")

    def has_add_permission(self, request):
        return False
