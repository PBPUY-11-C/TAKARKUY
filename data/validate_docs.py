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
    for path in (ROOT / "PIPELINE_DATA.md", ROOT / "DATASETS.md"):
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
    # The root README.md follows the team's own template and is not checked here.
    print(
        "VALID: hitungan katalog dan fixture sinkron pada data/PIPELINE_DATA.md dan data/DATASETS.md"
    )


if __name__ == "__main__":
    validate_documents()
