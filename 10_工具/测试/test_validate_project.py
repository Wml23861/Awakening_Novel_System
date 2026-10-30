import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from validate_project import parse_frontmatter, validate_project  # noqa: E402


REQUIRED_FILES = ("红楼梦.md", "三国演义.md", "水浒传.md", "西游记.md", "觉醒小说 AI 创作工程总纲.md")


def make_valid_project(root: Path) -> None:
    for name in REQUIRED_FILES:
        (root / name).write_text("", encoding="utf-8")
    (root / "10_工具").mkdir()
    definitions = {
        ".claude/agents/reviewer.md": "agent",
        ".claude/commands/review.md": "command",
        ".claude/skills/review/SKILL.md": "skill",
    }
    for relative, name in definitions.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative.startswith(".claude/commands/"):
            frontmatter = "description: Test command"
        else:
            frontmatter = f"name: {name}\ndescription: Test definition"
        path.write_text(f"---\n{frontmatter}\n---\nBody\n", encoding="utf-8")


class ValidateProjectTests(unittest.TestCase):
    def test_valid_project_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_valid_project(root)
            result = validate_project(root)
            self.assertTrue(result["valid"], result["errors"])
            self.assertEqual(result["errors"], [])

    def test_agents_and_skills_still_require_name(self) -> None:
        for relative in (".claude/agents/reviewer.md", ".claude/skills/review/SKILL.md"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                make_valid_project(root)
                (root / relative).write_text(
                    "---\ndescription: Missing name\n---\n", encoding="utf-8"
                )
                result = validate_project(root)
                self.assertFalse(result["valid"])
                self.assertTrue(any("name" in error for error in result["errors"]))

    def test_missing_paths_and_definition_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_valid_project(root)
            (root / "红楼梦.md").unlink()
            (root / ".claude/agents/reviewer.md").unlink()
            result = validate_project(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("红楼梦.md" in error for error in result["errors"]))
            self.assertTrue(any("agents" in error and "definition" in error for error in result["errors"]))

    def test_frontmatter_is_required_with_name_and_description(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_valid_project(root)
            (root / ".claude/commands/review.md").write_text("name: no-delimiters\n", encoding="utf-8")
            result = validate_project(root)
            self.assertFalse(result["valid"])
            self.assertTrue(any("frontmatter" in error for error in result["errors"]))
        with self.assertRaisesRegex(ValueError, "description"):
            parse_frontmatter("---\nname: demo\n---\n")
        with self.assertRaisesRegex(ValueError, "closing"):
            parse_frontmatter("---\nname: demo\ndescription: demo\n")

    def test_cli_returns_nonzero_and_json_on_invalid_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(TOOLS_DIR / "validate_project.py"),
                    "--project-root",
                    temp_dir,
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["valid"])
            self.assertGreater(len(payload["errors"]), 0)


if __name__ == "__main__":
    unittest.main()
