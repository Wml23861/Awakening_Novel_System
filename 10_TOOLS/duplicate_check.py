#!/usr/bin/env python3
"""Report conservative textual repetition warnings, never plagiarism verdicts."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

DISCLAIMER = "Warning-only textual heuristics; these findings are not a plagiarism verdict."


def split_paragraphs(text: str) -> list[str]:
    """Split nonempty paragraphs on blank lines and normalize internal whitespace."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    parts = re.split(r"\n[\t ]*\n+", normalized)
    return [" ".join(part.split()) for part in parts if part.strip()]


def analyze_text(text: str, threshold: float = 0.85, opening_length: int = 6) -> dict[str, Any]:
    """Return exact, similar, and repeated-opening warnings for a text."""
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError("threshold must be a number greater than 0 and at most 1")
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("threshold must be greater than 0 and at most 1")
    if not isinstance(opening_length, int) or isinstance(opening_length, bool) or opening_length < 1:
        raise ValueError("opening_length must be a positive integer")

    paragraphs = split_paragraphs(text)
    occurrences: dict[str, list[int]] = defaultdict(list)
    for index, paragraph in enumerate(paragraphs, start=1):
        occurrences[paragraph].append(index)
    exact = [
        {"text": paragraph, "paragraphs": indices}
        for paragraph, indices in occurrences.items()
        if len(indices) > 1
    ]

    similar: list[dict[str, Any]] = []
    for left in range(len(paragraphs)):
        for right in range(left + 1, len(paragraphs)):
            first, second = paragraphs[left], paragraphs[right]
            if first == second:
                continue
            similarity = difflib.SequenceMatcher(None, first, second, autojunk=False).ratio()
            if similarity >= threshold:
                similar.append(
                    {
                        "paragraphs": [left + 1, right + 1],
                        "similarity": round(similarity, 4),
                    }
                )

    openings: Counter[str] = Counter()
    for paragraph in paragraphs:
        for sentence in re.split(r"[。！？!?；;]+", paragraph):
            compact = "".join(sentence.split())
            if len(compact) >= opening_length:
                openings[compact[:opening_length]] += 1
    repeated_openings = [
        {"opening": opening, "count": count}
        for opening, count in sorted(openings.items(), key=lambda item: (-item[1], item[0]))
        if count > 1
    ]
    return {
        "threshold": float(threshold),
        "opening_length": opening_length,
        "paragraph_count": len(paragraphs),
        "exact_duplicates": exact,
        "similar_paragraphs": similar,
        "repeated_openings": repeated_openings,
        "disclaimer": DISCLAIMER,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="UTF-8 text file to inspect")
    parser.add_argument("--threshold", type=float, default=0.85, help="similarity in (0, 1]; default: 0.85")
    parser.add_argument("--opening-length", type=int, default=6, help="opening prefix length; default: 6")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = analyze_text(
            args.file.read_text(encoding="utf-8-sig"),
            threshold=args.threshold,
            opening_length=args.opening_length,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Exact duplicate groups: {len(result['exact_duplicates'])}")
        print(f"High-similarity pairs: {len(result['similar_paragraphs'])}")
        print(f"Repeated sentence openings: {len(result['repeated_openings'])}")
        print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
