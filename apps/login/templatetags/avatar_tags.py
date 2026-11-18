from django import template
from django.templatetags.static import static

from ..avatars import avatar_asset

register = template.Library()


@register.simple_tag
def avatar_url(value):
    """Template tag: URL statis gambar avatar, atau string kosong untuk avatar inisial."""
    asset = avatar_asset(value)
    return static(asset) if asset else ""
