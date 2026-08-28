import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from web_lorebooks import (
    add_book, add_entry, assigned_book_names, delete_book, update_assignments, update_entry,
)


def base_draft():
    return {"books": [], "assignments": {}, "settings": {}}


class WebLorebookTests(unittest.TestCase):
    def test_entry_update_preserves_unexposed_fields(self):
        draft, book_id = add_book(base_draft())
        draft, entry_id = add_entry(draft, book_id)
        draft["books"][0]["entries"][0]["extensions"] = {"custom": 42}
        updated = update_entry(draft, book_id, entry_id, name="Changed", keys="one, two")
        entry = updated["books"][0]["entries"][0]
        self.assertEqual(entry["name"], "Changed")
        self.assertEqual(entry["keys"], ["one", "two"])
        self.assertEqual(entry["extensions"], {"custom": 42})
        self.assertEqual(draft["books"][0]["entries"][0]["name"], "New Entry")

    def test_delete_book_removes_assignments(self):
        draft, book_id = add_book(base_draft())
        draft["assignments"] = {"step1": [book_id], "writer": [book_id, "other"]}
        updated = delete_book(draft, book_id)
        self.assertEqual(updated["books"], [])
        self.assertNotIn("step1", updated["assignments"])
        self.assertEqual(updated["assignments"]["writer"], ["other"])

    def test_updates_all_visible_agent_assignments_at_once(self):
        draft = {
            "books": [{"id": "world", "name": "World", "entries": []},
                      {"id": "cast", "name": "Cast", "entries": []}],
            "assignments": {"old": ["world"]},
            "settings": {},
        }
        updated = update_assignments(
            draft,
            ["step1", "step2", "writer", None],
            [["world", "world", "missing"], [], ["cast", "world"], ["world"]],
        )
        self.assertEqual(updated["assignments"], {
            "step1": ["world"],
            "writer": ["cast", "world"],
        })
        self.assertEqual(draft["assignments"], {"old": ["world"]})

    def test_summary_is_never_assigned(self):
        draft = {
            "books": [{"id": "world", "name": "World", "entries": []}],
            "assignments": {},
            "settings": {},
        }
        updated = update_assignments(draft, ["summary", "writer"], [["world"], ["world"]])
        self.assertEqual(updated["assignments"], {"writer": ["world"]})

    def test_assigned_book_names_preserve_selection_order_and_skip_missing_books(self):
        draft = {
            "books": [{"id": "world", "name": "World", "entries": []},
                      {"id": "cast", "name": "Cast", "entries": []}],
        }
        self.assertEqual(
            assigned_book_names(draft, ["cast", "missing", "world"]),
            ["Cast", "World"],
        )
