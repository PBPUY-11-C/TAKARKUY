"""Three successful calculations per browser; each window starts at its first success."""

from datetime import timedelta
from uuid import UUID, uuid4

from django.conf import settings
from django.core import signing
from django.db.models import Case, F, Q, Value, When
from django.utils import timezone
from django.utils.cache import patch_cache_control

from .models import GuestTrial

LIMIT = 3
WINDOW = timedelta(hours=24)
COOKIE_NAME = "takarkuy_trial"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60
COOKIE_SALT = "budget-planner.guest-trial.v1"


def browser_trial(request):
    try:
        trial_id = UUID(
            signing.loads(
                request.COOKIES.get(COOKIE_NAME, ""), salt=COOKIE_SALT, max_age=COOKIE_MAX_AGE
            )
        )
    except (signing.BadSignature, ValueError, TypeError):
        trial_id = uuid4()
    # Viewing a page does not create rows. The cookie is issued before the first POST.
    return GuestTrial.objects.filter(pk=trial_id).first() or GuestTrial(id=trial_id)


def trial_state(trial, now=None):
    now = now or timezone.now()
    active = trial.window_started_at is not None and now < trial.window_started_at + WINDOW
    return {
        "limit": LIMIT,
        "remaining": LIMIT - trial.successful_uses if active else LIMIT,
        "reset_at": trial.window_started_at + WINDOW if active else None,
    }


def record_success(trial, now=None):
    """Conditional UPDATE atomically claims a slot, even with stale/concurrent readers."""
    now = now or timezone.now()
    GuestTrial.objects.get_or_create(pk=trial.pk)
    expired = Q(window_started_at__isnull=True) | Q(window_started_at__lte=now - WINDOW)
    updated = (
        GuestTrial.objects.filter(pk=trial.pk)
        .filter(expired | Q(successful_uses__lt=LIMIT))
        .update(
            successful_uses=Case(When(expired, then=Value(1)), default=F("successful_uses") + 1),
            window_started_at=Case(When(expired, then=Value(now)), default=F("window_started_at")),
        )
    )
    trial.refresh_from_db()
    return bool(updated)


def protect_trial_response(response, trial):
    response.set_cookie(
        COOKIE_NAME,
        signing.dumps(str(trial.pk), salt=COOKIE_SALT),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )
    patch_cache_control(response, private=True, no_store=True)
    return response
