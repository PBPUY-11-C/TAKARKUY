import json
import subprocess
import sys
import time
from unittest.mock import patch

from django.test import SimpleTestCase

from .gemini import GeminiUnavailable, generate_json


@patch.dict("os.environ", {"PANTRY_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"})
class DeadlineTests(SimpleTestCase):
    @patch("apps.pantry.gemini.subprocess.Popen")
    def test_timeout_kills_and_reaps_child_without_sensitive_argv(self, popen):
        child = popen.return_value
        child.communicate.side_effect = [subprocess.TimeoutExpired("transport", 0.1), (b"", b"")]
        child.poll.return_value = None
        with self.assertRaises(GeminiUnavailable):
            generate_json([{"text": "private receipt"}], timeout=0.1)
        child.kill.assert_called_once()
        self.assertEqual(child.communicate.call_count, 2)
        self.assertNotIn("test-key", str(popen.call_args.args))
        self.assertNotIn("private receipt", str(popen.call_args.args))
        self.assertLessEqual(child.communicate.call_args_list[0].kwargs["timeout"], 0.1)

    @patch("apps.pantry.gemini.subprocess.Popen")
    def test_valid_result_does_not_kill_completed_child(self, popen):
        child = popen.return_value
        child.returncode = 0
        child.communicate.return_value = (json.dumps({"items": []}).encode(), None)
        child.poll.return_value = 0
        self.assertEqual(generate_json([], timeout=1), {"items": []})
        child.kill.assert_not_called()

    @patch("apps.pantry.gemini.subprocess.Popen", side_effect=OSError("secret upstream"))
    def test_start_failure_is_sanitized(self, popen):
        with self.assertRaises(GeminiUnavailable) as error:
            generate_json([], timeout=1)
        self.assertNotIn("secret", str(error.exception))

    @patch("apps.pantry.gemini.subprocess.Popen")
    def test_deep_transport_json_becomes_provider_error(self, popen):
        child = popen.return_value
        child.returncode = 0
        child.poll.return_value = 0
        child.communicate.return_value = (("[" * 1200 + "0" + "]" * 1200).encode(), None)
        with self.assertRaises(GeminiUnavailable):
            generate_json([], timeout=1)

    def test_real_stalled_process_is_killed_within_total_deadline(self):
        real_popen = subprocess.Popen
        children = []

        def stalled(command, **kwargs):
            child = real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with patch("apps.pantry.gemini.subprocess.Popen", side_effect=stalled):
            with self.assertRaises(GeminiUnavailable):
                generate_json([], timeout=0.15)
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(children[0].poll())
