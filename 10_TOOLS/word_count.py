#!/usr/bin/env python3
"""Count Han characters, non-whitespace characters, and paragraphs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

HAN_RANGES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
    (0x30000, 0x323AF),
)


def is_han_character(character: str) -> bool:
    """Return whether a character is in a documented CJK ideograph range."""
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in HAN_RANGES)


def count_text(text: str) -> dict[str, int]:
    """Count text metrics; paragraphs are nonempty blocks split by blank lines."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = (
        [part for part in re.split(r"\n[\t ]*\n+", normalized) if part.strip()]
        if normalized
        else []
    )
    return {
        "han_characters": sum(is_han_character(char) for char in text),
        "non_whitespace_characters": sum(not char.isspace() for char in text),
        "paragraphs": len(paragraphs),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="UTF-8 text file to count")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        text = args.file.read_text(encoding="utf-8-sig")
        result = count_text(text)
    except (OSError, UnicodeError) as exc:
        parser.exit(2, f"error: cannot read {args.file}: {exc}\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Han characters: {result['han_characters']}")
        print(f"Non-whitespace characters: {result['non_whitespace_characters']}")
        print(f"Paragraphs: {result['paragraphs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
