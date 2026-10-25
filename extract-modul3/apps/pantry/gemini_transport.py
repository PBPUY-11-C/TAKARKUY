"""Shared Gemini JSON transport; credentials remain on the server."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_usage import GeminiResult

DEFAULT_MODEL = "gemini-2.5-flash-lite"


class GeminiUnavailable(Exception):
    """An optional Gemini request could not return a usable JSON object."""


def gemini_ready():
    return os.getenv("PANTRY_LLM_PROVIDER", "").strip().lower() == "gemini" and bool(
        os.getenv("GEMINI_API_KEY", "").strip()
    )


def generate_json(parts, *, timeout, generation_config=None):
    if not gemini_ready():
        raise GeminiUnavailable("Gemini is not configured")
    model = os.getenv("PANTRY_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
        raise GeminiUnavailable("Invalid Gemini model")
    config = {"responseMimeType": "application/json", "temperature": 0}
    if model in {"gemini-2.5-flash", "gemini-2.5-flash-lite"}:
        config["thinkingConfig"] = {"thinkingBudget": 0}
    config.update(generation_config or {})
    body = json.dumps(
        {
            "contents": [{"parts": parts}],
            "generationConfig": config,
        }
    ).encode("utf-8")
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": os.environ["GEMINI_API_KEY"].strip(),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("Response too large")
            result = json.loads(raw)
        answer_parts = result["candidates"][0]["content"]["parts"]
        answer = "".join(
            part["text"]
            for part in answer_parts
            if isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and not part.get("thought")
        )
        payload = json.loads(answer)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return GeminiResult(payload, result.get("usageMetadata"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        RecursionError,
        KeyError,
        IndexError,
        TypeError,
        OSError,
    ) as exc:
        # Do not expose HTTP response bodies, receipt text, or credentials.
        raise GeminiUnavailable("Gemini JSON request failed") from exc


if __name__ == "__main__":
    import sys

    try:
        data = json.loads(sys.stdin.buffer.read(15000000))
        result = generate_json(
            data["parts"], timeout=data["timeout"], generation_config=data.get("config")
        )
        sys.stdout.write(
            json.dumps({"_pantry_transport_v": 1, "payload": result, "usage": result.usage})
        )
    except Exception:
        # Never print upstream bodies, keys, or receipt data.
        sys.exit(1)
