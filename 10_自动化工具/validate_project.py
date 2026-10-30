#!/usr/bin/env python3
"""Validate required project paths and basic Claude definition frontmatter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REQUIRED_FILES = ("红楼梦.md", "三国演义.md", "水浒传.md", "西游记.md", "觉醒小说人工智能创作工程总纲.md")
REQUIRED_DIRECTORIES = ("10_自动化工具", ".claude/agents", ".claude/skills", ".claude/commands")
DEFINITION_SETS = (
    (".claude/agents", "*.md"),
    (".claude/commands", "*.md"),
    (".claude/skills", "SKILL.md"),
)


def parse_frontmatter(text: str, source: str = "<text>", *, require_name: bool = True) -> dict[str, str]:
    """Parse flat frontmatter, optionally allowing description-only definitions."""
    if not isinstance(text, str):
        raise TypeError("frontmatter input must be a string")
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source}: missing opening frontmatter delimiter")
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"{source}: missing closing frontmatter delimiter") from exc
    fields: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not separator or not key or not value:
            raise ValueError(f"{source}:{line_number}: expected a nonempty flat key: value entry")
        if key in fields:
            raise ValueError(f"{source}:{line_number}: duplicate frontmatter key {key!r}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1].strip()
        fields[key] = value
    required_fields = ("name", "description") if require_name else ("description",)
    for required in required_fields:
        if not fields.get(required):
            raise ValueError(f"{source}: frontmatter requires a nonempty {required} field")
    return fields


def validate_project(root: Path) -> dict[str, Any]:
    """Return all path and frontmatter errors instead of stopping at the first."""
    root = Path(root)
    errors: list[str] = []
    if not root.is_dir():
        errors.append(f"Project root is not a directory: {root}")
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"Required file is missing: {relative}")
    for relative in REQUIRED_DIRECTORIES:
        if not (root / relative).is_dir():
            errors.append(f"Required directory is missing: {relative}")

    definition_count = 0
    for relative, pattern in DEFINITION_SETS:
        directory = root / relative
        definitions = sorted(directory.rglob(pattern)) if directory.is_dir() else []
        if directory.is_dir() and not definitions:
            errors.append(f"{relative} contains no definition files matching {pattern}")
        for path in definitions:
            definition_count += 1
            try:
                parse_frontmatter(
                    path.read_text(encoding="utf-8-sig"),
                    str(path.relative_to(root)),
                    require_name=relative != ".claude/commands",
                )
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(str(exc))
    return {
        "project_root": str(root),
        "valid": not errors,
        "errors": errors,
        "checked": {"required_files": len(REQUIRED_FILES), "definition_files": definition_count},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = validate_project(args.project_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["valid"]:
        print(f"Project validation passed: {result['checked']['definition_files']} definition files checked.")
    else:
        print("Project validation failed:")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
