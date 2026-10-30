import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from duplicate_check import analyze_text  # noqa: E402


class DuplicateCheckTests(unittest.TestCase):
    def test_exact_duplicates_use_normalized_whitespace(self) -> None:
        result = analyze_text("甲  乙。\n\n丙。\n\n甲\n乙。")
        self.assertEqual(result["exact_duplicates"][0]["paragraphs"], [1, 3])
        self.assertEqual(len(result["exact_duplicates"]), 1)

    def test_similarity_is_threshold_based_and_excludes_exact_matches(self) -> None:
        text = "众人走到石桥边，看见水面起了雾。\n\n众人走到石桥边，看见水面起了薄雾。\n\n完全不同。"
        high = analyze_text(text, threshold=0.90)
        self.assertEqual(high["similar_paragraphs"][0]["paragraphs"], [1, 2])
        self.assertGreaterEqual(high["similar_paragraphs"][0]["similarity"], 0.90)
        low = analyze_text("短句。\n\n另一个差别很大的段落。", threshold=0.99)
        self.assertEqual(low["similar_paragraphs"], [])

    def test_repeated_sentence_openings_are_conservative_warnings(self) -> None:
        result = analyze_text("春风拂过城门，人群散开。夜雨落下。\n\n春风拂过城墙，旗影摇动。", opening_length=5)
        self.assertEqual(result["repeated_openings"][0]["opening"], "春风拂过城")
        self.assertEqual(result["repeated_openings"][0]["count"], 2)
        self.assertIn("warning", result["disclaimer"].lower())

    def test_empty_text_and_invalid_parameters(self) -> None:
        result = analyze_text("")
        self.assertEqual(result["exact_duplicates"], [])
        self.assertEqual(result["similar_paragraphs"], [])
        for threshold in (0, -1, 1.1, float("nan")):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                analyze_text("文字", threshold=threshold)
        with self.assertRaises(ValueError):
            analyze_text("文字", opening_length=0)

    def test_cli_returns_json_and_zero_when_warnings_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chapter.txt"
            path.write_text("重复。\n\n重复。", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-I", str(TOOLS_DIR / "duplicate_check.py"), str(path), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["exact_duplicates"][0]["paragraphs"], [1, 2])


if __name__ == "__main__":
    unittest.main()
