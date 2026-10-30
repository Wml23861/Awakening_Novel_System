import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from continuity_check import check_continuity  # noqa: E402


def valid_ledger() -> dict:
    return {
        "characters": {"林黛玉": {"aliases": ["黛玉"]}},
        "locations": {"大观园": {}},
        "items": {"旧帕": {}},
        "abilities": {"诗才": {}},
        "events": {"入园": 1, "夜宴": 2},
        "state_values": ["在场", "离场"],
        "chapters": [
            {
                "id": "001",
                "references": {
                    "characters": ["黛玉"],
                    "locations": ["大观园"],
                    "items": ["旧帕"],
                    "abilities": ["诗才"],
                    "events": ["入园"],
                },
                "states": {
                    "林黛玉": {
                        "location": "大观园",
                        "items": ["旧帕"],
                        "abilities": ["诗才"],
                        "state": "在场",
                    }
                },
            }
        ],
    }


class ContinuityCheckTests(unittest.TestCase):
    def test_valid_ledger_and_alias_have_no_issues(self) -> None:
        result = check_continuity(valid_ledger())
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["missing_data"], [])
        self.assertEqual(result["checked_chapters"], 1)
        self.assertIn("semantic", result["disclaimer"].lower())

    def test_unknown_references_and_backward_timeline_are_warnings(self) -> None:
        ledger = valid_ledger()
        ledger["chapters"][0]["references"]["events"] = ["夜宴"]
        ledger["chapters"].append(
            {
                "id": "002",
                "references": {
                    "characters": ["未知人物"],
                    "locations": [],
                    "items": [],
                    "abilities": [],
                    "events": ["入园"],
                },
                "states": {},
            }
        )
        result = check_continuity(ledger)
        kinds = {issue["kind"] for issue in result["issues"]}
        self.assertIn("unknown_reference", kinds)
        self.assertIn("timeline_order", kinds)

    def test_missing_categories_are_explicit(self) -> None:
        result = check_continuity({"characters": {}, "chapters": []})
        missing = {entry["path"] for entry in result["missing_data"]}
        self.assertIn("locations", missing)
        self.assertIn("chapters", missing)
        self.assertEqual(result["checked_chapters"], 0)

    def test_state_values_and_state_references_are_checked(self) -> None:
        ledger = valid_ledger()
        ledger["chapters"][0]["states"]["林黛玉"]["state"] = "未知状态"
        ledger["chapters"][0]["states"]["林黛玉"]["location"] = "未知地点"
        result = check_continuity(ledger)
        self.assertEqual(len([i for i in result["issues"] if i["kind"] == "unknown_state"]), 2)

    def test_malformed_ledger_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "chapters"):
            check_continuity({"chapters": "not-a-list"})

    def test_non_event_registries_require_object_metadata(self) -> None:
        for category in ("locations", "items", "abilities"):
            with self.subTest(category=category):
                ledger = valid_ledger()
                ledger[category] = {"invalid": []}
                with self.assertRaisesRegex(ValueError, category):
                    check_continuity(ledger)

    def test_cli_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ledger.json"
            path.write_text("{bad", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-I", str(TOOLS_DIR / "continuity_check.py"), str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("error", completed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
