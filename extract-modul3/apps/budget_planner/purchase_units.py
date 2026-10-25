"""Conservative whole-fruit shopping quotes over the local per-kg price snapshot."""

import json
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parents[2] / "data/mapping/fruit_purchase_units.json"


def load_fruit_rules():
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules = {}
    for row in payload["rules"]:
        gross = Decimal(str(row["gross_grams_per_unit"]))
        fraction = Decimal(str(row["edible_fraction"]))
        if gross <= 0 or not 0 < fraction <= 1:
            raise ValueError("Aturan pembelian buah tidak valid.")
        rules[row["ingredient_code"]] = {
            "unit": row["purchase_unit"],
            "gross_grams": gross,
            "edible_grams": gross * fraction,
            "source": payload["source"],
            "source_url": payload["source_url"],
            "source_detail": row["source_detail"],
        }
    return rules


def whole_fruit_quote(required_edible_grams, price_per_kg, rule):
    """Quote all selected servings together, retaining whole-fruit leftovers."""
    required = Decimal(str(required_edible_grams))
    if required <= 0:
        return {
            "units": 0,
            "gross_grams": Decimal(0),
            "leftover_edible_grams": Decimal(0),
            "cost": 0,
        }
    units = int((required / rule["edible_grams"]).to_integral_value(rounding=ROUND_CEILING))
    gross = units * rule["gross_grams"]
    # The catalog publishes a per-kg market price, not a per-piece checkout price.
    # Keep the estimate conservative by rounding the derived purchase cost up.
    cost = int(
        (gross * Decimal(str(price_per_kg)) / Decimal(1000) / Decimal(100)).to_integral_value(
            rounding=ROUND_CEILING
        )
        * 100
    )
    return {
        "units": units,
        "gross_grams": gross,
        "leftover_edible_grams": units * rule["edible_grams"] - required,
        "cost": cost,
    }
