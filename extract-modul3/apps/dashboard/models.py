from django.conf import settings
from django.db import models


class MapLookupCache(models.Model):
    # Public place results only. No GPS, user identity, or personal address.
    key = models.CharField(max_length=64, primary_key=True)
    payload = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)


class MapProviderGate(models.Model):
    # One shared lock/cooldown across all workers and users for each provider.
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
