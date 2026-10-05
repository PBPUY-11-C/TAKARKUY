import json
from datetime import date
from decimal import Decimal

from apps.catalog.content_policy import protect_plan_instructions


def encode_value(value):
    if isinstance(value, Decimal):
        return {"_decimal": str(value)}
    if isinstance(value, date):
        return {"_date": value.isoformat()}
    raise TypeError(f"Unsupported planner result type: {type(value).__name__}")


def decode_value(value):
    if set(value) == {"_decimal"}:
        return Decimal(value["_decimal"])
    if set(value) == {"_date"}:
        return date.fromisoformat(value["_date"])
    return value


def freeze(result):
    return json.loads(json.dumps(result, default=encode_value))


def thaw(snapshot):
    return protect_plan_instructions(json.loads(json.dumps(snapshot), object_hook=decode_value))
