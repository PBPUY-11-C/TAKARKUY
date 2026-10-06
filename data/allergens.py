"""Reviewed ID mapping; no runtime guessing from ingredient names."""

import csv
import json
from pathlib import Path

KEYS = {
    "telur",
    "susu",
    "kacang_tanah",
    "kedelai",
    "gluten",
    "ikan",
    "krustasea",
    "moluska",
    "wijen",
    "kacang_pohon",
    "sulfit",
}


def build_allergens(items):
    path = Path(__file__).resolve().parent / "mapping/ingredient_allergens.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    mapping = {row["ingredient_code"]: row for row in rows}
    if len(mapping) != len(rows) or set(mapping) - set(items):
        raise ValueError("Mapping alergen memiliki ID duplikat atau bahan tidak dikenal.")
    output = []
    for code, item in items.items():
        row = mapping.get(
            code,
            {
                "allergens": "[]",
                "allergen_status": "unknown",
                "allergen_source_url": "",
                "allergen_note": "Bahan baru belum ditinjau.",
            },
        )
        values = json.loads(row["allergens"])
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or value not in KEYS for value in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError(f"Kelompok alergen tidak valid: {code}")
        if row["allergen_status"] not in {"reviewed", "unknown"}:
            raise ValueError(f"Status alergen tidak valid: {code}")
        fields = {
            key: row[key]
            for key in ("allergens", "allergen_status", "allergen_source_url", "allergen_note")
        }
        if fields["allergen_status"] == "reviewed" and not fields["allergen_source_url"]:
            raise ValueError(f"Sumber review belum diisi: {code}")
        item.update(fields)
        output.append({"ingredient_code": code, "name": item["name"], **fields})
    return output
