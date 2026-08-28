import csv
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ENGINE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

import prompt_store
import web_prompt_studio


def step(step_id="step_alpha"):
    return {
        "id": step_id,
        "name": "Analysis",
        "step": 1,
        "prompt": "Analyze the scene.",
    }


def writer():
    return {"id": "writer", "name": "Writer", "prompt": "Write the response."}


def summary():
    return {"id": "summary", "name": "Summarize", "prompt": "Summarize the scene."}


class PromptIdentityTests(unittest.TestCase):
    def test_csv_round_trip_preserves_preset_and_step_ids(self):
        csv_text = prompt_store.config_to_csv(
            [step()], writer(), summary(),
            preset_id="preset_alpha", preset_name="Alpha")

        loaded = prompt_store.csv_to_config(
            csv_text, writer(), summary(), preset_name="Ignored")

        self.assertEqual("preset_alpha", loaded["preset_id"])
        self.assertEqual("Alpha", loaded["preset_name"])
        self.assertEqual("step_alpha", loaded["steps"][0]["id"])

    def test_legacy_csv_receives_new_stable_identifiers(self):
        legacy = io.StringIO(newline="")
        csv.writer(legacy, lineterminator="\n").writerows([
            ["step1", "writer", "step1_title"],
            ["Analyze the scene.", "Write the response.", "Analysis"],
        ])

        loaded = prompt_store.csv_to_config(
            legacy.getvalue(), writer(), summary(), preset_name="Legacy")

        self.assertRegex(loaded["preset_id"], r"^preset_[0-9a-f]{32}$")
        self.assertRegex(loaded["steps"][0]["id"], r"^step_[0-9a-f]{12}$")
        self.assertEqual("Legacy", loaded["preset_name"])

    def test_plain_save_keeps_the_active_preset_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            prompts_file = os.path.join(directory, "prompts.json")
            with mock.patch.object(prompt_store, "PROMPTS_FILE", prompts_file):
                prompt_store.save_config(
                    [step()], writer(), summary(),
                    preset_id="preset_active", preset_name="Active")
                saved = prompt_store.save_config(
                    [step()], writer(), summary(), group_prompt="Updated")

            self.assertEqual("preset_active", saved["preset_id"])
            self.assertEqual("Active", saved["preset_name"])
            with open(prompts_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(8, payload["version"])
            self.assertEqual("preset_active", payload["active_preset_id"])

    def test_loading_legacy_file_upgrades_the_csv_once(self):
        legacy = io.StringIO(newline="")
        csv.writer(legacy, lineterminator="\n").writerows([
            ["step1", "writer", "step1_title"],
            ["Analyze the scene.", "Write the response.", "Analysis"],
        ])
        with tempfile.TemporaryDirectory() as directory:
            preset_dir = os.path.join(directory, "Preset")
            os.makedirs(preset_dir)
            preset_path = os.path.join(preset_dir, "Legacy.csv")
            prompts_file = os.path.join(directory, "prompts.json")
            with open(preset_path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(legacy.getvalue())

            with mock.patch.object(prompt_store, "PRESET_DIR", preset_dir), \
                    mock.patch.object(prompt_store, "PROMPTS_FILE", prompts_file):
                loaded = prompt_store.load_preset_file(
                    "Legacy.csv", writer(), summary())
                with open(preset_path, "r", encoding="utf-8-sig", newline="") as handle:
                    upgraded = list(csv.DictReader(handle))[0]

            self.assertEqual(loaded["preset_id"], upgraded["preset_id"])
            self.assertEqual(loaded["steps"][0]["id"], upgraded["step1_id"])
            self.assertEqual("Legacy", upgraded["preset_name"])

    def test_new_named_presets_receive_distinct_ids(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(prompt_store, "PRESET_DIR", directory):
            first = prompt_store.save_preset(
                "First", [step()], writer(), summary())
            second = prompt_store.save_preset(
                "Second", [step()], writer(), summary())

            self.assertNotEqual(first["preset_id"], second["preset_id"])
            with open(
                os.path.join(directory, first["filename"]),
                "r", encoding="utf-8-sig", newline="",
            ) as handle:
                stored = next(csv.DictReader(handle))
            self.assertEqual(first["preset_id"], stored["preset_id"])
            self.assertEqual("First", stored["preset_name"])

    def test_rename_preserves_preset_and_step_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            prompts_file = os.path.join(directory, "prompts.json")
            with mock.patch.object(prompt_store, "PRESET_DIR", directory), \
                    mock.patch.object(prompt_store, "PROMPTS_FILE", prompts_file):
                saved = prompt_store.save_preset(
                    "Before", [step()], writer(), summary(),
                    preset_id="preset_same", preset_name="Before")
                result = prompt_store.rename_preset(
                    saved["filename"], "After", writer(), summary())

            self.assertEqual("preset_same", result["preset_id"])
            self.assertEqual("step_alpha", result["config"]["steps"][0]["id"])
            self.assertEqual("After.csv", result["filename"])
            self.assertFalse(os.path.exists(os.path.join(directory, "Before.csv")))
            self.assertTrue(os.path.exists(os.path.join(directory, "After.csv")))

    def test_save_as_copies_lore_while_new_starts_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            prompts_file = os.path.join(directory, "prompts.json")
            preset_dir = os.path.join(directory, "Preset")
            os.makedirs(preset_dir)
            calls = []
            callbacks = web_prompt_studio.PromptStudioCallbacks(
                [step()], writer(), summary(),
                ensure_profile=lambda *args, **kwargs: calls.append((args, kwargs)),
            )
            with mock.patch.object(prompt_store, "PRESET_DIR", preset_dir), \
                    mock.patch.object(prompt_store, "PROMPTS_FILE", prompts_file):
                prompt_store.save_config(
                    [step()], writer(), summary(),
                    preset_id="preset_source", preset_name="Source")
                callbacks.save_preset(
                    "Copy", *web_prompt_studio.config_to_form(
                        prompt_store.load_config([step()], writer(), summary())))
                callbacks.new_preset("Empty")

            self.assertEqual("preset_source", calls[0][1]["copy_from"])
            self.assertNotIn("copy_from", calls[1][1])
            self.assertNotEqual(calls[0][0][0], calls[1][0][0])

    def test_copied_csv_receives_a_distinct_preset_id_when_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            prompts_file = os.path.join(directory, "prompts.json")
            csv_text = prompt_store.config_to_csv(
                [step()], writer(), summary(),
                preset_id="preset_shared", preset_name="Shared")
            for filename in ("A.csv", "B.csv"):
                with open(
                    os.path.join(directory, filename),
                    "w", encoding="utf-8-sig", newline="",
                ) as handle:
                    handle.write(csv_text)
            with mock.patch.object(prompt_store, "PRESET_DIR", directory), \
                    mock.patch.object(prompt_store, "PROMPTS_FILE", prompts_file):
                loaded = prompt_store.load_preset_file(
                    "B.csv", writer(), summary())
                with open(
                    os.path.join(directory, "B.csv"),
                    "r", encoding="utf-8-sig", newline="",
                ) as handle:
                    stored = next(csv.DictReader(handle))

            self.assertNotEqual("preset_shared", loaded["preset_id"])
            self.assertEqual(loaded["preset_id"], stored["preset_id"])


if __name__ == "__main__":
    unittest.main()
