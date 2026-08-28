import os
import sys
import unittest


ENGINE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

import web_lorebooks


class LorebookUiHelpersTests(unittest.TestCase):
    def test_missing_books_remain_selectable_and_survive_assignment_update(self):
        draft = {
            "books": [{"id": "World.json", "name": "World", "entries": []}],
            "missing_files": ["Missing.json"],
            "assignments": {"step_one": ["Missing.json"]},
        }

        choices = web_lorebooks.assignment_book_choices(draft)
        updated = web_lorebooks.update_assignments(
            draft, ["step_one"], [["Missing.json", "World.json"]])

        self.assertIn(("⚠ Missing.json (Missing)", "Missing.json"), choices)
        self.assertEqual(
            ["Missing.json", "World.json"],
            updated["assignments"]["step_one"],
        )

    def test_missing_book_name_is_visible_in_assignment_summary(self):
        self.assertEqual(
            ["⚠ Missing.json (Missing)"],
            web_lorebooks.assigned_book_names(
                {"books": []}, ["Missing.json"]),
        )


if __name__ == "__main__":
    unittest.main()
