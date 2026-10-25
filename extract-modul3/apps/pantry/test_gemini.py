"""Provider failures must leave OCR drafts and manual entry usable."""

import io
import json
import os
from unittest.mock import patch
from urllib.error import URLError

from django.test import SimpleTestCase

from .gemini_transport import DEFAULT_MODEL, GeminiUnavailable, generate_json
from .recommendations import _gemini_choices


@patch.dict(
    os.environ,
    {
        "PANTRY_LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "test-key",
        "PANTRY_LLM_MODEL": "",
    },
)
@patch("apps.pantry.recommendations.generate_json", new=generate_json)
class GeminiTransportTests(SimpleTestCase):
    @patch("apps.pantry.gemini_transport.urlopen")
    def test_empty_model_uses_shared_default_and_header_key(self, urlopen):
        response = {"candidates": [{"content": {"parts": [{"text": '{"0": null}'}]}}]}
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        self.assertEqual(_gemini_choices([]), {})
        request = urlopen.call_args.args[0]
        self.assertIn(f"/{DEFAULT_MODEL}:generateContent", request.full_url)
        self.assertNotIn("test-key", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")

    @patch("apps.pantry.gemini_transport.urlopen")
    def test_malformed_envelopes_fail_without_uncaught_type_errors(self, urlopen):
        for response in (
            None,
            [],
            {},
            {"candidates": None},
            {"candidates": [None]},
            {"candidates": [{"content": {"parts": None}}]},
        ):
            with self.subTest(response=response):
                urlopen.return_value.__enter__.return_value = io.BytesIO(
                    json.dumps(response).encode()
                )
                with self.assertRaises(GeminiUnavailable):
                    generate_json([{"text": "Test"}], timeout=5)

    @patch("apps.pantry.gemini_transport.urlopen")
    def test_text_parts_are_combined_without_thinking_content(self, urlopen):
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Not JSON", "thought": True},
                            {"text": '{"items":'},
                            {"text": "[]}"},
                        ]
                    }
                }
            ]
        }
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        self.assertEqual(generate_json([{"text": "Test"}], timeout=5), {"items": []})

    @patch(
        "apps.pantry.gemini_transport.urlopen", side_effect=URLError("private provider response")
    )
    def test_provider_failure_returns_no_suggestions(self, urlopen):
        self.assertEqual(_gemini_choices([]), {})
        with self.assertRaises(GeminiUnavailable) as caught:
            generate_json([{"text": "Test"}], timeout=5)
        self.assertNotIn("private provider response", str(caught.exception))

    @patch("apps.pantry.gemini_transport.urlopen")
    def test_invalid_model_does_not_send_request(self, urlopen):
        with patch.dict(os.environ, {"PANTRY_LLM_MODEL": "../../invalid"}):
            with self.assertRaises(GeminiUnavailable):
                generate_json([{"text": "Test"}], timeout=5)
        urlopen.assert_not_called()

    @patch("apps.pantry.gemini_transport.urlopen")
    def test_deep_envelope_or_answer_becomes_provider_error(self, urlopen):
        nested = "[" * 1200 + "0" + "]" * 1200
        envelope = json.dumps({"candidates": [{"content": {"parts": [{"text": nested}]}}]})
        for raw in (nested, envelope):
            urlopen.return_value.__enter__.return_value = io.BytesIO(raw.encode())
            with self.assertRaises(GeminiUnavailable):
                generate_json([], timeout=1)
