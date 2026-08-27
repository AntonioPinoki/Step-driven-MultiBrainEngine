import os
import random
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "engine"))
import lorebook_store


class LorebookStoreTests(unittest.TestCase):
    def settings(self, **changes):
        return {**lorebook_store.DEFAULT_SETTINGS, **changes}

    def book(self, entries):
        return {"id": "world", "name": "World", "entries": [
            lorebook_store.validate_entry(entry, index) for index, entry in enumerate(entries)
        ]}

    def test_constant_and_keyword_entries_activate_in_order(self):
        book = self.book([
            {"id": "always", "name": "Always", "content": "A", "constant": True, "order": 1},
            {"id": "school", "name": "School", "content": "B", "keys": ["academy"], "order": 10},
            {"id": "miss", "name": "Miss", "content": "C", "keys": ["spaceship"], "order": 20},
        ])
        active = lorebook_store.activate_book(
            book, [{"role": "user", "content": "We entered the academy."}], self.settings(), random.Random(1))
        self.assertEqual([entry["id"] for entry in active], ["school", "always"])

    def test_scan_depth_can_be_overridden_per_entry(self):
        messages = [
            {"role": "user", "content": "ancient gate"},
            {"role": "assistant", "content": "Later."},
            {"role": "user", "content": "Now."},
        ]
        book = self.book([
            {"id": "global", "name": "Global", "content": "A", "keys": ["ancient"], "scan_depth": None},
            {"id": "deep", "name": "Deep", "content": "B", "keys": ["ancient"], "scan_depth": 3},
        ])
        active = lorebook_store.activate_book(book, messages, self.settings(scan_depth=2), random.Random(1))
        self.assertEqual([entry["id"] for entry in active], ["deep"])

    def test_secondary_logic_and_whole_word_matching(self):
        entry = lorebook_store.validate_entry({
            "id": "selective", "name": "Selective", "content": "A", "keys": ["cat"],
            "secondary_keys": ["black", "white"], "selective": True, "selective_logic": 3,
            "match_whole_words": True,
        })
        book = {"id": "b", "name": "B", "entries": [entry]}
        self.assertFalse(lorebook_store.activate_book(book, [{"role": "user", "content": "black catfish white"}], self.settings()))
        self.assertTrue(lorebook_store.activate_book(book, [{"role": "user", "content": "black cat and white fur"}], self.settings()))

    def test_recursive_activation_scans_activated_content(self):
        book = self.book([
            {"id": "first", "name": "First", "content": "hidden-key", "keys": ["door"]},
            {"id": "second", "name": "Second", "content": "Found", "keys": ["hidden-key"]},
        ])
        messages = [{"role": "user", "content": "Open the door."}]
        self.assertEqual(len(lorebook_store.activate_book(book, messages, self.settings(recursive=False))), 1)
        self.assertEqual(len(lorebook_store.activate_book(book, messages, self.settings(recursive=True))), 2)

    def test_fixed_card_context_activates_without_consuming_chat_depth(self):
        book = self.book([
            {"name": "Card match", "keys": ["clockwork heart"], "content": "card lore"},
            {"name": "Recent match", "keys": ["recent phrase"], "content": "recent lore"},
            {"name": "Old match", "keys": ["old phrase"], "content": "old lore"},
        ])
        messages = [
            {"role": "user", "content": "old phrase"},
            {"role": "assistant", "content": "recent phrase"},
        ]

        active = lorebook_store.activate_book(
            book,
            messages,
            self.settings(scan_depth=1),
            fixed_context="A clockwork heart is part of the character card.",
        )

        self.assertEqual(
            {entry["name"] for entry in active},
            {"Card match", "Recent match"},
        )

    def test_render_wraps_all_entries_and_expands_macros(self):
        entries = self.book([
            {"id": "a", "name": "世界 設定", "content": "{{char}} lives here", "constant": True},
            {"id": "b", "name": "人物関係", "content": "friend", "constant": True},
        ])["entries"]
        rendered = lorebook_store.render_lore(entries, lambda text: text.replace("{{char}}", "Alice"))
        self.assertEqual(rendered.count("<lorebook>"), 1)
        self.assertIn("<世界_設定>\nAlice lives here\n</世界_設定>", rendered)
        self.assertIn("<人物関係>\nfriend\n</人物関係>", rendered)

    def test_sillytavern_import_preserves_core_fields(self):
        book = lorebook_store.import_sillytavern({"entries": {"7": {
            "uid": 7, "comment": "Castle", "content": "Stone walls", "key": ["castle"],
            "keysecondary": ["king"], "constant": False, "selective": True,
            "order": 50, "scanDepth": 8, "caseSensitive": True, "disable": False,
            "extensions": {"match_whole_words": True, "probability": 80},
        }}}, "Imported")
        entry = book["entries"][0]
        self.assertEqual(book["name"], "Imported")
        self.assertEqual(entry["name"], "Castle")
        self.assertEqual(entry["scan_depth"], 8)
        self.assertTrue(entry["case_sensitive"])
        self.assertTrue(entry["match_whole_words"])
        self.assertEqual(entry["probability"], 80)

    def test_empty_sillytavern_entry_is_preserved_but_not_rendered(self):
        book = lorebook_store.import_sillytavern({"entries": {
            "1": {"uid": 1, "comment": "選別", "content": "", "constant": True},
            "2": {"uid": 2, "comment": "Visible", "content": "Lore", "constant": True},
        }}, "Imported")
        self.assertEqual(len(book["entries"]), 2)
        self.assertEqual(book["entries"][0]["content"], "")
        rendered = lorebook_store.render_lore(book["entries"])
        self.assertNotIn("<選別>", rendered)
        self.assertIn("<Visible>\nLore\n</Visible>", rendered)

    def test_summary_and_unknown_agents_are_removed(self):
        clean = lorebook_store.validate_config({
            "books": [{"id": "b", "name": "B", "entries": []}],
            "assignments": {"step": ["b"], "writer": ["b"], "summary": ["b"], "gone": ["b"]},
        }, ["step", "writer"])
        self.assertEqual(clean["assignments"], {"step": ["b"], "writer": ["b"]})


if __name__ == "__main__":
    unittest.main()
