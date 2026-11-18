AVATAR_CHOICES = (
    ("initials", "Inisial"),
    ("takar", "Si Takar"),
    ("chef", "Koki"),
    ("rice", "Nasi"),
    ("leaf", "Daun"),
    ("tempe", "Tempe"),
    ("carrot", "Wortel"),
)
AVATAR_KEYS = tuple(value for value, _ in AVATAR_CHOICES)


def avatar_asset(value):
    """Path statis SVG untuk kunci avatar; None untuk "initials" atau kunci yang tidak dikenal."""
    if value in AVATAR_KEYS and value != "initials":
        return f"login/avatars/{value}.svg"
    return None
