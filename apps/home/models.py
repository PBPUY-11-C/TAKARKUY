from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class MapLookupCache(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    payload = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)


class MapProviderGate(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    next_at = models.DateTimeField()
    lease_until = models.DateTimeField()
    lease = models.UUIDField(null=True)


class MapQuota(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_started_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(attempts__lte=10), name="map_quota_max_10")
        ]

class MyRecipe(models.Model):
    WAKTU_MAKAN = [
        ("pagi", "Sarapan"),
        ("siang", "Makan siang"),
        ("malam", "Makan malam"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resep_saya"
    )

    nama = models.CharField(max_length=100)
    waktu_makan = models.CharField(max_length=10, choices=WAKTU_MAKAN, default="siang")
    porsi = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(10)])
    bahan = models.TextField()
    langkah = models.TextField()
    estimasi_harga = models.PositiveIntegerField(null=True, blank=True)
    dibuat = models.DateTimeField(auto_now_add=True)
    diubah = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-diubah"]

    def __str__(self):
        return self.nama

    def daftar_bahan(self):
        return [b.strip() for b in self.bahan.splitlines() if b.strip()]

    def daftar_langkah(self):
        return [s.strip() for s in self.langkah.splitlines() if s.strip()]
