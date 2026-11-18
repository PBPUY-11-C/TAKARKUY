"""Telemetri pemakaian AI per request tanpa isi; tidak pernah mencatat teks atau foto struk."""

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger("apps.pantry.ai_usage")
current = ContextVar("pantry_ai_usage", default=None)
TOKEN_FIELDS = (
    "promptTokenCount",
    "candidatesTokenCount",
    "totalTokenCount",
    "cachedContentTokenCount",
    "thoughtsTokenCount",
)


def safe_usage(usage):
    """Menyaring metadata token Gemini: hanya field dikenal dengan nilai int 0 s.d. 1 miliar."""
    if not isinstance(usage, dict):
        return {}
    return {
        key: usage[key]
        for key in TOKEN_FIELDS
        if type(usage.get(key)) is int and 0 <= usage[key] <= 1000000000
    }


class GeminiResult(dict):
    """Payload JSON dari Gemini berbentuk dict, dengan atribut usage berisi jumlah token."""

    def __init__(self, payload, usage=None):
        """Menyalin payload ke dict dan menyimpan usage yang sudah disaring."""
        super().__init__(payload)
        self.usage = safe_usage(usage)


@contextmanager
def collect_usage():
    """Context manager yang mengumpulkan event panggilan AI selama blok berjalan ke sebuah list."""
    calls = []
    token = current.set(calls)
    try:
        yield calls
    finally:
        current.reset(token)


def record_call(parts, status, milliseconds, usage=None):
    """Mencatat satu panggilan AI (jenis foto/nama, status, durasi, token) ke log dan kolektor.

    Isi prompt tidak ikut dicatat; parts hanya dipakai untuk menentukan jenis tugas.
    """
    event = {
        "task": "photo"
        if any(isinstance(part, dict) and "inlineData" in part for part in parts)
        else "names",
        "status": status,
        "duration_ms": milliseconds,
        "tokens": safe_usage(usage),
    }
    calls = current.get()
    if calls is not None:
        calls.append(event)
    logger.info("pantry_ai_call %s", json.dumps(event))
