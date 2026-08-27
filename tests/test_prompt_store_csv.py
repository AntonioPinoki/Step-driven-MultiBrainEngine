import csv
import io
import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "engine"))

import prompt_store


WRITER = {"id": "writer", "name": "Writer", "prompt": "Write the reply."}
SUMMARY = {"id": "summary", "name": "Summarize", "prompt": "Summarize the story."}


class PromptPresetCsvTests(unittest.TestCase):
    def test_titles_round_trip(self):
        steps = [
            {"id": "reality", "name": "Verified Reality", "step": 1, "prompt": "Observe facts."},
            {"id": "director", "name": "Executive Director", "step": 5, "prompt": "Choose action."},
        ]
        writer = {**WRITER, "name": "Scene Writer"}
        csv_text = prompt_store.config_to_csv(steps, writer, SUMMARY)
        row = next(csv.DictReader(io.StringIO(csv_text)))

        self.assertEqual(row["step1_title"], "Verified Reality")
        self.assertEqual(row["step5_title"], "Executive Director")
        self.assertEqual(row["writer_title"], "Scene Writer")
        self.assertEqual(row["summarize_title"], "Summarize")

        restored = prompt_store.csv_to_config(csv_text, WRITER, SUMMARY)
        self.assertEqual([step["name"] for step in restored["steps"]],
                         ["Verified Reality", "Executive Director"])
        self.assertEqual(restored["writer"]["name"], "Scene Writer")

    def test_legacy_csv_without_titles_uses_defaults(self):
        legacy = "step1,writer\nAnalyze.,Write.\n"
        restored = prompt_store.csv_to_config(legacy, WRITER, SUMMARY)

        self.assertEqual(restored["steps"][0]["name"], "Step 1")
        self.assertEqual(restored["writer"]["name"], "Writer")
        self.assertEqual(restored["summary"]["name"], "Summarize")

    def test_export_includes_titles_without_saving(self):
        steps = [{"id": "tom", "name": "Theory of Mind", "step": 4,
                  "prompt": "Preserve uncertainty."}]
        exported = prompt_store.export_preset("social reading", steps, WRITER, SUMMARY)
        row = next(csv.DictReader(io.StringIO(exported["csv"])))

        self.assertEqual(exported["filename"], "social_reading.csv")
        self.assertEqual(row["step4_title"], "Theory of Mind")

    def test_group_prompt_round_trip(self):
        group_prompt = (
            "User={{user}} Speaker={{char}} Active={{groupchar}} All={{allchar}}"
        )
        csv_text = prompt_store.config_to_csv([], WRITER, SUMMARY, group_prompt)
        row = next(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(row["group_prompt"], group_prompt)

        restored = prompt_store.csv_to_config(csv_text, WRITER, SUMMARY)
        self.assertEqual(restored["group_prompt"], group_prompt)


if __name__ == "__main__":
    unittest.main()
