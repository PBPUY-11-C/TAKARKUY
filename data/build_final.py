#!/usr/bin/env python3
"""Build the TAKARKUY MVP from frozen source snapshots; standard library only."""

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

if __package__:
    from .mendeley_recipes import build_mendeley
    from .recipe_estimation import estimate_candidates, replace_recipe, unique_rows
    from .recipe_names import EXCLUDE, load_overrides, standard_name
else:
    from mendeley_recipes import build_mendeley
    from recipe_estimation import estimate_candidates, replace_recipe, unique_rows
    from recipe_names import EXCLUDE, load_overrides, standard_name

ROOT = Path(__file__).resolve().parent
RAW, MAP, OUT, FIX = (ROOT / x for x in ("raw", "mapping", "processed", "fixtures"))
BPN_URL = "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia"
GARUT_URL = "https://bapokting.disperindag.garutkab.go.id/Bapokting/"
BI_URL = "https://www.bi.go.id/hargapangan/Website/Home/Index/widget"
KAGGLE_URL = "https://www.kaggle.com/datasets/canggih/indonesian-food-recipes"
FK_URL = (
    "https://raw.githubusercontent.com/jelera/food-shelflife-db/master/lib/seeds/ingredients.csv"
)
NUTRIENTS = ("calories", "protein", "carbs", "fat")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def clean_text_fields(row):
    return {
        key: "\n".join(
            line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        )
        if isinstance(value, str)
        else value
        for key, value in row.items()
    }


def write_csv(path, rows, fields):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(clean_text_fields(row) for row in rows)


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub("-+", "-", re.sub("[^A-Z0-9]+", "-", s)).strip("-")


def stable(prefix, *parts):
    return prefix + "-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12].upper()


def fnum(x):
    try:
        return float(x) if x not in ("", "-") else None
    except (ValueError, TypeError):
        return None


def fmt(x):
    return "" if x is None else ("%.2f" % x).rstrip("0").rstrip(".")


def category(s):
    s = s.lower()
    if s in ("kubis", "kol", "kembang kol"):
        return "sayur"
    if any(
        x in s
        for x in (
            "beras",
            "tepung",
            "jagung",
            "kentang",
            "singkong",
            "ubi",
            "sagu",
            "talas",
            "roti",
            "mie",
        )
    ):
        return "karbohidrat"
    if any(
        x in s
        for x in ("ikan", "udang", "cumi", "daging", "telur", "tahu", "tempe", "kacang", "susu")
    ):
        return "protein"
    if any(x in s for x in ("bawang", "cabe", "cabai", "garam", "gula")):
        return "bumbu"
    if "minyak" in s or "kelapa" in s:
        return "lemak"
    if any(
        x in s
        for x in (
            "pisang",
            "jeruk",
            "apel",
            "pepaya",
            "semangka",
            "salak",
            "mangga",
            "nanas",
            "buah",
            "jambu",
            "melon",
            "anggur",
            "leci",
            "lengkeng",
        )
    ):
        return "buah"
    return "sayur"


# Product-specific codes are retained for distinct qualities and packaging.
OVERRIDE = {
    "Beras Medium": "ING-BERAS-MEDIUM",
    "Daging Ayam Broiler": "ING-DAGING-AYAM-BROILER",
    "Telur Ayam Broiler": "ING-TELUR-AYAM-BROILER",
    "Minyak Goreng Curah": "ING-MINYAK-GORENG-CURAH",
    "Tahu Mentah / Kg": "ING-TAHU-PUTIH",
    "Tempe / Kg": "ING-TEMPE",
    "Tomat Merah": "ING-TOMAT",
    "Ikan kembung": "ING-IKAN-KEMBUNG",
    "Pak Choi": "ING-PAKCOY",
    "Kol/Kubis": "ING-KUBIS",
    "Jagung Manis": "ING-JAGUNG-MANIS",
    "Ketela Pohon": "ING-SINGKONG",
    "Ubi Jalar Putih": "ING-UBI-JALAR-PUTIH",
    "Cabe Merah Keriting": "ING-CABAI-MERAH-KERITING",
    "Cabe Rawit Merah": "ING-CABAI-RAWIT-MERAH",
    "Cabe Rawit Hijau": "ING-CABAI-RAWIT-HIJAU",
}
PROXY = {
    "Beras Medium": "beras",
    "Beras Premium": "beras",
    "Beras Termahal": "beras",
    "Beras Termurah (Non Bulog)": "beras",
    "Daging Ayam Broiler": "daging_ayam",
    "Telur Ayam Broiler": "telur_ayam",
    "Minyak Goreng Curah": "minyak_goreng",
    "Minyak Goreng Bimoli Kemasan": "minyak_goreng",
    "Minyak Goreng Kemasan Sederhana": "minyak_goreng",
    "Tahu Mentah / Kg": "USDA:172476",
    "Tahu Mentah / pcs": "USDA:172476",
    "Tempe / Kg": "USDA:174272",
    "Tempe / pcs": "USDA:174272",
    "Cabe Merah Keriting": "cabe_merah",
    "Cabe Merah Biasa": "cabe_merah",
    "Cabe Rawit Merah": "cabe_rawit",
    "Cabe Rawit Hijau": "cabe_rawit",
    "Bawang Bombay": "USDA:170000",
    "Jagung Manis": "jagung_segar",
    "Ubi Jalar Putih": "ubi_jalar",
    "Tomat Merah": "tomat",
    "Tomat Hijau": "tomat",
    "Kol/Kubis": "kubis",
    "Kol": "kubis",
    "Pak Choi": "pakcoy",
    "Gula Pasir Dalam Negeri": "USDA:169655",
    "Gula Merah": "USDA:168833",
    "Kacang Hijau": "USDA:174256",
    "Garam Beryodium Halus": "USDA:173468",
    "Garam Beryodium Bata": "USDA:173468",
    "Pisang": "pisang",
    "Jeruk": "jeruk",
    "Tepung Terigu Curah": "tepung_terigu",
    "Kacang Kedelai Impor": "kacang_kedelai",
    "Telur Ayam Kampung": "telur_ayam_kampung",
    "Daging Ayam Kampung": "daging_ayam_kampung",
    "Ikan kembung": "ikan_kembung",
    "Ketela Pohon": "singkong",
}
USDA_EXTRA = {
    "ING-TAHU-PUTIH": ("Tahu Putih", 172476),
    "ING-TEMPE": ("Tempe", 174272),
    "ING-GARAM": ("Garam", 173468),
    "ING-GULA-PASIR": ("Gula Pasir", 169655),
    "ING-GULA-MERAH": ("Gula Merah", 168833),
    "ING-BAWANG-BOMBAY": ("Bawang Bombay", 170000),
    "ING-KACANG-HIJAU": ("Kacang Hijau", 174256),
    "ING-AIR": ("Air", 173647),
}


def bpn_nutrition(r, verified):
    p, f, c = (fnum(r[x]) for x in ("protein_per_100g", "fat_per_100g", "carbs_total_per_100g"))
    available = fnum(r["carbs_available_per_100g"])
    kcal = (
        4 * p + 9 * f + 4 * (available if available is not None else c)
        if None not in (p, f, c)
        else None
    )
    return dict(
        calories_per_100g=fmt(kcal),
        protein_per_100g=fmt(p),
        carbs_per_100g=fmt(c),
        fat_per_100g=fmt(f),
        nutrition_source="Badan Pangan Nasional - Komposisi Pangan Segar Indonesia",
        nutrition_source_id="row:" + r["source_id"],
        nutrition_verified=str(verified).lower(),
        calories_method="Atwater 4-4-9; karbohidrat tersedia bila ada",
        nutrition_source_url=BPN_URL,
    )


def usda_nutrition(f):
    n = {x["nutrient"]["id"]: x["amount"] for x in f["foodNutrients"] if "amount" in x}
    return dict(
        calories_per_100g=fmt(n.get(1008)),
        protein_per_100g=fmt(n.get(1003)),
        carbs_per_100g=fmt(n.get(1005)),
        fat_per_100g=fmt(n.get(1004)),
        nutrition_source="USDA FoodData Central SR Legacy",
        nutrition_source_id=str(f["fdcId"]),
        nutrition_verified="false",
        calories_method="USDA reported energy",
        nutrition_source_url="https://fdc.nal.usda.gov/food-details/"
        + str(f["fdcId"])
        + "/nutrients",
    )


def add_product(items, name, code, bpn, usda):
    if code in items:
        return
    proxy = PROXY.get(name)
    if proxy is None:
        match = next((r for r in bpn.values() if slug(r["raw_name"]) == slug(name)), None)
        proxy = match["source_id"] if match else ""
    if proxy.startswith("USDA:"):
        n = usda_nutrition(usda[int(proxy.split(":")[1])])
    elif proxy in bpn:
        n = bpn_nutrition(bpn[proxy], False)
    else:
        n = {
            x: ""
            for x in (
                "calories_per_100g",
                "protein_per_100g",
                "carbs_per_100g",
                "fat_per_100g",
                "nutrition_source",
                "nutrition_source_id",
                "calories_method",
                "nutrition_source_url",
            )
        }
        n["nutrition_verified"] = "false"
    items[code] = dict(ingredient_code=code, name=name, category=category(name), base_unit="g", **n)


def build_ingredients_prices():
    bpn = {
        r["source_id"]: r
        for r in json.loads((MAP / "bapanas_nutrition_snapshot.json").read_text(encoding="utf-8"))
    }
    with zipfile.ZipFile(RAW / "usda_sr_legacy_2018-04.zip") as z:
        usda = {f["fdcId"]: f for f in json.loads(z.read(z.namelist()[0]))["SRLegacyFoods"]}
    items = {}
    for r in bpn.values():
        code = "ING-" + slug(r["raw_name"])
        items[code] = dict(
            ingredient_code=code,
            name=r["raw_name"],
            category=category(r["raw_name"]),
            base_unit="g",
            **bpn_nutrition(r, True),
        )
    for code, (name, fid) in USDA_EXTRA.items():
        items[code] = dict(
            ingredient_code=code,
            name=name,
            category=category(name),
            base_unit="g",
            **usda_nutrition(usda[fid]),
        )
    prices = []
    aliases = []
    for r in read_csv(MAP / "garut_price_snapshot.csv"):
        name = r["raw_name"]
        if "Gas " in name or "Elpiji" in name:
            continue
        code = OVERRIDE.get(name, "ING-" + slug(name))
        add_product(items, name, code, bpn, usda)
        aliases.append(dict(source="Bapokting Garut", raw_name=name, ingredient_code=code))
        prices.append(
            dict(
                price_code=stable("PRC", code, "Garut", r["recorded_at"], name),
                ingredient_code=code,
                price_rupiah=r["price_rupiah"],
                quantity="1",
                unit=r["unit"].lower(),
                region="Kabupaten Garut",
                recorded_at=r["recorded_at"],
                source="Bapokting Disperindag Garut",
                source_url=r["source_url"],
                source_recorded_at=r["recorded_at"],
                source_license="Tidak disebutkan pada laman",
                source_commodity_name=name,
                price_status="published",
            )
        )
    for item in json.loads((RAW / "pihps_prices_2026-09-28.json").read_text()):
        name = item["commodity"]
        d = item["response"][0]
        if d["nominal"] <= 0:
            continue
        code = "ING-" + slug(name)
        add_product(items, name, code, bpn, usda)
        aliases.append(dict(source="PIHPS BI", raw_name=name, ingredient_code=code))
        day = d["date"][:10]
        prices.append(
            dict(
                price_code=stable("PRC", code, "PIHPS", day, name),
                ingredient_code=code,
                price_rupiah=fmt(d["nominal"]),
                quantity="1",
                unit=d["denomination"].lower(),
                region="Nasional PIHPS",
                recorded_at=day,
                source="PIHPS Bank Indonesia",
                source_url=BI_URL,
                source_recorded_at=day,
                source_license="Tidak disebutkan pada respons; lihat ketentuan situs",
                source_commodity_name=name,
                price_status="published",
            )
        )
    off = {
        p["code"]: p
        for p in json.loads((RAW / "openfoodfacts_indonesia_sample.json").read_text())["products"]
    }
    # The Mendeley file adds foods and prices needed by Mendeley recipes; it is
    # observed on its own date and processed exactly like the first file.
    for source_file in ("recipe_estimation_sources.json", "mendeley_sources.json"):
        supplements = json.loads((MAP / source_file).read_text(encoding="utf-8"))
        for row in supplements["nutrition"]:
            if "fdc_id" in row:
                nutrition = usda_nutrition(usda[row["fdc_id"]])
            elif "off_code" in row:
                product = off[row["off_code"]]
                nutriments = product["nutriments"]
                nutrition = dict(
                    zip(
                        (n + "_per_100g" for n in NUTRIENTS),
                        (
                            fmt(nutriments[k])
                            for k in (
                                "energy-kcal_100g",
                                "proteins_100g",
                                "carbohydrates_100g",
                                "fat_100g",
                            )
                        ),
                    )
                )
                nutrition.update(
                    nutrition_source="Open Food Facts; CC BY-SA; label komunitas belum diverifikasi",
                    nutrition_source_id=row["off_code"],
                    nutrition_verified="false",
                    calories_method="Energi label komunitas",
                    nutrition_source_url="https://world.openfoodfacts.org/product/"
                    + row["off_code"],
                )
            else:
                scale = 1
                if "assumed_water_fraction" in row:
                    assumed, original = row["assumed_water_fraction"], row["source_water_fraction"]
                    if not (0 <= assumed < 1 and 0 <= original < 1):
                        raise ValueError("Asumsi kadar air tidak valid: " + row["code"])
                    scale = (1 - assumed) / (1 - original)
                nutrition = dict(
                    zip(
                        (n + "_per_100g" for n in ("calories", "protein", "carbs", "fat")),
                        (fmt(value * scale) for value in row["macros"]),
                    )
                )
                nutrition.update(
                    nutrition_source=row.get(
                        "source", "TKPI 2019 melalui mirror; belum dicocokkan PDF asli"
                    ),
                    nutrition_source_id=row.get("source_id", row.get("tkpi_id", "")),
                    nutrition_verified="false",
                    calories_method="Energi terlapor sumber; proksi belum diverifikasi lokal",
                    nutrition_source_url=row.get("source_url", supplements["tkpi_mirror_url"]),
                )
            if row.get("note"):
                nutrition["calories_method"] += "; " + row["note"]
            items[row["code"]] = dict(
                ingredient_code=row["code"],
                name=row["name"],
                category=row["category"],
                base_unit="g",
                **nutrition,
            )
        for row in supplements["retail_prices"]:
            if row["code"] not in items:
                raise ValueError("Harga referensi tanpa bahan: " + row["code"])
            mass = row["grams"] * row.get("edible_yield", 1)
            prices.append(
                dict(
                    price_code=stable("PRC", row["code"], row["url"], supplements["observed_at"]),
                    ingredient_code=row["code"],
                    price_rupiah=fmt(row["price"]),
                    quantity=f"{mass / 1000:.6f}".rstrip("0").rstrip("."),
                    unit="kg",
                    region="Referensi toko daring (non-Garut)",
                    recorded_at=supplements["observed_at"],
                    source=row["source"],
                    source_url=row["url"],
                    source_recorded_at="",
                    source_license="Tidak dinyatakan; fakta harga referensi untuk estimasi",
                    source_commodity_name=row["product"]
                    + (" — " + row["note"] if row.get("note") else ""),
                    price_status="retail_reference",
                )
            )
    return items, prices, aliases, bpn, usda


def planning_prices(prices):
    # Reference prices supplement missing Garut ingredients only. Never relabel
    # national/retail prices as Garut or replace an available local quote.
    local = [
        p
        for p in prices
        if p["region"] == "Kabupaten Garut"
        and p["unit"] == "kg"
        and p["price_status"] == "published"
    ]
    latest = max((p["recorded_at"] for p in local), default=None)
    selected = {p["ingredient_code"]: p for p in local if p["recorded_at"] == latest}
    for p in sorted(prices, key=lambda p: (p["recorded_at"], p["price_code"]), reverse=True):
        if p["unit"] == "kg" and p["price_status"] == "retail_reference":
            selected.setdefault(p["ingredient_code"], p)
    return selected


# These are TAKARKUY's standardized two-serving variants. Gram quantities are
# authored for the MVP and are not presented as copied Kaggle measurements.
# Water used to wash/boil food is a household utility outside grocery cost.
CURATED = [
    (
        "Nasi telur tomat",
        "sarapan",
        "Masak nasi; tumis bawang dan tomat, lalu orak-arik telur.",
        "BERAS-MEDIUM:160,TELUR-AYAM-BROILER:120,TOMAT:100,BAWANG-MERAH:40,MINYAK-GORENG-CURAH:12",
    ),
    (
        "Nasi ayam bawang",
        "makan_siang",
        "Masak nasi; tumis bawang dan ayam hingga matang.",
        "BERAS-MEDIUM:160,DAGING-AYAM-BROILER:240,BAWANG-MERAH:50,BAWANG-PUTIH:18,MINYAK-GORENG-CURAH:12",
    ),
    (
        "Nasi tempe cabai",
        "makan_siang",
        "Masak nasi; tumis tempe, bawang, dan cabai hingga matang.",
        "BERAS-MEDIUM:150,TEMPE:200,CABAI-MERAH-KERITING:35,BAWANG-MERAH:40,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Nasi tahu buncis",
        "makan_siang",
        "Masak nasi; tumis tahu dan buncis bersama bawang putih.",
        "BERAS-MEDIUM:150,TAHU-PUTIH:260,BUNCIS:180,BAWANG-PUTIH:16,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Nasi udang tomat",
        "makan_malam",
        "Masak nasi; tumis udang dan tomat hingga udang matang.",
        "BERAS-MEDIUM:150,UDANG:240,TOMAT:150,BAWANG-PUTIH:16,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Nasi kembung cabai",
        "makan_siang",
        "Masak nasi; masak ikan kembung dan cabai sampai matang.",
        "BERAS-MEDIUM:150,IKAN-KEMBUNG:260,CABAI-MERAH-KERITING:30,BAWANG-MERAH:45,MINYAK-GORENG-CURAH:15",
    ),
    (
        "Nasi bandeng tomat",
        "makan_siang",
        "Masak nasi; masak bandeng bersama tomat dan bawang sampai matang.",
        "BERAS-MEDIUM:150,IKAN-BANDENG:260,TOMAT:130,BAWANG-MERAH:45,MINYAK-GORENG-CURAH:15",
    ),
    (
        "Nasi sapi cabai",
        "makan_malam",
        "Masak nasi; tumis daging sapi, cabai, dan bawang sampai matang.",
        "BERAS-MEDIUM:150,DAGING-SAPI:220,CABAI-RAWIT-MERAH:18,BAWANG-MERAH:45,MINYAK-GORENG-CURAH:15",
    ),
    (
        "Tumis kangkung tempe",
        "makan_malam",
        "Tumis bawang, tempe, dan kangkung sampai matang.",
        "KANGKUNG:300,TEMPE:220,BAWANG-MERAH:45,BAWANG-PUTIH:15,MINYAK-GORENG-CURAH:15",
    ),
    (
        "Tumis bayam tahu",
        "makan_malam",
        "Tumis bawang putih, tahu, dan bayam sampai matang.",
        "BAYAM:280,TAHU-PUTIH:260,BAWANG-PUTIH:16,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Sup ayam wortel kentang",
        "makan_siang",
        "Rebus ayam dan sayuran hingga matang; sajikan hangat.",
        "DAGING-AYAM-BROILER:220,WORTEL:180,KENTANG:260,BAWANG-MERAH:35",
    ),
    (
        "Sup udang jagung",
        "makan_malam",
        "Rebus jagung, tomat, dan udang hingga matang.",
        "UDANG:200,JAGUNG-MANIS:260,TOMAT:120,BAWANG-MERAH:35",
    ),
    (
        "Orak-arik telur buncis",
        "sarapan",
        "Tumis bawang dan buncis, lalu masukkan telur dan masak hingga matang.",
        "TELUR-AYAM-BROILER:180,BUNCIS:220,BAWANG-MERAH:45,MINYAK-GORENG-CURAH:12",
    ),
    (
        "Dadar telur pakcoy",
        "sarapan",
        "Campur telur dan pakcoy cincang; masak sampai matang.",
        "TELUR-AYAM-BROILER:180,PAKCOY:200,BAWANG-PUTIH:14,MINYAK-GORENG-CURAH:12",
    ),
    (
        "Singkong ayam cabai",
        "makan_siang",
        "Kukus singkong; tumis ayam dan cabai hingga matang.",
        "SINGKONG:300,DAGING-AYAM-BROILER:220,CABAI-MERAH-KERITING:30,BAWANG-MERAH:35,MINYAK-GORENG-CURAH:12",
    ),
    (
        "Ubi panggang telur",
        "sarapan",
        "Panggang ubi hingga empuk; sajikan bersama telur matang.",
        "UBI-JALAR-PUTIH:320,TELUR-AYAM-BROILER:180",
    ),
    (
        "Kentang tempe tumis",
        "makan_malam",
        "Masak kentang hingga empuk; tumis bersama tempe dan bawang.",
        "KENTANG:320,TEMPE:200,BAWANG-MERAH:45,CABAI-MERAH-KERITING:25,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Sawi putih tahu tumis",
        "makan_malam",
        "Tumis bawang, tahu, dan sawi putih sampai matang.",
        "SAWI-PUTIH:320,TAHU-PUTIH:240,BAWANG-MERAH:45,BAWANG-PUTIH:15,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Kubis ayam wortel",
        "makan_siang",
        "Tumis ayam hingga matang, lalu masukkan kubis dan wortel.",
        "KUBIS:300,DAGING-AYAM-BROILER:230,WORTEL:120,BAWANG-PUTIH:15,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Tahu tempe cabai",
        "makan_malam",
        "Tumis tahu, tempe, cabai, dan bawang hingga matang.",
        "TAHU-PUTIH:230,TEMPE:210,CABAI-RAWIT-MERAH:20,BAWANG-MERAH:45,MINYAK-GORENG-CURAH:14",
    ),
    (
        "Pisang segar",
        "sarapan",
        "Sajikan pisang matang sebagai sarapan ringan.",
        "PISANG:400",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Pisang dan jeruk",
        "sarapan",
        "Kupas pisang dan jeruk, lalu sajikan sebagai sarapan ringan.",
        "PISANG:240,JERUK:300",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Melon dan pisang",
        "sarapan",
        "Potong melon dan sajikan bersama pisang matang.",
        "MELON:300,PISANG:240",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Jeruk dan melon",
        "sarapan",
        "Kupas jeruk dan potong melon untuk sarapan ringan.",
        "JERUK:300,MELON:300",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Pisang, jeruk, dan melon",
        "sarapan",
        "Potong dan sajikan pisang, jeruk, serta melon sebagai salad buah sederhana.",
        "PISANG:160,JERUK:160,MELON:160",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Bubur Nasi Telur",
        "sarapan",
        "Masak beras dengan air sampai menjadi bubur; tambahkan telur dan bawang tumis, lalu masak hingga telur matang.",
        "BERAS-MEDIUM:140,TELUR-AYAM-BROILER:100,BAWANG-MERAH:24,MINYAK-GORENG-CURAH:6",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Goreng Sayur Telur",
        "sarapan",
        "Tumis bawang, wortel, dan kubis; masukkan nasi dan telur, lalu masak sampai telur matang.",
        "BERAS-MEDIUM:140,TELUR-AYAM-BROILER:100,WORTEL:60,KUBIS:80,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Kentang Tumis Telur",
        "sarapan",
        "Rebus kentang sampai empuk; tumis bersama bawang dan telur hingga matang.",
        "KENTANG:260,TELUR-AYAM-BROILER:100,BAWANG-MERAH:25,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Jagung Orak-arik Telur",
        "sarapan",
        "Rebus jagung sampai empuk; tumis bawang dan jagung, lalu masukkan telur dan masak hingga matang.",
        "JAGUNG-MANIS:240,TELUR-AYAM-BROILER:100,TOMAT:80,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tempe Telur",
        "sarapan",
        "Masak nasi; tumis tempe dan bawang, lalu sajikan dengan telur matang.",
        "BERAS-MEDIUM:140,TEMPE:120,TELUR-AYAM-BROILER:80,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Ubi Tumis Tempe",
        "sarapan",
        "Kukus ubi sampai empuk; tumis tempe dan bawang, lalu sajikan bersama ubi.",
        "UBI-JALAR-PUTIH:300,TEMPE:120,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Singkong Telur Bawang",
        "sarapan",
        "Kukus singkong sampai empuk; sajikan dengan telur matang dan bawang tumis.",
        "SINGKONG:280,TELUR-AYAM-BROILER:100,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Pakcoy",
        "sarapan",
        "Masak nasi; tumis pakcoy dan bawang putih, lalu masak bersama telur sampai matang.",
        "BERAS-MEDIUM:140,TELUR-AYAM-BROILER:100,PAKCOY:120,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Jagung",
        "makan_siang",
        "Masak nasi; tumis ayam, jagung, wortel, dan bawang sampai ayam matang.",
        "BERAS-MEDIUM:150,DAGING-AYAM-BROILER:180,JAGUNG-MANIS:100,WORTEL:60,BAWANG-PUTIH:12,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tempe Buncis",
        "makan_siang",
        "Masak nasi; tumis tempe dan buncis bersama bawang sampai matang.",
        "BERAS-MEDIUM:150,TEMPE:180,BUNCIS:140,BAWANG-MERAH:25,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Kubis",
        "makan_siang",
        "Masak nasi; tumis kubis dan wortel, lalu tambahkan telur dan masak sampai matang.",
        "BERAS-MEDIUM:150,TELUR-AYAM-BROILER:120,KUBIS:140,WORTEL:60,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tahu Kangkung",
        "makan_siang",
        "Masak nasi; tumis tahu dan kangkung dengan bawang putih sampai matang.",
        "BERAS-MEDIUM:150,TAHU-PUTIH:180,KANGKUNG:180,BAWANG-PUTIH:12,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Sapi Kentang",
        "makan_siang",
        "Masak nasi; masak daging sapi dan kentang bersama bawang hingga empuk dan matang.",
        "BERAS-MEDIUM:140,DAGING-SAPI:140,KENTANG:140,TOMAT:60,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Kembung Kangkung",
        "makan_siang",
        "Masak nasi; masak ikan kembung sampai matang dan tumis kangkung dengan bawang.",
        "BERAS-MEDIUM:150,IKAN-KEMBUNG:180,KANGKUNG:120,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Kubis Wortel",
        "makan_siang",
        "Masak nasi; tumis ayam hingga matang, tambahkan kubis dan wortel, lalu masak hingga sayur layu.",
        "BERAS-MEDIUM:150,DAGING-AYAM-BROILER:180,KUBIS:100,WORTEL:80,BAWANG-PUTIH:12,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Sup Tahu Kentang Wortel",
        "makan_malam",
        "Rebus kentang dan wortel hingga hampir empuk; masukkan tahu dan bawang, lalu masak sampai matang.",
        "TAHU-PUTIH:180,KENTANG:180,WORTEL:100,KUBIS:80,BAWANG-PUTIH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Pakcoy",
        "makan_malam",
        "Masak nasi; tumis ayam hingga matang, lalu masukkan pakcoy dan bawang putih.",
        "BERAS-MEDIUM:150,DAGING-AYAM-BROILER:180,PAKCOY:140,BAWANG-PUTIH:12,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tempe Bayam",
        "makan_malam",
        "Masak nasi; tumis tempe dan bawang, lalu masukkan bayam dan masak hingga layu.",
        "BERAS-MEDIUM:150,TEMPE:180,BAYAM:140,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Bayam Tomat",
        "makan_malam",
        "Masak nasi; tumis tomat dan bayam, tambahkan telur, lalu masak hingga telur matang.",
        "BERAS-MEDIUM:150,TELUR-AYAM-BROILER:120,BAYAM:100,TOMAT:80,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Kembung Kubis",
        "makan_malam",
        "Masak nasi; masak ikan kembung sampai matang, lalu tumis kubis dan bawang.",
        "BERAS-MEDIUM:150,IKAN-KEMBUNG:180,KUBIS:150,TOMAT:60,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tahu Tempe Kentang",
        "makan_malam",
        "Masak nasi; masak tahu, tempe, dan kentang dengan bawang sampai matang.",
        "BERAS-MEDIUM:140,TAHU-PUTIH:100,TEMPE:100,KENTANG:120,BAWANG-MERAH:20,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Bubur Kacang Hijau Gula Merah",
        "sarapan",
        "Rendam kacang hijau, lalu rebus dengan air sampai empuk. Tambahkan gula merah secukupnya; resep ini memakai takaran 20 g untuk dua porsi.",
        "KACANG-HIJAU:120,GULA-MERAH:20",
        "TAKARKUY kurasi internal; takaran bumbu ditetapkan untuk MVP",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Pancake Pisang Telur",
        "sarapan",
        "Haluskan pisang dan campur dengan telur serta tepung. Masak adonan kecil di wajan beroles minyak sampai kedua sisi matang.",
        "PISANG:180,TELUR-AYAM-BROILER:100,TEPUNG-TERIGU-CURAH:50,MINYAK-GORENG-CURAH:5",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Jagung Telur Bayam",
        "sarapan",
        "Masak nasi dan jagung; tumis bayam sebentar lalu sajikan dengan telur mata sapi.",
        "BERAS-MEDIUM:120,JAGUNG-MANIS:120,TELUR-AYAM-BROILER:100,BAYAM:100,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Kentang Dadar Telur Kubis",
        "sarapan",
        "Rebus kentang sampai empuk, potong kecil, lalu campur dengan telur dan kubis. Masak menjadi dadar hingga matang.",
        "KENTANG:180,TELUR-AYAM-BROILER:120,KUBIS:80,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Bubur Nasi Ayam Wortel",
        "sarapan",
        "Masak beras dengan air lebih banyak sampai menjadi bubur. Masukkan ayam dan wortel cincang; masak hingga ayam matang.",
        "BERAS-MEDIUM:120,DAGING-AYAM-BROILER:100,WORTEL:60,BAWANG-PUTIH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Bubur Kacang Hijau Pisang",
        "sarapan",
        "Rebus kacang hijau sampai empuk. Tambahkan pisang iris dan gula merah, lalu masak sebentar sampai pisang hangat.",
        "KACANG-HIJAU:100,PISANG:120,GULA-MERAH:15",
        "TAKARKUY kurasi internal; takaran bumbu ditetapkan untuk MVP",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Ubi Kukus Tempe Tumis",
        "sarapan",
        "Kukus ubi sampai empuk. Tumis tempe dan bawang dengan sedikit minyak hingga matang, lalu sajikan bersama ubi.",
        "UBI-JALAR-PUTIH:280,TEMPE:120,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:6",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Goreng Telur Pakcoy",
        "sarapan",
        "Tumis bawang dan pakcoy, masukkan nasi serta telur kocok, lalu aduk sampai telur matang.",
        "BERAS-MEDIUM:130,TELUR-AYAM-BROILER:100,PAKCOY:100,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Singkong Telur Tomat",
        "sarapan",
        "Kukus singkong sampai empuk. Masak telur orak-arik dengan tomat dan bawang, lalu sajikan bersama singkong.",
        "SINGKONG:260,TELUR-AYAM-BROILER:100,TOMAT:80,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:6",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Pisang Panggang Telur",
        "sarapan",
        "Potong pisang memanjang dan panggang di wajan beroles tipis minyak. Sajikan dengan telur matang.",
        "PISANG:220,TELUR-AYAM-BROILER:100,MINYAK-GORENG-CURAH:5",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Tumis Tahu Telur Buncis",
        "sarapan",
        "Tumis buncis dan tahu sampai matang, tuangkan telur kocok, lalu aduk hingga telur set.",
        "TAHU-PUTIH:160,TELUR-AYAM-BROILER:100,BUNCIS:120,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Bubur Ubi Kacang Hijau",
        "sarapan",
        "Rebus kacang hijau sampai mulai empuk. Tambahkan ubi potong dan lanjutkan memasak hingga lunak; beri gula merah sesuai takaran.",
        "KACANG-HIJAU:80,UBI-JALAR-PUTIH:180,GULA-MERAH:15",
        "TAKARKUY kurasi internal; takaran bumbu ditetapkan untuk MVP",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Tomat Buncis",
        "makan_siang",
        "Masak nasi. Tumis ayam sampai matang, tambahkan tomat dan buncis, lalu masak sampai sayuran empuk.",
        "BERAS-MEDIUM:150,DAGING-AYAM-BROILER:180,TOMAT:100,BUNCIS:100,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Udang Kubis Wortel",
        "makan_siang",
        "Masak nasi. Tumis udang sampai berubah warna, masukkan kubis dan wortel, lalu masak hingga matang.",
        "BERAS-MEDIUM:150,UDANG:160,KUBIS:100,WORTEL:80,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:10",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Dadar Bayam",
        "makan_siang",
        "Masak nasi. Campur bayam cincang dengan telur, lalu masak menjadi dadar matang.",
        "BERAS-MEDIUM:150,TELUR-AYAM-BROILER:140,BAYAM:100,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ikan Bandeng Tomat",
        "makan_siang",
        "Masak nasi. Masak ikan bandeng hingga matang, tumis tomat dan bawang sebagai pendamping.",
        "BERAS-MEDIUM:150,IKAN-BANDENG:200,TOMAT:120,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Sapi Kubis",
        "makan_siang",
        "Masak nasi. Tumis daging sapi hingga matang, masukkan kubis dan bawang, lalu masak sampai layu.",
        "BERAS-MEDIUM:150,DAGING-SAPI:160,KUBIS:140,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Kembung Buncis",
        "makan_siang",
        "Masak nasi. Masak ikan kembung hingga matang; tumis buncis dan bawang sebagai sayur pendamping.",
        "BERAS-MEDIUM:150,IKAN-KEMBUNG:180,BUNCIS:120,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tempe Wortel Pakcoy",
        "makan_siang",
        "Masak nasi. Tumis tempe sampai kecokelatan, masukkan wortel dan pakcoy, lalu masak hingga matang.",
        "BERAS-MEDIUM:150,TEMPE:180,WORTEL:80,PAKCOY:100,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tahu Tomat Kubis",
        "makan_siang",
        "Masak nasi. Tumis tahu hingga hangat, tambahkan tomat dan kubis, lalu masak sampai sayur layu.",
        "BERAS-MEDIUM:150,TAHU-PUTIH:180,TOMAT:100,KUBIS:100,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Kentang Bayam",
        "makan_siang",
        "Masak nasi. Rebus ayam dan kentang dengan air sampai matang; masukkan bayam menjelang selesai.",
        "BERAS-MEDIUM:140,DAGING-AYAM-BROILER:160,KENTANG:140,BAYAM:80,BAWANG-PUTIH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Tempe Kangkung",
        "makan_siang",
        "Masak nasi. Tumis tempe dan kangkung, lalu sajikan dengan telur ceplok matang.",
        "BERAS-MEDIUM:140,TELUR-AYAM-BROILER:100,TEMPE:120,KANGKUNG:120,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Udang Jagung Bayam",
        "makan_siang",
        "Masak nasi. Tumis udang dan jagung hingga matang, masukkan bayam sebentar sebelum disajikan.",
        "BERAS-MEDIUM:140,UDANG:140,JAGUNG-MANIS:100,BAYAM:80,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ikan Dori Tomat",
        "makan_siang",
        "Masak nasi. Masak ikan dori sampai matang dan sajikan dengan tumis tomat serta bawang.",
        "BERAS-MEDIUM:150,IKAN-DORI:180,TOMAT:120,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Pakcoy Wortel",
        "makan_siang",
        "Masak nasi. Tumis ayam hingga matang, tambahkan wortel dan pakcoy, lalu masak sampai sayur lunak.",
        "BERAS-MEDIUM:150,DAGING-AYAM-BROILER:170,PAKCOY:100,WORTEL:80,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Kentang Kubis",
        "makan_siang",
        "Masak nasi. Tumis kentang sampai empuk, tambahkan kubis dan telur, lalu masak hingga telur matang.",
        "BERAS-MEDIUM:140,TELUR-AYAM-BROILER:120,KENTANG:120,KUBIS:100,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Bandeng Buncis Tomat",
        "makan_siang",
        "Masak nasi. Panggang atau goreng bandeng dengan sedikit minyak; tumis buncis dan tomat sampai matang.",
        "BERAS-MEDIUM:150,IKAN-BANDENG:180,BUNCIS:100,TOMAT:80,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Sup Ayam Kubis Kentang",
        "makan_malam",
        "Rebus ayam dan kentang sampai hampir empuk. Masukkan kubis dan wortel, lalu rebus sampai semua bahan matang.",
        "DAGING-AYAM-BROILER:180,KENTANG:160,KUBIS:120,WORTEL:80,BAWANG-PUTIH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Goreng Tempe Kubis",
        "makan_malam",
        "Tumis bawang dan tempe, masukkan nasi serta kubis, lalu aduk sampai panas merata.",
        "BERAS-MEDIUM:140,TEMPE:140,KUBIS:100,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Tumis Udang Pakcoy Wortel",
        "makan_malam",
        "Tumis udang hingga matang. Masukkan pakcoy dan wortel, lalu masak sebentar sampai sayuran matang.",
        "UDANG:180,PAKCOY:140,WORTEL:100,BAWANG-PUTIH:10,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Sapi Tomat Buncis",
        "makan_malam",
        "Masak nasi. Tumis daging sapi sampai matang, tambahkan tomat dan buncis, lalu masak sampai lunak.",
        "BERAS-MEDIUM:150,DAGING-SAPI:150,TOMAT:100,BUNCIS:100,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Tumis Ikan Kembung Kubis",
        "makan_malam",
        "Masak ikan kembung sampai matang. Tumis kubis dan tomat, lalu sajikan bersama ikan.",
        "IKAN-KEMBUNG:200,KUBIS:140,TOMAT:80,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Sup Tahu Buncis Wortel",
        "makan_malam",
        "Rebus wortel dan buncis sampai hampir empuk. Masukkan tahu dan bawang, lalu lanjutkan memasak hingga matang.",
        "TAHU-PUTIH:180,BUNCIS:100,WORTEL:100,KUBIS:80,BAWANG-PUTIH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ayam Ubi Tumis Bayam",
        "makan_malam",
        "Masak nasi. Panggang atau tumis ayam sampai matang; kukus ubi dan tumis bayam sebentar sebagai pendamping.",
        "BERAS-MEDIUM:140,DAGING-AYAM-BROILER:160,UBI-JALAR-PUTIH:140,BAYAM:80,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Telur Orak-arik Pakcoy",
        "makan_malam",
        "Masak nasi. Tumis pakcoy dengan bawang, masukkan telur kocok, dan masak hingga matang.",
        "BERAS-MEDIUM:140,TELUR-AYAM-BROILER:140,PAKCOY:120,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Udang Tomat Kangkung",
        "makan_malam",
        "Masak nasi. Tumis udang dan tomat sampai matang, lalu masukkan kangkung hingga layu.",
        "BERAS-MEDIUM:140,UDANG:140,TOMAT:100,KANGKUNG:100,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Kentang Tempe Bayam Kukus",
        "makan_malam",
        "Kukus kentang sampai empuk. Tumis tempe dan bayam dengan bawang sampai matang, lalu sajikan bersama kentang.",
        "KENTANG:180,TEMPE:150,BAYAM:100,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Ikan Dori Kubis Wortel",
        "makan_malam",
        "Masak nasi. Masak ikan dori sampai matang; tumis kubis dan wortel sebagai sayur pendamping.",
        "BERAS-MEDIUM:140,IKAN-DORI:170,KUBIS:100,WORTEL:80,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Tumis Ayam Sawi Putih Kentang",
        "makan_malam",
        "Masak kentang hingga empuk. Tumis ayam sampai matang, masukkan sawi putih, lalu sajikan bersama kentang.",
        "DAGING-AYAM-BROILER:180,SAWI-PUTIH:160,KENTANG:160,BAWANG-PUTIH:8,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Nasi Tempe Jagung Tomat",
        "makan_malam",
        "Masak nasi. Tumis tempe dan jagung sampai matang, tambahkan tomat dan masak hingga layu.",
        "BERAS-MEDIUM:140,TEMPE:150,JAGUNG-MANIS:100,TOMAT:80,BAWANG-MERAH:15,MINYAK-GORENG-CURAH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
    (
        "Sup Udang Kentang Kubis",
        "makan_malam",
        "Rebus kentang sampai hampir empuk. Masukkan udang, kubis, dan tomat; masak sampai udang matang.",
        "UDANG:150,KENTANG:160,KUBIS:100,TOMAT:80,BAWANG-PUTIH:8",
        "TAKARKUY kurasi internal",
        "https://badanpangan.go.id/tabel-komposisi-pangan-segar-indonesia",
    ),
]


def build_recipes(items, prices):
    price_by_code = planning_prices(prices)
    recipes = []
    links = []
    tags = []
    estimates = []
    animal = ("DAGING-", "IKAN-", "UDANG", "TELUR-")
    for i, entry in enumerate(CURATED, 1):
        name, meal, instructions, spec = entry[:4]
        source = entry[4] if len(entry) > 4 else "TAKARKUY kurasi MVP; inspirasi Kaggle"
        source_url = entry[5] if len(entry) > 5 else KAGGLE_URL
        code = "RCP-MVP-%03d" % i
        quantities = []
        missing = []
        for part in spec.split(","):
            short, amount = part.split(":")
            ic = "ING-" + short
            g = float(amount)
            quantities.append((ic, g))
            if ic not in items or not items[ic]["calories_per_100g"] or ic not in price_by_code:
                missing.append(ic)
            links.append(
                dict(
                    recipe_ingredient_code=stable("RIN", code, ic),
                    recipe_code=code,
                    ingredient_code=ic,
                    quantity=fmt(g),
                    unit="g",
                    is_optional="false",
                    quantity_status="curated",
                    raw_text="",
                    source="TAKARKUY kurasi MVP",
                )
            )
        ok = not missing
        reason = "; ".join(missing)
        recipes.append(
            dict(
                recipe_code=code,
                name=name,
                base_servings="2",
                meal_type=meal,
                instructions=instructions,
                is_plannable=str(ok).lower(),
                missing_data_reason=reason,
                source=source,
                source_url=source_url,
                raw_ingredients="",
                is_active="true",
            )
        )
        if ok:
            kcal = protein = carbs = fat = cost = 0.0
            for ic, g in quantities:
                item = items[ic]
                price = price_by_code[ic]
                kcal += g * float(item["calories_per_100g"]) / 100
                protein += g * float(item["protein_per_100g"]) / 100
                carbs += g * float(item["carbs_per_100g"]) / 100
                fat += g * float(item["fat_per_100g"]) / 100
                cost += g * float(price["price_rupiah"]) / float(price["quantity"]) / 1000
            estimates.append(
                dict(
                    recipe_code=code,
                    region="Kabupaten Garut",
                    price_date="2026-09-28",
                    cost_total_rupiah=fmt(cost),
                    cost_per_serving_rupiah=fmt(cost / 2),
                    calories_per_serving=fmt(kcal / 2),
                    protein_per_serving_g=fmt(protein / 2),
                    carbs_per_serving_g=fmt(carbs / 2),
                    fat_per_serving_g=fmt(fat / 2),
                    calculation_status="estimasi_bahan_mentah",
                )
            )
            tagset = {"halal", "tanpa_garam_tambahan", meal}
            if meal == "sarapan" and source == "TAKARKUY kurasi internal":
                tagset.add("sarapan_ringan")
            if not any(ic.startswith("ING-" + x) for ic, _ in quantities for x in animal):
                tagset.add("vegetarian")
            if protein / 2 >= 20:
                tagset.add("tinggi_protein")
            if kcal / 2 <= 400:
                tagset.add("rendah_kalori")
            if (
                any(items[ic]["category"] == "sayur" for ic, _ in quantities)
                and any(items[ic]["category"] == "protein" for ic, _ in quantities)
                and any(items[ic]["category"] == "karbohidrat" for ic, _ in quantities)
            ):
                tagset.add("seimbang_internal")
            for ic, _ in quantities:
                if any(x in ic for x in ("TAHU", "TEMPE", "KEDELAI")):
                    tagset.add("mengandung_kedelai")
                if "TELUR" in ic:
                    tagset.add("mengandung_telur")
                if "UDANG" in ic:
                    tagset.add("mengandung_krustasea")
                if "IKAN" in ic:
                    tagset.add("mengandung_ikan")
                if "KACANG-TANAH" in ic:
                    tagset.add("mengandung_kacang")
            for tag in sorted(tagset):
                tags.append(
                    dict(
                        recipe_tag_code=stable("TAG", code, tag),
                        recipe_code=code,
                        tag=tag,
                        source="TAKARKUY aturan internal",
                    )
                )
    # Raw Kaggle recipes are staged for future curation and explicitly excluded
    # from planning. This keeps the 80-row catalog honest.
    with zipfile.ZipFile(RAW / "indonesian_food_recipes.zip") as z:
        selected = []
        seen = set()
        for member in sorted(z.namelist()):
            if not member.endswith(".csv"):
                continue
            source_category = member.replace("dataset-", "").replace(".csv", "")
            for row in csv.DictReader(io.TextIOWrapper(z.open(member), encoding="utf-8-sig")):
                match = re.search(r"/resep/(\d+)-", row["URL"])
                if not match or match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                selected.append((row, source_category))
                if len(selected) >= 60:
                    break
            if len(selected) >= 60:
                break
    for row, source_category in selected:
        rid = re.search(r"/resep/(\d+)-", row["URL"]).group(1)
        code = "RCP-KAGGLE-" + rid
        recipes.append(
            dict(
                recipe_code=code,
                name=row["Title"],
                base_servings="",
                meal_type="",
                instructions="",
                is_plannable="false",
                missing_data_reason="base_servings, kuantitas, satuan, harga, dan tag belum dikurasi",
                source="Kaggle Indonesian Food Recipes",
                source_url="https://cookpad.com" + row["URL"],
                raw_ingredients="",
                is_active="true",
            )
        )
        tags.append(
            dict(
                recipe_tag_code=stable("TAG", code, source_category),
                recipe_code=code,
                tag="kategori_sumber_" + source_category,
                source="Kaggle file category",
            )
        )

    # Discovery candidates from TheMealDB are retained in the catalog as
    # metadata only. The tentative meal slot is a browsing suggestion, not a
    # claim from the source or a signal that this recipe is safe to plan.
    candidates_path = ROOT / "scratch" / "themealdb_100_candidates.json"
    if candidates_path.exists():
        snapshot = json.loads(candidates_path.read_text(encoding="utf-8"))
        seen_candidates = {}
        for candidate in snapshot.get("recipes", []):
            source_id = str(candidate.get("source_id", "")).strip()
            code = "RCP-TMDB-" + slug(source_id)
            if code in seen_candidates and seen_candidates[code] == candidate:
                continue
            if (
                not source_id
                or code in seen_candidates
                or code in {r["recipe_code"] for r in recipes}
            ):
                raise ValueError(f"Duplikat/id kandidat TheMealDB tidak valid: {source_id!r}")
            seen_candidates[code] = candidate
            meal = candidate.get("suggested_meal_type", "")
            if meal not in ("sarapan", "makan_siang", "makan_malam"):
                meal = ""
            source_url = candidate.get("source_url") or candidate.get("themealdb_url", "")
            raw = json.dumps(
                {
                    "api_source": "TheMealDB API",
                    "source_id": source_id,
                    "source_category": candidate.get("source_category", ""),
                    "source_area": candidate.get("source_area", ""),
                    "suggested_meal_type": meal,
                    "themealdb_url": candidate.get("themealdb_url", ""),
                    "image_url": candidate.get("image_url", ""),
                    "ingredients": candidate.get("ingredients", []),
                    "review_status": candidate.get("review_status", "needs_manual_review"),
                },
                ensure_ascii=False,
            )
            recipes.append(
                dict(
                    recipe_code=code,
                    name=candidate.get("name", "").strip(),
                    base_servings="",
                    meal_type=meal,
                    instructions=candidate.get("instructions", "").strip(),
                    is_plannable="false",
                    missing_data_reason=(
                        "Kandidat scratch: meal slot masih saran; porsi, bahan/takaran gram, "
                        "harga lokal, gizi, dan penggunaan sumber belum ditinjau"
                    ),
                    source="TheMealDB API; kandidat belum dikurasi",
                    source_url=source_url,
                    raw_ingredients=raw,
                    is_active="true",
                )
            )
            source_category = slug(candidate.get("source_category", "unknown")).lower()
            tags.append(
                dict(
                    recipe_tag_code=stable("TAG", code, "candidate"),
                    recipe_code=code,
                    tag="kandidat_belum_dikurasi",
                    source="TheMealDB API",
                )
            )
            tags.append(
                dict(
                    recipe_tag_code=stable("TAG", code, "slot", meal),
                    recipe_code=code,
                    tag="slot_saran_" + meal if meal else "slot_saran_belum_diatur",
                    source="TAKARKUY; penempatan sementara",
                )
            )
            tags.append(
                dict(
                    recipe_tag_code=stable("TAG", code, "category", source_category),
                    recipe_code=code,
                    tag="kategori_sumber_" + source_category,
                    source="TheMealDB API",
                )
            )

    # API records only enter the planner after explicit, per-row review in the
    # curation table. Raw API output remains a discovery/review artifact.
    approved = defaultdict(list)
    seen_curation_rows = set()
    for row in read_csv(MAP / "themealdb_recipe_curation.csv"):
        identity = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if identity in seen_curation_rows:
            continue
        seen_curation_rows.add(identity)
        if row.get("curation_status", "").strip().casefold() == "approved":
            approved[row["source_id"].strip()].append(row)
    for source_id, rows in sorted(approved.items()):
        first = rows[0]
        code = "RCP-TMDB-" + slug(source_id)
        # Promotion replaces discovery metadata at the SAME stable ID. It must
        # not append a second recipe or leave stale candidate tags behind.
        tags[:] = [row for row in tags if row["recipe_code"] != code]
        links[:] = [row for row in links if row["recipe_code"] != code]
        if (
            not source_id
            or not first["name"].strip()
            or not first["source_url"].startswith("https://")
            or first["meal_type"] not in ("sarapan", "makan_siang", "makan_malam")
            or not first["base_servings"].isdigit()
            or int(first["base_servings"]) < 1
            or not first["instructions"].strip()
        ):
            raise ValueError(f"Metadata resep TheMealDB belum lengkap untuk id {source_id!r}")
        required_reviews = ("ingredient_mapping_reviewed", "source_use_reviewed", "halal_reviewed")
        if any(
            any(row.get(field, "").strip().casefold() != "true" for row in rows)
            for field in required_reviews
        ):
            raise ValueError(f"Review bahan, penggunaan sumber, dan halal harus true untuk {code}")
        quantities = defaultdict(float)
        for row in rows:
            if any(
                row[field] != first[field]
                for field in ("name", "source_url", "meal_type", "base_servings", "instructions")
            ):
                raise ValueError(f"Metadata berbeda antarbaris resep {code}")
            ingredient_code = row["ingredient_code"].strip()
            quantity = fnum(row["quantity_g"])
            if (
                ingredient_code not in items
                or quantity is None
                or not math.isfinite(quantity)
                or quantity <= 0
            ):
                raise ValueError(
                    f"Kode bahan/takaran gram tidak valid pada {code}: {ingredient_code!r}"
                )
            quantities[ingredient_code] += quantity
        if not quantities:
            raise ValueError(f"Resep TheMealDB tanpa bahan terkurasi: {code}")
        unavailable = [
            ic
            for ic in quantities
            if ic not in price_by_code
            or any(not items[ic].get(f"{nutrient}_per_100g") for nutrient in NUTRIENTS)
        ]
        if unavailable:
            raise ValueError(
                f"Empat makro/harga gram belum tersedia untuk {code}: {', '.join(unavailable)}"
            )

        servings = int(first["base_servings"])
        kcal = protein = carbs = fat = cost = 0.0
        animal = ("DAGING-", "IKAN-", "UDANG", "TELUR-")
        tagset = {"halal", first["meal_type"], "kategori_sumber_themealdb"}
        if not any(ic.startswith("ING-" + prefix) for ic in quantities for prefix in animal):
            tagset.add("vegetarian")
        categories = {items[ic]["category"] for ic in quantities}
        for ic, grams in quantities.items():
            item = items[ic]
            price = price_by_code[ic]
            kcal += grams * float(item["calories_per_100g"]) / 100
            protein += grams * float(item["protein_per_100g"]) / 100
            carbs += grams * float(item["carbs_per_100g"]) / 100
            fat += grams * float(item["fat_per_100g"]) / 100
            cost += grams * float(price["price_rupiah"]) / float(price["quantity"]) / 1000
            links.append(
                dict(
                    recipe_ingredient_code=stable("RIN", code, ic),
                    recipe_code=code,
                    ingredient_code=ic,
                    quantity=fmt(grams),
                    unit="g",
                    is_optional="false",
                    quantity_status="curated",
                    raw_text="",
                    source="TheMealDB API; mapping TAKARKUY disetujui",
                )
            )
            if any(x in ic for x in ("TAHU", "TEMPE", "KEDELAI")):
                tagset.add("mengandung_kedelai")
            if "TELUR" in ic:
                tagset.add("mengandung_telur")
            if "UDANG" in ic:
                tagset.add("mengandung_krustasea")
            if "IKAN" in ic:
                tagset.add("mengandung_ikan")
            if "KACANG" in ic:
                tagset.add("mengandung_kacang")
        if protein / servings >= 20:
            tagset.add("tinggi_protein")
        if kcal / servings <= 400:
            tagset.add("rendah_kalori")
        if {"sayur", "protein", "karbohidrat"} <= categories:
            tagset.add("seimbang_internal")
        replace_recipe(
            recipes,
            dict(
                recipe_code=code,
                name=first["name"],
                base_servings=str(servings),
                meal_type=first["meal_type"],
                instructions=first["instructions"],
                is_plannable="true",
                missing_data_reason="",
                source="TheMealDB API; kurasi TAKARKUY",
                source_url=first["source_url"],
                raw_ingredients=json.dumps(
                    [{"ingredient_code": ic, "quantity_g": fmt(g)} for ic, g in quantities.items()],
                    ensure_ascii=False,
                ),
                is_active="true",
            ),
        )
        estimates.append(
            dict(
                recipe_code=code,
                region="Kabupaten Garut",
                price_date="2026-09-28",
                cost_total_rupiah=fmt(cost),
                cost_per_serving_rupiah=fmt(cost / servings),
                calories_per_serving=fmt(kcal / servings),
                protein_per_serving_g=fmt(protein / servings),
                carbs_per_serving_g=fmt(carbs / servings),
                fat_per_serving_g=fmt(fat / servings),
                calculation_status="estimasi_bahan_mentah",
            )
        )
        for tag in sorted(tagset):
            tags.append(
                dict(
                    recipe_tag_code=stable("TAG", code, tag),
                    recipe_code=code,
                    tag=tag,
                    source="TheMealDB API; kurasi TAKARKUY",
                )
            )
    updates, audit = estimate_candidates(ROOT, items, price_by_code)
    for update in updates:
        code = update["recipe_code"]
        if code.removeprefix("RCP-TMDB-") in approved and code.startswith("RCP-TMDB-"):
            continue  # Explicit manual review wins over generated estimates.
        quantities = update.pop("quantities")
        replace_recipe(recipes, update)
        if update["is_plannable"] != "true":
            continue
        tags[:] = [row for row in tags if row["recipe_code"] != code]
        tags.append(
            dict(
                recipe_tag_code=stable("TAG", code, "takaran_estimasi"),
                recipe_code=code,
                tag="takaran_estimasi",
                source="TAKARKUY estimasi v2",
            )
        )
        # The actual list has been mapped to known foods; this is an ingredient
        # heuristic only, not a halal certificate for branded products/processes.
        for tag in ("halal", update["meal_type"]):
            tags.append(
                dict(
                    recipe_tag_code=stable("TAG", code, tag),
                    recipe_code=code,
                    tag=tag,
                    source="TAKARKUY heuristik daftar bahan estimasi",
                )
            )
        totals = {
            n: sum(g * float(items[ic][n + "_per_100g"]) / 100 for ic, g in quantities.items())
            for n in NUTRIENTS
        }
        cost = sum(
            g
            * float(price_by_code[ic]["price_rupiah"])
            / float(price_by_code[ic]["quantity"])
            / 1000
            for ic, g in update["purchase_quantities"].items()
        )
        portions = int(update["base_servings"])
        for ic, g in quantities.items():
            provenance = [
                row for row in audit if row["recipe_code"] == code and row["ingredient_code"] == ic
            ]
            links.append(
                dict(
                    recipe_ingredient_code=stable("RIN", code, ic),
                    recipe_code=code,
                    ingredient_code=ic,
                    quantity=fmt(g),
                    unit="g",
                    is_optional="false",
                    quantity_status="estimated",
                    raw_text=json.dumps(provenance, ensure_ascii=False),
                    source=update["source"],
                )
            )
        estimates.append(
            dict(
                recipe_code=code,
                region="Garut + referensi non-Garut",
                price_date="2026-10-01",
                cost_total_rupiah=fmt(cost),
                cost_per_serving_rupiah=fmt(cost / portions),
                calories_per_serving=fmt(totals["calories"] / portions),
                protein_per_serving_g=fmt(totals["protein"] / portions),
                carbs_per_serving_g=fmt(totals["carbs"] / portions),
                fat_per_serving_g=fmt(totals["fat"] / portions),
                calculation_status="estimasi_takaran_porsi_dan_bahan_mentah",
            )
        )
    mendeley = build_mendeley(ROOT, items, price_by_code, [r["name"] for r in recipes])
    for rows, extra in zip((recipes, links, tags, estimates), mendeley[:4]):
        rows.extend(extra)
    # Users see one clear name per menu: curated renames first, then standard
    # spelling and casing. Mendeley rows already went through the same steps.
    overrides = load_overrides(MAP / "recipe_name_overrides.csv")
    for recipe in recipes:
        if recipe["source"] == "TheMealDB API; kurasi TAKARKUY":
            continue  # A manually reviewed name wins over generated naming rules.
        name, _ = overrides.get(recipe["recipe_code"], ("", ""))
        if name == EXCLUDE and not recipe["recipe_code"].startswith("RCP-MDL-"):
            raise ValueError(
                "Pengecualian nama hanya untuk resep Mendeley: " + recipe["recipe_code"]
            )
        if name and name != EXCLUDE:
            recipe["name"] = name
        if recipe["is_plannable"] == "true":
            recipe["name"] = standard_name(recipe["name"])
    names = [r["name"].casefold() for r in recipes if r["is_plannable"] == "true"]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError("Nama resep siap hitung ganda: " + ", ".join(duplicates))
    write_csv(
        ROOT / "staging/mendeley_recipe_audit.csv",
        mendeley[4],
        "recipe_code ingredient_position raw_ingredient raw_measure ingredient_code quantity_g purchase_quantity_g status estimation_note reference_url recipe_source_url rules_version".split(),
    )
    write_csv(
        ROOT / "staging/recipe_quantity_estimates.csv",
        audit,
        "recipe_code ingredient_position raw_ingredient raw_measure ingredient_code quantity_g purchase_quantity_g status estimation_note reference_url recipe_source_url rules_version".split(),
    )
    return recipes, links, tags, estimates


# FoodKeeper's English categories are mapped explicitly. The mapping is a
# reference approximation for Indonesian products, never a local expiry claim.
FK_MAP = {
    "BERAS": 318,
    "BERAS-KETAN": 318,
    "BERAS-PREMIUM": 318,
    "BERAS-MEDIUM": 318,
    "BERAS-TERMAHAL": 318,
    "BERAS-TERMURAH-NON-BULOG": 318,
    "TEPUNG-TERIGU": 205,
    "TEPUNG-TERIGU-CURAH": 205,
    "JAGUNG-SEGAR": 264,
    "JAGUNG-MANIS": 264,
    "JAGUNG-PIPIL": 202,
    "JAGUNG-PIPILAN": 202,
    "KENTANG": 279,
    "SINGKONG": 290,
    "UBI-JALAR": 402,
    "UBI-JALAR-PUTIH": 402,
    "IKAN-LELE": 134,
    "IKAN-BANDENG": 134,
    "IKAN-MUJAIR": 132,
    "IKAN-TONGKOL": 134,
    "IKAN-KEMBUNG": 134,
    "IKAN-TUNA": 134,
    "IKAN-DORI": 132,
    "IKAN-MAS": 134,
    "IKAN-SEGAR-TONGKOL-TUNA-CAKALANG": 134,
    "UDANG": 139,
    "DAGING-SAPI": 40,
    "DAGING-AYAM": 106,
    "DAGING-AYAM-KAMPUNG": 106,
    "DAGING-AYAM-BROILER": 106,
    "DAGING-AYAM-RAS-SEGAR": 106,
    "TELUR-AYAM": 20,
    "TELUR-AYAM-KAMPUNG": 20,
    "TELUR-AYAM-BROILER": 20,
    "TELUR-AYAM-RAS-SEGAR": 20,
    "TOMAT": 288,
    "TOMAT-HIJAU": 288,
    "BAYAM": 273,
    "KANGKUNG": 269,
    "KACANG-PANJANG": 255,
    "SAWI-HIJAU": 269,
    "TERONG": 266,
    "BUNCIS": 255,
    "TAUGE": 527,
    "DAUN-KETELA-POHON": 269,
    "PAKCOY": 269,
    "KUBIS": 260,
    "KOL": 260,
    "MENTIMUN": 265,
    "TIMUN": 265,
    "SAWI-PUTIH": 260,
    "SELADA": 273,
    "WORTEL": 261,
    "BAWANG-MERAH": 276,
    "BAWANG-PUTIH": 267,
    "BAWANG-BOMBAY": 276,
    "BAWANG-MERAH-UKURAN-SEDANG": 276,
    "BAWANG-PUTIH-UKURAN-SEDANG": 267,
    "CABE-MERAH": 278,
    "CABE-RAWIT": 526,
    "CABAI-MERAH-KERITING": 278,
    "CABE-MERAH-BIASA": 278,
    "CABE-HIJAU-BIASA": 278,
    "CABAI-RAWIT-MERAH": 526,
    "CABAI-RAWIT-HIJAU": 526,
    "KACANG-KEDELAI": 313,
    "KACANG-KEDELAI-IMPOR": 313,
    "KACANG-TANAH": 421,
    "KACANG-HIJAU": 658,
    "PISANG": 233,
    "PEPAYA": 247,
    "SEMANGKA": 474,
    "MANGGA": 247,
    "MELON": 246,
    "ANGGUR-MERAH": 243,
    "ANGGUR": 243,
    "TAHU-PUTIH": 156,
    "TAHU-MENTAH-PCS": 156,
    "TEMPE": 309,
    "TEMPE-PCS": 309,
}


def duration_days(number, metric):
    mult = {"Days": 1, "Weeks": 7, "Months": 30, "Years": 365}
    return int(round(float(number) * mult[metric]))


def build_shelf_life(items):
    fk = {i: r for i, r in enumerate(read_csv(RAW / "foodkeeper_mirror_2019.csv"), 2)}
    rows = []
    slots = (
        ("DOP_Pantry", "suhu_ruang", "tanggal_pembelian"),
        ("DOP_Refrigerate", "kulkas", "tanggal_pembelian"),
        ("DOP_Freeze", "freezer", "tanggal_pembelian"),
        ("Refrigerate", "kulkas", "mulai_disimpan"),
        ("Freeze", "freezer", "mulai_disimpan"),
    )
    for short, line in FK_MAP.items():
        code = "ING-" + short
        if code not in items:
            continue
        record = fk[line]
        for prefix, place, start in slots:
            lo, hi, metric = (record.get(prefix + "_" + s, "") for s in ("Min", "Max", "Metric"))
            if not lo or not hi or metric not in ("Days", "Weeks", "Months", "Years"):
                continue
            low, high = duration_days(lo, metric), duration_days(hi, metric)
            rows.append(
                dict(
                    shelf_life_code=stable("SHF", code, place, start),
                    ingredient_code=code,
                    storage_location=place,
                    min_days=low,
                    max_days=high,
                    warning_days=min(14, max(1, round(low * 0.1))),
                    starting_event=start,
                    source="USDA FoodKeeper (mirror arsip)",
                    source_record_id=f"mirror-line-{line}",
                    source_url=FK_URL,
                    source_recorded_at="",
                    source_license="USDA public domain; mirror terpisah",
                    source_duration=f"{lo}-{hi} {metric}",
                    days_conversion_method="1 minggu=7 hari; 1 bulan=30 hari; 1 tahun=365 hari",
                    shelf_life_status="referensi_perlu_verifikasi_lokal",
                    mapping_note=f"{items[code]['name']} dipadankan dengan {record['Name']} {record['Name_subtitle']}".strip(),
                )
            )
    return rows


def build_aliases(items, price_aliases, bpn):
    rows = []
    seen = set()
    for a in price_aliases:
        key = (a["source"], a["raw_name"].casefold())
        if key not in seen:
            rows.append(a)
            seen.add(key)
    for r in bpn.values():
        a = dict(
            source="Badan Pangan Nasional - Komposisi Pangan Segar Indonesia",
            raw_name=r["raw_name"],
            ingredient_code="ING-" + slug(r["raw_name"]),
        )
        key = (a["source"], a["raw_name"].casefold())
        if key not in seen:
            rows.append(a)
            seen.add(key)
    for x in items.values():
        a = dict(
            source="Nama katalog TAKARKUY", raw_name=x["name"], ingredient_code=x["ingredient_code"]
        )
        key = (a["source"], a["raw_name"].casefold())
        if key not in seen:
            rows.append(a)
            seen.add(key)
    # Familiar recipe spellings are mapped only when their meaning is clear.
    extra = {
        "bayam hijau": "ING-BAYAM",
        "tofu putih": "ING-TAHU-PUTIH",
        "cabe rawit merah": "ING-CABAI-RAWIT-MERAH",
        "cabai rawit merah": "ING-CABAI-RAWIT-MERAH",
        "bawang bombai": "ING-BAWANG-BOMBAY",
        "kol": "ING-KUBIS",
        "timun": "ING-MENTIMUN",
        "ayam broiler": "ING-DAGING-AYAM-BROILER",
        "telur ayam ras": "ING-TELUR-AYAM-BROILER",
        "beras putih": "ING-BERAS",
        "tauge": "ING-TAUGE",
        "toge": "ING-TAUGE",
    }
    for raw, code in extra.items():
        rows.append(
            dict(source="Kaggle - aturan kurasi TAKARKUY", raw_name=raw, ingredient_code=code)
        )
    for i, r in enumerate(rows):
        r["alias_code"] = stable("ALS", r["source"], r["raw_name"])
        r["mapping_status"] = (
            "reviewed" if r["source"] != "Kaggle - aturan kurasi TAKARKUY" else "manual_curated"
        )
    return rows


def build_conversions(items, usda):
    rows = []
    for code in sorted(items):
        for unit, grams in (("g", 1), ("kg", 1000), ("ons", 100)):
            src_url = (
                "https://repositori.kemendikdasmen.go.id/19098/1/6.%20%20Matematika_IV%20SD.pdf"
                if unit == "ons"
                else "https://www.bipm.org/en/measurement-units"
            )
            rows.append(
                dict(
                    conversion_code=stable("CNV", code, unit),
                    ingredient_code=code,
                    unit=unit,
                    gram_equivalent=grams,
                    source="Buku Matematika Kemendikdasmen" if unit == "ons" else "SI",
                    source_url=src_url,
                    conversion_status="standard",
                    note="Konversi massa; ons Indonesia = 100 g",
                )
            )
    for code in (
        "ING-TELUR-AYAM",
        "ING-TELUR-AYAM-BROILER",
        "ING-TELUR-AYAM-KAMPUNG",
        "ING-TELUR-AYAM-RAS-SEGAR",
    ):
        if code in items:
            rows.append(
                dict(
                    conversion_code=stable("CNV", code, "butir"),
                    ingredient_code=code,
                    unit="butir",
                    gram_equivalent=50,
                    source="USDA SR Legacy; telur ukuran large",
                    source_url="https://fdc.nal.usda.gov/food-details/171287/nutrients",
                    conversion_status="size_specific",
                    note="50 g bagian yang dimakan per butir large; ukuran lain berbeda",
                )
            )
    if "ING-BAWANG-PUTIH" in items:
        rows.append(
            dict(
                conversion_code=stable("CNV", "ING-BAWANG-PUTIH", "siung"),
                ingredient_code="ING-BAWANG-PUTIH",
                unit="siung",
                gram_equivalent=3,
                source="USDA SR Legacy; garlic clove",
                source_url="https://fdc.nal.usda.gov/food-details/169230/nutrients",
                conversion_status="size_specific",
                note="Siung ukuran USDA; perlu timbang bila akurasi penting",
            )
        )
    # A pack or bunch has no universal mass. Explicit empty rows ensure the
    # parser blocks it until the exact SKU has a measured package weight.
    for code, unit in [
        ("ING-BAYAM", "ikat"),
        ("ING-KANGKUNG", "ikat"),
        ("ING-TAHU-PUTIH", "pack"),
        ("ING-TEMPE", "pack"),
    ]:
        rows.append(
            dict(
                conversion_code=stable("CNV", code, unit),
                ingredient_code=code,
                unit=unit,
                gram_equivalent="",
                source="Perlu kemasan/penimbangan lokal",
                source_url="",
                conversion_status="unusable",
                note="Jangan hitung otomatis sebelum bobot SKU atau ikat terukur",
            )
        )
    return rows


FIELDS = {
    "processed/ingredients.csv": "ingredient_code name category base_unit calories_per_100g protein_per_100g carbs_per_100g fat_per_100g nutrition_source nutrition_source_id nutrition_verified calories_method nutrition_source_url",
    "processed/ingredient_prices.csv": "price_code ingredient_code price_rupiah quantity unit region recorded_at source source_url source_recorded_at source_license source_commodity_name price_status",
    "processed/ingredient_shelf_life.csv": "shelf_life_code ingredient_code storage_location min_days max_days warning_days starting_event source source_record_id source_url source_recorded_at source_license source_duration days_conversion_method shelf_life_status mapping_note",
    "processed/recipes.csv": "recipe_code name base_servings meal_type instructions is_plannable missing_data_reason source source_url raw_ingredients is_active",
    "processed/recipe_ingredients.csv": "recipe_ingredient_code recipe_code ingredient_code quantity unit is_optional quantity_status raw_text source",
    "processed/recipe_tags.csv": "recipe_tag_code recipe_code tag source",
    "mapping/ingredient_aliases.csv": "alias_code source raw_name ingredient_code mapping_status",
    "mapping/unit_conversions.csv": "conversion_code ingredient_code unit gram_equivalent source source_url conversion_status note",
}
MODEL = {
    "processed/ingredients.csv": "catalog.ingredient",
    "processed/ingredient_prices.csv": "catalog.ingredientprice",
    "processed/ingredient_shelf_life.csv": "catalog.ingredientshelflife",
    "processed/recipes.csv": "catalog.recipe",
    "processed/recipe_ingredients.csv": "catalog.recipeingredient",
    "processed/recipe_tags.csv": "catalog.recipetag",
    "mapping/ingredient_aliases.csv": "catalog.ingredientalias",
    "mapping/unit_conversions.csv": "catalog.unitconversion",
}
PK = {
    "processed/ingredients.csv": "ingredient_code",
    "processed/ingredient_prices.csv": "price_code",
    "processed/ingredient_shelf_life.csv": "shelf_life_code",
    "processed/recipes.csv": "recipe_code",
    "processed/recipe_ingredients.csv": "recipe_ingredient_code",
    "processed/recipe_tags.csv": "recipe_tag_code",
    "mapping/ingredient_aliases.csv": "alias_code",
    "mapping/unit_conversions.csv": "conversion_code",
}


def build_all():
    items, prices, price_aliases, bpn, usda = build_ingredients_prices()
    recipes, links, tags, estimates = build_recipes(items, prices)
    datasets = {
        "processed/ingredients.csv": list(items.values()),
        "processed/ingredient_prices.csv": prices,
        "processed/ingredient_shelf_life.csv": build_shelf_life(items),
        "processed/recipes.csv": recipes,
        "processed/recipe_ingredients.csv": links,
        "processed/recipe_tags.csv": tags,
        "mapping/ingredient_aliases.csv": build_aliases(items, price_aliases, bpn),
        "mapping/unit_conversions.csv": build_conversions(items, usda),
    }
    datasets = {
        rel: unique_rows([clean_text_fields(row) for row in rows], PK[rel])
        for rel, rows in datasets.items()
    }
    fixture = []
    numeric_null = {
        "calories_per_100g",
        "protein_per_100g",
        "carbs_per_100g",
        "fat_per_100g",
        "quantity",
        "base_servings",
        "gram_equivalent",
    }
    for rel, rows in datasets.items():
        fields = FIELDS[rel].split()
        write_csv(ROOT / rel, rows, fields)
        pk = PK[rel]
        for row in rows:
            data = {}
            for k, v in row.items():
                if k == pk or k not in fields:
                    continue
                field = (
                    "ingredient"
                    if k == "ingredient_code"
                    else "recipe"
                    if k == "recipe_code"
                    else k
                )
                data[field] = (
                    None if v == "" and (k in numeric_null or k == "source_recorded_at") else v
                )
            for k in ("is_plannable", "is_active", "is_optional", "nutrition_verified"):
                if k in data:
                    data[k] = data[k] == "true"
            fixture.append(dict(model=MODEL[rel], pk=row[pk], fields=data))
    FIX.mkdir(exist_ok=True)
    fixture_text = json.dumps(fixture, ensure_ascii=False, indent=2)
    (FIX / "catalog_seed.json").write_text(fixture_text, encoding="utf-8")
    app_fixtures = ROOT.parent / "apps/catalog/fixtures"
    app_fixtures.mkdir(parents=True, exist_ok=True)
    (app_fixtures / "catalog_seed.json").write_text(fixture_text, encoding="utf-8")
    counts = {rel: len(rows) for rel, rows in datasets.items()}
    counts["plannable_recipes"] = sum(r["is_plannable"] == "true" for r in recipes)
    counts["priced_plannable_ingredients"] = len({link["ingredient_code"] for link in links})
    counts["estimated_plannable_recipes"] = sum(
        r["is_plannable"] == "true"
        and any(
            link["recipe_code"] == r["recipe_code"] and link["quantity_status"] == "estimated"
            for link in links
        )
        for r in recipes
    )
    nutrient_complete = sum(
        all(row[n + "_per_100g"] not in ("", None) for n in NUTRIENTS) for row in items.values()
    )
    counts["ingredients_with_four_macros"] = nutrient_complete
    audit = [
        dict(
            recipe_code=r["recipe_code"],
            name=r["name"],
            source=r["source"],
            is_plannable=r["is_plannable"],
            base_servings=r["base_servings"],
            quantity_status="estimated"
            if any(
                link["recipe_code"] == r["recipe_code"] and link["quantity_status"] == "estimated"
                for link in links
            )
            else "curated",
            missing_data_reason=r["missing_data_reason"],
        )
        for r in recipes
    ]
    write_csv(
        OUT / "recipe_readiness.csv",
        audit,
        "recipe_code name source is_plannable base_servings quantity_status missing_data_reason".split(),
    )
    write_csv(
        OUT / "recipe_estimated_nutrition.csv",
        estimates,
        "recipe_code region price_date cost_total_rupiah cost_per_serving_rupiah calories_per_serving protein_per_serving_g carbs_per_serving_g fat_per_serving_g calculation_status".split(),
    )
    (ROOT / "dataset_counts.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return counts, estimates


if __name__ == "__main__":
    counts, estimates = build_all()
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print("Contoh estimasi resep:", estimates[0])
