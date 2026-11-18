"""Pembersihan tahan gagal untuk foto ulasan resep yang disimpan di luar database."""

import logging

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import F

from .models import RecipePhotoCleanup

logger = logging.getLogger(__name__)


def attempt_recipe_photo_cleanup(cleanup_id, using="default"):
    """Mencoba menghapus file dari storage; gagal menambah attempts, berhasil menghapus job antrean.
    Mengembalikan True bila file terhapus atau job sudah tidak ada."""
    job = RecipePhotoCleanup.objects.using(using).filter(pk=cleanup_id).first()
    if job is None:
        return True
    try:
        default_storage.delete(job.storage_name)
    except Exception as exc:
        RecipePhotoCleanup.objects.using(using).filter(pk=cleanup_id).update(
            attempts=F("attempts") + 1,
            last_error=f"{type(exc).__name__}: {exc}"[:500],
        )
        logger.warning(
            "Could not delete recipe review photo %s (%s)",
            job.storage_name,
            type(exc).__name__,
        )
        return False
    RecipePhotoCleanup.objects.using(using).filter(pk=cleanup_id).delete()
    return True


def enqueue_recipe_photo_cleanup(storage_name, *, using="default"):
    """Mencatat job pembersihan foto lalu menjadwalkan penghapusannya setelah transaksi commit."""
    if not storage_name:
        return None
    job, _ = RecipePhotoCleanup.objects.using(using).get_or_create(storage_name=storage_name)
    transaction.on_commit(
        lambda cleanup_id=job.pk, database=using: attempt_recipe_photo_cleanup(
            cleanup_id, database
        ),
        using=using,
        robust=True,
    )
    return job.pk


def discard_uncommitted_recipe_photo(storage_name):
    """Menghapus unggahan yang transaksi database-nya gagal; bila gagal, mengantrekan pembersihannya."""
    try:
        default_storage.delete(storage_name)
    except Exception:
        logger.exception("Could not remove uncommitted recipe review photo %s", storage_name)
        try:
            enqueue_recipe_photo_cleanup(storage_name)
        except Exception:
            logger.exception("Could not queue uncommitted recipe review photo cleanup")
