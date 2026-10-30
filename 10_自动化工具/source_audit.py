#!/usr/bin/env python3
"""Audit UTF-8 Markdown structure and report review clues without changing sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

STRUCTURE_RULE = (
    "结构识别规则：以当前文件中“最后一个第一回”为正文起点，此前识别到的回目作为目录；"
    "这只是当前文件的结构识别规则，不是版本裁决。"
)
DISCLAIMER = (
    "候选结构与人工复核线索：本工具不能决定“可用底本”，不验收版本，"
    "不清洗或改写原文；所有异常均须人工复核。"
)
CHARACTER_DISCLAIMER = (
    "以下仅为异常候选及定位，不是自动改字依据；问号、方框等字符也可能是原文合法内容。"
)
ANOMALY_NAMES = (
    "replacement_character",
    "nul",
    "control_character",
    "noncharacter",
    "private_use",
    "white_square",
    "ascii_question_mark",
)
CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000}
WHITESPACE = r"[^\S\r\n]"
HEADING_PATTERN = re.compile(
    rf"^{WHITESPACE}*(?:#{{1,6}}{WHITESPACE}*)?第{WHITESPACE}*"
    rf"(.*?){WHITESPACE}*回{WHITESPACE}*(.*)$"
)


@dataclass(frozen=True)
class Heading:
    """One recognized chapter heading; line numbers are one-based."""

    number: int
    line_number: int
    raw_heading: str
    inline_title: str


def parse_chapter_number(token: str) -> int:
    """Parse Arabic, standard Chinese, or digitwise Chinese chapter numbers."""
    if not isinstance(token, str):
        raise TypeError("chapter number must be a string")
    compact = "".join(token.split())
    if compact.startswith("第") and compact.endswith("回"):
        compact = compact[1:-1]
    if not compact:
        raise ValueError("chapter number is empty")
    if compact.isascii() and compact.isdigit():
        value = int(compact)
        if value < 1:
            raise ValueError("chapter number must be positive")
        return value
    if any(character not in CHINESE_DIGITS and character not in CHINESE_UNITS for character in compact):
        raise ValueError(f"unsupported chapter number: {token!r}")

    if not any(character in CHINESE_UNITS for character in compact):
        if any(character not in CHINESE_DIGITS for character in compact):
            raise ValueError(f"unsupported chapter number: {token!r}")
        value = int("".join(str(CHINESE_DIGITS[character]) for character in compact))
        if value < 1:
            raise ValueError("chapter number must be positive")
        return value

    # Unit notation cannot contain adjacent nonzero digits; digitwise notation is handled above.
    if re.search(r"[一二两三四五六七八九]{2}", compact):
        raise ValueError(f"ambiguous digit sequence in unit notation: {token!r}")

    # In a standard number, zero is only a skipped-place marker before one final digit.
    zero_positions = [index for index, character in enumerate(compact) if character in ("零", "〇")]
    if zero_positions:
        last_zero = zero_positions[-1]
        suffix = compact[last_zero + 1 :]
        if (
            len(zero_positions) != 1
            or zero_positions[0] == 0
            or compact[last_zero - 1] not in ("百", "千")
            or len(suffix) != 1
            or suffix not in CHINESE_DIGITS
            or CHINESE_DIGITS[suffix] == 0
            or any(character in CHINESE_UNITS for character in suffix)
        ):
            raise ValueError(f"invalid zero placement in chapter number: {token!r}")

    total = 0
    current_digit = 0
    previous_unit = 1001
    for character in compact:
        if character in CHINESE_DIGITS:
            current_digit = CHINESE_DIGITS[character]
            continue
        unit = CHINESE_UNITS[character]
        if unit >= previous_unit:
            raise ValueError(f"invalid unit order in chapter number: {token!r}")
        total += (current_digit or 1) * unit
        current_digit = 0
        previous_unit = unit
    value = total + current_digit
    if value < 1:
        raise ValueError("chapter number must be positive")
    return value


def _parse_heading(line: str, line_number: int) -> Heading | None:
    match = HEADING_PATTERN.fullmatch(line)
    if match is None:
        return None
    try:
        number = parse_chapter_number(match.group(1))
    except ValueError:
        return None
    inline_title = match.group(2).strip()
    if inline_title.startswith("中") and re.search(r"[，。！？；]", inline_title):
        return None
    return Heading(number, line_number, line, inline_title)


@dataclass(frozen=True)
class TitleOption:
    """A conservative one- or two-line title candidate."""

    title: str
    line_numbers: tuple[int, ...]
    content_remainder: str = ""


def _normalize_title(title: str) -> str:
    return "".join(title.split())


def _title_options(lines: list[str], heading: Heading, content_end: int) -> list[TitleOption]:
    """Build one- and two-line candidates without assuming both lines are always titles."""
    if heading.inline_title:
        return [TitleOption(heading.inline_title, (heading.line_number,))]
    heading_index = heading.line_number - 1
    candidates: list[tuple[int, str]] = []
    for offset in (1, 2):
        index = heading_index + offset
        if index >= content_end or _parse_heading(lines[index], index + 1) is not None:
            break
        candidate = lines[index].strip()
        if candidate:
            candidates.append((index, candidate))
    if not candidates:
        return []
    first_index, first_title = candidates[0]
    options = [TitleOption(first_title, (first_index + 1,))]
    if len(candidates) == 2 and candidates[1][0] == first_index + 1:
        second_index, second_title = candidates[1]
        options.append(
            TitleOption(f"{first_title} {second_title}", (first_index + 1, second_index + 1))
        )
    return options


def _split_inline_title(inline: str, title: str) -> TitleOption:
    """Split a verified normalized title prefix from same-line body content."""
    normalized_prefix = _normalize_title(title)
    seen = 0
    for index, character in enumerate(inline):
        if not character.isspace():
            seen += 1
        if seen == len(normalized_prefix):
            return TitleOption(
                inline[: index + 1].strip(),
                (0,),
                inline[index + 1 :].strip(),
            )
    return TitleOption(inline, (0,))


def _select_titles(
    toc_options: list[TitleOption],
    body_options: list[TitleOption],
    heading: Heading,
) -> tuple[TitleOption | None, TitleOption | None, bool]:
    """Cross-check title alternatives and conservatively default to the first line."""
    toc_default = toc_options[0] if toc_options else None
    body_default = body_options[0] if body_options else None
    exact_matches = [
        (toc_option, body_option)
        for toc_option in toc_options
        for body_option in body_options
        if _normalize_title(toc_option.title)
        and _normalize_title(toc_option.title) == _normalize_title(body_option.title)
    ]
    if exact_matches:
        toc_selected, body_selected = max(
            exact_matches,
            key=lambda pair: (len(pair[0].line_numbers) + len(pair[1].line_numbers), len(pair[0].title)),
        )
        return toc_selected, body_selected, True

    if heading.inline_title and toc_options:
        normalized_inline = _normalize_title(heading.inline_title)
        toc_selected = max(toc_options, key=lambda option: len(_normalize_title(option.title)))
        normalized_toc = _normalize_title(toc_selected.title)
        if (
            normalized_toc
            and len(normalized_toc) < len(normalized_inline)
            and normalized_inline.startswith(normalized_toc)
        ):
            body_selected = _split_inline_title(heading.inline_title, toc_selected.title)
            body_selected = TitleOption(
                body_selected.title,
                (heading.line_number,),
                body_selected.content_remainder,
            )
            return toc_selected, body_selected, True
    return toc_default, body_default, False


def _toc_records(
    lines: list[str],
    headings: list[Heading],
    content_end: int,
) -> tuple[list[dict[str, Any]], dict[int, list[TitleOption]]]:
    records: list[dict[str, Any]] = []
    options_by_number: dict[int, list[TitleOption]] = {}
    for heading in headings:
        options = _title_options(lines, heading, content_end)
        options_by_number.setdefault(heading.number, options)
        selected = options[0] if options else TitleOption("", ())
        records.append(
            {
                "number": heading.number,
                "line_number": heading.line_number,
                "raw_heading": heading.raw_heading,
                "inline_title": heading.inline_title,
                "candidate_title": selected.title,
                "normalized_title": _normalize_title(selected.title),
                "title_line_numbers": list(selected.line_numbers),
            }
        )
    return records, options_by_number


def _update_toc_record(record: dict[str, Any], selected: TitleOption) -> None:
    record["candidate_title"] = selected.title
    record["normalized_title"] = _normalize_title(selected.title)
    record["title_line_numbers"] = list(selected.line_numbers)


def _trailing_metadata(lines: list[str]) -> dict[str, Any] | None:
    """Recognize only the explicit three-marker Daizhige footer in the final 20 lines."""
    markers = ["标题：", "转换自「殆知阁」", "daizhige.org"]
    for index in range(max(0, len(lines) - 20), len(lines)):
        if not lines[index].strip().startswith("标题："):
            continue
        tail = lines[index:]
        if any("转换自「殆知阁」" in line for line in tail) and any(
            "daizhige.org" in line for line in tail
        ):
            return {"start_line": index + 1, "end_line": len(lines), "markers": markers}
    return None


def _anomaly_category(character: str) -> str | None:
    codepoint = ord(character)
    if character == "�":
        return "replacement_character"
    if character == "\x00":
        return "nul"
    if unicodedata.category(character) == "Cc" and character not in ("\t", "\n", "\r"):
        return "control_character"
    if 0xFDD0 <= codepoint <= 0xFDEF or codepoint & 0xFFFF in (0xFFFE, 0xFFFF):
        return "noncharacter"
    if unicodedata.category(character) == "Co":
        return "private_use"
    if character == "□":
        return "white_square"
    if character == "?":
        return "ascii_question_mark"
    return None


def _character_anomalies(text: str) -> dict[str, Any]:
    counts = {name: 0 for name in ANOMALY_NAMES}
    occurrences: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        for column, character in enumerate(line, start=1):
            category = _anomaly_category(character)
            if category is None:
                continue
            counts[category] += 1
            occurrences.append(
                {
                    "category": category,
                    "line": line_number,
                    "column": column,
                    "codepoint": f"U+{ord(character):04X}",
                    "character": character,
                }
            )
    return {
        "counts": counts,
        "occurrences": occurrences,
        "disclaimer": CHARACTER_DISCLAIMER,
    }


def _validate_arguments(
    text: str,
    expected_chapters: int | None,
    short_chapter_threshold: int,
) -> None:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if expected_chapters is not None and (
        not isinstance(expected_chapters, int)
        or isinstance(expected_chapters, bool)
        or expected_chapters < 1
    ):
        raise ValueError("expected_chapters must be a positive integer or None")
    if (
        not isinstance(short_chapter_threshold, int)
        or isinstance(short_chapter_threshold, bool)
        or short_chapter_threshold < 0
    ):
        raise ValueError("short_chapter_threshold must be a nonnegative integer")


def analyze_text(
    text: str,
    expected_chapters: int | None = None,
    short_chapter_threshold: int = 200,
) -> dict[str, Any]:
    """Return candidate chapter structure and conservative textual review clues."""
    _validate_arguments(text, expected_chapters, short_chapter_threshold)
    lines = text.splitlines()
    trailing_metadata = _trailing_metadata(lines)
    content_end = (
        trailing_metadata["start_line"] - 1 if trailing_metadata is not None else len(lines)
    )
    headings = [
        heading
        for line_number, line in enumerate(lines[:content_end], start=1)
        if (heading := _parse_heading(line, line_number)) is not None
    ]
    first_chapter_indices = [index for index, heading in enumerate(headings) if heading.number == 1]
    if first_chapter_indices:
        body_start = first_chapter_indices[-1]
        toc_headings = headings[:body_start]
        body_headings = headings[body_start:]
    else:
        toc_headings = []
        body_headings = headings

    toc, toc_options_by_number = _toc_records(lines, toc_headings, content_end)
    toc_by_number: dict[int, dict[str, Any]] = {}
    for record in toc:
        toc_by_number.setdefault(record["number"], record)

    chapters: list[dict[str, Any]] = []
    title_mismatches: list[dict[str, Any]] = []
    body_hashes: dict[str, list[int]] = defaultdict(list)
    for index, heading in enumerate(body_headings):
        start_index = heading.line_number - 1
        end_index = (
            body_headings[index + 1].line_number - 1
            if index + 1 < len(body_headings)
            else content_end
        )
        toc_options = toc_options_by_number.get(heading.number, [])
        body_options = (
            _title_options(lines, heading, end_index)
            if heading.inline_title or toc_options
            else []
        )
        toc_selected, body_selected, titles_match = _select_titles(
            toc_options, body_options, heading
        )
        if body_selected is None:
            body_selected = TitleOption("", ())
        toc_record = toc_by_number.get(heading.number)
        if toc_record is not None and toc_selected is not None and titles_match:
            _update_toc_record(toc_record, toc_selected)

        toc_title = toc_selected.title if toc_selected is not None else ""
        if heading.inline_title:
            candidate_title = body_selected.title
            candidate_source = "body_inline"
        elif toc_title:
            candidate_title = toc_title
            candidate_source = "table_of_contents"
        elif body_selected.title:
            candidate_title = body_selected.title
            candidate_source = "body_following_lines"
        else:
            candidate_title = ""
            candidate_source = "none"

        content_parts = [body_selected.content_remainder] if body_selected.content_remainder else []
        title_lines = set(body_selected.line_numbers) if titles_match else set()
        content_parts.extend(
            lines[line_index]
            for line_index in range(start_index + 1, end_index)
            if line_index + 1 not in title_lines
        )
        section_text = "\n".join(lines[start_index:end_index])
        content_text = "\n".join(content_parts)
        normalized_body = "".join(content_text.split())
        body_hash = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
        if normalized_body:
            body_hashes[body_hash].append(heading.number)
        non_whitespace = sum(not character.isspace() for character in section_text)
        content_non_whitespace = sum(not character.isspace() for character in content_text)
        chapter = {
            "number": heading.number,
            "start_line": heading.line_number,
            "end_line": end_index,
            "raw_heading": heading.raw_heading,
            "inline_title": heading.inline_title,
            "body_title": body_selected.title,
            "body_title_line_numbers": list(body_selected.line_numbers),
            "candidate_title": candidate_title,
            "candidate_title_source": candidate_source,
            "non_whitespace_characters": non_whitespace,
            "content_non_whitespace_characters": content_non_whitespace,
            "normalized_body_sha256": body_hash,
        }
        chapters.append(chapter)
        if toc_record is not None and not titles_match and _normalize_title(
            toc_title
        ) != _normalize_title(body_selected.title):
            title_mismatches.append(
                {
                    "number": heading.number,
                    "toc_line": toc_record["line_number"],
                    "body_line": heading.line_number,
                    "toc_title": toc_title,
                    "body_title": body_selected.title,
                }
            )

    body_numbers = [heading.number for heading in body_headings]
    occurrences: dict[int, list[int]] = defaultdict(list)
    for heading in body_headings:
        occurrences[heading.number].append(heading.line_number)
    duplicate_chapters = [
        {"number": number, "heading_lines": line_numbers}
        for number, line_numbers in sorted(occurrences.items())
        if len(line_numbers) > 1
    ]
    out_of_order = [
        {
            "previous_number": body_headings[index - 1].number,
            "previous_line": body_headings[index - 1].line_number,
            "number": heading.number,
            "line": heading.line_number,
        }
        for index, heading in enumerate(body_headings[1:], start=1)
        if heading.number < body_headings[index - 1].number
    ]
    present = set(body_numbers)
    missing = (
        [number for number in range(1, expected_chapters + 1) if number not in present]
        if expected_chapters is not None
        else []
    )
    unexpected = (
        sorted(number for number in present if number > expected_chapters)
        if expected_chapters is not None
        else []
    )
    empty_chapters = [
        chapter["number"] for chapter in chapters if chapter["content_non_whitespace_characters"] == 0
    ]
    short_chapters = [
        {
            "number": chapter["number"],
            "heading_line": chapter["start_line"],
            "content_non_whitespace_characters": chapter["content_non_whitespace_characters"],
        }
        for chapter in chapters
        if 0 < chapter["content_non_whitespace_characters"] < short_chapter_threshold
    ]
    duplicate_body_groups = [
        {"chapters": numbers, "normalized_body_sha256": body_hash}
        for body_hash, numbers in sorted(body_hashes.items())
        if len(numbers) > 1
    ]

    return {
        "expected_chapters": expected_chapters,
        "short_chapter_threshold": short_chapter_threshold,
        "structure_rule": STRUCTURE_RULE,
        "disclaimer": DISCLAIMER,
        "trailing_metadata": trailing_metadata,
        "table_of_contents": toc,
        "chapters": chapters,
        "structure_warnings": {
            "missing_chapters": missing,
            "duplicate_chapters": duplicate_chapters,
            "out_of_order": out_of_order,
            "unexpected_chapters": unexpected,
            "empty_chapters": empty_chapters,
            "short_chapters": short_chapters,
            "duplicate_body_groups": duplicate_body_groups,
            "title_mismatches": title_mismatches,
        },
        "character_anomalies": _character_anomalies(text),
    }


def audit_file(
    path: str | Path,
    expected_chapters: int | None = None,
    short_chapter_threshold: int = 200,
) -> dict[str, Any]:
    """Read one UTF-8 Markdown file strictly and add immutable source metrics."""
    source = Path(path)
    raw = source.read_bytes()
    text = raw.decode("utf-8-sig", errors="strict")
    result = analyze_text(text, expected_chapters, short_chapter_threshold)
    return {
        "file": {
            "path": str(source),
            "byte_count": len(raw),
            "character_count": len(text),
            "line_count": len(text.splitlines()),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        **result,
    }


def _markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def render_index(result: dict[str, Any]) -> str:
    """Render a candidate chapter index; this is never an approved-base-text record."""
    if not isinstance(result, dict) or not isinstance(result.get("chapters"), list):
        raise TypeError("result must be an audit result containing a chapters array")
    file_info = result.get("file", {})
    lines = [
        "# 候选结构索引",
        "",
        "> **候选结构索引，不是已验收底本。**",
        f"> {STRUCTURE_RULE}",
        "> 本索引只提供人工复核线索；工具不能决定“可用底本”，不清洗或改写原文。",
        "",
        f"- 来源文件：{file_info.get('path', '<内存文本>')}",
        f"- 来源 SHA-256：{file_info.get('sha256', '未计算')}",
        "",
        "| 回目 | 候选标题 | 正文行范围 | 非空白字符数 | 研究状态 | 备注 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    warnings = result.get("structure_warnings", {})
    mismatch_lines = {item["body_line"] for item in warnings.get("title_mismatches", [])}
    short_lines = {item["heading_line"] for item in warnings.get("short_chapters", [])}
    for chapter in result["chapters"]:
        notes = ["待人工复核"]
        if chapter["candidate_title_source"] == "table_of_contents":
            notes.append("标题按回号取自目录")
        elif chapter["candidate_title_source"] == "body_following_lines":
            notes.append("标题取自正文后续一至两行")
        if chapter["start_line"] in mismatch_lines:
            notes.append("目录/正文标题异常")
        if chapter["start_line"] in short_lines:
            notes.append("异常短回线索")
        if chapter["content_non_whitespace_characters"] == 0:
            notes.append("空回线索")
        lines.append(
            "| {number} | {title} | {start}-{end} | {count} | 未开始 | {notes} |".format(
                number=f"第{chapter['number']}回",
                title=_markdown_cell(chapter["candidate_title"]),
                start=chapter["start_line"],
                end=chapter["end_line"],
                count=chapter["non_whitespace_characters"],
                notes=_markdown_cell("；".join(notes)),
            )
        )
    return "\n".join(lines) + "\n"


def _resolved_name(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def write_index(result: dict[str, Any], input_path: str | Path, output_path: str | Path) -> None:
    """Exclusively create a Markdown index without overwriting any existing file."""
    source = Path(input_path)
    output = Path(output_path)
    if _resolved_name(source) == _resolved_name(output) or (
        output.exists() and output.samefile(source)
    ):
        raise ValueError("输出文件不得等于输入文件（包括硬链接或符号链接）")
    if output.suffix.lower() != ".md":
        raise ValueError("索引输出文件必须使用 .md 扩展名")
    if not output.parent.is_dir():
        raise ValueError("索引输出目录必须已存在；工具不会创建目录")
    rendered = render_index(result)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="read-only UTF-8 Markdown source")
    parser.add_argument("--expected-chapters", type=int, help="expected positive chapter count")
    parser.add_argument("--index-output", type=Path, help="write a candidate Markdown chapter index")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = audit_file(args.file, expected_chapters=args.expected_chapters)
        if args.index_output is not None:
            write_index(result, args.file, args.index_output)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        parser.exit(2, f"error: cannot audit source: {exc}\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(f"File bytes: {result['file']['byte_count']}")
        print(f"File characters: {result['file']['character_count']}")
        print(f"File lines: {result['file']['line_count']}")
        print(f"SHA-256: {result['file']['sha256']}")
        print(f"Candidate TOC headings: {len(result['table_of_contents'])}")
        print(f"Candidate body chapters: {len(result['chapters'])}")
        print(f"Character anomaly candidates: {len(result['character_anomalies']['occurrences'])}")
        if args.index_output is not None:
            print(f"Candidate index written: {args.index_output}")
        print(STRUCTURE_RULE)
        print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
