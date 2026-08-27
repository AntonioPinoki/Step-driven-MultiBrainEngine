import pathlib
import sys
import unittest


ENGINE_DIR = pathlib.Path(__file__).resolve().parents[1] / "engine"
sys.path.insert(0, str(ENGINE_DIR))

from ui_text import LANGUAGE_CHOICES, UI_TEXT, normalize_language, t
from ui_theme import CUSTOM_CSS, FONT_STACK


class UiTextTests(unittest.TestCase):
    def test_normalizes_browser_language_values(self):
        self.assertEqual(normalize_language("ja-JP"), "ja")
        self.assertEqual(normalize_language("en_US"), "en")
        self.assertEqual(normalize_language(["fr-FR", "ja-JP"]), "ja")
        self.assertEqual(normalize_language("fr-FR, ja;q=0.8"), "ja")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(normalize_language(None), "en")
        self.assertEqual(normalize_language("fr-FR"), "en")
        self.assertEqual(t("save", "fr-FR"), "Save")

    def test_all_locales_have_the_same_fixed_ui_keys(self):
        self.assertEqual(set(UI_TEXT["ja"]), set(UI_TEXT["en"]))

    def test_unknown_key_is_visible_instead_of_raising(self):
        self.assertEqual(t("missing.translation", "ja"), "missing.translation")

    def test_format_values_are_preserved_verbatim(self):
        user_value = "タイトル / Prompt そのまま"
        self.assertEqual(
            t("connection_failed", "ja", error=user_value),
            f"接続に失敗しました: {user_value}",
        )

    def test_prompt_studio_sampler_labels_are_japanese(self):
        expected = {
            "temperature": "温度",
            "frequency_penalty": "頻度ペナルティ",
            "presence_penalty": "存在ペナルティ",
            "repetition_penalty": "反復ペナルティ",
            "repetition_range": "反復範囲",
        }
        for key, value in expected.items():
            self.assertEqual(UI_TEXT["ja"][key], value)

    def test_enabled_csv_languages_populate_the_selector(self):
        self.assertEqual(LANGUAGE_CHOICES, (("English", "en"), ("日本語", "ja")))

    def test_namespaced_csv_keys_and_legacy_component_keys_match(self):
        self.assertEqual(t("nav.dashboard", "ja"), t("dashboard", "ja"))
        self.assertEqual(t("prompt_studio.temperature", "en"), t("temperature", "en"))


class UiThemeTests(unittest.TestCase):
    def test_css_uses_stable_brainengine_classes_and_fonts(self):
        self.assertIn(".brain-editor textarea", CUSTOM_CSS)
        self.assertIn("--brain-success", CUSTOM_CSS)
        self.assertIn("Noto Sans JP", FONT_STACK)
        self.assertIn('[role="tab"]:hover', CUSTOM_CSS)
        self.assertIn(".brain-dashboard-card code", CUSTOM_CSS)
        self.assertIn(".brain-export-file", CUSTOM_CSS)
        self.assertIn("width: calc(100vw - 2rem) !important", CUSTOM_CSS)
        self.assertIn('[role="tabpanel"]', CUSTOM_CSS)


if __name__ == "__main__":
    unittest.main()
