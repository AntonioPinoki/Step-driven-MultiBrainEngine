import os
import sys
import types
import unittest


ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

# Importing server normally mounts the optional Gradio UI. Keep this unit test
# focused on request identity resolution and avoid constructing that UI.
sys.modules["web_ui"] = types.SimpleNamespace(mount=lambda app, _server: app)
import server
del sys.modules["web_ui"]


class RequestRoleBindingTests(unittest.TestCase):
    def test_explicit_names_take_priority_over_message_names(self):
        messages = [
            {"role": "user", "name": "Message User", "content": "Hello"},
            {"role": "assistant", "name": "Message Char", "content": "Hi"},
        ]
        binding = server.request_role_binding(
            {"user_name": "Explicit User", "character_name": "Explicit Char"},
            messages,
        )
        self.assertEqual(binding["user_name"], "Explicit User")
        self.assertEqual(binding["char_name"], "Explicit Char")

    def test_message_names_are_supported(self):
        messages = [
            {"role": "user", "name": "Akira", "content": "Hello"},
            {"role": "assistant", "name": "Alice", "content": "Hi"},
        ]
        binding = server.request_role_binding({}, messages)
        self.assertEqual(binding["user_name"], "Akira")
        self.assertEqual(binding["char_name"], "Alice")

    def test_generic_fallback_expands_supported_macros(self):
        binding = server.request_role_binding({}, [
            {"role": "user", "content": "Hello"},
        ])
        rendered = server.expand_role_placeholders(
            "{{user}} speaks to {{char}}", binding
        )
        self.assertEqual(rendered, "user speaks to assistant")

    def test_connector_binding_remains_authoritative(self):
        connector = {
            "user_name": "ST User",
            "char_name": "ST Char",
            "generation_type": "normal",
            "is_group": False,
        }
        binding = server.request_role_binding(
            {"user_name": "Other User", "character_name": "Other Char"},
            [],
            connector,
        )
        self.assertIs(binding, connector)


if __name__ == "__main__":
    unittest.main()
