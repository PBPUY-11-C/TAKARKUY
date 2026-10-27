"""Public reviews only after cooking; account-wide quota and optimistic locking."""

from datetime import timedelta
from io import BytesIO
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.budget_planner.services import PreviewRateLimit
from apps.catalog.models import Recipe
from apps.pantry.services import StockError

from . import photo_storage
from .models import CookingHistory, RecipeReview, ReviewQuota

MAX_REVIEW_PHOTO_BYTES = 6 * 1024 * 1024
MAX_REVIEW_PHOTO_PIXELS = 16_000_000


class ReviewLimited(PreviewRateLimit):
    def __init__(self, retry_after):
        self.retry_after = max(1, retry_after)
        ValueError.__init__(self, "Batas 10 upaya ulasan per 10 menit tercapai. Coba lagi nanti.")


def public_username(user):
    # Legacy accounts used their email as username. Never publish that address.
    if "@" in user.username or (user.email and user.username.casefold() == user.email.casefold()):
        alias = salted_hmac("recipe-review-public-author-v1", str(user.pk)).hexdigest()[:12]
        return f"Penakar #{alias}"
    return user.username


def review_photo_url(review):
    """Version photo URLs so moderation and consent changes bypass stale caches."""
    path = reverse("modul4-review-photo", args=[review.pk])
    return f"{path}?{urlencode({'v': review.version})}"


@transaction.atomic
def reserve_review(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    quota, _ = ReviewQuota.objects.get_or_create(user=user, defaults={"window_started_at": now})
    if quota.window_started_at <= now - timedelta(minutes=10):
        quota.window_started_at, quota.attempts = now, 0
    if quota.attempts >= 10:
        retry = max(
            1, int((quota.window_started_at + timedelta(minutes=10) - now).total_seconds()) + 1
        )
        raise ReviewLimited(retry)
    quota.attempts += 1
    quota.save()


def write_review(user, data):
    code, action = data.get("recipe_code"), data.get("action", "save")
    version = data.get("version")
    if not isinstance(code, str) or not 1 <= len(code) <= 100 or action not in {"save", "delete"}:
        raise ValueError("Kode resep atau tindakan tidak valid.")
    if version is not None and (type(version) is not int or version < 1):
        raise ValueError("Versi ulasan tidak valid.")
    if action == "save":
        rating, comment = data.get("rating"), data.get("comment", "")
        if type(rating) is not int or not 1 <= rating <= 5:
            raise ValueError("Rating harus bilangan bulat 1–5.")
        if not isinstance(comment, str) or len(comment) > 500:
            raise ValueError("Komentar maksimal 500 karakter.")
        comment = comment.strip()
    # Committed before the mutation: failed eligibility/version checks still
    # count. Logout or another worker cannot reset this quota.
    reserve_review(user)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        review = (
            RecipeReview.objects.select_for_update()
            .filter(user=user, recipe_id=code)
            .first()
        )
        if review and version != review.version:
            raise StockError("Ulasan sudah berubah. Muat ulang halaman.")
        if not review and version is not None:
            raise StockError("Ulasan sudah dihapus. Muat ulang halaman.")
        if action == "delete":
            if review is None:
                raise StockError("Ulasan tidak ditemukan.", 404)
            review.delete()
            return {"deleted": True}
        recipe = Recipe.objects.filter(pk=code, is_active=True).first()
        if recipe is None:
            raise StockError("Resep tidak tersedia.", 404)
        # Check on every save, not only when the form was displayed.
        if not CookingHistory.objects.filter(user=user, recipe=recipe).exists():
            raise StockError("Masak resep ini dahulu sebelum memberi ulasan.", 403)
        if review is None:
            review = RecipeReview(user=user, recipe=recipe)
        else:
            review.version += 1
        review.rating, review.comment = rating, comment
        # A user's edit does not undo staff moderation.
        review.save()
        return {"id": review.pk, "version": review.version}


def normalize_review_photo(upload):
    if upload is None or upload.size < 1 or upload.size > MAX_REVIEW_PHOTO_BYTES:
        raise ValueError("Pilih foto JPG, PNG, atau WebP maksimal 6 MB.")
    raw = upload.read(MAX_REVIEW_PHOTO_BYTES + 1)
    upload.close()
    if len(raw) > MAX_REVIEW_PHOTO_BYTES:
        raise ValueError("Ukuran foto maksimal 6 MB.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Format foto harus JPG, PNG, atau WebP.")
            if source.width < 1 or source.height < 1 or source.width * source.height > MAX_REVIEW_PHOTO_PIXELS:
                raise ValueError("Resolusi foto terlalu besar.")
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            oriented = ImageOps.exif_transpose(source)
            if "A" in oriented.getbands() or "transparency" in oriented.info:
                rgba = oriented.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = oriented.convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            clean = BytesIO()
            image.save(clean, format="JPEG", quality=84, optimize=True, progressive=True)
            result = clean.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Berkas bukan foto yang valid.") from exc
    if len(result) > MAX_REVIEW_PHOTO_BYTES:
        raise ValueError("Hasil kompresi foto masih terlalu besar.")
    return result


def attach_review_photo(user, code, version, upload, *, permission_granted=False):
    if not isinstance(code, str) or not 1 <= len(code) <= 100:
        raise ValueError("Kode resep tidak valid.")
    if not isinstance(version, int) or version < 1:
        raise ValueError("Versi ulasan tidak valid. Simpan ulasan lalu coba lagi.")
    if permission_granted is not True:
        raise ValueError("Konfirmasi hak penggunaan foto sebelum mengunggah.")
    # Reserve before Pillow decodes/normalizes the image so repeated expensive
    # uploads are throttled even when the image is invalid or storage later fails.
    reserve_review(user)
    normalized = normalize_review_photo(upload)
    saved_name = ""
    try:
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            review = (
                RecipeReview.objects.select_for_update()
                .filter(user=user, recipe_id=code, recipe__is_active=True)
                .first()
            )
            if review is None:
                raise StockError("Simpan ulasan untuk resep ini terlebih dahulu.", 404)
            if review.version != version:
                raise StockError("Ulasan sudah berubah. Muat ulang halaman.")
            if not CookingHistory.objects.filter(user=user, recipe_id=code).exists():
                raise StockError("Catat masak resep ini sebelum membagikan foto.", 403)
            old_name = review.photo.name if review.photo else ""
            path = review.photo.field.generate_filename(review, "photo.jpg")
            saved_name = photo_storage.default_storage.save(path, ContentFile(normalized))
            review.photo.name = saved_name
            review.photo_is_hidden = True
            review.photo_permission_granted = True
            review.photo_consent_at = timezone.now()
            review.photo_moderated_at = None
            review.photo_moderated_by = None
            review.version += 1
            review.save(update_fields=[
                "photo", "photo_is_hidden", "photo_permission_granted",
                "photo_consent_at", "photo_moderated_at", "photo_moderated_by",
                "version", "updated_at",
            ])
            if old_name:
                photo_storage.enqueue_recipe_photo_cleanup(old_name)
    except Exception:
        if saved_name:
            photo_storage.discard_uncommitted_recipe_photo(saved_name)
        raise
    return {"photo_pending_review": True, "version": review.version}


def delete_review_photo(user, code, version):
    if not isinstance(code, str) or not 1 <= len(code) <= 100:
        raise ValueError("Kode resep tidak valid.")
    if type(version) is not int or version < 1:
        raise ValueError("Versi ulasan tidak valid. Muat ulang halaman.")
    old_name = ""
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        review = (
            RecipeReview.objects.select_for_update()
            .filter(user=user, recipe_id=code)
            .first()
        )
        if review is None:
            raise StockError("Ulasan tidak ditemukan.", 404)
        if review.version != version:
            raise StockError("Ulasan sudah berubah. Muat ulang halaman.")
        if not review.photo:
            return {"photo_deleted": False, "version": review.version}
        old_name = review.photo.name
        review.photo = ""
        review.photo_permission_granted = False
        review.photo_consent_at = None
        review.photo_is_hidden = True
        review.photo_moderated_at = None
        review.photo_moderated_by = None
        review.version += 1
        review.save(update_fields=[
            "photo", "photo_permission_granted", "photo_consent_at", "photo_is_hidden",
            "photo_moderated_at", "photo_moderated_by", "version", "updated_at",
        ])
        photo_storage.enqueue_recipe_photo_cleanup(old_name)
    return {"photo_deleted": True, "version": review.version}


def review_context(user, recipe, page=1):
    from django.core.paginator import Paginator

    visible = RecipeReview.objects.filter(recipe=recipe, is_hidden=False)
    stats = visible.aggregate(average=Avg("rating"), count=Count("pk"))
    reviews = Paginator(visible.select_related("user"), 5).get_page(page)
    for entry in reviews:
        entry.public_name = public_username(entry.user)
    own = RecipeReview.objects.filter(recipe=recipe, user=user).first()
    if own and own.photo:
        own.photo_url = review_photo_url(own)
    for entry in reviews:
        if (
            entry.photo
            and not entry.photo_is_hidden
            and entry.photo_permission_granted
            and entry.photo_consent_at is not None
            and entry.photo_moderated_at is not None
        ):
            entry.photo_url = review_photo_url(entry)
    can_review = CookingHistory.objects.filter(user=user, recipe=recipe).exists()
    return {"review_stats": stats, "reviews": reviews, "own_review": own, "can_review": can_review}
