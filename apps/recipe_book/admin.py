from django.contrib import admin
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse

from .models import RecipeDataReport, RecipeReview


@admin.register(RecipeDataReport)
class RecipeDataReportAdmin(admin.ModelAdmin):
    list_display = ("recipe", "category", "status", "reporter", "created_at")
    list_filter = ("status", "category", "created_at")
    search_fields = ("recipe__name", "recipe__recipe_code", "details", "reporter__username")
    readonly_fields = ("recipe", "reporter", "category", "details", "created_at")
    fields = ("recipe", "reporter", "category", "details", "status", "created_at")
    ordering = ("status", "-created_at")

    def has_add_permission(self, request):
        return False


@admin.register(RecipeReview)
class RecipeReviewAdmin(admin.ModelAdmin):
    list_display = (
        "recipe", "user", "rating", "is_hidden", "photo_is_hidden", "photo_consent",
        "photo_moderation", "photo_moderated_at", "photo_moderated_by", "updated_at",
    )
    list_filter = ("is_hidden", "photo_is_hidden", "rating")
    search_fields = ("recipe__name", "user__username", "comment")
    readonly_fields = (
        "user", "recipe", "rating", "comment", "photo", "photo_permission_granted",
        "photo_consent_at", "photo_is_hidden", "photo_moderated_at", "photo_moderated_by",
        "version", "created_at", "updated_at",
    )
    actions = ("approve_consented_photos", "hide_selected_photos")

    @admin.display(description="Foto")
    def photo_moderation(self, obj):
        if not obj.photo:
            return "—"
        return format_html('<a href="{}">Lihat foto</a> · {}', reverse("modul4-review-photo", args=[obj.pk]), "Menunggu" if obj.photo_is_hidden else "Tampil")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Izin foto")
    def photo_consent(self, obj):
        return "Tercatat" if obj.photo_permission_granted and obj.photo_consent_at else "Tidak ada"

    @admin.action(description="Setujui foto dengan izin yang tercatat")
    def approve_consented_photos(self, request, queryset):
        eligible = queryset.filter(
            photo__gt="", photo_permission_granted=True,
            photo_consent_at__isnull=False, is_hidden=False
        )
        self._update_moderation(eligible, {
            "photo_is_hidden": False,
            "photo_moderated_at": timezone.now(),
            "photo_moderated_by": request.user,
        })

    @admin.action(description="Sembunyikan foto terpilih")
    def hide_selected_photos(self, request, queryset):
        self._update_moderation(queryset.filter(photo__gt=""), {
            "photo_is_hidden": True,
            "photo_moderated_at": timezone.now(),
            "photo_moderated_by": request.user,
        })

    @staticmethod
    def _update_moderation(queryset, changes):
        with transaction.atomic():
            review_ids = list(
                queryset.select_for_update().values_list("pk", flat=True)
            )
            if not review_ids:
                return
            queryset.model.objects.filter(pk__in=review_ids).update(
                **changes,
                version=F("version") + 1,
                updated_at=timezone.now(),
            )
