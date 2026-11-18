"""Cache resolusi nama bahan dengan lease, terikat pada versi katalog."""

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
    """Membuat key SHA-256 dari nama, versi katalog, provider, dan model LLM.

    Ganti katalog atau model otomatis membuat key baru; versi katalog wajib string fingerprint.
    """
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
    """Mengambil hasil cache yang sudah selesai (tanpa lease aktif) dan belum kedaluwarsa."""
    return NameResolution.objects.filter(
        pk=cache_key(name, catalog_version), lease__isnull=True, expires_at__gt=timezone.now()
    ).first()


def claim(name, catalog_version, *, allowed_codes=None):
    """Mencoba mengambil lease 45 detik atas key nama; mengembalikan (record, dimiliki).

    Record lama diambil alih bila sudah kedaluwarsa atau kodenya di luar allowed_codes.
    """
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
    """Menyimpan kode hasil dan melepas lease; TTL 5 menit jika gagal, 30 hari jika ada kode.

    Hasil tanpa kode disimpan 1 jam. Hanya berlaku bila lease masih milik pemanggil.
    """
    NameResolution.objects.filter(pk=record.pk, lease=record.lease).update(
        ingredient_id=code,
        lease=None,
        expires_at=timezone.now()
        + (timedelta(minutes=5) if failed else timedelta(days=30) if code else timedelta(hours=1)),
    )


def release(record):
    """Melepas lease dan langsung mengedaluwarsakan record yang masih dipegang.

    Kuota satu akun yang habis tidak boleh menghalangi akun lain mencoba cache yang sama.
    """
    NameResolution.objects.filter(pk=record.pk, lease=record.lease).update(
        lease=None, expires_at=timezone.now()
    )


def remember_photo(items, snapshot):
    """Menyimpan pasangan nama mentah dan kode bahan hasil OCR foto ke cache nama.

    Hanya item dengan kode yang ada di katalog snapshot yang disimpan.
    """
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
