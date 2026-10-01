"""Conservative catalogue matching and storage suggestions for receipt items."""

import json
import re
from difflib import SequenceMatcher

from django.db.models import Count

from apps.catalog.models import Ingredient, IngredientAlias, IngredientShelfLife

from .gemini import GeminiUnavailable, gemini_ready, generate_json
from .models import PantryNameCorrection


def normalize_name(value):
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def everyday_ingredient_name(name):
    """Use a familiar pantry label without changing the matched catalogue item."""
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


def _catalog_entries():
    entries = {}
    for ingredient in Ingredient.objects.all().only("ingredient_code", "name"):
        entries.setdefault(normalize_name(ingredient.name), set()).add(ingredient.ingredient_code)
    for alias in IngredientAlias.objects.filter(
        mapping_status__in=["reviewed", "manual_curated"]
    ).only("raw_name", "ingredient_id"):
        entries.setdefault(normalize_name(alias.raw_name), set()).add(alias.ingredient_id)
    return entries


def exact_ingredient_code(name):
    codes = _catalog_entries().get(normalize_name(name), set())
    return next(iter(codes)) if len(codes) == 1 else None


def _candidates(name, entries):
    scored = {}
    for alias, codes in entries.items():
        if not alias:
            continue
        score = SequenceMatcher(None, name, alias).ratio()
        if score < 0.55:
            continue
        for code in codes:
            scored[code] = max(scored.get(code, 0), score)
    return sorted(scored, key=lambda code: (-scored[code], code))[:5], scored


def _gemini_choices(pending):
    if not gemini_ready():
        return {}
    prompt = (
        "Cocokkan nama barang OCR bahasa Indonesia dengan kandidat katalog. "
        "Utamakan konsep bahan sehari-hari; abaikan merek, ukuran kemasan, dan label harga/kualitas "
        "bila tidak diperlukan untuk mengenali jenis bahannya. Jangan samakan jenis yang berbeda. "
        "Pilih HANYA ingredient_code yang diberikan, atau null jika tidak yakin, "
        "barang bukan bahan makanan, atau merek/jenis produk berbeda. "
        "Jangan tebak lokasi atau masa simpan. Balas JSON object dengan key berupa indeks string "
        "dan value ingredient_code atau null.\n" + json.dumps(pending, ensure_ascii=False)
    )
    try:
        return generate_json(
            [{"text": prompt}], timeout=5, generation_config={"maxOutputTokens": 1000}
        )
    except GeminiUnavailable:
        return {}


def _storage(ingredient_code):
    records = list(IngredientShelfLife.objects.filter(ingredient_id=ingredient_code))
    usable = [record for record in records if record.storage_location in {"kulkas", "suhu_ruang"}]
    if not usable:
        return None
    # Recommend refrigeration when both room-temperature and refrigerated guidance exists.
    record = min(usable, key=lambda row: (row.storage_location != "kulkas", row.min_days))
    return {
        "location": "chiller" if record.storage_location == "kulkas" else "suhu_ruang",
        "min_days": record.min_days,
        "max_days": record.max_days,
        "starting_event": record.starting_event,
        "source": record.source,
        "source_url": record.source_url,
        "status": record.shelf_life_status,
    }


def resolve_names(names, session_id, *, allow_llm=True):
    entries = _catalog_entries()
    learned = {
        correction.normalized_name: correction.ingredient_id
        for correction in PantryNameCorrection.objects.filter(session_id=session_id)
    }
    normalized_names = {normalize_name(name) for name in names}
    community = {}
    votes = (
        PantryNameCorrection.objects.filter(normalized_name__in=normalized_names)
        .values("normalized_name", "ingredient_id")
        .annotate(sessions=Count("session_id", distinct=True))
    )
    for vote in votes:
        community.setdefault(vote["normalized_name"], []).append(vote)
    codes = {}
    methods = {}
    pending = {}
    for index, raw in enumerate(names):
        normalized = normalize_name(raw)
        if not normalized:
            continue
        if normalized in learned:
            codes[index], methods[index] = learned[normalized], "koreksi_anda"
            continue
        exact = entries.get(normalized, set())
        if len(exact) == 1:
            codes[index], methods[index] = next(iter(exact)), "katalog"
            continue
        votes_for_name = community.get(normalized, [])
        if len(votes_for_name) == 1 and votes_for_name[0]["sessions"] >= 5:
            codes[index], methods[index] = votes_for_name[0]["ingredient_id"], "koreksi_bersama"
            continue
        candidates, scores = _candidates(normalized, entries)
        if (
            candidates
            and scores[candidates[0]] >= 0.90
            and (len(candidates) == 1 or scores[candidates[0]] - scores[candidates[1]] >= 0.12)
        ):
            codes[index], methods[index] = candidates[0], "ejaan_mirip"
        elif candidates:
            pending[index] = candidates

    llm_attempted = allow_llm and bool(pending) and gemini_ready()
    if llm_attempted:
        candidate_codes = {code for choices in pending.values() for code in choices}
        ingredients = Ingredient.objects.in_bulk(candidate_codes)
        prompts = [
            {
                "index": str(index),
                "ocr": names[index],
                "candidates": [
                    {
                        "ingredient_code": code,
                        "name": ingredients[code].name,
                        "nama_sehari_hari": everyday_ingredient_name(ingredients[code].name),
                    }
                    for code in choices
                    if code in ingredients
                ],
            }
            for index, choices in list(pending.items())[:8]
        ]
        llm_choices = _gemini_choices(prompts)
        for index, candidates in pending.items():
            choice = llm_choices.get(str(index))
            if choice in candidates:
                codes[index], methods[index] = choice, "ai_perlu_periksa"

    ingredients = Ingredient.objects.in_bulk(set(codes.values()))
    results = []
    for index, raw in enumerate(names):
        ingredient = ingredients.get(codes.get(index))
        results.append(
            {
                "raw_name": raw,
                "ingredient_code": ingredient.ingredient_code if ingredient else None,
                "suggested_name": everyday_ingredient_name(ingredient.name) if ingredient else None,
                "method": methods.get(index, "tidak_cocok"),
                "storage": _storage(ingredient.ingredient_code) if ingredient else None,
            }
        )
    return results, llm_attempted
