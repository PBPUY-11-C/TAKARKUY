from django import template

register = template.Library()


@register.filter
def rupiah(value):
    """Filter template: format angka jadi "Rp 150.000"; nilai yang bukan angka jadi "Rp —"."""
    try:
        return "Rp " + format(int(value), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "Rp —"
