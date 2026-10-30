#!/usr/bin/env python3
"""Report repeated chapter fingerprint values within a recent chapter window."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

SCALAR_FIELDS = ("event", "conflict", "satisfaction", "ending")
DISCLAIMER = "Repetition is a warning for human review, not an error or quality verdict."


def check_fingerprints(data: dict[str, Any], window: int = 5) -> dict[str, Any]:
    """Compare each chapter with up to ``window`` preceding chapters."""
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    if not isinstance(data, dict) or not isinstance(data.get("chapters"), list):
        raise ValueError("input must be an object containing a chapters array")
    chapters: list[Any] = data["chapters"]
    warnings: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    if not chapters:
        missing.append({"path": "chapters", "message": "No chapter fingerprints were supplied."})

    normalized: list[dict[str, Any]] = []
    supplied_ids: set[str] = set()
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise ValueError(f"chapters[{index}] must be an object")
        chapter_id = chapter.get("id")
        if isinstance(chapter_id, str) and chapter_id.strip():
            if chapter_id in supplied_ids:
                raise ValueError(f"duplicate chapter id: {chapter_id}")
            supplied_ids.add(chapter_id)
    identifiers = set(supplied_ids)
    for index, chapter in enumerate(chapters):
        path = f"chapters[{index}]"
        if not isinstance(chapter, dict):
            raise ValueError(f"{path} must be an object")
        chapter_id = chapter.get("id")
        if not isinstance(chapter_id, str) or not chapter_id.strip():
            base_id = f"index-{index + 1}"
            chapter_id = base_id
            if chapter_id in identifiers:
                chapter_id = f"{base_id}-generated"
                suffix = 2
                while chapter_id in identifiers:
                    chapter_id = f"{base_id}-generated-{suffix}"
                    suffix += 1
            identifiers.add(chapter_id)
            missing.append({"path": f"{path}.id", "message": "Chapter id is missing or empty."})
        record: dict[str, Any] = {"id": chapter_id}
        for field in SCALAR_FIELDS:
            value = chapter.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append({"path": f"{path}.{field}", "message": "Fingerprint value is missing or empty."})
                record[field] = ""
            elif not isinstance(value, str):
                raise ValueError(f"{path}.{field} must be a string")
            else:
                record[field] = " ".join(value.split())
        raw_actions = chapter.get("character_actions")
        if raw_actions is None:
            actions: list[str] = []
        elif not isinstance(raw_actions, list) or any(not isinstance(action, str) for action in raw_actions):
            raise ValueError(f"{path}.character_actions must be an array of strings")
        else:
            actions = [" ".join(action.split()) for action in raw_actions if action.strip()]
        record["character_actions"] = actions
        if not actions:
            missing.append({"path": f"{path}.character_actions", "message": "No character actions were supplied."})
        normalized.append(record)

    for current_index, current in enumerate(normalized):
        start = max(0, current_index - window)
        for previous in normalized[start:current_index]:
            for field in SCALAR_FIELDS:
                value = current[field]
                if value and value == previous[field]:
                    warnings.append(
                        {
                            "field": field,
                            "value": value,
                            "current_chapter": current["id"],
                            "previous_chapter": previous["id"],
                        }
                    )
            for action in current["character_actions"]:
                if action in previous["character_actions"]:
                    warnings.append(
                        {
                            "field": "character_actions",
                            "value": action,
                            "current_chapter": current["id"],
                            "previous_chapter": previous["id"],
                        }
                    )
    return {
        "window": window,
        "checked_chapters": len(chapters),
        "warnings": warnings,
        "missing_data": missing,
        "disclaimer": DISCLAIMER,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="UTF-8 JSON chapter fingerprints")
    parser.add_argument("--window", type=int, default=5, help="number of preceding chapters; default: 5")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.file.read_text(encoding="utf-8-sig"))
        result = check_fingerprints(data, window=args.window)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(2, f"error: cannot check fingerprints: {exc}\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Checked chapters: {result['checked_chapters']}")
        print(f"Repetition warnings: {len(result['warnings'])}")
        print(f"Missing data entries: {len(result['missing_data'])}")
        print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
