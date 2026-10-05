"""Stable catalogue identity shared by photo and text name resolution."""

import hashlib
import json
import re
from collections import Counter

from apps.catalog.models import Ingredient


def normalize_name(value):
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold())) if isinstance(value, str) else ""


def everyday_ingredient_name(name):
    if name.startswith("Beras Kualitas ") or name in {
        "Beras Termahal",
        "Beras Termurah (Non Bulog)",
    }:
        return "Beras"
    if name.startswith("Daging Sapi, Lokal, "):
        return "Daging Sapi " + name.removeprefix("Daging Sapi, Lokal, ")
    if name in {"Daging Ayam Broiler", "Daging Ayam Ras Segar"}:
        return "Daging Ayam"
    if name in {"Telur Ayam Broiler", "Telur Ayam Ras Segar"}:
        return "Telur Ayam"
    if name.startswith("Gula Pasir "):
        return "Gula Pasir"
    if name.startswith("Minyak Goreng ") and ("Kemasan" in name or name.endswith("Curah")):
        return "Minyak Goreng"
    if name.startswith("Susu Bubuk "):
        return "Susu Bubuk"
    if name.startswith("Susu Kental Manis Merk "):
        return "Susu Kental Manis"
    if name.startswith("Tepung Terigu Cap ") or name == "Tepung Terigu Curah":
        return "Tepung Terigu"
    return {"Tahu Mentah / pcs": "Tahu", "Tempe / pcs": "Tempe"}.get(name, name)


def catalog_snapshot():
    rows = list(
        Ingredient.objects.order_by("ingredient_code").values_list("ingredient_code", "name")
    )
    version = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()
    counts = Counter(everyday_ingredient_name(name) for _, name in rows)
    # Do not send indistinguishable labels for distinct catalogue IDs.
    prompt = "\n".join(
        f"{code}|{everyday_ingredient_name(name) if counts[everyday_ingredient_name(name)] == 1 else name}"
        for code, name in rows
    )
    return {"version": version, "names": dict(rows), "prompt": prompt}
