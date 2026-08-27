import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from web_prompt_assistant import append_user_message, greeting_message


class PromptAssistantTests(unittest.TestCase):
    def test_append_user_message_does_not_mutate_history(self):
        original = [{"role": "assistant", "content": "hello"}]
        result, cleared = append_user_message("  world  ", original)
        self.assertEqual(original, [{"role": "assistant", "content": "hello"}])
        self.assertEqual(result[-1], {"role": "user", "content": "world"})
        self.assertEqual(cleared, "")

    def test_append_user_message_keeps_twenty_messages(self):
        history = [{"role": "user", "content": str(i)} for i in range(20)]
        result, _ = append_user_message("next", history)
        self.assertEqual(len(result), 20)
        self.assertEqual(result[0]["content"], "1")
        self.assertEqual(result[-1]["content"], "next")

    def test_append_user_message_rejects_empty_and_oversized(self):
        for value in ("", "   ", "x" * 12001):
            with self.assertRaises(ValueError):
                append_user_message(value, [])

    def test_greeting_lists_agents_and_remains_display_only(self):
        greeting = greeting_message([
            {"id": "perception", "name": "Perception", "step": 1},
            {"id": "writer", "name": "Writer"},
        ])
        self.assertIn("Step 1: Perception", greeting)
        self.assertIn("Writer: Writer", greeting)
        history, _ = append_user_message("hello", [])
        self.assertNotIn(greeting, [item["content"] for item in history])
