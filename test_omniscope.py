import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from omniscope_brain import Brain
from omniscope_service import app


class CoreTests(unittest.TestCase):
    def request(self, path, method="GET", auth="", body=b"{}"):
        status = []
        data = app({"PATH_INFO": path, "REQUEST_METHOD": method,
                    "HTTP_AUTHORIZATION": auth, "CONTENT_LENGTH": str(len(body)),
                    "wsgi.input": io.BytesIO(body)}, lambda s, h: status.append(s))
        return status[0], json.loads(b"".join(data))

    def test_status_does_not_claim_unconnected_tools(self):
        status, data = self.request("/healthz")
        self.assertEqual(status, "200 OK")
        self.assertFalse(data["gps"])
        self.assertFalse(data["code_execution"])

    @patch.dict(os.environ, {}, clear=True)
    def test_chat_disabled_without_auth_configuration(self):
        self.assertTrue(self.request("/api/chat", "POST")[0].startswith("503"))

    @patch.dict(os.environ, {"OMNISCOPE_ACCESS_TOKEN": "test"}, clear=True)
    def test_rejects_wrong_token(self):
        self.assertTrue(self.request("/api/chat", "POST", "Bearer bad")[0].startswith("401"))

    @patch.dict(os.environ, {"OMNISCOPE_ACCESS_TOKEN": "test", "OMNISCOPE_MODEL": "test"}, clear=True)
    def test_invalid_json(self):
        self.assertTrue(self.request("/api/chat", "POST", "Bearer test", b"[")[0].startswith("400"))

    def test_failed_provider_call_preserves_history(self):
        brain = Brain("test")
        brain.http = MagicMock()
        brain.http.open.side_effect = TimeoutError
        with self.assertRaises(TimeoutError):
            brain.ask("hello")
        self.assertEqual(brain.history, [])

    def test_successful_provider_call_commits_history(self):
        brain = Brain("test")
        brain.http = MagicMock()
        brain.http.open.return_value.__enter__.return_value = io.BytesIO(
            b'{"done":true,"message":{"content":"hello"}}')
        self.assertEqual(brain.ask("hi"), "hello")
        self.assertEqual(len(brain.history), 2)


if __name__ == "__main__":
    unittest.main()
