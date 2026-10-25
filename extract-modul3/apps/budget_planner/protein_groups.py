"""Main protein source per recipe, used to keep menus from repeating one protein."""

# Explicit codes instead of substring rules: "ING-TELUR-AYAM" must not count as
# chicken, and "ING-KACANG-PANJANG" is a vegetable despite its catalog category.
PROTEIN_GROUPS = {
    "ayam": (
        "ING-ATI-AMPELA",
        "ING-DAGING-AYAM",
        "ING-DAGING-AYAM-BROILER",
        "ING-DAGING-AYAM-KAMPUNG",
        "ING-DAGING-AYAM-RAS-SEGAR",
    ),
    "telur": (
        "ING-TELUR-AYAM",
        "ING-TELUR-AYAM-BROILER",
        "ING-TELUR-AYAM-KAMPUNG",
        "ING-TELUR-AYAM-RAS-SEGAR",
        "ING-TELUR-PUYUH",
    ),
    "sapi": (
        "ING-DAGING-SAPI",
        "ING-DAGING-SAPI-KUALITAS-1",
        "ING-DAGING-SAPI-KUALITAS-2",
        "ING-DAGING-SAPI-LOKAL-HAS-DALAM",
        "ING-DAGING-SAPI-LOKAL-HAS-LUAR",
        "ING-DAGING-SAPI-LOKAL-PAHA-BELAKANG",
        "ING-DAGING-SAPI-LOKAL-PAHA-DEPAN",
        "ING-DAGING-SAPI-LOKAL-TETELAN",
    ),
    "ikan": (
        "ING-IKAN-ASIN-TERI-NO-2",
        "ING-IKAN-BANDENG",
        "ING-IKAN-DORI",
        "ING-IKAN-KEMBUNG",
        "ING-IKAN-LELE",
        "ING-IKAN-MAS",
        "ING-IKAN-MUJAIR",
        "ING-IKAN-PATIN",
        "ING-IKAN-SEGAR-TONGKOL-TUNA-CAKALANG",
        "ING-IKAN-TENGGIRI",
        "ING-IKAN-TONGKOL",
        "ING-IKAN-TUNA",
    ),
    "seafood": ("ING-CUMI", "ING-EBI", "ING-UDANG"),
    "tahu_tempe": ("ING-TAHU-MENTAH-PCS", "ING-TAHU-PUTIH", "ING-TEMPE", "ING-TEMPE-PCS"),
    "kacang": (
        "ING-KACANG-HIJAU",
        "ING-KACANG-KEDELAI",
        "ING-KACANG-KEDELAI-IMPOR",
        "ING-KACANG-TANAH",
    ),
    "susu": (
        "ING-KEJU-CHEDDAR",
        "ING-SUSU-BALITA-SGM-400GR",
        "ING-SUSU-BUBUK-DANCOW",
        "ING-SUSU-BUBUK-INDOMILK",
        "ING-SUSU-KENTAL-MANIS-MERK-BENDERA",
        "ING-SUSU-KENTAL-MANIS-MERK-INDOMILK",
        "ING-SUSU-KOTAK",
        "ING-SUSU-SAPI-SEGAR",
    ),
}
NO_PROTEIN_GROUP = "lainnya"
# Catalog "protein" items that are deliberately not a main protein source.
NOT_MAIN_PROTEIN = {"ING-KACANG-PANJANG"}
GROUP_BY_CODE = {code: group for group, codes in PROTEIN_GROUPS.items() for code in codes}


def main_protein_group(links):
    """Return the group of the heaviest protein ingredient in a recipe."""
    grams = {}
    for link in links:
        group = GROUP_BY_CODE.get(link.ingredient_id)
        if group:
            grams[group] = grams.get(group, 0) + (link.quantity or 0)
    if not grams:
        return NO_PROTEIN_GROUP
    return max(sorted(grams), key=grams.get)
