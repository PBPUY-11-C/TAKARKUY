from uuid import uuid4

from django.conf import settings
from django.db import models


def recipe_review_photo_path(instance, filename):
    """Membuat path acak per resep untuk foto ulasan; nama asli diabaikan karena file selalu JPEG."""
    return f"recipe-reviews/{instance.recipe_id}/{uuid4().hex}.jpg"


class RecipeFavorite(models.Model):
    """Resep yang ditandai favorit oleh pengguna; satu baris per pasangan pengguna dan resep."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "recipe"], name="recipe_favorite_unique")
        ]


class RecipeNote(models.Model):
    """Catatan pribadi pengguna untuk sebuah resep, maksimal satu catatan per resep."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.CASCADE)
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "recipe"], name="recipe_note_unique")
        ]


class CookingHistory(models.Model):
    """Riwayat Sudah Masak beserta snapshot resep dan operasi pantry yang mengurangi stok.
    Satu menu rencana hanya boleh dicatat masak sekali."""
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
    """Ulasan publik satu pengguna per resep; foto tersembunyi sampai dimoderasi.
    Field version dipakai untuk optimistic locking."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=500, blank=True)
    photo = models.FileField(upload_to=recipe_review_photo_path, blank=True)
    photo_is_hidden = models.BooleanField(default=True, db_index=True)
    photo_permission_granted = models.BooleanField(default=False)
    photo_consent_at = models.DateTimeField(null=True, blank=True)
    photo_moderated_at = models.DateTimeField(null=True, blank=True)
    photo_moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="moderated_recipe_photos",
    )
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


class RecipePhotoCleanup(models.Model):
    """Antrean file foto ulasan yang harus dihapus dari storage, beserta jumlah percobaan dan error."""
    storage_name = models.CharField(max_length=255, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]


class ReviewQuota(models.Model):
    """Kuota upaya ulasan per akun: maksimal 10 upaya dalam jendela 10 menit."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(attempts__lte=10), name="review_quota_max_10")
        ]


class RecipeBookPreviewQuota(models.Model):
    """Kuota estimasi dan preview Buku Resep per akun, terpisah dari kuota Planner."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempts__lte=60), name="recipe_preview_quota_max_60"
            )
        ]


class RecipeDataReport(models.Model):
    """Laporan pengguna tentang data resep yang salah, ditindaklanjuti staf lewat admin."""
    CATEGORY_CHOICES = [
        ("ingredients", "Bahan atau takaran"),
        ("instructions", "Panduan memasak"),
        ("photo", "Foto resep"),
        ("nutrition", "Informasi gizi"),
        ("other", "Lainnya"),
    ]
    STATUS_CHOICES = [
        ("open", "Belum ditinjau"),
        ("reviewing", "Sedang ditinjau"),
        ("resolved", "Selesai diperbaiki"),
        ("dismissed", "Tidak ditindaklanjuti"),
    ]

    recipe = models.ForeignKey("catalog.Recipe", on_delete=models.CASCADE, related_name="data_reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_recipe_data_reports",
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    details = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open", db_index=True)
    decision_note = models.TextField(max_length=1000, blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-created_at"]

    def clean(self):
        """Status ditinjau wajib punya penanggung jawab dan jadwal tindak lanjut.
        Status selesai atau ditolak wajib punya catatan keputusan."""
        from django.core.exceptions import ValidationError

        super().clean()
        if self.status == "reviewing" and not self.assigned_to_id:
            raise ValidationError({"assigned_to": "Pilih penanggung jawab saat laporan ditinjau."})
        if self.status == "reviewing" and not self.follow_up_at:
            raise ValidationError({"follow_up_at": "Tentukan waktu tindak lanjut saat laporan ditinjau."})
        if self.status in {"resolved", "dismissed"} and not self.decision_note.strip():
            raise ValidationError({"decision_note": "Catat alasan sebelum menutup laporan."})
