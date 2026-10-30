import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from omniscope_integrations import (IntegrationError, integrations_status,
    openai_chat, places_search, people_contacts, request_json)
import test_omniscope as core


class ProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_credentials_reported_without_live_claim(self):
        data = integrations_status()
        self.assertEqual(data["openai"]["status"], "credentials_missing")
        self.assertFalse(data["google_people"]["live_verified"])
        with self.assertRaises(IntegrationError):
            openai_chat("test")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test", "OPENAI_MODEL": "test-model"}, clear=True)
    @patch("omniscope_integrations.request_json")
    def test_openai_parses_messages_and_disables_response_storage(self, call):
        call.return_value = {"status": "completed", "output": [
            {"type": "reasoning"}, {"type": "message", "content": [
                {"type": "output_text", "text": "answer"}]}]}
        self.assertEqual(openai_chat("hi")["answer"], "answer")
        self.assertFalse(call.call_args.kwargs["body"]["store"])
        self.assertEqual(call.call_args.kwargs["body"]["input"], "hi")

    @patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "secret-test"}, clear=True)
    @patch("omniscope_integrations.request_json")
    def test_places_pagination_and_required_field_mask(self, call):
        call.return_value = {"places": [{"id": "example"}], "nextPageToken": "next"}
        data = places_search("plumbers", 5, "page")
        self.assertEqual(data["next_page_token"], "next")
        self.assertEqual(call.call_args.kwargs["body"]["pageToken"], "page")
        self.assertIn("places.attributions", call.call_args.kwargs["headers"]["X-Goog-FieldMask"])

    @patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "secret",
                            "GOOGLE_PEOPLE_REFRESH_TOKEN": "refresh"}, clear=True)
    @patch("omniscope_integrations.request_json")
    def test_people_refreshes_token_and_only_reads_own_connections(self, call):
        call.side_effect = [{"access_token": "access"}, {"connections": [{"resourceName": "people/test"}]}]
        result = people_contacts(1)
        self.assertEqual(len(result["contacts"]), 1)
        self.assertEqual(call.call_args_list[0].kwargs["body"]["grant_type"], "refresh_token")
        self.assertIn("people/me/connections", call.call_args_list[1].args[1])
        self.assertEqual(call.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer access")

    @patch("omniscope_integrations.urllib.request.build_opener")
    def test_upstream_error_does_not_disclose_secrets(self, opener):
        opener.return_value.open.side_effect = urllib.error.HTTPError(
            "https://example.invalid/secret", 403, "secret", {}, io.BytesIO(b"secret"))
        with self.assertRaises(IntegrationError) as caught:
            request_json("openai", "https://api.openai.com/v1/responses")
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(caught.exception.status, 502)


class EndpointTests(unittest.TestCase):
    request = core.CoreTests.request
    @patch.dict(os.environ, {"OMNISCOPE_ACCESS_TOKEN": "test"}, clear=True)
    def test_places_rejects_boolean_page_size(self):
        status, _ = self.request("/api/places/search", "POST", "Bearer test",
                                 json.dumps({"query": "plumbers", "page_size": True}).encode())
        self.assertTrue(status.startswith("400"))

    @patch.dict(os.environ, {"OMNISCOPE_ACCESS_TOKEN": "test"}, clear=True)
    def test_places_requires_credentials(self):
        status, data = self.request("/api/places/search", "POST", "Bearer test", b'{"query":"plumbers"}')
        self.assertTrue(status.startswith("503"))
        self.assertEqual(data["provider"], "google_places")

    @patch.dict(os.environ, {"OMNISCOPE_ACCESS_TOKEN": "test"}, clear=True)
    def test_people_requires_auth(self):
        self.assertTrue(self.request("/api/people/contacts", "POST")[0].startswith("401"))
