import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from report_generator import generate_report  # noqa: E402


class ReportGeneratorTests(unittest.TestCase):
    def test_aggregates_all_categories(self) -> None:
        data = {
            "research_progress": {"completed": 2, "total": 4},
            "creative_progress": {"completed": 1, "total": 5},
            "review_results": [{"status": "passed"}, {"status": "warning"}, {"status": "passed"}],
            "continuity_issues": [{"message": "unknown reference"}],
            "training_scores": [{"score": 80, "max_score": 100}, {"score": 60, "max_score": 100}],
            "project_risks": [{"severity": "high"}, {"severity": "low"}],
        }
        result = generate_report(data)
        categories = result["categories"]
        self.assertEqual(categories["research_progress"]["summary"]["percent"], 50.0)
        self.assertEqual(categories["creative_progress"]["summary"]["percent"], 20.0)
        self.assertEqual(categories["review_results"]["summary"]["statuses"], {"passed": 2, "warning": 1})
        self.assertEqual(categories["continuity_issues"]["summary"]["count"], 1)
        self.assertEqual(categories["training_scores"]["summary"]["average_score"], 70.0)
        self.assertEqual(categories["training_scores"]["summary"]["average_percent"], 70.0)
        self.assertEqual(categories["project_risks"]["summary"]["severities"], {"high": 1, "low": 1})
        self.assertEqual(result["overall_status"], "complete")

    def test_missing_and_empty_categories_are_distinct(self) -> None:
        result = generate_report({"review_results": [], "continuity_issues": []})
        self.assertEqual(result["categories"]["research_progress"]["status"], "missing")
        self.assertEqual(result["categories"]["review_results"]["status"], "empty")
        self.assertEqual(result["categories"]["continuity_issues"]["summary"]["count"], 0)
        self.assertEqual(result["overall_status"], "incomplete")
        self.assertIn("not", result["disclaimer"].lower())

    def test_zero_total_and_invalid_values(self) -> None:
        result = generate_report({"research_progress": {"completed": 0, "total": 0}})
        self.assertIsNone(result["categories"]["research_progress"]["summary"]["percent"])
        with self.assertRaisesRegex(ValueError, "research_progress"):
            generate_report({"research_progress": {"completed": 5, "total": 2}})
        with self.assertRaisesRegex(ValueError, "training_scores"):
            generate_report({"training_scores": [{"score": "high"}]})
        with self.assertRaises(TypeError):
            generate_report([])  # type: ignore[arg-type]

    def test_huge_json_integer_is_a_cli_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "huge.json"
            path.write_text(
                json.dumps({"research_progress": {"completed": 0, "total": 10**400}}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, "-I", str(TOOLS_DIR / "report_generator.py"), str(path), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("error", completed.stderr.lower())
            self.assertNotIn("Traceback", completed.stderr)
        with self.assertRaisesRegex(ValueError, "finite number"):
            generate_report({"research_progress": {"completed": 0, "total": 10**400}})

    def test_large_finite_scores_have_finite_strict_json_mean(self) -> None:
        data = {
            "training_scores": [
                {"score": 1e308, "max_score": 1e308},
                {"score": 1e308, "max_score": 1e308},
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scores.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-I", str(TOOLS_DIR / "report_generator.py"), str(path), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("Infinity", completed.stdout)
            payload = json.loads(completed.stdout)
            average = payload["categories"]["training_scores"]["summary"]["average_score"]
            self.assertTrue(math.isfinite(average))
            self.assertEqual(average, 1e308)
        result = generate_report(data)
        self.assertTrue(math.isfinite(result["categories"]["training_scores"]["summary"]["average_score"]))

    def test_cli_json_output_and_invalid_category_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(json.dumps({"review_results": []}), encoding="utf-8")
            command = [sys.executable, "-I", str(TOOLS_DIR / "report_generator.py"), str(path)]
            completed = subprocess.run(
                [*command, "--json"], capture_output=True, text=True, encoding="utf-8", check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["categories"]["review_results"]["status"], "empty")

            path.write_text(json.dumps({"review_results": {}}), encoding="utf-8")
            failed = subprocess.run(
                [*command], capture_output=True, text=True, encoding="utf-8", check=False
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("review_results", failed.stderr)


if __name__ == "__main__":
    unittest.main()
