"""Membatasi kedalaman JSON selain ukurannya; error parsing tidak boleh berujung HTML 500."""

import json
import math


def _reject_constant(value):
    """Menolak konstanta NaN/Infinity saat json.loads dengan ValueError."""
    raise ValueError("Non-finite JSON constant")


def load_payload(raw):
    """Mem-parse JSON request; ValueError bila bersarang lebih dari 8 level atau memuat NaN/Inf."""
    try:
        payload = json.loads(raw, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError("JSON too deeply nested") from exc
    pending = [(payload, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 8:
            raise ValueError("JSON too deeply nested")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return payload
