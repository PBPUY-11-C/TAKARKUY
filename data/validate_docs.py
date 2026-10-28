#!/usr/bin/env python3
"""Check that the catalog counts in DATA_API.md match the build output."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def validate_documents():
    counts = json.loads((ROOT / "dataset_counts.json").read_text(encoding="utf-8"))
    fixture = json.loads((ROOT / "fixtures/catalog_seed.json").read_text(encoding="utf-8"))
    fixture_count = len(fixture)
    mendeley_count = sum(
        row["model"] == "catalog.recipe"
        and str(row["pk"]).startswith("RCP-MDL-")
        and row["fields"].get("is_plannable", False)
        for row in fixture
    )
    path = ROOT.parent / "DATA_API.md"
    content = path.read_text(encoding="utf-8")
    plain = content.replace("**", "")
    for relative, expected in counts.items():
        if not relative.endswith(".csv"):
            continue
        match = re.search(rf"\| `{re.escape(relative)}` \| ([\d.]+) \|", content)
        assert match and int(match[1].replace(".", "")) == expected, (relative, expected)
    assert f"{fixture_count:,}".replace(",", ".") + " objek" in plain, "jumlah objek fixture"
    assert f"{counts['plannable_recipes']} siap dihitung" in plain, "jumlah resep siap dihitung"
    assert f"{mendeley_count} Mendeley" in plain, "jumlah resep Mendeley"
    print("VALID: hitungan katalog dan fixture sinkron dengan DATA_API.md")


if __name__ == "__main__":
    validate_documents()
