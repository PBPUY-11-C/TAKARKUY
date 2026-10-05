import json
from unittest.mock import patch

from django.test import SimpleTestCase

from .ai_usage import collect_usage, safe_usage
from .gemini import GeminiUnavailable, generate_json


@patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "private-key"})
class UsageTests(SimpleTestCase):
    @patch("apps.pantry.gemini.subprocess.Popen")
    def test_transport_metadata_reaches_collector_without_content(self, popen):
        child = popen.return_value
        child.returncode = 0
        child.poll.return_value = 0
        child.communicate.return_value = (
            json.dumps(
                {
                    "_pantry_transport_v": 1,
                    "payload": {"items": []},
                    "usage": {
                        "promptTokenCount": 321,
                        "totalTokenCount": 400,
                        "cachedContentTokenCount": 100,
                        "receipt": "PRIVATE",
                        "thoughtsTokenCount": True,
                    },
                }
            ).encode(),
            None,
        )
        with (
            collect_usage() as calls,
            self.assertLogs("apps.pantry.ai_usage", level="INFO") as logs,
        ):
            response = generate_json([{"inlineData": {"data": "PRIVATE PHOTO"}}], timeout=1)
        self.assertEqual(response, {"items": []})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["task"], "photo")
        self.assertEqual(
            calls[0]["tokens"],
            {"promptTokenCount": 321, "totalTokenCount": 400, "cachedContentTokenCount": 100},
        )
        self.assertNotIn("PRIVATE", str(logs.output))
        self.assertNotIn("private-key", str(logs.output))

    @patch("apps.pantry.gemini.subprocess.Popen", side_effect=OSError("PRIVATE"))
    def test_failed_attempt_has_unknown_tokens_not_a_fake_zero(self, popen):
        with collect_usage() as calls:
            with self.assertRaises(GeminiUnavailable):
                generate_json([{"text": "PRIVATE"}], timeout=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["status"], "failed")
        self.assertEqual(calls[0]["tokens"], {})
        self.assertEqual(safe_usage({"totalTokenCount": -1, "promptTokenCount": "123"}), {})
