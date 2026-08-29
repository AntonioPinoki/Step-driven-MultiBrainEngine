import os
import sys
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient


ENGINE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

import server


def snapshot(chat_id, text, character="Alice", generation_type="normal"):
    return {
        "schema_version": 1,
        "source": "sillytavern-brainengine-connector",
        "generation": {"type": generation_type},
        "chat": {
            "id": chat_id,
            "last_message": {"role": "user", "text": text},
        },
        "character": {"name": character, "card": {}},
        "user": {"name": "User"},
        "_received_monotonic": time.monotonic(),
    }


class ConnectorBindingTests(unittest.TestCase):
    def setUp(self):
        server.PENDING_SILLYTAVERN_CONTEXTS.clear()

    def tearDown(self):
        server.PENDING_SILLYTAVERN_CONTEXTS.clear()

    def test_new_preset_defaults_have_four_steps_at_temperature_point_eight(self):
        steps = server.DEFAULT_REASONING_STEPS

        self.assertEqual([1, 2, 3, 4], [item["step"] for item in steps])
        self.assertNotIn("dmn", [item["id"] for item in steps])
        self.assertEqual([0.8, 0.8, 0.8, 0.8], [item["temperature"] for item in steps])
        self.assertNotIn("schedule", steps[-1]["prompt"].lower())

    def test_only_matching_snapshot_is_claimed(self):
        server.PENDING_SILLYTAVERN_CONTEXTS.extend([
            snapshot("chat-a", "Alpha", "Alice", "continue"),
            snapshot("chat-b", "Beta", "Bob"),
        ])

        binding = server.claim_sillytavern_role_binding(
            [{"role": "user", "content": "Alpha"}], {})

        self.assertEqual("Alice", binding["char_name"])
        self.assertEqual("continue", binding["generation_type"])
        self.assertEqual(
            ["chat-b"],
            [item["chat"]["id"] for item in server.PENDING_SILLYTAVERN_CONTEXTS],
        )

    def test_ambiguous_message_match_is_not_claimed(self):
        server.PENDING_SILLYTAVERN_CONTEXTS.extend([
            snapshot("chat-a", "Same", "Alice"),
            snapshot("chat-b", "Same", "Bob"),
        ])

        binding = server.claim_sillytavern_role_binding(
            [{"role": "user", "content": "Same"}], {})

        self.assertIsNone(binding)
        self.assertEqual(2, len(server.PENDING_SILLYTAVERN_CONTEXTS))

    def test_explicit_chat_id_resolves_an_ambiguous_message(self):
        server.PENDING_SILLYTAVERN_CONTEXTS.extend([
            snapshot("chat-a", "Same", "Alice"),
            snapshot("chat-b", "Same", "Bob"),
        ])

        binding = server.claim_sillytavern_role_binding(
            [{"role": "user", "content": "Same"}],
            {"chat_id": "chat-b"},
        )

        self.assertEqual("Bob", binding["char_name"])

    def test_summary_request_consumes_its_matching_snapshot(self):
        text = "[[SUMMARIZE]] Summarize this chat."
        server.PENDING_SILLYTAVERN_CONTEXTS.append(
            snapshot("chat-summary", text))
        client = TestClient(server.app)
        with mock.patch.object(
            server, "summary_response",
            new=mock.AsyncMock(return_value={"summary": True}),
        ):
            response = client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": text}],
            })

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, len(server.PENDING_SILLYTAVERN_CONTEXTS))

    def test_delete_is_allowed_by_local_cors_policy(self):
        client = TestClient(server.app)
        response = client.options(
            "/api/lorebooks/books/World.json",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "DELETE",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertIn(
            "DELETE", response.headers.get("access-control-allow-methods", ""))


if __name__ == "__main__":
    unittest.main()
