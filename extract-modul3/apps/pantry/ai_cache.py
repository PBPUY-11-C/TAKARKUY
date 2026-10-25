"""Leased, catalogue-sensitive name cache. Never promotes AI guesses to aliases."""

import hashlib
import json
import os
from datetime import timedelta
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone

from .gemini_transport import DEFAULT_MODEL
from .models import NameResolution


def cache_key(name, catalog_version):
    if not isinstance(catalog_version, str):
        raise ValueError("catalog_version must be a catalogue fingerprint")
    return hashlib.sha256(
        json.dumps(
            [
                "pantry-names-v3",
                name,
                catalog_version,
                os.getenv("PANTRY_LLM_PROVIDER", "").strip().lower(),
                os.getenv("PANTRY_LLM_MODEL", "").strip() or DEFAULT_MODEL,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def lookup(name, catalog_version):
    return NameResolution.objects.filter(
        pk=cache_key(name, catalog_version), lease__isnull=True, expires_at__gt=timezone.now()
    ).first()


def claim(name, catalog_version, *, allowed_codes=None):
    key = cache_key(name, catalog_version)
    now = timezone.now()
    lease = uuid4()
    with transaction.atomic():
        try:
            with transaction.atomic():
                record = NameResolution.objects.create(
                    key=key,
                    normalized_name=name,
                    lease=lease,
                    expires_at=now + timedelta(seconds=45),
                )
            return record, True
        except IntegrityError:
            record = NameResolution.objects.select_for_update().get(pk=key)
        compatible = (
            record.ingredient_id is None
            or allowed_codes is None
            or record.ingredient_id in allowed_codes
        )
        if record.expires_at > now and (record.lease is not None or compatible):
            return record, False
        record.lease = lease
        record.ingredient_id = None
        record.expires_at = now + timedelta(seconds=45)
        record.save()
        return record, True


def finish(record, code, *, failed=False):
    NameResolution.objects.filter(pk=record.pk, lease=record.lease).update(
        ingredient_id=code,
        lease=None,
        expires_at=timezone.now()
        + (timedelta(minutes=5) if failed else timedelta(days=30) if code else timedelta(hours=1)),
    )


def release(record):
    """An account quota miss must not suppress other accounts' cache attempts."""
    NameResolution.objects.filter(pk=record.pk, lease=record.lease).update(
        lease=None, expires_at=timezone.now()
    )


def remember_photo(items, snapshot):
    from .catalog_context import normalize_name

    for item in items:
        code = item.get("ingredient_code")
        if code not in snapshot["names"]:
            continue
        record, owned = claim(
            normalize_name(item["raw"]), snapshot["version"], allowed_codes=snapshot["names"]
        )
        if owned:
            try:
                finish(record, code)
            finally:
                release(record)
