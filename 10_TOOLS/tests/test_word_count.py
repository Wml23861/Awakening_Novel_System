import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from word_count import count_text  # noqa: E402


class WordCountTests(unittest.TestCase):
    def test_counts_han_non_whitespace_and_paragraphs(self) -> None:
        text = "红楼，Dream 123。\n\n第二段\t有字。\n   \n第三段"
        result = count_text(text)
        self.assertEqual(result["han_characters"], 10)
        self.assertEqual(result["non_whitespace_characters"], 21)
        self.assertEqual(result["paragraphs"], 3)

    def test_empty_and_whitespace_only_text(self) -> None:
        for text in ("", " \n\t\r\n"):
            with self.subTest(text=text):
                self.assertEqual(
                    count_text(text),
                    {"han_characters": 0, "non_whitespace_characters": 0, "paragraphs": 0},
                )

    def test_counts_extension_b_han_character(self) -> None:
        self.assertEqual(count_text("𠀀")["han_characters"], 1)

    def test_rejects_non_string_input(self) -> None:
        with self.assertRaises(TypeError):
            count_text(None)  # type: ignore[arg-type]

    def test_cli_json_and_missing_file_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chapter.txt"
            path.write_text("你好，世界！", encoding="utf-8")
            command = [sys.executable, "-I", str(TOOLS_DIR / "word_count.py")]
            completed = subprocess.run(
                [*command, str(path), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["han_characters"], 4)

            missing = subprocess.run(
                [*command, str(Path(temp_dir) / "missing.txt")],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("error", missing.stderr.lower())


if __name__ == "__main__":
    unittest.main()
