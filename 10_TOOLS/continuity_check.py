#!/usr/bin/env python3
"""Machine-check explicit references against a JSON continuity ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

DISCLAIMER = (
    "Reference and ordering warnings only; this tool cannot establish semantic correctness."
)
REGISTRY_KEYS = ("characters", "locations", "items", "abilities", "events")
REFERENCE_KEYS = ("characters", "locations", "items", "abilities", "events")


def _missing(path: str, message: str = "Required data is missing or empty.") -> dict[str, str]:
    return {"path": path, "message": message}


def _issue(kind: str, chapter: str, category: str, value: str) -> dict[str, str]:
    return {
        "kind": kind,
        "chapter": chapter,
        "category": category,
        "value": value,
        "message": f"{category} reference {value!r} requires human review.",
    }


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{path} must be an array of strings")
    return value


def _registries(ledger: dict[str, Any], missing: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    registries: dict[str, dict[str, Any]] = {}
    for key in REGISTRY_KEYS:
        if key not in ledger:
            missing.append(_missing(key))
            registries[key] = {}
            continue
        value = ledger[key]
        if not isinstance(value, dict) or any(not isinstance(name, str) for name in value):
            raise ValueError(f"{key} must be an object keyed by reference names")
        registries[key] = value
    for name, order in registries["events"].items():
        if not isinstance(order, int) or isinstance(order, bool):
            raise ValueError(f"events.{name} must be an integer order value")
    for key in ("locations", "items", "abilities"):
        for name, metadata in registries[key].items():
            if not isinstance(metadata, dict):
                raise ValueError(f"{key}.{name} must be an object")
    return registries


def _character_aliases(characters: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for name, metadata in characters.items():
        if not isinstance(metadata, dict):
            raise ValueError(f"characters.{name} must be an object")
        names = [name, *_string_list(metadata.get("aliases", []), f"characters.{name}.aliases")]
        for candidate in names:
            if candidate in aliases and aliases[candidate] != name:
                raise ValueError(f"character alias {candidate!r} is ambiguous")
            aliases[candidate] = name
    return aliases


def _check_references(
    chapter_id: str,
    references: dict[str, Any],
    registries: dict[str, dict[str, Any]],
    aliases: dict[str, str],
    chapter_path: str,
    missing: list[dict[str, str]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for category in REFERENCE_KEYS:
        if category not in references:
            missing.append(_missing(f"{chapter_path}.references.{category}"))
            continue
        values = _string_list(references[category], f"{chapter_path}.references.{category}")
        for value in values:
            known = aliases.get(value, value) if category == "characters" else value
            if known not in registries[category]:
                issues.append(_issue("unknown_reference", chapter_id, category, value))
    return issues


def _check_states(
    chapter_id: str,
    states: dict[str, Any],
    registries: dict[str, dict[str, Any]],
    aliases: dict[str, str],
    state_values: list[str],
    chapter_path: str,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for character, state in states.items():
        path = f"{chapter_path}.states.{character}"
        if not isinstance(state, dict):
            raise ValueError(f"{path} must be an object")
        if aliases.get(character, character) not in registries["characters"]:
            issues.append(_issue("unknown_state", chapter_id, "characters", character))
        location = state.get("location")
        if location is not None:
            if not isinstance(location, str):
                raise ValueError(f"{path}.location must be a string or null")
            if location and location not in registries["locations"]:
                issues.append(_issue("unknown_state", chapter_id, "locations", location))
        for category in ("items", "abilities"):
            for value in _string_list(state.get(category, []), f"{path}.{category}"):
                if value not in registries[category]:
                    issues.append(_issue("unknown_state", chapter_id, category, value))
        status = state.get("state")
        if status is not None:
            if not isinstance(status, str):
                raise ValueError(f"{path}.state must be a string or null")
            if status not in state_values:
                issues.append(_issue("unknown_state", chapter_id, "state", status))
    return issues


def check_continuity(ledger: dict[str, Any]) -> dict[str, Any]:
    """Check ledger references; missing ledger data is returned explicitly."""
    if not isinstance(ledger, dict):
        raise ValueError("ledger root must be a JSON object")
    missing: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    registries = _registries(ledger, missing)
    aliases = _character_aliases(registries["characters"])

    if "state_values" not in ledger:
        missing.append(_missing("state_values"))
        state_values: list[str] = []
    else:
        state_values = _string_list(ledger["state_values"], "state_values")
    if "chapters" not in ledger:
        missing.append(_missing("chapters"))
        chapters: list[Any] = []
    else:
        if not isinstance(ledger["chapters"], list):
            raise ValueError("chapters must be an array")
        chapters = ledger["chapters"]
        if not chapters:
            missing.append(_missing("chapters", "No chapter records were supplied."))

    latest_event_order: int | None = None
    for index, chapter in enumerate(chapters):
        path = f"chapters[{index}]"
        if not isinstance(chapter, dict):
            raise ValueError(f"{path} must be an object")
        chapter_id = chapter.get("id")
        if not isinstance(chapter_id, str) or not chapter_id.strip():
            missing.append(_missing(f"{path}.id"))
            chapter_id = f"index-{index + 1}"
        references = chapter.get("references")
        if references is None:
            missing.append(_missing(f"{path}.references"))
            references = {}
        if not isinstance(references, dict):
            raise ValueError(f"{path}.references must be an object")
        issues.extend(
            _check_references(chapter_id, references, registries, aliases, path, missing)
        )
        states = chapter.get("states")
        if states is None:
            missing.append(_missing(f"{path}.states"))
            states = {}
        if not isinstance(states, dict):
            raise ValueError(f"{path}.states must be an object")
        issues.extend(_check_states(chapter_id, states, registries, aliases, state_values, path))

        event_orders = [
            registries["events"][event]
            for event in references.get("events", [])
            if event in registries["events"]
        ]
        for event in references.get("events", []):
            if event not in registries["events"]:
                continue
            order = registries["events"][event]
            if latest_event_order is not None and order < latest_event_order:
                issues.append(_issue("timeline_order", chapter_id, "events", event))
        if event_orders:
            current_max = max(event_orders)
            latest_event_order = current_max if latest_event_order is None else max(latest_event_order, current_max)

    return {
        "checked_chapters": len(chapters),
        "issues": issues,
        "missing_data": missing,
        "disclaimer": DISCLAIMER,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, help="UTF-8 JSON continuity ledger")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        ledger = json.loads(args.ledger.read_text(encoding="utf-8-sig"))
        result = check_continuity(ledger)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(2, f"error: cannot validate ledger: {exc}\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Checked chapters: {result['checked_chapters']}")
        print(f"Issues: {len(result['issues'])}")
        print(f"Missing data entries: {len(result['missing_data'])}")
        print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
