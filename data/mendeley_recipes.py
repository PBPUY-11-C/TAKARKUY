"""Promote Mendeley Indonesian recipes that can be fully priced and costed.

Source: Purwanto et al., "Indonesian recipe nutrition" v3, Mendeley Data,
CC BY 4.0 (attribution required). Only recipes whose every ingredient maps to a
priced catalog food with four macros, with a halal ingredient list, a main-meal
title and plausible per-serving nutrition, become plannable. Everything else
is kept in the audit with its blocker instead of being guessed.
"""

import csv
import hashlib
import json
import re
from contextlib import contextmanager

try:
    from . import recipe_estimation as estimation
    from .recipe_names import EXCLUDE, load_overrides, standard_name
except ImportError:
    import recipe_estimation as estimation
    from recipe_names import EXCLUDE, load_overrides, standard_name

normalize = estimation.normalize

MENDELEY_URL = "https://data.mendeley.com/datasets/8b4ztns76h/3"
SOURCE = "Mendeley Data, Purwanto et al. v3 (CC BY 4.0); estimasi takaran TAKARKUY"
RULES_VERSION = "takarkuy-mendeley-2026-10-05-v2"
MACROS = ("calories", "protein", "carbs", "fat")

# Unit mass (g), mass per 240 ml cup, default batch amount (g) for foods the
# shared estimator has no profile for yet. Same meaning as estimation.PROFILES.
EXTRA_PROFILES = {
    "KACANG-PANJANG": (10, 110, 100),
    "TAUGE": (0, 104, 100),
    "LABU-SIAM": (200, 130, 200),
    "KELAPA": (350, 80, 100),
    "EBI": (0, 128, 15),
    "TERASI": (5, 240, 5),
    "CENGKEH": (0.1, 0, 1),
    "JAMUR-KUPING": (5, 50, 50),
    "BIHUN": (0, 0, 100),
    "SOUN": (0, 0, 100),
    "JENGKOL": (15, 0, 150),
    "PETAI": (4, 0, 50),
    "IKAN-PATIN": (0, 0, 300),
    "IKAN-TENGGIRI": (0, 0, 250),
    "IKAN-SEGAR-TONGKOL-TUNA-CAKALANG": (0, 0, 250),
    "IKAN-ASIN-TERI-NO-2": (0, 60, 30),
    "IKAN-KEMBUNG": (0, 0, 300),
    "IKAN-BANDENG": (0, 0, 300),
    "IKAN-MAS": (0, 0, 300),
    "ATI-AMPELA": (40, 0, 200),
    "LABU-KUNING": (0, 116, 200),
    "KENCUR": (5, 0, 5),
    "KALDU-JAMUR": (0, 128, 3),
    "KACANG-TANAH": (0.5, 146, 50),
    "JAGUNG-MANIS": (150, 145, 150),
    "KANGKUNG": (0, 30, 200),
    "PAKCOY": (100, 0, 150),
    "SAWI-PUTIH": (500, 0, 200),
}
# Whole fish bought "per ekor" without a source weight: gross mass per fish.
FISH_PER_EKOR = {
    "IKAN-PATIN": 500,
    "IKAN-TENGGIRI": 500,
    "IKAN-SEGAR-TONGKOL-TUNA-CAKALANG": 300,
    "IKAN-KEMBUNG": 150,
    "IKAN-BANDENG": 300,
    "IKAN-MAS": 400,
}
FISH_EDIBLE_SHARE = 0.6
# Household measures the shared estimator does not know, rewritten to grams.
MEASURE_REWRITES = (
    (r"^(\d+(?:[.,]\d+)?)\s*(?:jempol|ibu jari)\b", r"\1 ruas", ""),
    (r"^(?:1\s*)?sejumput\b", "secukupnya", ""),
    (r"^(\d+(?:[.,]\d+)?)\s*(?:genggam|gengam)\b", None, "KEMANGI:10|TAUGE:50|EBI:15"),
    (
        r"^(\d+(?:[.,]\d+)?)\s*(?:bungkus|bks|sachet|saset)\b",
        None,
        "SANTAN:65|BIHUN:100|SOUN:100|TERASI:5|KALDU-AYAM-BUBUK:9|KALDU-JAMUR:9",
    ),
    (r"^(\d+(?:[.,]\d+)?)\s*papan\b", None, "TEMPE:450"),
    (
        r"^(\d+(?:[.,]\d+)?)\s*ikat\b",
        None,
        "BAYAM:250|KANGKUNG:250|KACANG-PANJANG:250|PAKCOY:250|KEMANGI:50|DAUN-BAWANG:50|SELEDRI:50",
    ),
    (r"^(\d+(?:[.,]\d+)?)\s*(?:ruas|cm)\b", None, "KENCUR:5|KAYU-MANIS:0.5"),
    (r"^(\d+(?:[.,]\d+)?)\s*(?:blok|bh|buah|biji)\b", None, "TERASI:5"),
)
NOT_MAIN = re.compile(
    r"\b(?:kue|cake|bolu|puding|pudding|agar|minuman|jus|juice|wedang|smoothie|sirup|selai|"
    r"keripik|kripik|kerupuk|rempeyek|peyek|cookies|kukis|brownies?|donat|martabak manis|"
    r"klepon|onde|dodol|manisan|kolak|sumsum|candil|cendol|dawet|serabi|apem|lapis|nastar|"
    r"kastengel|pastel|risol(?:es)?|lumpia|bakwan|cireng|cilok|tahu isi|gorengan|bumbu dasar|"
    r"saus|kaldu|minyak|camilan|cemilan|snack|es|teh|kopi|susu|roti manis|pisang goreng|"
    r"bala|cimol|seblak|bandrek|cuko|mpasi|chili oil|minyak cabai|sambal bawang)\b"
)
STARTS_AS_CONDIMENT = re.compile(r"^(?:sambal|sambel|bumbu|acar)\b")
BREAKFAST = re.compile(
    r"^(?:bubur|nasi uduk|nasi kuning|lontong|ketupat|kupat|roti|sandwich|omelet|omelette|"
    r"telur dadar|nasi goreng|mi goreng|mie goreng|oat|pancake|nasi liwet|ketan|arem)"
)
DINNER = re.compile(
    r"\b(?:sup|sop|soto|sayur|tumis|cah|oseng|osengan|pepes|pindang|garang asem|asem|bening|"
    r"lodeh|capcay|cap cay|kuah|rawon|brongkos|mangut|bothok|botok|urap|pecel|gado|sambal goreng)\b"
)
TITLE_NOISE = re.compile(
    r"\b(?:resep|simple|simpel|praktis|enak|mudah|sederhana|ala|rumahan|special|spesial|"
    r"ekonomis|anak kos|kos|homemade|home made|khas|masakan)\b"
)
ALLERGENS = (
    (("TAHU", "TEMPE", "KEDELAI"), "mengandung_kedelai"),
    (("TELUR",), "mengandung_telur"),
    (("UDANG", "EBI", "TERASI"), "mengandung_krustasea"),
    (("IKAN",), "mengandung_ikan"),
    (("KACANG-TANAH",), "mengandung_kacang"),
    (("SUSU", "KEJU"), "mengandung_susu"),
    (("TEPUNG-TERIGU", "ROTI", "TEPUNG-PANIR"), "mengandung_gluten"),
)
# A title food must appear in the ingredient list; some source records list only
# the seasoning of a dish, which would otherwise be priced as a full meal.
TITLE_REQUIRES = (
    (r"\b(?:mie|mi|bakmi|kwetiau|kwetiaw)\b", ("ING-MIE-",)),
    (r"\b(?:bakso|baso|pentol)\b", ("ING-BAKSO",)),
    (r"\b(?:nasi|lontong|ketupat|kupat|bubur)\b", ("ING-BERAS",)),
    (r"\b(?:bihun)\b", ("ING-BIHUN",)),
    (r"\b(?:soun|suun|sohun)\b", ("ING-SOUN",)),
    (r"\btahu\b", ("ING-TAHU-",)),
    (r"\btempe\b", ("ING-TEMPE",)),
    (r"\b(?:ayam|chicken)\b", ("ING-DAGING-AYAM", "ING-ATI-AMPELA")),
    (r"\b(?:sapi|daging|empal|rendang|semur daging|rawon)\b", ("ING-DAGING-SAPI",)),
    (r"\b(?:udang|ebi|rebon)\b", ("ING-UDANG", "ING-EBI")),
    (r"\b(?:telur|telor|endog)\b", ("ING-TELUR-",)),
    (
        r"\b(?:ikan|lele|patin|tongkol|tuna|cakalang|bandeng|kembung|teri|tenggiri|nila|gurame|mujair|mas)\b",
        ("ING-IKAN-",),
    ),
    (r"\b(?:jengkol)\b", ("ING-JENGKOL",)),
    (r"\b(?:kentang)\b", ("ING-KENTANG",)),
)
ANIMAL = ("ING-DAGING-", "ING-IKAN-", "ING-UDANG", "ING-TELUR-", "ING-EBI", "ING-ATI-AMPELA")


def stable(prefix, *parts):
    """Same ID scheme as build_final.stable."""
    return prefix + "-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12].upper()


@contextmanager
def extra_profiles():
    added = {k: v for k, v in EXTRA_PROFILES.items() if k not in estimation.PROFILES}
    estimation.PROFILES.update(added)
    try:
        yield
    finally:
        for key in added:
            del estimation.PROFILES[key]


def load_terms(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                (re.compile(row["pattern"]), row["action"], row["ingredient_code"], row["note"])
            )
    return rows


def clean_term(text):
    text = normalize(text)
    text = re.sub(r"\([^)]*\)", "", text)
    return text.strip(" .,-:;*")


def clean_title(title):
    title = re.sub(r"^\W*\d+\s*[).]\s*", "", str(title))
    title = re.sub(r"[^\w\s(),.&'/-]", "", title)
    return re.sub(r"\s+", " ", title).strip(" .,-")


def display_title(title):
    """Readable name: drop 'resep', fluff in brackets and trailing remarks."""
    name = re.sub(r"(?i)^resep\s+(?:masakan\s+)?(?:sehari-hari\s+)?", "", title)
    name = re.sub(
        r"\s*[(\[][^)\]]*(?:masakan|rumahan|simple|simpel|anak kos|mudah|sederhana|praktis|enak|"
        r"menu|resep|ekonomis|hemat)[^)\]]*[)\]]",
        "",
        name,
        flags=re.I,
    )
    name = re.split(r",|\s+-\s+(?=(?:masakan|resep|menu)\b)", name, maxsplit=1, flags=re.I)[0]
    name = re.sub(r"\s+", " ", name).strip(" .,-")
    letters = [c for c in name if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        name = name.title()
    return name[:1].upper() + name[1:]


def title_key(title):
    text = normalize(re.sub(r"\([^)]*\)", "", title))
    text = TITLE_NOISE.sub(" ", re.sub(r"[^\w\s]", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def clean_instructions(text):
    text = re.sub(r"\s*,{2,}\s*", ". ", str(text))
    text = re.sub(r"\?{2,}|[^\w\s.,;:()/%&'+-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,")
    return text + "." if text else ""


def meal_type(title, source_id):
    """Breakfast/dinner by title words; other main dishes alternate lunch/dinner.

    Most Indonesian main dishes suit either slot, so the split keeps both pools
    comparable instead of claiming a slot the source never stated.
    """
    text = normalize(title)
    if BREAKFAST.search(text):
        return "sarapan"
    if DINNER.search(text):
        return "makan_malam"
    return "makan_siang" if int(source_id) % 2 == 0 else "makan_malam"


def number(value):
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def resolve(raw, terms):
    """Return (action, ingredient_code, note) for one source ingredient text."""
    term = clean_term(raw)
    if not term or estimation.is_section_heading(term):
        return "heading", "", "judul bagian, bukan bahan"
    for pattern, action, code, note in terms:
        if pattern.fullmatch(term):
            return action, code, note
    code = estimation.resolve_ingredient(term, "id")
    return ("map", code, "") if code else ("unmapped", "", "bahan belum dipetakan")


def measure_text(row):
    value = row.get("value")
    unit = str(row.get("measurement") or "").strip().casefold()
    if row.get("is_secukupnya") or unit in ("secukupnya", "sesuai selera") or number(value) is None:
        return "secukupnya"
    if unit in ("none", "", "unit", "jumlah"):
        unit = ""
    amount = f"{number(value):g}"
    return f"{amount} {unit}".strip()


def estimate(row, code):
    """Return (edible_g, purchase_g, note) or (None, None, reason)."""
    short = code.removeprefix("ING-")
    source_g = number(row.get("weight_in_grams"))
    bdd = number(row.get("BDD"))
    measure = measure_text(row)
    if source_g and row.get("name_of_material"):
        share = min(bdd, 100) / 100 if bdd else 1
        return (
            source_g * share,
            source_g,
            f"berat sumber Mendeley {source_g:g} g; BDD {bdd or 100:g}% untuk bagian termakan",
        )
    match = re.match(r"^(\d+(?:[.,]\d+)?)\s*(?:ekor|ekr)\b", measure)
    if match and short in FISH_PER_EKOR:
        gross = number(match[1]) * FISH_PER_EKOR[short]
        return (
            gross * FISH_EDIBLE_SHARE,
            gross,
            f"asumsi TAKARKUY {FISH_PER_EKOR[short]} g per ekor; 60% daging termakan",
        )
    for pattern, replacement, per_code in MEASURE_REWRITES:
        match = re.match(pattern, measure)
        if not match:
            continue
        if replacement is not None:
            measure = re.sub(pattern, replacement, measure)
            break
        grams = dict(item.split(":") for item in per_code.split("|")).get(short)
        if grams:
            total = number(match[1]) * float(grams)
            return total, total, f"asumsi TAKARKUY {grams} g per satuan rumah tangga"
    grams, note, _ = estimation.estimate_quantity(measure, code, "id")
    if grams is None:
        return None, None, note
    purchase = grams / 0.6 if "belanja memakai berat utuh" in note else grams
    return grams, purchase, note


def build_mendeley(root, items, price_by_code, existing_names):
    """Return recipes, links, tags, estimates and a per-recipe audit."""
    data = json.loads(
        (root / "scratch/mendeley_indonesian_recipe_nutrition_v3.json").read_text(encoding="utf-8")
    )["data"]
    terms = load_terms(root / "mapping/mendeley_terms.csv")
    overrides = load_overrides(root / "mapping/recipe_name_overrides.csv")
    seen = {title_key(name) for name in existing_names}
    recipes, links, tags, estimates, audit = [], [], [], [], []
    with extra_profiles():
        for source in data:
            code = f"RCP-MDL-{int(source['id']):04d}"
            name = display_title(clean_title(source.get("title", "")))
            override, override_reason = overrides.get(code, ("", ""))
            if override and override != EXCLUDE:
                name = override
            name = standard_name(name) if name else name
            texts = [normalize(row.get("ingredient", "")) for row in source["composition"]]
            errors, minor, quantities, purchases, provenance = [], [], {}, {}, {}
            excluded = None
            if override == EXCLUDE:
                excluded = "kurasi nama: " + override_reason
            elif not name:
                excluded = "judul kosong"
            elif any(resolve(text, terms)[0] == "block" for text in texts + [normalize(name)]):
                excluded = "bahan non-halal"
            elif NOT_MAIN.search(normalize(name)) or (
                STARTS_AS_CONDIMENT.match(normalize(name))
                and not any(re.search(pattern, normalize(name)) for pattern, _ in TITLE_REQUIRES)
            ):
                excluded = "bukan menu utama"
            elif title_key(name) in seen:
                excluded = "duplikat nama resep"
            if excluded is None:
                for position, row in enumerate(source["composition"], 1):
                    raw = str(row.get("ingredient", "")).strip()
                    action, ic, note = resolve(raw, terms)
                    entry = dict(
                        ingredient_position=str(position),
                        raw_ingredient=raw,
                        raw_measure=measure_text(row),
                        ingredient_code=ic,
                        quantity_g="",
                        purchase_quantity_g="",
                        status=action,
                        estimation_note=note,
                        reference_url=MENDELEY_URL,
                        recipe_source_url=MENDELEY_URL,
                        rules_version=RULES_VERSION,
                    )
                    if action == "minor":
                        minor.append(raw)
                    elif action == "unmapped":
                        errors.append(f"padanan bahan: {clean_term(raw)}")
                    elif action == "map":
                        grams, buy, qty_note = estimate(row, ic)
                        entry["estimation_note"] = "; ".join(filter(None, [note, qty_note]))
                        if grams is None:
                            errors.append(f"takaran {clean_term(raw)}: {qty_note}")
                        else:
                            entry.update(
                                quantity_g=round(grams, 3),
                                purchase_quantity_g=round(buy, 3),
                                status="estimated",
                            )
                            quantities[ic] = quantities.get(ic, 0) + grams
                            purchases[ic] = purchases.get(ic, 0) + buy
                            provenance.setdefault(ic, []).append(entry)
                        if ic not in items or any(
                            items[ic].get(f"{n}_per_100g") in ("", None) for n in MACROS
                        ):
                            errors.append(f"gizi belum lengkap: {ic}")
                        if ic not in price_by_code:
                            errors.append(f"harga gram belum tersedia: {ic}")
                    audit.append(dict(recipe_code=code, **entry))
                servings = number(source.get("portion"))
                if not servings or servings > 12 or servings != int(servings):
                    errors.append("jumlah porsi sumber tidak valid")
                instructions = clean_instructions(source.get("how_to_cook", ""))
                if len(instructions) < 60:
                    errors.append("langkah memasak terlalu singkat")
                if not quantities:
                    errors.append("belum ada bahan dengan takaran gram")
                title = normalize(name)
                for pattern, prefixes in TITLE_REQUIRES:
                    if re.search(pattern, title) and not any(
                        ic.startswith(prefixes) for ic in quantities
                    ):
                        errors.append(f"bahan utama pada judul tidak ada di daftar: {pattern}")
            if excluded is None and not errors:
                portions = int(servings)
                totals = {
                    n: sum(
                        g * float(items[ic][n + "_per_100g"]) / 100 for ic, g in quantities.items()
                    )
                    for n in MACROS
                }
                kcal = totals["calories"] / portions
                if not 120 <= kcal <= 1300 or totals["protein"] / portions > 120:
                    errors.append(f"gizi per porsi tidak wajar: {kcal:.0f} kkal")
            reason = excluded or "; ".join(dict.fromkeys(errors))
            audit.append(
                dict(
                    recipe_code=code,
                    ingredient_position="resep",
                    raw_ingredient=name,
                    raw_measure=str(source.get("portion", "")),
                    ingredient_code="",
                    quantity_g="",
                    purchase_quantity_g="",
                    status="plannable" if not reason else "excluded" if excluded else "blocked",
                    estimation_note=reason,
                    reference_url=MENDELEY_URL,
                    recipe_source_url=MENDELEY_URL,
                    rules_version=RULES_VERSION,
                )
            )
            if reason:
                continue
            seen.add(title_key(name))
            meal = meal_type(name, source["id"])
            cost = sum(
                g
                * float(price_by_code[ic]["price_rupiah"])
                / float(price_by_code[ic]["quantity"])
                / 1000
                for ic, g in purchases.items()
            )
            recipes.append(
                dict(
                    recipe_code=code,
                    name=name,
                    base_servings=str(portions),
                    meal_type=meal,
                    # Source prose stays in the raw snapshot, not the published fixture.
                    instructions="",
                    is_plannable="true",
                    missing_data_reason="",
                    source=SOURCE,
                    source_url=MENDELEY_URL,
                    raw_ingredients=json.dumps(
                        {
                            "rules_version": RULES_VERSION,
                            "servings_status": "source",
                            "meal_type_status": "estimated_from_title",
                            "instructions_status": "withheld_pending_rights_review",
                            "license": "CC BY 4.0",
                            "attribution": "Devi Dwi Purwanto; Aji Prasetya Wibawa; Mazarina Devi",
                            "source_id": source["id"],
                            "source_title": source.get("title", ""),
                            "source_ingredients": source.get("ingredient", ""),
                            "minor_ingredients_not_counted": minor,
                        },
                        ensure_ascii=False,
                    ),
                    is_active="true",
                )
            )
            for ic, grams in quantities.items():
                links.append(
                    dict(
                        recipe_ingredient_code=stable("RIN", code, ic),
                        recipe_code=code,
                        ingredient_code=ic,
                        quantity=f"{grams:.3f}".rstrip("0").rstrip("."),
                        unit="g",
                        is_optional="false",
                        quantity_status="estimated",
                        raw_text=json.dumps(provenance[ic], ensure_ascii=False),
                        source=SOURCE,
                    )
                )
            per = {n: totals[n] / portions for n in MACROS}
            tagset = {"halal", meal, "takaran_estimasi", "sumber_mendeley"}
            if minor:
                tagset.add("bumbu_minor_tidak_dihitung")
            if per["protein"] >= 20:
                tagset.add("tinggi_protein")
            if per["calories"] <= 400:
                tagset.add("rendah_kalori")
            categories = {items[ic]["category"] for ic in quantities}
            if {"sayur", "protein", "karbohidrat"} <= categories:
                tagset.add("seimbang_internal")
            if not any(ic.startswith(ANIMAL) for ic in quantities):
                tagset.add("vegetarian")
            for markers, tag in ALLERGENS:
                if any(marker in ic for ic in quantities for marker in markers):
                    tagset.add(tag)
            for tag in sorted(tagset):
                tags.append(
                    dict(
                        recipe_tag_code=stable("TAG", code, tag),
                        recipe_code=code,
                        tag=tag,
                        source="TAKARKUY heuristik daftar bahan Mendeley",
                    )
                )
            estimates.append(
                dict(
                    recipe_code=code,
                    region="Garut + referensi non-Garut",
                    price_date="2026-10-05",
                    cost_total_rupiah=f"{cost:.2f}",
                    cost_per_serving_rupiah=f"{cost / portions:.2f}",
                    calories_per_serving=f"{per['calories']:.2f}",
                    protein_per_serving_g=f"{per['protein']:.2f}",
                    carbs_per_serving_g=f"{per['carbs']:.2f}",
                    fat_per_serving_g=f"{per['fat']:.2f}",
                    calculation_status="estimasi_takaran_sumber_mendeley",
                )
            )
    return recipes, links, tags, estimates, audit
