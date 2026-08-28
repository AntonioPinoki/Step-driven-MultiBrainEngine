import os
import sys
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient


ENGINE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

import lorebook_store
import prompt_store
import server


def step():
    return {
        "id": "step_alpha", "name": "Analysis", "step": 1,
        "prompt": "Analyze the scene.",
    }


def writer():
    return {"id": "writer", "name": "Writer", "prompt": "Write the response."}


def summary():
    return {"id": "summary", "name": "Summarize", "prompt": "Summarize."}


def world():
    return {
        "name": "World",
        "entries": {"0": {
            "uid": 0, "comment": "Magic", "content": "Magic exists.",
            "key": ["magic"], "enabled": True,
        }},
    }


class PresetApiTests(unittest.TestCase):
    def test_api_profile_rules_match_prompt_studio(self):
        with tempfile.TemporaryDirectory() as directory:
            preset_dir = os.path.join(directory, "Preset")
            lore_root = os.path.join(directory, "Lorebooks")
            books_dir = os.path.join(lore_root, "books")
            settings_file = os.path.join(lore_root, "settings.json")
            prompts_file = os.path.join(directory, "prompts.json")
            os.makedirs(preset_dir)
            with mock.patch.multiple(
                prompt_store,
                PRESET_DIR=preset_dir,
                PROMPTS_FILE=prompts_file,
            ), mock.patch.multiple(
                lorebook_store,
                LOREBOOK_DIR=lore_root,
                BOOKS_DIR=books_dir,
                SETTINGS_FILE=settings_file,
            ):
                source = prompt_store.save_config(
                    [step()], writer(), summary(),
                    preset_id="preset_source", preset_name="Source")
                lorebook_store.import_book_file(world(), "World.json")
                lorebook_store.save_config({
                    "settings": {},
                    "assignments": {"step_alpha": ["World.json"]},
                }, source)
                client = TestClient(server.app)

                saved = client.post("/api/presets/save", json={
                    "name": "Copy",
                    "steps": [step()], "writer": writer(), "summary": summary(),
                })
                self.assertEqual(200, saved.status_code, saved.text)
                copied = saved.json()
                self.assertNotEqual("preset_source", copied["preset_id"])
                self.assertEqual(
                    ["World.json"],
                    lorebook_store.load_config(copied)["assignments"]["step_alpha"],
                )

                target = prompt_store.save_preset(
                    "Empty Target", [step()], writer(), summary(),
                    preset_id="preset_empty", preset_name="Empty Target")
                loaded = client.post("/api/presets/load", json={
                    "filename": target["filename"], "profile_mode": "empty",
                })
                self.assertEqual(200, loaded.status_code, loaded.text)
                self.assertEqual(
                    {}, lorebook_store.load_config(loaded.json())["assignments"])

                prompt_store.save_config(**source)
                prompt_store.save_preset(
                    "Imported", [step()], writer(), summary(),
                    preset_id="preset_existing", preset_name="Existing")
                csv_text = prompt_store.config_to_csv(
                    [step()], writer(), summary(),
                    preset_id="preset_source", preset_name="Imported")
                imported = client.post("/api/presets/import", json={
                    "filename": "Imported.csv", "csv": csv_text,
                    "profile_mode": "copy",
                })
                self.assertEqual(200, imported.status_code, imported.text)
                body = imported.json()
                self.assertEqual("Imported_2.csv", body["filename"])
                self.assertNotEqual("preset_source", body["preset_id"])
                self.assertEqual(
                    ["World.json"],
                    lorebook_store.load_config(body)["assignments"]["step_alpha"],
                )


if __name__ == "__main__":
    unittest.main()
