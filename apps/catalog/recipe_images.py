"""Curated recipe photos and their attribution metadata."""

import csv
from functools import lru_cache
from pathlib import Path


MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "mapping" / "recipe_image_mapping.csv"


@lru_cache(maxsize=4)
def _read_recipe_image_index(modified_ns, file_size):
    """Cache the mapping until its CSV file changes."""
    try:
        with MAPPING_PATH.open(encoding="utf-8-sig", newline="") as source:
            return {
                row["recipe_code"]: row
                for row in csv.DictReader(source)
                if row.get("recipe_code") and row.get("image_url")
            }
    except FileNotFoundError:
        return {}


def recipe_image_index():
    try:
        stat = MAPPING_PATH.stat()
    except FileNotFoundError:
        return {}
    return _read_recipe_image_index(stat.st_mtime_ns, stat.st_size)


def recipe_image_for(recipe_code):
    return recipe_image_index().get(recipe_code)

