"""Public reviews only after cooking; account-wide quota and optimistic locking."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.budget_planner.services import PreviewRateLimit
from apps.catalog.models import Recipe
from apps.pantry.services import StockError

from .models import CookingHistory, RecipeReview, ReviewQuota


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
        review = RecipeReview.objects.filter(user=user, recipe_id=code).first()
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


def review_context(user, recipe, page=1):
    from django.core.paginator import Paginator

    visible = RecipeReview.objects.filter(recipe=recipe, is_hidden=False)
    stats = visible.aggregate(average=Avg("rating"), count=Count("pk"))
    reviews = Paginator(visible.select_related("user"), 5).get_page(page)
    for entry in reviews:
        entry.public_name = public_username(entry.user)
    own = RecipeReview.objects.filter(recipe=recipe, user=user).first()
    can_review = CookingHistory.objects.filter(user=user, recipe=recipe).exists()
    return {"review_stats": stats, "reviews": reviews, "own_review": own, "can_review": can_review}
