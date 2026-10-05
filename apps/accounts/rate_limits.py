import hashlib
import hmac
import ipaddress
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F

from .models import AuthRateBucket


class AuthLimited(ValueError):
    def __init__(self, retry_after):
        self.retry_after = max(1, retry_after)
        super().__init__("Terlalu banyak percobaan. Silakan coba lagi nanti.")


def client_ip(request):
    peer = request.META.get("REMOTE_ADDR", "")
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return "unknown"
    networks = [ipaddress.ip_network(value) for value in settings.AUTH_TRUSTED_PROXY_CIDRS]
    if any(address in network for network in networks):
        # Walk right-to-left; never trust a client-supplied leftmost address.
        chain = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if len(chain) > 32:
            return str(address)
        for text in reversed(chain):
            try:
                candidate = ipaddress.ip_address(text.strip())
            except ValueError:
                return peer
            if not any(candidate in network for network in networks):
                return str(candidate)
    return str(address)


@transaction.atomic
def reserve_auth_attempt(request, action, identity, *, now=None):
    now = now or datetime.now(timezone.utc)
    window = 900
    start = int(now.timestamp()) // window * window
    end = datetime.fromtimestamp(start + window, timezone.utc)
    identity = str(identity).strip().lower()[:254]
    if action == "login":
        users = get_user_model().objects
        account = users.filter(email__iexact=identity).first() if "@" in identity else None
        account = account or users.filter(username__iexact=identity).first()
        if account is not None:
            identity = f"account:{account.pk}"
    limits = (
        ("identity", identity, 10 if action == "login" else 5),
        ("ip", client_ip(request), 100 if action == "login" else 30),
    )
    rows = []
    for kind, value, limit in limits:
        raw = f"auth-v1:{action}:{kind}:{value}:{start}".encode()
        key = hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()
        rows.append((key, limit))
    # Stable lock order; unique PK also serializes first creation across workers.
    for key, limit in sorted(rows):
        AuthRateBucket.objects.get_or_create(key=key, defaults={"expires_at": end})
        if not AuthRateBucket.objects.filter(key=key, attempts__lt=limit).update(
            attempts=F("attempts") + 1
        ):
            raise AuthLimited(int((end - now).total_seconds()) + 1)
    AuthRateBucket.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
