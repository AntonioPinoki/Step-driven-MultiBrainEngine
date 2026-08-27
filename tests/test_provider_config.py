import json
import tempfile
import unittest
from pathlib import Path

from engine import provider_config


def sample_config():
    return {
        "main": {"api_key": "main-key", "model": "main-model", "base_url": "http://main/v1"},
        "logic": {"api_key": "logic-key", "model": "logic-model", "base_url": "https://logic/v1"},
    }


class ProviderConfigTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            saved = provider_config.save_config(sample_config(), path)
            self.assertEqual(provider_config.load_config(path, validate=True), saved)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)

    def test_optional_logic_is_omitted_when_empty(self):
        raw = sample_config()
        raw["logic"] = {"api_key": "", "model": "", "base_url": ""}
        self.assertEqual(provider_config.validate_config(raw), {"main": raw["main"]})

    def test_partial_provider_is_rejected(self):
        raw = sample_config()
        raw["logic"]["model"] = ""
        with self.assertRaisesRegex(provider_config.ProviderConfigError, "Background provider"):
            provider_config.validate_config(raw)

    def test_environment_overrides_file_without_changing_fallbacks(self):
        settings = provider_config.runtime_settings(sample_config(), {
            "BRAIN_API_KEY": "environment-key",
            "BRAIN_MODEL": "",
        })
        self.assertEqual(settings["API_KEY"], "environment-key")
        self.assertEqual(settings["MODEL_NAME"], "main-model")
        self.assertEqual(settings["LOGIC_MODEL"], "logic-model")

    def test_connection_check_rejects_bad_input_without_network(self):
        self.assertFalse(provider_config.test_provider("", "key")["ok"])
        result = provider_config.test_provider("ftp://provider/v1", "key")
        self.assertFalse(result["ok"])
        self.assertIn("http", result["error"])
