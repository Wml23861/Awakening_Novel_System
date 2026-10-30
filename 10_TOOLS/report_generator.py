#!/usr/bin/env python3
"""Aggregate documented project-progress JSON without judging creative quality."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

CATEGORIES = (
    "research_progress",
    "creative_progress",
    "review_results",
    "continuity_issues",
    "training_scores",
    "project_risks",
)
DISCLAIMER = "This report aggregates supplied data only; it does not judge creative quality."


def _number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{path} must be a finite number") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{path} must be a finite number")
    return converted


def _mean(values: list[float]) -> float | None:
    """Calculate a nonnegative mean without overflowing the running total."""
    if not values:
        return None
    mean = 0.0
    for index, value in enumerate(values, start=1):
        mean += (value - mean) / index
    return mean


def _progress(value: dict[str, Any], path: str) -> dict[str, Any]:
    if "completed" not in value or "total" not in value:
        raise ValueError(f"{path} requires completed and total values")
    completed = _number(value["completed"], f"{path}.completed")
    total = _number(value["total"], f"{path}.total")
    if completed < 0 or total < 0 or completed > total:
        raise ValueError(f"{path} requires 0 <= completed <= total")
    return {
        "completed": completed,
        "total": total,
        "percent": completed / total * 100 if total else None,
    }


def _status_summary(items: list[Any], path: str, key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError(f"{path}[{index}].{key} must be a nonempty string")
        counts[item[key]] += 1
    return dict(sorted(counts.items()))


def _training_summary(items: list[Any]) -> dict[str, Any]:
    scores: list[float] = []
    percentages: list[float] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"training_scores[{index}] must be an object")
        score = _number(item.get("score"), f"training_scores[{index}].score")
        maximum = _number(item.get("max_score"), f"training_scores[{index}].max_score")
        if maximum <= 0 or score < 0 or score > maximum:
            raise ValueError(f"training_scores[{index}] requires 0 <= score <= max_score and max_score > 0")
        scores.append(score)
        percentages.append(score / maximum * 100)
    return {
        "count": len(items),
        "average_score": _mean(scores),
        "average_percent": _mean(percentages),
    }


def generate_report(data: dict[str, Any]) -> dict[str, Any]:
    """Aggregate all six categories, distinguishing missing from empty input."""
    if not isinstance(data, dict):
        raise TypeError("report input must be a JSON object")
    categories: dict[str, dict[str, Any]] = {}
    for name in CATEGORIES:
        if name not in data or data[name] is None:
            categories[name] = {"status": "missing", "data": None, "summary": {}}
            continue
        value = data[name]
        if name in ("research_progress", "creative_progress"):
            if not isinstance(value, dict):
                raise ValueError(f"{name} must be an object")
            status = "empty" if not value else "present"
            summary = _progress(value, name) if value else {"completed": None, "total": None, "percent": None}
            copied: Any = dict(value)
        else:
            if not isinstance(value, list):
                raise ValueError(f"{name} must be an array")
            status = "empty" if not value else "present"
            copied = list(value)
            if name == "review_results":
                summary = {"count": len(value), "statuses": _status_summary(value, name, "status")}
            elif name == "continuity_issues":
                summary = {"count": len(value)}
            elif name == "training_scores":
                summary = _training_summary(value)
            else:
                summary = {"count": len(value), "severities": _status_summary(value, name, "severity")}
        categories[name] = {"status": status, "data": copied, "summary": summary}
    return {
        "overall_status": "complete" if all(c["status"] == "present" for c in categories.values()) else "incomplete",
        "categories": categories,
        "disclaimer": DISCLAIMER,
    }


def _human_report(result: dict[str, Any]) -> str:
    lines = [f"Overall status: {result['overall_status']}"]
    for name, category in result["categories"].items():
        lines.append(f"{name}: {category['status']}; summary={json.dumps(category['summary'], ensure_ascii=False, allow_nan=False)}")
    lines.append(DISCLAIMER)
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="UTF-8 JSON report input")
    parser.add_argument("--output", type=Path, help="write the report to this UTF-8 file")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.file.read_text(encoding="utf-8-sig"))
        result = generate_report(data)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n" if args.json else _human_report(result)
        if args.output:
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            print(rendered, end="")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        parser.exit(2, f"error: cannot generate report: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
