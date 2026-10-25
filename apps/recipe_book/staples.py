"""User-configurable common seasonings that need not block recipe cooking."""

STAPLE_GROUPS = (
    (
        "salt",
        "Garam",
        frozenset({"ING-GARAM", "ING-GARAM-BERYODIUM-BATA", "ING-GARAM-BERYODIUM-HALUS"}),
    ),
    ("pepper", "Merica", frozenset({"ING-MERICA"})),
    ("water", "Air", frozenset({"ING-AIR"})),
    (
        "sugar",
        "Gula pasir dan gula merah",
        frozenset(
            {
                "ING-GULA-PASIR",
                "ING-GULA-PASIR-DALAM-NEGERI",
                "ING-GULA-PASIR-KUALITAS-PREMIUM",
                "ING-GULA-PASIR-LOKAL",
                "ING-GULA-MERAH",
            }
        ),
    ),
    (
        "seasoning",
        "Penyedap atau kaldu bubuk",
        frozenset({"ING-KALDU-AYAM-BUBUK", "ING-KALDU-JAMUR"}),
    ),
    (
        "cooking_oil",
        "Minyak goreng",
        frozenset(
            {
                "ING-MINYAK-GORENG",
                "ING-MINYAK-GORENG-CURAH",
                "ING-MINYAK-GORENG-BIMOLI-KEMASAN",
                "ING-MINYAK-GORENG-KEMASAN-SEDERHANA",
                "ING-MINYAK-KITA",
                "ING-MINYAK-GORENG-KEMASAN-BERMERK-1",
                "ING-MINYAK-GORENG-KEMASAN-BERMERK-2",
            }
        ),
    ),
)

STAPLE_GROUP_CODES = {key: codes for key, _label, codes in STAPLE_GROUPS}
ALL_STAPLE_CODES = frozenset().union(*STAPLE_GROUP_CODES.values())
DEFAULT_TRACKED_STAPLE_GROUPS = ["cooking_oil"]


def tracked_staple_codes(user):
    from apps.accounts.preferences import preferences_for

    selected = preferences_for(user).tracked_staples
    groups = selected if isinstance(selected, list) else []
    return frozenset().union(
        *(STAPLE_GROUP_CODES[key] for key in groups if key in STAPLE_GROUP_CODES)
    )
