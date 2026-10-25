"""Optional Gemini transport with a killable wall-clock deadline."""

import json
import subprocess
import sys
import time
from pathlib import Path

from .ai_usage import GeminiResult, record_call
from .gemini_transport import GeminiUnavailable, gemini_ready


def generate_json(parts, *, timeout, generation_config=None):
    started = time.monotonic()
    deadline = started + timeout
    if not gemini_ready():
        raise GeminiUnavailable("Gemini is not configured")
    request = json.dumps({"parts": parts, "timeout": timeout, "config": generation_config}).encode()
    if len(request) > 15000000:
        raise GeminiUnavailable("Request too large")
    child = None
    status, usage = "failed", {}
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", "apps.pantry.gemini_transport"],
            cwd=Path(__file__).resolve().parents[2],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        output, _ = child.communicate(request, timeout=max(0, deadline - time.monotonic()))
        if child.returncode or len(output) > 262144:
            raise ValueError
        result = json.loads(output)
        if not isinstance(result, dict):
            raise ValueError
        if result.get("_pantry_transport_v") == 1:
            payload = result.get("payload")
            if not isinstance(payload, dict):
                raise ValueError
            result = GeminiResult(payload, result.get("usage"))
        else:
            result = GeminiResult(result)
        status, usage = "ok", result.usage
        return result
    except (OSError, ValueError, RecursionError, subprocess.TimeoutExpired) as exc:
        raise GeminiUnavailable("Gemini JSON request failed") from exc
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()
        record_call(parts, status, round((time.monotonic() - started) * 1000), usage)
