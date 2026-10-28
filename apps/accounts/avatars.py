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
    if value in AVATAR_KEYS and value != "initials":
        return f"accounts/avatars/{value}.svg"
    return None
