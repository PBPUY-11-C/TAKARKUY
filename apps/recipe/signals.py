from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import RecipeReview
from .photo_storage import enqueue_recipe_photo_cleanup


@receiver(post_delete, sender=RecipeReview)
def queue_deleted_review_photo(sender, instance, using, **kwargs):
    """Mengantrekan penghapusan file foto saat ulasan dihapus lewat API, admin, atau cascade ORM."""
    if instance.photo and instance.photo.name:
        enqueue_recipe_photo_cleanup(instance.photo.name, using=using)
