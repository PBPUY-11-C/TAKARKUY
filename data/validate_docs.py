#!/usr/bin/env python3
"""Catch stale catalog counts in the three user-facing dataset documents."""

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
    for path in (ROOT / "README.md", ROOT / "DATASETS.md"):
        content = path.read_text(encoding="utf-8")
        for relative, expected in counts.items():
            if not relative.endswith(".csv"):
                continue
            pattern = rf"\| `{re.escape(relative)}` \| ([\d.]+) \|"
            match = re.search(pattern, content)
            assert match and int(match[1].replace(".", "")) == expected, (
                path.name,
                relative,
                expected,
            )
        assert f"{fixture_count:,}".replace(",", ".") + " objek" in content.replace("**", ""), path
        assert f"{counts['plannable_recipes']} siap dihitung" in content.replace("**", ""), path
        assert "SOURCE_REVIEW.md" in content and "Mendeley" in content
        assert f"{mendeley_count} Mendeley" in content.replace("**", ""), path
    main = (ROOT.parent / "README.md").read_text(encoding="utf-8")
    summary = (
        f"{counts['processed/ingredients.csv']} bahan, "
        f"{counts['processed/ingredient_prices.csv']} catatan harga, dan "
        f"{counts['processed/recipes.csv']} resep; {counts['plannable_recipes']} resep siap dihitung"
    )
    assert summary in main, "README utama: ringkasan katalog tertinggal"
    assert f"{fixture_count:,}".replace(",", ".") + " objek" in main.replace("**", "")
    assert f"Sebanyak {mendeley_count} resep Mendeley" in main
    print(
        "VALID: hitungan katalog dan fixture sinkron pada README utama, data/README.md, dan DATASETS.md"
    )


if __name__ == "__main__":
    validate_documents()
