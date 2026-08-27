import os
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import prompt_store
import web_prompt_studio


WRITER = {"id": "writer", "name": "Writer", "prompt": "Write it."}
SUMMARY = {"id": "summary", "name": "Summarize", "prompt": "Summarize it."}


class PromptStudioFormTests(unittest.TestCase):
    def config(self):
        return prompt_store.validate_config([
            {"id": "mind", "name": "Mind", "step": 2, "prompt": "Think."},
        ], WRITER, SUMMARY, "Group only.")

    def test_fixed_form_round_trip(self):
        values = web_prompt_studio.config_to_form(self.config())
        self.assertEqual(len(values), 23 * 10 + 7 * 2 + 1)
        restored = web_prompt_studio.form_to_config(values)
        self.assertEqual(restored, self.config())

    def test_disabled_slot_is_not_validated_as_a_step(self):
        values = list(web_prompt_studio.config_to_form(self.config()))
        first = 0
        values[first:first + 4] = [False, "", "", 99]
        restored = web_prompt_studio.form_to_config(values)
        self.assertEqual([item["id"] for item in restored["steps"]], ["mind"])

    def test_step_choices_exclude_numbers_used_by_other_steps(self):
        choices = web_prompt_studio.step_number_choices(
            [True, True, False], [2, 5, 3])
        self.assertIn(2, choices[0])
        self.assertNotIn(5, choices[0])
        self.assertIn(5, choices[1])
        self.assertNotIn(2, choices[1])
        self.assertNotIn(2, choices[2])
        self.assertNotIn(5, choices[2])

    def test_callbacks_save_uses_prompt_store(self):
        callbacks = web_prompt_studio.PromptStudioCallbacks([], WRITER, SUMMARY)
        values = web_prompt_studio.config_to_form(self.config())
        with mock.patch.object(prompt_store, "save_config", wraps=prompt_store.validate_config) as save:
            result = callbacks.save(*values)
        save.assert_called_once()
        self.assertIn("Saved", result[0])

    def test_import_and_export_csv(self):
        callbacks = web_prompt_studio.PromptStudioCallbacks([], WRITER, SUMMARY)
        config = self.config()
        csv_text = prompt_store.config_to_csv(**config)
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "sample.csv")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write(csv_text)
            with mock.patch.object(prompt_store, "save_config", side_effect=prompt_store.validate_config), \
                    mock.patch.object(prompt_store, "save_preset", return_value={"filename": "sample.csv"}), \
                    mock.patch.object(prompt_store, "list_presets", return_value=[]):
                imported = callbacks.import_preset(source)
            self.assertIn("Imported", imported[0])
            restored = web_prompt_studio.form_to_config(imported[2:])
            self.assertEqual(restored["steps"][0]["prompt"], "Think.")
            self.assertEqual(restored["writer"], config["writer"])
            self.assertEqual(restored["summary"], config["summary"])
            self.assertEqual(restored["group_prompt"], "Group only.")

        with tempfile.TemporaryDirectory() as export_directory:
            with mock.patch.object(tempfile, "gettempdir", return_value=export_directory):
                message, path = callbacks.export_preset(
                    "sample", *web_prompt_studio.config_to_form(config))
            self.assertIn("Export ready", message)
            self.assertTrue(os.path.isfile(path))

    def test_debug_callbacks_are_injected(self):
        seen = []
        callbacks = web_prompt_studio.PromptStudioCallbacks(
            [], WRITER, SUMMARY, get_debug=lambda: True,
            set_debug=lambda enabled: seen.append(enabled) or {"enabled": enabled},
        )
        self.assertTrue(callbacks.debug_state())
        self.assertEqual(callbacks.toggle_debug(False), (False, "Debug mode disabled."))
        self.assertEqual(seen, [False])


if __name__ == "__main__":
    unittest.main()
