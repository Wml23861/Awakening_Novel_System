import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from plot_fingerprint import check_fingerprints  # noqa: E402


def chapter(identifier: str, event: str = "出发", action: str = "甲:观察") -> dict:
    return {
        "id": identifier,
        "event": event,
        "conflict": f"冲突{identifier}",
        "satisfaction": f"反馈{identifier}",
        "ending": f"结尾{identifier}",
        "character_actions": [action],
    }


class PlotFingerprintTests(unittest.TestCase):
    def test_repeated_values_in_recent_window_are_warnings(self) -> None:
        data = {"chapters": [chapter("001"), chapter("002"), chapter("003")]}
        result = check_fingerprints(data, window=2)
        repeated = {(w["field"], w["current_chapter"], w["previous_chapter"]) for w in result["warnings"]}
        self.assertIn(("event", "003", "001"), repeated)
        self.assertIn(("character_actions", "003", "002"), repeated)
        self.assertIn("warning", result["disclaimer"].lower())

    def test_repetition_outside_window_is_not_reported(self) -> None:
        data = {"chapters": [chapter("001"), chapter("002"), chapter("003"), chapter("004")]}
        result = check_fingerprints(data, window=1)
        self.assertFalse(any(w["current_chapter"] == "004" and w["previous_chapter"] == "001" for w in result["warnings"]))
        self.assertTrue(any(w["current_chapter"] == "004" and w["previous_chapter"] == "003" for w in result["warnings"]))

    def test_missing_fingerprint_fields_and_chapters_are_explicit(self) -> None:
        result = check_fingerprints({"chapters": [{"id": "001", "event": ""}]})
        paths = {entry["path"] for entry in result["missing_data"]}
        self.assertIn("chapters[0].event", paths)
        self.assertIn("chapters[0].conflict", paths)
        empty = check_fingerprints({"chapters": []})
        self.assertEqual(empty["missing_data"][0]["path"], "chapters")

    def test_invalid_window_and_input_raise_errors(self) -> None:
        for window in (0, -1, 1.5, True):
            with self.subTest(window=window), self.assertRaises(ValueError):
                check_fingerprints({"chapters": []}, window=window)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "chapters"):
            check_fingerprints([])

    def test_character_actions_have_one_normalized_missing_entry(self) -> None:
        for actions in ("missing", None, [" \t "]):
            with self.subTest(actions=actions):
                record = chapter("001")
                if actions == "missing":
                    del record["character_actions"]
                else:
                    record["character_actions"] = actions
                result = check_fingerprints({"chapters": [record]})
                entries = [
                    entry for entry in result["missing_data"]
                    if entry["path"] == "chapters[0].character_actions"
                ]
                self.assertEqual(len(entries), 1)

        record = chapter("001")
        record["character_actions"] = ["  甲:观察  ", " "]
        result = check_fingerprints({"chapters": [record, chapter("002")]})
        self.assertFalse(any(
            entry["path"] == "chapters[0].character_actions"
            for entry in result["missing_data"]
        ))
        self.assertTrue(any(
            warning["field"] == "character_actions" and warning["value"] == "甲:观察"
            for warning in result["warnings"]
        ))

    def test_generated_ids_do_not_collide_with_supplied_ids(self) -> None:
        missing_id = chapter("temporary")
        del missing_id["id"]
        result = check_fingerprints({"chapters": [missing_id, chapter("index-1")]})
        generated = {
            warning["previous_chapter"]
            for warning in result["warnings"]
            if warning["current_chapter"] == "index-1"
        }
        self.assertEqual(len(generated), 1)
        self.assertNotEqual(generated.pop(), "index-1")
        with self.assertRaisesRegex(ValueError, "duplicate chapter id"):
            check_fingerprints({"chapters": [chapter("same"), chapter("same")]})

    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fingerprints.json"
            path.write_text(json.dumps({"chapters": [chapter("001"), chapter("002")]}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-I", str(TOOLS_DIR / "plot_fingerprint.py"), str(path), "--window", "2", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertGreater(len(json.loads(completed.stdout)["warnings"]), 0)


if __name__ == "__main__":
    unittest.main()
