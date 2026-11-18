"""Foto resep kurasi beserta metadata atribusinya."""

import csv
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "mapping" / "recipe_image_mapping.csv"


@lru_cache(maxsize=4)
def _read_recipe_image_index(modified_ns, file_size):
    """Membaca CSV pemetaan foto (baris ber-image_url) per recipe_code; di-cache sampai
    mtime atau ukuran berkas berubah."""
    try:
        with MAPPING_PATH.open(encoding="utf-8-sig", newline="") as source:
            return {
                row["recipe_code"]: row
                for row in csv.DictReader(source)
                if row.get("recipe_code") and row.get("image_url")
            }
    except FileNotFoundError:
        return {}


def recipe_image_index():
    """Indeks foto kurasi per recipe_code; dict kosong jika berkas pemetaan tidak ada."""
    try:
        stat = MAPPING_PATH.stat()
    except FileNotFoundError:
        return {}
    return _read_recipe_image_index(stat.st_mtime_ns, stat.st_size)


def recipe_image_for(recipe_code):
    """Data foto untuk satu resep, atau None jika belum ada foto kurasi maupun komunitas."""
    return recipe_images_for([recipe_code]).get(recipe_code)


def recipe_images_for(recipe_codes):
    """Foto kurasi lebih dulu; resep tanpa foto kurasi memakai foto ulasan komunitas terbaru
    yang berizin, sudah dimoderasi, dan tidak disembunyikan."""
    codes = set(recipe_codes)
    curated = recipe_image_index()
    images = {code: curated[code] for code in codes if code in curated}
    missing_codes = codes - images.keys()
    if not missing_codes:
        return images

    from django.urls import reverse

    from apps.recipe.models import RecipeReview
    from apps.recipe.reviews import public_username, review_photo_url

    source_base = reverse("recipe:show_recipes")
    reviews = (
        RecipeReview.objects.filter(
            recipe_id__in=missing_codes,
            recipe__is_active=True,
            photo__gt="",
            photo_is_hidden=False,
            is_hidden=False,
            photo_permission_granted=True,
            photo_consent_at__isnull=False,
            photo_moderated_at__isnull=False,
        )
        .select_related("recipe", "user")
        .order_by("recipe_id", "-updated_at", "-pk")
    )
    for review in reviews:
        if review.recipe_id in images:
            continue
        review_url = f"{source_base}?{urlencode({'recipe': review.recipe_id})}#recipe-reviews"
        images[review.recipe_id] = {
            "image_url": review_photo_url(review),
            "source_url": review_url,
            "creator": public_username(review.user),
            "license_name": "Foto komunitas · izin untuk TAKARKUY",
            "license_url": review_url,
            "file_title": f"Foto komunitas: {review.recipe.name}",
        }
    return images
