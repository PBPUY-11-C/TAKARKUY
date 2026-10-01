import uuid

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
