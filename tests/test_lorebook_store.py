import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock


ENGINE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

import lorebook_store
import server


def prompt_config(preset_id="preset_alpha", steps=None):
    return {
        "preset_id": preset_id,
        "preset_name": preset_id.replace("_", " ").title(),
        "steps": steps if steps is not None else [{
            "id": "step_alpha", "name": "Analysis", "step": 1,
        }],
        "writer": {"id": "writer", "name": "Writer"},
    }


def st_book(name="World", key="magic"):
    return {
        "name": name,
        "entries": {
            "0": {
                "uid": 0,
                "comment": "Magic",
                "content": "Magic follows established rules.",
                "key": [key],
                "enabled": True,
            },
        },
    }


class LorebookStoreTests(unittest.TestCase):
    @contextmanager
    def isolated_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "Lorebooks")
            books = os.path.join(root, "books")
            settings = os.path.join(root, "settings.json")
            with mock.patch.multiple(
                lorebook_store,
                LOREBOOK_DIR=root,
                BOOKS_DIR=books,
                SETTINGS_FILE=settings,
            ):
                yield root, books, settings

    def test_directly_placed_sillytavern_json_is_discovered(self):
        with self.isolated_store() as (_, books, _):
            os.makedirs(books)
            path = os.path.join(books, "World.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(st_book(), handle)

            loaded = lorebook_store.load_config(prompt_config())

            self.assertEqual(["World.json"], [book["id"] for book in loaded["books"]])
            self.assertEqual("World", loaded["books"][0]["name"])
            self.assertEqual(["magic"], loaded["books"][0]["entries"][0]["keys"])
            self.assertEqual([], loaded["book_errors"])

    def test_import_writes_one_source_json_file_immediately(self):
        source = st_book("Imported World")
        with self.isolated_store() as (_, books, _):
            imported = lorebook_store.import_book_file(source, "Imported World.json")
            path = os.path.join(books, "Imported World.json")

            self.assertTrue(os.path.isfile(path))
            self.assertEqual("Imported World.json", imported["id"])
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(source, json.load(handle))

    def test_assignments_are_isolated_by_prompt_preset(self):
        with self.isolated_store():
            lorebook_store.import_book_file(st_book(), "World.json")
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_alpha": ["World.json"]},
            }, prompt_config("preset_alpha"))

            alpha = lorebook_store.load_config(prompt_config("preset_alpha"))
            beta = lorebook_store.load_config(prompt_config("preset_beta"))

            self.assertEqual(["World.json"], alpha["assignments"]["step_alpha"])
            self.assertEqual({}, beta["assignments"])

    def test_deleted_file_becomes_missing_without_losing_assignment(self):
        with self.isolated_store() as (_, books, settings):
            lorebook_store.import_book_file(st_book(), "World.json")
            prompts = prompt_config()
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_alpha": ["World.json"]},
            }, prompts)
            lorebook_store.delete_book_file("World.json")

            loaded = lorebook_store.load_config(prompts)

            self.assertEqual(["World.json"], loaded["assignments"]["step_alpha"])
            self.assertEqual(["World.json"], loaded["missing_files"])
            with open(settings, "r", encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertEqual(
                ["World.json"],
                persisted["profiles"]["preset_alpha"]["assignments"]
                ["step_alpha"]["books"],
            )
            self.assertFalse(os.path.exists(os.path.join(books, "World.json")))

    def test_removed_step_is_reported_as_missing_target(self):
        with self.isolated_store():
            lorebook_store.import_book_file(st_book(), "World.json")
            original = prompt_config(steps=[{
                "id": "step_six", "name": "Relationships", "step": 6,
            }])
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_six": ["World.json"]},
            }, original)

            changed = prompt_config(steps=[])
            loaded = lorebook_store.load_config(changed)

            self.assertEqual({}, loaded["assignments"])
            self.assertEqual("step_six", loaded["missing_targets"][0]["target_id"])
            self.assertEqual("Relationships", loaded["missing_targets"][0]["target_name"])
            self.assertEqual(6, loaded["missing_targets"][0]["target_position"])

    def test_invalid_book_does_not_hide_valid_books(self):
        with self.isolated_store() as (_, books, _):
            os.makedirs(books)
            with open(os.path.join(books, "Broken.json"), "w", encoding="utf-8") as handle:
                handle.write("{broken")
            with open(os.path.join(books, "World.json"), "w", encoding="utf-8") as handle:
                json.dump(st_book(), handle)

            loaded = lorebook_store.load_config(prompt_config())

            self.assertEqual(["World.json"], [book["id"] for book in loaded["books"]])
            self.assertEqual("Broken.json", loaded["book_errors"][0]["file"])

    def test_nested_character_book_format_is_supported(self):
        source = {
            "data": {
                "character_book": {
                    "name": "Character Lore",
                    "entries": [{
                        "id": 4,
                        "name": "Habit",
                        "content": "She taps the table when thinking.",
                        "keys": ["thinking"],
                    }],
                },
            },
        }
        with self.isolated_store():
            imported = lorebook_store.import_book_file(source, "Character Lore.json")

            self.assertEqual("Character Lore", imported["name"])
            self.assertEqual(["thinking"], imported["entries"][0]["keys"])

    def test_top_level_character_book_name_is_preserved(self):
        source = {
            "character_book": {
                "name": "Top Level Lore",
                "entries": [{
                    "id": 1, "name": "Fact", "content": "A fact.",
                    "keys": ["fact"],
                }],
            },
        }
        with self.isolated_store():
            imported = lorebook_store.import_book_file(
                source, "Fallback.json")

            self.assertEqual("Top Level Lore", imported["name"])

    def test_runtime_uses_only_the_active_preset_profile(self):
        with self.isolated_store():
            lorebook_store.import_book_file(st_book(), "World.json")
            alpha_prompts = prompt_config("preset_alpha")
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_alpha": ["World.json"]},
            }, alpha_prompts)

            messages = [{"role": "user", "content": "Tell me about magic."}]
            alpha = server.activated_lore_by_agent(
                messages, alpha_prompts, {})
            beta = server.activated_lore_by_agent(
                messages, prompt_config("preset_beta"), {})

            self.assertIn("Magic follows established rules.", alpha["step_alpha"])
            self.assertEqual({}, beta)

    def test_new_profile_can_clone_or_start_empty(self):
        with self.isolated_store():
            lorebook_store.import_book_file(st_book(), "World.json")
            alpha = prompt_config("preset_alpha")
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_alpha": ["World.json"]},
            }, alpha)

            lorebook_store.ensure_profile(
                "preset_copy", "Copy", copy_from="preset_alpha")
            lorebook_store.ensure_profile("preset_empty", "Empty")

            self.assertEqual(
                ["World.json"],
                lorebook_store.load_config(
                    prompt_config("preset_copy"))["assignments"]["step_alpha"],
            )
            self.assertEqual(
                {}, lorebook_store.load_config(
                    prompt_config("preset_empty"))["assignments"],
            )

    def test_missing_target_can_be_moved_or_removed(self):
        with self.isolated_store():
            lorebook_store.import_book_file(st_book(), "World.json")
            original = prompt_config(steps=[{
                "id": "step_six", "name": "Old", "step": 6,
            }])
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_six": ["World.json"]},
            }, original)
            current = prompt_config(steps=[{
                "id": "step_new", "name": "New", "step": 2,
            }])

            lorebook_store.move_assignment_target(
                "preset_alpha", "step_six", "step_new", current)
            moved = lorebook_store.load_config(current)
            self.assertEqual(["World.json"], moved["assignments"]["step_new"])
            self.assertEqual([], moved["missing_targets"])

            lorebook_store.remove_assignment_target("preset_alpha", "step_new")
            self.assertEqual({}, lorebook_store.load_config(current)["assignments"])

    def test_missing_file_reference_can_be_removed(self):
        with self.isolated_store():
            lorebook_store.import_book_file(st_book(), "World.json")
            prompts = prompt_config()
            lorebook_store.save_config({
                "settings": {},
                "assignments": {"step_alpha": ["World.json"]},
            }, prompts)
            lorebook_store.delete_book_file("World.json")
            lorebook_store.remove_missing_file_reference(
                "preset_alpha", "World.json")

            loaded = lorebook_store.load_config(prompts)
            self.assertEqual([], loaded["missing_files"])
            self.assertEqual({}, loaded["assignments"])

    def test_stale_draft_cannot_overwrite_another_preset(self):
        with self.isolated_store():
            stale = {
                "preset_id": "preset_alpha",
                "settings": {},
                "books": [],
                "assignments": {},
            }
            with self.assertRaisesRegex(ValueError, "active prompt preset changed"):
                lorebook_store.save_config(stale, prompt_config("preset_beta"))

    def test_assignment_save_does_not_rewrite_direct_json(self):
        source = st_book()
        source["custom_top_level"] = {"preserve": True}
        source["entries"]["0"]["custom_entry_field"] = "preserve"
        with self.isolated_store() as (_, books, _):
            lorebook_store.import_book_file(source, "World.json")
            path = os.path.join(books, "World.json")
            with open(path, "rb") as handle:
                before = handle.read()
            draft = lorebook_store.load_config(prompt_config())
            draft["assignments"] = {"step_alpha": ["World.json"]}

            lorebook_store.save_config(draft, prompt_config())

            with open(path, "rb") as handle:
                self.assertEqual(before, handle.read())

    def test_edit_preserves_unknown_source_fields(self):
        source = st_book()
        source["custom_top_level"] = {"preserve": True}
        source["entries"]["0"]["custom_entry_field"] = "preserve"
        with self.isolated_store() as (_, books, _):
            lorebook_store.import_book_file(source, "World.json")
            draft = lorebook_store.load_config(prompt_config())
            draft["books"][0]["entries"][0]["content"] = "Edited lore."

            lorebook_store.save_config(draft, prompt_config())

            with open(
                os.path.join(books, "World.json"), "r", encoding="utf-8",
            ) as handle:
                saved = json.load(handle)
            self.assertEqual({"preserve": True}, saved["custom_top_level"])
            self.assertEqual(
                "preserve", saved["entries"]["0"]["custom_entry_field"])
            self.assertEqual("Edited lore.", saved["entries"]["0"]["content"])

    def test_malformed_settings_are_visible_and_cannot_be_overwritten(self):
        with self.isolated_store() as (_, _, settings):
            os.makedirs(os.path.dirname(settings))
            original = b"{broken"
            with open(settings, "wb") as handle:
                handle.write(original)

            loaded = lorebook_store.load_config(prompt_config())

            self.assertIn("Could not read", loaded["settings_error"])
            with self.assertRaises(lorebook_store.SettingsDocumentError):
                lorebook_store.save_config(loaded, prompt_config())
            with open(settings, "rb") as handle:
                self.assertEqual(original, handle.read())


if __name__ == "__main__":
    unittest.main()
