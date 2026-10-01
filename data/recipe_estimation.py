"""Auditable, offline estimates. Unknown foods/units are never silently discarded.

These are authored demonstration variants, not measurements of the source dishes.
NIST mass conversions are exact; USDA household portions and all recipe servings
are approximations. The generated audit retains every source ingredient.
"""

import csv
import io
import json
import math
import re
import unicodedata
import zipfile
from collections import defaultdict
from fractions import Fraction

NIST = "https://www.nist.gov/pml/owm/metric-si/unit-conversion/approximate-conversions-us-customary-measures-metric"
USDA = "https://fdc.nal.usda.gov/download-datasets/"
KA = "https://www.kingarthurbaking.com/learn/ingredient-weight-chart"
RULES_VERSION = "takarkuy-estimates-2026-10-01-v2"
MACROS = ("calories", "protein", "carbs", "fat")


def normalize(text):
    text = str(text).casefold().replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4")
    text = unicodedata.normalize("NFKC", text).replace("⁄", "/")
    return re.sub(r"\s+", " ", text).strip()


# code, estimated unit/household mass, gram amount for an unspecified batch.
# Defaults apply to the authored variant only, not pantry/OCR package conversion.
PROFILES = {
    "DAGING-AYAM-BROILER": (150, 140, 300),
    "DAGING-AYAM-KAMPUNG": (150, 140, 300),
    "DAGING-SAPI": (150, 225, 300),
    "UDANG": (12, 145, 250),
    "TELUR-AYAM-BROILER": (50, 243, 100),
    "BAWANG-PUTIH": (3, 136, 12),
    "BAWANG-MERAH": (10, 160, 40),
    "BAWANG-BOMBAY": (110, 160, 110),
    "TOMAT": (123, 180, 150),
    "TOMAT-CHERRY": (17, 149, 100),
    "KENTANG": (170, 150, 250),
    "WORTEL": (61, 128, 120),
    "MENTIMUN": (200, 104, 150),
    "TERONG": (450, 82, 250),
    "KUBIS": (900, 89, 150),
    "BUNCIS": (5, 100, 150),
    "CABAI-MERAH-KERITING": (10, 75, 20),
    "CABAI-RAWIT-MERAH": (3, 75, 12),
    "CABE-HIJAU-BIASA": (10, 75, 20),
    "PAPRIKA-MERAH": (119, 149, 120),
    "PAPRIKA-HIJAU": (119, 149, 120),
    "BERAS-MEDIUM": (0, 185, 150),
    "TEPUNG-TERIGU-CURAH": (0, 120, 100),
    "MAIZENA": (0, 128, 10),
    "GULA-PASIR-DALAM-NEGERI": (0, 198, 8),
    "GULA-MERAH": (0, 220, 10),
    "GARAM": (0, 292, 3),
    "MERICA": (0, 110, 1),
    "KETUMBAR-BIJI": (0, 80, 2),
    "JAHE": (10, 96, 10),
    "LENGKUAS": (10, 96, 10),
    "KUNYIT": (10, 96, 10),
    "KUNYIT-BUBUK": (0, 160, 2),
    "KEMIRI": (4, 130, 12),
    "SERAI": (20, 67, 20),
    "DAUN-SALAM": (0.5, 0, 1),
    "DAUN-JERUK": (0.5, 0, 1),
    "KEMANGI": (1, 24, 10),
    "BASIL": (1, 24, 10),
    "DAUN-KETUMBAR": (1, 16, 5),
    "PARSLEY": (1, 60, 5),
    "DAUN-BAWANG": (15, 100, 15),
    "SELEDRI": (40, 101, 15),
    "JERUK-NIPIS": (44, 242, 20),
    "LEMON": (58, 244, 25),
    "MINYAK-GORENG-CURAH": (0, 218, 20),
    "MINYAK-ZAITUN": (0, 216, 20),
    "MENTEGA": (0, 227, 15),
    "SANTAN": (0, 240, 100),
    "KECAP-ASIN": (0, 255, 15),
    "ROTI": (25, 0, 50),
    "SUSU-SAPI-SEGAR": (0, 244, 120),
    "TEMPE": (100, 166, 200),
    "TAHU-PUTIH": (100, 248, 200),
    "PISANG": (118, 225, 240),
    "JERUK": (131, 180, 260),
    "BAYAM": (0, 30, 150),
    "SAWI-HIJAU": (0, 56, 150),
    "JAMUR-TIRAM": (0, 86, 100),
    "CUMIN": (0, 96, 2),
    "PAPRIKA-BUBUK": (0, 109, 2),
    "THYME": (0, 43, 1),
    "KAYU-MANIS": (3, 125, 1),
    "PALA": (5, 112, 1),
    "SAUS-TIRAM": (0, 288, 15),
    "SAUS-TOMAT": (0, 272, 20),
    "SAUS-TERIYAKI": (0, 288, 20),
    "MARGARIN": (0, 227, 15),
    "MINT": (1, 26, 5),
    "ALLSPICE": (0, 96, 1),
    "CABAI-BUBUK": (0, 85, 2),
    "WIJEN": (0, 144, 10),
    "ASAM-JAWA": (0, 120, 10),
    "BAY-LEAF": (0.6, 0, 1.2),
    "KEJU-CHEDDAR": (0, 113, 50),
    "TOMAT-PUREE": (0, 250, 100),
    "KALDU-AYAM-BUBUK": (0, 128, 3),
    "KECAP-MANIS": (0, 312, 20),
    "MINYAK-WIJEN": (0, 218, 10),
    "TEPUNG-PANIR": (0, 108, 50),
    "TEPUNG-TAPIOKA": (0, 120, 100),
}

ENGLISH = {
    "chicken": "DAGING-AYAM-BROILER",
    "chicken breast": "DAGING-AYAM-BROILER",
    "chicken breasts": "DAGING-AYAM-BROILER",
    "beef": "DAGING-SAPI",
    "ground beef": "DAGING-SAPI",
    "minced beef": "DAGING-SAPI",
    "lean minced steak": "DAGING-SAPI",
    "sirloin steak": "DAGING-SAPI",
    "raw king prawns": "UDANG",
    "raw tiger prawns": "UDANG",
    "king prawns": "UDANG",
    "prawns": "UDANG",
    "egg": "TELUR-AYAM-BROILER",
    "eggs": "TELUR-AYAM-BROILER",
    "onion": "BAWANG-BOMBAY",
    "onions": "BAWANG-BOMBAY",
    "red onions": "BAWANG-BOMBAY",
    "chopped onion": "BAWANG-BOMBAY",
    "garlic": "BAWANG-PUTIH",
    "garlic clove": "BAWANG-PUTIH",
    "shallots": "BAWANG-MERAH",
    "tomato": "TOMAT",
    "tomatoes": "TOMAT",
    "plum tomatoes": "TOMAT",
    "cherry tomatoes": "TOMAT-CHERRY",
    "potatoes": "KENTANG",
    "russet potato": "KENTANG",
    "baby new potatoes": "KENTANG",
    "red potatoes": "KENTANG",
    "carrots": "WORTEL",
    "cucumber": "MENTIMUN",
    "aubergine": "TERONG",
    "egg plants": "TERONG",
    "baby aubergine": "TERONG",
    "cabbage": "KUBIS",
    "white cabbage": "KUBIS",
    "green beans": "BUNCIS",
    "red pepper": "PAPRIKA-MERAH",
    "green pepper": "PAPRIKA-HIJAU",
    "green chilli": "CABE-HIJAU-BIASA",
    "red chilli": "CABAI-MERAH-KERITING",
    "rice": "BERAS-MEDIUM",
    "flour": "TEPUNG-TERIGU-CURAH",
    "plain flour": "TEPUNG-TERIGU-CURAH",
    "cornstarch": "MAIZENA",
    "corn flour": "MAIZENA",
    "sugar": "GULA-PASIR-DALAM-NEGERI",
    "caster sugar": "GULA-PASIR-DALAM-NEGERI",
    "granulated sugar": "GULA-PASIR-DALAM-NEGERI",
    "golden caster sugar": "GULA-PASIR-DALAM-NEGERI",
    "salt": "GARAM",
    "sea salt": "GARAM",
    "kosher salt": "GARAM",
    "pepper": "MERICA",
    "black pepper": "MERICA",
    "whole black peppercorns": "MERICA",
    "ginger": "JAHE",
    "turmeric": "KUNYIT",
    "ground turmeric": "KUNYIT-BUBUK",
    "coriander": "KETUMBAR-BIJI",
    "ground coriander": "KETUMBAR-BIJI",
    "coriander leaves": "DAUN-KETUMBAR",
    "cilantro": "DAUN-KETUMBAR",
    "parsley": "PARSLEY",
    "spring onions": "DAUN-BAWANG",
    "scallions": "DAUN-BAWANG",
    "celery": "SELEDRI",
    "lime": "JERUK-NIPIS",
    "lime juice": "JERUK-NIPIS",
    "lemon": "LEMON",
    "lemon juice": "LEMON",
    "vegetable oil": "MINYAK-GORENG-CURAH",
    "oil": "MINYAK-GORENG-CURAH",
    "high heat cooking oil": "MINYAK-GORENG-CURAH",
    "olive oil": "MINYAK-ZAITUN",
    "extra virgin olive oil": "MINYAK-ZAITUN",
    "butter": "MENTEGA",
    "melted butter": "MENTEGA",
    "unsalted butter": "MENTEGA",
    "coconut milk": "SANTAN",
    "soy sauce": "KECAP-ASIN",
    "bread": "ROTI",
    "milk": "SUSU-SAPI-SEGAR",
    "whole milk": "SUSU-SAPI-SEGAR",
    "tempeh": "TEMPE",
    "banana": "PISANG",
    "orange": "JERUK",
    "spinach": "BAYAM",
    "ground cumin": "CUMIN",
    "cumin": "CUMIN",
    "cumin seeds": "CUMIN",
    "paprika": "PAPRIKA-BUBUK",
    "thyme": "THYME",
    "cinnamon": "KAYU-MANIS",
    "ground cinnamon": "KAYU-MANIS",
    "cinnamon stick": "KAYU-MANIS",
    "nutmeg": "PALA",
    "ground nutmeg": "PALA",
    "basil": "BASIL",
    "basil leaves": "BASIL",
    "bay leaf": "BAY-LEAF",
    "bay leaves": "BAY-LEAF",
    "mint": "MINT",
    "allspice": "ALLSPICE",
    "ground allspice": "ALLSPICE",
    "cayenne pepper": "CABAI-BUBUK",
    "chili powder": "CABAI-BUBUK",
    "chilli powder": "CABAI-BUBUK",
    "red chilli powder": "CABAI-BUBUK",
    "tomato puree": "TOMAT-PUREE",
    "cheddar cheese": "KEJU-CHEDDAR",
    "oyster sauce": "SAUS-TIRAM",
    "teriyaki sauce": "SAUS-TERIYAKI",
    "sesame seeds": "WIJEN",
}
# Longest/specific matches first; no fuzzy matching for nutrient-bearing data.
INDONESIAN = (
    (r"minyak wijen", "MINYAK-WIJEN"),
    (r"tepung roti(?:\s*/\s*tepung panir)?|tepung panir", "TEPUNG-PANIR"),
    (r"tepung tapioka|kanji", "TEPUNG-TAPIOKA"),
    (r"kunyit bubuk", "KUNYIT-BUBUK"),
    (r"paprika merah", "PAPRIKA-MERAH"),
    (r"paprika hijau", "PAPRIKA-HIJAU"),
    (r"sa[uo]s tiram", "SAUS-TIRAM"),
    (r"sa[uo]s tomat", "SAUS-TOMAT"),
    (r"sa[uo]s teriyaki", "SAUS-TERIYAKI"),
    (r"kecap manis", "KECAP-MANIS"),
    (r"ayam kampung", "DAGING-AYAM-KAMPUNG"),
    (
        r"bawang putih|b\.?putih|bwg putih|bawah putih|bawanh putih|bawang p(?: kating)?|baput",
        "BAWANG-PUTIH",
    ),
    (r"bawang merah|b\.?merah|bwg merah|bamer", "BAWANG-MERAH"),
    (r"bawang bomba[yi]|b\.bombay", "BAWANG-BOMBAY"),
    (r"bawang (?:daun|prei)|daun bawang", "DAUN-BAWANG"),
    (r"(?:cabe|cabai) (?:merah )?rawit|cabe kecil|rawit merah", "CABAI-RAWIT-MERAH"),
    (r"(?:cabe|cabai) (?:hijau|ijo)", "CABE-HIJAU-BIASA"),
    (r"cabe|cabai", "CABAI-MERAH-KERITING"),
    (r"telur(?: ayam)?", "TELUR-AYAM-BROILER"),
    (r"ayam|dada", "DAGING-AYAM-BROILER"),
    (r"udang", "UDANG"),
    (r"daging sapi", "DAGING-SAPI"),
    (r"kentang", "KENTANG"),
    (r"wortel", "WORTEL"),
    (r"tomat", "TOMAT"),
    (r"maizena|meizena", "MAIZENA"),
    (r"tepung terigu|terigu", "TEPUNG-TERIGU-CURAH"),
    (r"beras", "BERAS-MEDIUM"),
    (r"gula merah|gula jawa|gula aren", "GULA-MERAH"),
    (r"gula|gulpas", "GULA-PASIR-DALAM-NEGERI"),
    (r"garam|garan", "GARAM"),
    (r"merica|lada", "MERICA"),
    (r"ketumbar", "KETUMBAR-BIJI"),
    (r"jahe", "JAHE"),
    (r"kunyit", "KUNYIT"),
    (r"laos|lengkuas", "LENGKUAS"),
    (r"kemiri", "KEMIRI"),
    (r"serai|sereh|sere", "SERAI"),
    (r"daun salam", "DAUN-SALAM"),
    (r"daun jeruk", "DAUN-JERUK"),
    (r"kemangi", "KEMANGI"),
    (r"jeruk nipis", "JERUK-NIPIS"),
    (r"minyak", "MINYAK-GORENG-CURAH"),
    (r"mentega", "MENTEGA"),
    (r"santan", "SANTAN"),
    (r"kecap asin", "KECAP-ASIN"),
    (r"sa[uo]s tiram", "SAUS-TIRAM"),
    (r"sa[uo]s tomat", "SAUS-TOMAT"),
    (r"sa[uo]s teriyaki", "SAUS-TERIYAKI"),
    (r"margarin", "MARGARIN"),
    (r"paprika bubuk", "PAPRIKA-BUBUK"),
    (r"wijen", "WIJEN"),
    (r"asam jawa", "ASAM-JAWA"),
    (r"(?:daun )?seledri", "SELEDRI"),
    (r"kayu manis|kulit manis", "KAYU-MANIS"),
    (r"biji pala|\bpala\b", "PALA"),
    (r"tahu", "TAHU-PUTIH"),
    (r"tempe", "TEMPE"),
    (r"buncis", "BUNCIS"),
    (r"jamur tiram", "JAMUR-TIRAM"),
    (r"sawi hijau", "SAWI-HIJAU"),
    (r"kol|kubis", "KUBIS"),
    (r"timun", "MENTIMUN"),
)


def resolve_ingredient(raw, language):
    text = normalize(raw)
    if language == "en":
        short = ENGLISH.get(text)
        return "ING-" + short if short else None
    single = re.sub(r"\([^)]*\)", "", text).strip()
    single = re.sub(
        r"^(?:(?:\d+(?:[.,]\d+)?|\d+/\d+)\s*(?:sdt|sdm|g|gr|gram)\s*|secukupnya\s+|sedikit\s+|sesuai selera\s+)",
        "",
        single,
    ).strip()
    if re.fullmatch(
        r"(?:royco(?: ayam)?|penyedap(?: rasa)?(?: ayam)?|kaldu(?: ayam)? bubuk)", single
    ):
        # Authored variant chooses chicken bouillon, explicitly marked nutrition proxy.
        return "ING-KALDU-AYAM-BUBUK"
    if single == "kecap":
        return "ING-KECAP-MANIS"
    # Form, mixed seasoning and prepared food must not be mapped to raw meat/flour.
    # Removing bones from citrus leaves is preparation, not an animal-bone SKU.
    text = re.sub(r"buang tulangnya|buang tulang daun", "", text)
    if re.search(
        r"kulit ayam|ceker|\btulang\b|kepala ayam|ayam suwir.*sudah|ayam.*(?:rebus/goreng|sudah di\s?rebus|sudah direbus)|"
        r"tepung (?:ayam|bumbu)|bumbu ayam|bumbu racik|bumbu instan|sajiku|royco|masako|kaldu|penyedap|terasi|"
        r"sa[uo]s(?! (?:tiram|tomat|teriyaki))|sambal|hintalu|bawang goreng|nasi|keju|kecap(?! (?:asin|manis))|"
        r"jahe bubuk|lalapan",
        text,
    ):
        return None
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"untuk (?:ayam|sambal)\b.*$", "", text)
    matches = []
    for pattern, short in INDONESIAN:
        match = re.search(r"(?<!\w)(?:" + pattern + r")(?!\w)", text)
        if match:
            # "ayam kampung" and generic "ayam" are overlapping, not two foods.
            if not any(match.start() < end and start < match.end() for start, end, _ in matches):
                matches.append((match.start(), match.end(), short))
    codes = {short for _, _, short in matches}
    return "ING-" + next(iter(codes)) if len(codes) == 1 else None


def number_at_start(text):
    match = re.match(
        r"^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)(?:\s*[-–]\s*(\d+(?:[.,]\d+)?))?", text
    )
    if not match:
        return None, text, ""
    value = sum(float(Fraction(x.replace(",", "."))) for x in match[1].split())
    note = ""
    if match[2]:
        value = max(value, float(match[2].replace(",", ".")))
        note = "rentang memakai batas atas untuk estimasi belanja"
    return value, text[match.end() :].strip(), note


def estimate_quantity(raw_measure, code, language="en", instructions=""):
    text = normalize(raw_measure)
    short = code.removeprefix("ING-")
    piece, cup, default = PROFILES.get(short, (0, 0, 0))
    try:
        amount, rest, range_note = number_at_start(text)
    except (ValueError, ZeroDivisionError):
        return None, "angka/pecahan tidak valid; perlu koreksi sumber", ""
    note = range_note
    # Never interpret unknown units (tin/pack/handful/etc.) as a known count.
    if amount is not None and amount > 0:
        mass = re.match(
            r"^(kg|kilograms?|kilogram|g|gr|grm|grams?|gram|oz|ounces?|lb|lbs|pounds?|ons)\b", rest
        )
        if mass:
            unit = mass[1]
            factor = (
                1000
                if unit.startswith("k")
                else 28.349523125
                if unit.startswith(("oz", "ounce"))
                else 453.59237
                if unit.startswith(("lb", "pound"))
                else 100
                if unit == "ons"
                else 1
            )
            source = (
                "https://repositori.kemendikdasmen.go.id/19098/1/6.%20%20Matematika_IV%20SD.pdf"
                if unit == "ons"
                else NIST
            )
            return (
                amount * factor,
                "; ".join(filter(None, [note, f"konversi massa {unit} → g"])),
                source,
            )
        unit = re.match(
            r"^(cups?|tbsp|tbs|tblsp|tablespoons?|tsp|teaspoons?|sdm|sdt|sendok makan|sendok teh|ml|cc|milliliters?|l|liters?|litres?|gelas)\b",
            rest,
        )
        if unit:
            unit = unit[1]
            if not cup:
                return None, "massa per volume bahan belum ditentukan", ""
            if unit in ("sdm", "tbsp", "tbs", "tblsp") or unit.startswith(
                ("tablespoon", "sendok makan")
            ):
                grams = cup / 16
            elif unit in ("sdt", "tsp") or unit.startswith(("teaspoon", "sendok teh")):
                grams = cup / 48
            elif unit.startswith("cup"):
                grams = cup
            else:
                # 1 US cup ≈ 240 ml; Indonesian glass is authored 200 ml.
                volume = (
                    200
                    if unit == "gelas"
                    else 1000
                    if unit in ("l", "liter", "liters", "litre", "litres")
                    else 1
                )
                grams = cup / 240 * volume
            return (
                amount * grams,
                "; ".join(
                    filter(None, [note, f"perkiraan {unit}; massa khusus bahan, cup ≈ 240 ml"])
                ),
                USDA + "; " + KA,
            )
        if re.match(r"^(?:ruas(?: jari)?|jari|cm)\b", rest) and short in (
            "JAHE",
            "LENGKUAS",
            "KUNYIT",
        ):
            grams = amount * (5 if rest.startswith("cm") else 10)
            return grams, "asumsi TAKARKUY: 1 ruas ≈ 10 g, 1 cm ≈ 5 g", ""
        if re.match(r"^(?:ekor|ekr)\b", rest) and short.startswith("DAGING-AYAM"):
            gross = 1500 if "jumbo" in rest else 1000
            return (
                amount * gross * 0.6,
                f"asumsi 1 ekor {gross:g} g × 60% daging termakan; belanja memakai berat utuh, gizi memakai daging",
                "",
            )
        if rest.startswith("ikat") and short in ("KEMANGI", "DAUN-BAWANG"):
            return (
                amount * 50,
                "asumsi TAKARKUY: ikat ini 50 g, bukan konversi kemasan universal",
                "",
            )
        known_count = re.match(
            r"^(?:siung|cloves?|butir|btr|buah|bh|batang|btg|btng|tangkai|lembar|lmbr|lbr|sticks?|slices?|slice|pieces?|potong|biji|large|medium|small|besar|kecil|head|diced|chopped|finely chopped|sliced)\b",
            rest,
        )
        bare_food = (
            language == "id"
            and resolve_ingredient(rest, "id") == code
            and any(re.match(pattern, rest) for pattern, profile in INDONESIAN if profile == short)
        )
        if piece and (known_count or not rest or bare_food):
            multiplier = (
                1.25
                if re.match(r"^(?:large|besar)\b", rest)
                else 0.75
                if re.match(r"^(?:small|kecil)\b", rest)
                else 1
            )
            return (
                amount * piece * multiplier,
                f"asumsi TAKARKUY berat bagian termakan per unit {piece:g} g; mengacu ukuran USDA, bukan bobot pasti produk",
                USDA,
            )
        if not rest and short in (
            "GARAM",
            "MERICA",
            "KETUMBAR-BIJI",
            "CUMIN",
            "PAPRIKA-BUBUK",
            "KUNYIT-BUBUK",
        ):
            return (
                amount,
                "asumsi TAKARKUY satuan hilang pada bumbu: angka diperlakukan sebagai gram",
                "",
            )
        return None, f"satuan/format belum dipetakan: {rest}", ""
    if amount is not None:
        return None, "takaran harus positif", ""
    if default and (
        not text
        or re.search(
            r"to taste|secukup|sck|sedikit|sejumput|pinch|dash|serv(?:e|ing)|chopped|garnish|dikira|as required|as needed|for frying",
            text,
        )
        or text in ("sprinkling", "drizzle", "drizzling")
        or language == "id"
    ):
        # Deep frying: retained-oil estimate is not the whole pan's oil purchase.
        if short == "MINYAK-GORENG-CURAH" and re.search(
            r"untuk menggoreng|deep.?fry|goreng.*tiriskan", text
        ):
            return (
                30,
                "asumsi 30 g minyak termakan per batch; minyak penggorengan utuh belum dihitung",
                "",
            )
        return (
            default,
            f"asumsi TAKARKUY untuk batch: {default:g} g; sumber tidak memberi angka pasti",
            "",
        )
    return None, "takaran belum dapat diperkirakan dengan aturan bahan", ""


def source_candidates(root):
    with zipfile.ZipFile(root / "raw/indonesian_food_recipes.zip") as archive:
        seen = set()
        for member in sorted(archive.namelist()):
            if not member.endswith(".csv"):
                continue
            for row in csv.DictReader(io.TextIOWrapper(archive.open(member), encoding="utf-8-sig")):
                match = re.search(r"/resep/(\d+)-", row["URL"])
                if not match or match[1] in seen:
                    continue
                seen.add(match[1])
                yield dict(
                    code="RCP-KAGGLE-" + match[1],
                    name=row["Title"],
                    language="id",
                    source_url="https://cookpad.com" + row["URL"],
                    category="Chicken",
                    instructions=row["Steps"],
                    ingredients=[
                        {"ingredient": line, "measure": line}
                        for line in row["Ingredients"].split("--")
                        if line.strip()
                    ],
                )
                if len(seen) == 60:
                    break
            if len(seen) == 60:
                break
    snapshot = json.loads((root / "scratch/themealdb_100_candidates.json").read_text())
    seen = {}
    for row in snapshot.get("recipes", []):
        code = "RCP-TMDB-" + str(row["source_id"])
        if code in seen:
            if seen[code] != row:
                raise ValueError(f"ID TheMealDB memiliki data berbeda: {code}")
            continue
        seen[code] = row
        yield dict(
            code=code,
            name=row["name"],
            language="en",
            source_url=row.get("source_url") or row["themealdb_url"],
            category=row["source_category"],
            instructions=row["instructions"],
            ingredients=row["ingredients"],
            meal_type=row.get("suggested_meal_type", ""),
        )


def is_section_heading(raw):
    text = re.sub(r"[^\w\s]", " ", normalize(raw))
    text = re.sub(r"\s+", " ", text).strip()
    return bool(
        re.fullmatch(
            r"(?:bahan(?: utama| pelengkap| mie ayam| saus jamur| sambal| sambel| saus| saos| daging| halus| bumbu)?|"
            r"bumbu(?: halus(?: kuah ayam untuk mie ayam)?| iris| yg di haluskan| dihaluskan| yang dihaluskan| perendam| rajang| saus| ungkep| ayam panggang| kuning halus| bakar| ulek| marinasi ayam)?|"
            r"adonan (?:basah|kering)|rempah|sambal korek|sambel penyet|tepung pelapis|pelapis|pelengkap|tambahan|baham sambal|saos kecap cocolan)",
            text,
        )
    )


def ingredient_components(raw, measure, language):
    """Split explicit lists, never duplicate a shared numeric amount across foods."""
    if language != "id" or is_section_heading(raw):
        return [(raw, measure, "")]
    text = normalize(raw)
    # Select one of alternatives explicitly offered by the source, not both.
    for pattern, selected in (
        (r"butter\s*/\s*margarin", "margarin"),
        (r"paprika merah\s*/\s*hijau", "paprika merah"),
        (r"gula\s*/\s*penyedap", "gula"),
    ):
        if re.search(pattern, text):
            chosen = re.sub(pattern, selected, text)
            return [
                (
                    chosen,
                    chosen,
                    "varian demonstrasi memilih " + selected + " dari alternatif sumber",
                )
            ]
    if re.match(r"^(?:secukupnya\s+)?lalapan\s*\(", text):
        match = re.search(r"\(([^)]+)\)", text)
        text = "secukupnya " + match[1] if match else text
    # Parenthetical preparation often contains commas; keep it out of splitting.
    text = re.sub(r"\([^)]*\)", "", text).strip()
    # Slash alternatives require a choice and cannot both be charged as ingredients.
    if "/" in re.sub(r"\d+/\d+", "", text):
        return [(raw, measure, "")]
    parts = [p.strip() for p in re.split(r"\s+(?:dan|and)\s+|\s*&\s*|,", text) if p.strip()]
    if len(parts) < 2:
        return [(raw, measure, "")]
    # Only decompose a food list, not phrases such as "cuci bersih, tiriskan".
    food_parts = [resolve_ingredient(part, "id") for part in parts]
    if sum(code is not None for code in food_parts) < 2:
        return [(raw, measure, "")]
    try:
        amounts = [number_at_start(part)[0] for part in parts]
    except (ValueError, ZeroDivisionError):
        return [(raw, measure, "")]
    if any(amount is not None for amount in amounts) and not all(
        amount is not None for amount in amounts
    ):
        return [(raw, measure, "")]
    return [
        (
            part,
            part,
            "daftar bahan dipecah; takaran per komponen adalah estimasi terpisah, bukan angka bersama",
        )
        for part in parts
    ]


def estimate_candidates(root, items, prices):
    """Return recipe updates plus a complete ingredient audit, including blockers."""
    updates, audit = [], []
    for candidate in source_candidates(root):
        code, lang = candidate["code"], candidate["language"]
        quantities, purchases, errors, assumptions = defaultdict(float), defaultdict(float), [], []
        expanded = []
        for index, ingredient in enumerate(candidate["ingredients"], 1):
            components = ingredient_components(
                ingredient["ingredient"], ingredient["measure"], lang
            )
            for part, (raw, measure, split_note) in enumerate(components, 1):
                position = str(index) if len(components) == 1 else f"{index}.{part}"
                expanded.append(
                    (
                        position,
                        dict(ingredient=raw, measure=measure),
                        ingredient["ingredient"],
                        split_note,
                    )
                )
        for position, ingredient, source_raw, split_note in expanded:
            raw = ingredient["ingredient"].strip()
            measure = ingredient["measure"].strip()
            text = normalize(raw)
            status, ic, grams, buy_grams, note, url = "blocked", "", None, None, "", ""
            heading = lang == "id" and is_section_heading(raw)
            preparation = lang == "id" and text in (
                "ulek halus",
                "dicampur",
                "tiriskan",
                "cuci bersih",
            )
            utility = (
                text in ("water", "warm water", "air")
                or lang == "id"
                and not re.search(r"jeruk|lemon|susu|kelapa", text)
                and re.search(
                    r"^(?:secukupnya\s+)?air\b|\b(?:gelas|ml|liter)\s+air\b|daun pisang|lidi/|tusuk gigi",
                    text,
                )
            )
            if heading:
                status, note = "section_heading", "judul bagian, bukan bahan"
            elif preparation:
                status, note = (
                    "excluded_preparation",
                    "frasa persiapan yang dipisahkan koma, bukan bahan",
                )
            elif utility:
                status, note = (
                    "excluded_utility",
                    "air/alat/pembungkus masak di luar gizi dan biaya bahan termakan",
                )
            else:
                ic = resolve_ingredient(raw, lang) or ""
                if ic:
                    grams, note, url = estimate_quantity(
                        measure, ic, lang, candidate["instructions"]
                    )
                    if grams is not None:
                        status = "estimated"
                        quantities[ic] += grams
                        buy_grams = grams / 0.6 if "belanja memakai berat utuh" in note else grams
                        purchases[ic] += buy_grams
                        assumptions.append(note)
                    else:
                        errors.append(f"takaran {raw}: {note}")
                    if ic not in items or any(
                        items.get(ic, {}).get(f"{n}_per_100g") in ("", None) for n in MACROS
                    ):
                        errors.append(f"gizi belum lengkap: {ic}")
                    if ic not in prices:
                        errors.append(f"harga gram belum tersedia: {ic}")
                    # Whole/bone-in and deep-fry purchasing yield needs a separate
                    # quote; do not understate budget just because macros are estimable.
                    if "penggorengan utuh" in note:
                        errors.append(f"biaya massa beli belum lengkap: {raw}")
                else:
                    note = "bahan/bentuk/komposisi belum dipetakan; tidak dibuang dari perhitungan"
                    # Explicit mass can still be normalized before the food is
                    # identified. It must NOT become a planner ingredient yet.
                    mass, mass_note, mass_url = estimate_quantity(measure, "ING-UNMAPPED", lang)
                    if mass is not None:
                        grams, url = mass, mass_url
                        note += "; " + mass_note
                    errors.append(f"padanan bahan: {raw}")
            if split_note:
                note = split_note + "; komponen: " + raw + "; " + note
            audit.append(
                dict(
                    recipe_code=code,
                    ingredient_position=position,
                    raw_ingredient=source_raw,
                    raw_measure=measure,
                    ingredient_code=ic,
                    quantity_g="" if grams is None else round(grams, 3),
                    purchase_quantity_g="" if buy_grams is None else round(buy_grams, 3),
                    status=status,
                    estimation_note=note,
                    reference_url=url,
                    recipe_source_url=candidate["source_url"],
                    rules_version=RULES_VERSION,
                )
            )
        if not quantities:
            errors.append("belum ada bahan dengan takaran gram")
        # A deliberate serving estimate, not an invented source serving count.
        meat = sum(
            g
            for ic, g in quantities.items()
            if ic.startswith(("ING-DAGING-", "ING-UDANG", "ING-TELUR-"))
        )
        starch = sum(
            g
            for ic, g in quantities.items()
            if ic in ("ING-BERAS-MEDIUM", "ING-TEPUNG-TERIGU-CURAH")
        )
        servings = max(2, math.ceil(meat / 150), math.ceil(starch / 75))
        if candidate["category"].casefold() in ("dessert", "side", "starter", "miscellaneous"):
            errors.append("bukan menu utama; penempatan waktu makan perlu kurasi")
        if lang == "id" and normalize(candidate["name"]).startswith("minyak "):
            errors.append("bumbu/minyak olahan, bukan menu utama")
        meal = candidate.get("meal_type") or "makan_siang"
        if meal not in ("sarapan", "makan_siang", "makan_malam"):
            meal = "makan_siang"
        if not candidate["instructions"].strip():
            errors.append("langkah memasak belum tersedia")
        # Kaggle variants keep attribution but use brief authored instructions,
        # not a verbatim republication of the scraped Cookpad steps.
        instructions = (
            candidate["instructions"] if lang == "en" else authored_steps(candidate["name"])
        )
        reason = "; ".join(dict.fromkeys(errors))
        updates.append(
            dict(
                recipe_code=code,
                name=candidate["name"],
                base_servings=str(servings),
                meal_type=meal,
                instructions=instructions,
                quantities=dict(quantities),
                purchase_quantities=dict(purchases),
                is_plannable=str(not errors).lower(),
                missing_data_reason=reason,
                source=(
                    "TheMealDB API"
                    if lang == "en"
                    else "TAKARKUY adaptasi; inspirasi Kaggle/Cookpad"
                )
                + "; estimasi takaran/porsi",
                source_url=candidate["source_url"],
                raw_ingredients=json.dumps(
                    {
                        "rules_version": RULES_VERSION,
                        "servings_status": "estimated",
                        "meal_type_status": "estimated",
                        "source_category": candidate["category"],
                        "instructions_status": "source_api"
                        if lang == "en"
                        else "takarkuy_adaptation",
                        "servings_note": "asumsi batch minimal 2 porsi; 150 g protein hewani atau 75 g beras/tepung per porsi",
                        "source_ingredients": candidate["ingredients"],
                        "assumptions": assumptions,
                    },
                    ensure_ascii=False,
                ),
                is_active="true",
            )
        )
    return updates, audit


def authored_steps(name):
    title = normalize(name)
    if "bakar" in title or "panggang" in title or "oven" in title:
        return "Siapkan bahan sesuai takaran estimasi. Haluskan bumbu dan lumuri ayam; masak hingga matang, lalu panggang hingga bumbu meresap. Pastikan bagian terdalam ayam matang."
    if any(x in title for x in ("sup", "sop", "soto", "semur", "ungkep", "rebus")):
        return "Siapkan dan potong bahan. Tumis bumbu hingga harum, tambahkan ayam dan air; masak hingga ayam matang dan empuk. Tambahkan bahan pelengkap sesuai daftar. Sesuaikan rasa sebelum disajikan."
    if "goreng" in title or "geprek" in title:
        return "Siapkan ayam dan bumbu; jika ada tepung/telur dalam daftar, gunakan sebagai pelapis. Masak ayam hingga bagian terdalam matang; tiriskan dan sajikan dengan bumbu atau sambal sesuai daftar bahan."
    return "Siapkan bahan dan haluskan bumbu. Tumis bumbu hingga harum; tambahkan ayam dan masak sampai bagian terdalam matang. Tambahkan bahan pelengkap sesuai daftar, sesuaikan rasa, lalu sajikan."


def unique_rows(rows, key):
    """Collapse identical copies only; conflicting IDs must be corrected, not lost."""
    seen = {}
    for row in rows:
        pk = row[key]
        if not pk:
            raise ValueError(f"ID kosong pada {key}")
        if pk in seen and seen[pk] != row:
            raise ValueError(f"ID bentrok dengan isi berbeda pada {key}: {pk}")
        seen.setdefault(pk, row)
    return list(seen.values())


def replace_recipe(recipes, replacement):
    code = replacement["recipe_code"]
    matching = [i for i, row in enumerate(recipes) if row["recipe_code"] == code]
    if len(matching) > 1:
        raise ValueError(f"ID resep sudah ganda sebelum promosi: {code}")
    if matching:
        recipes[matching[0]] = replacement
    else:
        recipes.append(replacement)
