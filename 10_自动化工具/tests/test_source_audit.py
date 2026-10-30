import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from source_audit import (  # noqa: E402
    analyze_text,
    audit_file,
    parse_chapter_number,
    render_index,
    write_index,
)


class ChapterNumberTests(unittest.TestCase):
    def test_arabic_standard_chinese_and_digitwise_numbers(self) -> None:
        cases = {
            "1": 1,
            " 1 2 0 ": 120,
            "二十": 20,
            "十二": 12,
            "一百二十": 120,
            "一百零一": 101,
            "一二零": 120,
            "一〇〇": 100,
            "第 二 十 回": 20,
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                self.assertEqual(parse_chapter_number(token), expected)

    def test_invalid_numbers_are_rejected(self) -> None:
        for token in (
            "",
            "0",
            "零",
            "abc",
            "一百二零",
            "1.2",
            "一二百",
            "十一二",
            "二十一二三",
            "一百零零一",
            "一百零一零一",
            "一百一十零一",
            "一零一百零一",
        ):
            with self.subTest(token=token), self.assertRaises(ValueError):
                parse_chapter_number(token)
        with self.assertRaises(TypeError):
            parse_chapter_number(None)  # type: ignore[arg-type]


class SourceStructureTests(unittest.TestCase):
    def test_last_first_chapter_splits_toc_and_body_with_title_lookup(self) -> None:
        text = (
            "第一回\n"
            "目录标题 一\n"
            "第 二 回\n"
            "\n"
            "目录标题二\n"
            "第一回 正文标题一\n"
            "正文一\n"
            "## 第 二 回    目录标题二 \n"
            "正文二\n"
            "第五十六 回吴用使时迁盗甲 汤隆赚徐宁上山\n"
            "正文五十六\n"
        )
        result = analyze_text(text, expected_chapters=56, short_chapter_threshold=1)
        self.assertEqual([item["number"] for item in result["table_of_contents"]], [1, 2])
        self.assertEqual([item["number"] for item in result["chapters"]], [1, 2, 56])
        self.assertEqual(result["table_of_contents"][0]["candidate_title"], "目录标题 一")
        self.assertEqual(result["table_of_contents"][1]["candidate_title"], "目录标题二")
        self.assertEqual(result["table_of_contents"][1]["title_line_numbers"], [5])
        self.assertEqual(result["chapters"][0]["start_line"], 6)
        self.assertEqual(result["chapters"][0]["end_line"], 7)
        self.assertEqual(result["chapters"][2]["number"], 56)
        self.assertEqual(len(result["structure_warnings"]["title_mismatches"]), 1)
        self.assertIn("最后一个第一回", result["structure_rule"])
        self.assertIn("不是版本裁决", result["structure_rule"])

    def test_toc_title_is_used_as_candidate_when_body_title_is_absent(self) -> None:
        result = analyze_text("第一回\n目录候选标题\n第一回\n正文内容\n", short_chapter_threshold=1)
        chapter = result["chapters"][0]
        self.assertEqual(chapter["candidate_title"], "目录候选标题")
        self.assertEqual(chapter["candidate_title_source"], "table_of_contents")
        mismatch = result["structure_warnings"]["title_mismatches"][0]
        self.assertEqual(mismatch["body_title"], "正文内容")
        self.assertEqual(chapter["content_non_whitespace_characters"], 4)
        self.assertEqual(result["structure_warnings"]["empty_chapters"], [])
        self.assertEqual(
            chapter["normalized_body_sha256"],
            hashlib.sha256("正文内容".encode("utf-8")).hexdigest(),
        )

    def test_body_title_on_following_lines_is_compared_and_toc_title_is_indexed(self) -> None:
        text = (
            "第三回\n"
            "目录第三回标题\n"
            "第四回\n"
            "目录第四回标题\n"
            "第一回\n"
            "这是第一回正文\n"
            "第三回\n"
            "正文第三回标题\n"
            "这是第三回正文\n"
            "第四回\n"
            "\n"
            "目录第四回标题\n"
            "这是第四回正文\n"
        )
        result = analyze_text(text, short_chapter_threshold=1)
        third, fourth = result["chapters"][1:]
        self.assertEqual(third["candidate_title"], "目录第三回标题")
        self.assertEqual(third["candidate_title_source"], "table_of_contents")
        self.assertEqual(third["body_title"], "正文第三回标题")
        self.assertEqual(third["body_title_line_numbers"], [8])
        self.assertEqual(fourth["candidate_title"], "目录第四回标题")
        self.assertEqual(fourth["body_title_line_numbers"], [12])
        mismatches = result["structure_warnings"]["title_mismatches"]
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["number"], 3)

    def test_two_line_toc_title_is_matched_to_complete_inline_body_title(self) -> None:
        text = (
            "第一回\n首回标题\n"
            "第三回\n甄士隐梦幻识通灵\n贾雨村风尘怀闺秀\n"
            "第一回 首回标题\n这是正文\n"
            "第三回 甄士隐梦幻识通灵 贾雨村风尘怀闺秀\n这是第三回正文\n"
        )
        result = analyze_text(text, short_chapter_threshold=1)
        toc_third = result["table_of_contents"][1]
        body_third = result["chapters"][1]
        self.assertEqual(toc_third["candidate_title"], "甄士隐梦幻识通灵 贾雨村风尘怀闺秀")
        self.assertEqual(toc_third["title_line_numbers"], [4, 5])
        self.assertEqual(body_third["body_title"], "甄士隐梦幻识通灵 贾雨村风尘怀闺秀")
        self.assertEqual(body_third["content_non_whitespace_characters"], 7)
        self.assertEqual(result["structure_warnings"]["title_mismatches"], [])

    def test_two_line_body_title_is_matched_and_excluded_from_content(self) -> None:
        text = (
            "第一回 首回标题\n"
            "第三回 甄士隐梦幻识通灵 贾雨村风尘怀闺秀\n"
            "第一回 首回标题\n正文\n"
            "第三回\n甄士隐梦幻识通灵\n贾雨村风尘怀闺秀\n这是正文\n"
        )
        result = analyze_text(text, short_chapter_threshold=1)
        body_third = result["chapters"][1]
        self.assertEqual(body_third["body_title"], "甄士隐梦幻识通灵 贾雨村风尘怀闺秀")
        self.assertEqual(body_third["body_title_line_numbers"], [6, 7])
        self.assertEqual(body_third["content_non_whitespace_characters"], 4)
        self.assertEqual(
            body_third["normalized_body_sha256"],
            hashlib.sha256("这是正文".encode("utf-8")).hexdigest(),
        )
        self.assertEqual(result["structure_warnings"]["title_mismatches"], [])

    def test_inline_title_prefix_splits_same_line_content_using_toc_title(self) -> None:
        text = (
            "第一回 首回标题\n"
            "第三十一回 第三十一回完整标题\n"
            "第一回 首回标题\n正文\n"
            "第三十一回第三十一回完整标题正文同一行\n后续正文\n"
        )
        result = analyze_text(text, short_chapter_threshold=1)
        chapter = result["chapters"][1]
        self.assertEqual(chapter["body_title"], "第三十一回完整标题")
        self.assertEqual(chapter["body_title_line_numbers"], [5])
        self.assertEqual(chapter["content_non_whitespace_characters"], 9)
        self.assertEqual(
            chapter["normalized_body_sha256"],
            hashlib.sha256("正文同一行后续正文".encode("utf-8")).hexdigest(),
        )
        self.assertEqual(result["structure_warnings"]["title_mismatches"], [])

    def test_private_use_title_difference_does_not_truncate_inline_title(self) -> None:
        inline_title = "憨湘云醉眠芍药茵　呆香菱情解石榴裙"
        text = (
            "第一回 首回标题\n"
            "第六十二回\n憨湘云醉眠芍药茵\n呆香菱情解石榴裙\n"
            "第一回 首回标题\n正文\n"
            f"第六十二回　{inline_title}\n后续正文\n"
        )
        result = analyze_text(text, short_chapter_threshold=1)
        chapter = result["chapters"][1]
        self.assertEqual(chapter["candidate_title"], inline_title)
        self.assertEqual(chapter["body_title"], inline_title)
        self.assertEqual(chapter["content_non_whitespace_characters"], 4)
        self.assertEqual(
            chapter["normalized_body_sha256"],
            hashlib.sha256("后续正文".encode("utf-8")).hexdigest(),
        )
        mismatches = result["structure_warnings"]["title_mismatches"]
        self.assertEqual([item["number"] for item in mismatches], [62])

    def test_hui_zhong_prose_is_not_a_heading_but_real_duplicates_remain_visible(self) -> None:
        prose = "第四回中既将薛家母子在荣府内寄居等事略已表明，此回则暂不能写矣。"
        text = (
            "第一回\n甲\n"
            "第二回\n乙\n"
            "第三回\n丙\n"
            f"{prose}\n"
            "第四回 真正标题\n丁\n"
            "第四回 真正重复回目\n戊\n"
        )
        result = analyze_text(text, expected_chapters=4, short_chapter_threshold=1)
        self.assertEqual([item["number"] for item in result["chapters"]], [1, 2, 3, 4, 4])
        self.assertNotIn(prose, [item["raw_heading"] for item in result["chapters"]])
        duplicate = result["structure_warnings"]["duplicate_chapters"][0]
        self.assertEqual(duplicate["number"], 4)
        self.assertEqual(duplicate["heading_lines"], [8, 10])

    def test_unspaced_title_starting_with_zhong_is_not_mistaken_for_hui_zhong_prose(self) -> None:
        text = "第一回\n正文\n第一一九回中乡魁宝玉却尘缘　沐皇恩贾家延世泽\n正文\n"
        result = analyze_text(text, short_chapter_threshold=1)
        self.assertEqual([item["number"] for item in result["chapters"]], [1, 119])

    def test_missing_duplicate_out_of_order_and_unexpected_chapters(self) -> None:
        text = "第一回\n甲\n第三回\n乙\n第二回\n丙\n第二回\n丁\n"
        result = analyze_text(text, expected_chapters=4, short_chapter_threshold=1)
        warnings = result["structure_warnings"]
        self.assertEqual(warnings["missing_chapters"], [4])
        self.assertEqual(warnings["duplicate_chapters"][0]["number"], 2)
        self.assertEqual(warnings["duplicate_chapters"][0]["heading_lines"], [5, 7])
        self.assertEqual(warnings["out_of_order"][0]["previous_number"], 3)
        self.assertEqual(warnings["out_of_order"][0]["number"], 2)
        self.assertEqual(warnings["unexpected_chapters"], [])

        beyond = analyze_text("第一回\n甲\n第三回\n乙\n", expected_chapters=2, short_chapter_threshold=1)
        self.assertEqual(beyond["structure_warnings"]["unexpected_chapters"], [3])

    def test_empty_short_and_exact_duplicate_body_clues(self) -> None:
        text = "第一回\n重复正文。\n第二回\n重复正文。\n第三回\n第四回\n短短\n"
        result = analyze_text(text, expected_chapters=4, short_chapter_threshold=20)
        warnings = result["structure_warnings"]
        self.assertEqual(warnings["empty_chapters"], [3])
        self.assertEqual({item["number"] for item in warnings["short_chapters"]}, {1, 2, 4})
        self.assertEqual(warnings["duplicate_body_groups"][0]["chapters"], [1, 2])
        self.assertEqual(result["chapters"][0]["start_line"], 1)
        self.assertEqual(result["chapters"][0]["end_line"], 2)
        self.assertEqual(result["chapters"][2]["content_non_whitespace_characters"], 0)
        self.assertIn("人工复核", result["disclaimer"])
        self.assertIn("不能决定", result["disclaimer"])

    def test_explicit_trailing_metadata_is_excluded_but_still_scanned_for_anomalies(self) -> None:
        text = "第一回 标题\n正文\n标题：示例\n转换自「殆知阁」\ndaizhige.org/?\n"
        result = analyze_text(text, short_chapter_threshold=1)
        self.assertEqual(
            result["trailing_metadata"],
            {"start_line": 3, "end_line": 5, "markers": ["标题：", "转换自「殆知阁」", "daizhige.org"]},
        )
        chapter = result["chapters"][0]
        self.assertEqual(chapter["end_line"], 2)
        self.assertEqual(chapter["content_non_whitespace_characters"], 2)
        self.assertEqual(
            chapter["normalized_body_sha256"],
            hashlib.sha256("正文".encode("utf-8")).hexdigest(),
        )
        self.assertEqual(result["character_anomalies"]["counts"]["ascii_question_mark"], 1)

        ordinary = analyze_text("第一回 标题\n正文\n标题：普通正文\n", short_chapter_threshold=1)
        self.assertIsNone(ordinary["trailing_metadata"])
        self.assertEqual(ordinary["chapters"][0]["end_line"], 3)

    def test_metadata_markers_outside_final_small_block_are_not_excluded(self) -> None:
        text = (
            "第一回 标题\n正文\n标题：示例\n转换自「殆知阁」\ndaizhige.org\n"
            + "后续正文\n" * 25
        )
        result = analyze_text(text, short_chapter_threshold=1)
        self.assertIsNone(result["trailing_metadata"])
        self.assertEqual(result["chapters"][0]["end_line"], 30)

    def test_no_headings_and_invalid_arguments(self) -> None:
        result = analyze_text("普通文本\n", expected_chapters=2)
        self.assertEqual(result["chapters"], [])
        self.assertEqual(result["structure_warnings"]["missing_chapters"], [1, 2])
        with self.assertRaises(TypeError):
            analyze_text(None)  # type: ignore[arg-type]
        for expected in (0, -1, True):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                analyze_text("第一回\n正文", expected_chapters=expected)
        with self.assertRaises(ValueError):
            analyze_text("第一回\n正文", short_chapter_threshold=-1)


class CharacterAnomalyTests(unittest.TestCase):
    def test_locates_all_required_anomaly_categories(self) -> None:
        text = "甲�\x00\x01﷐□?\n乙\t\r\n"
        result = analyze_text(text)
        counts = result["character_anomalies"]["counts"]
        self.assertEqual(counts["replacement_character"], 1)
        self.assertEqual(counts["nul"], 1)
        self.assertEqual(counts["control_character"], 1)
        self.assertEqual(counts["noncharacter"], 1)
        self.assertEqual(counts["private_use"], 1)
        self.assertEqual(counts["white_square"], 1)
        self.assertEqual(counts["ascii_question_mark"], 1)
        occurrences = result["character_anomalies"]["occurrences"]
        self.assertEqual(len(occurrences), 7)
        self.assertEqual(occurrences[0]["line"], 1)
        self.assertEqual(occurrences[0]["column"], 2)
        self.assertEqual(occurrences[0]["codepoint"], "U+FFFD")
        self.assertTrue(all(item["line"] == 1 for item in occurrences))
        self.assertIn("异常候选", result["character_anomalies"]["disclaimer"])


class FileAndIndexTests(unittest.TestCase):
    def test_file_metrics_sha256_and_read_only_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.md"
            raw = "第一回\n正文\n".encode("utf-8")
            path.write_bytes(raw)
            result = audit_file(path, expected_chapters=1, short_chapter_threshold=1)
            self.assertEqual(result["file"]["byte_count"], len(raw))
            self.assertEqual(result["file"]["character_count"], len(raw.decode("utf-8")))
            self.assertEqual(result["file"]["line_count"], 2)
            self.assertEqual(result["file"]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(), raw)

    def test_index_has_candidate_warning_status_and_source_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.md"
            path.write_text("第一回\n目录标题\n第一回\n正文内容\n", encoding="utf-8")
            result = audit_file(path, short_chapter_threshold=1)
            rendered = render_index(result)
            self.assertIn("候选结构索引，不是已验收底本", rendered)
            self.assertIn("不是版本裁决", rendered)
            self.assertIn("目录标题", rendered)
            self.assertIn("未开始", rendered)
            self.assertIn("非空白字符数", rendered)

            output = Path(temp_dir) / "index.md"
            write_index(result, path, output)
            self.assertEqual(output.read_text(encoding="utf-8"), rendered)
            self.assertEqual(path.read_text(encoding="utf-8"), "第一回\n目录标题\n第一回\n正文内容\n")

    def test_index_rejects_same_file_non_markdown_and_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.md"
            path.write_text("第一回\n正文\n", encoding="utf-8")
            result = audit_file(path)
            with self.assertRaisesRegex(ValueError, "不得等于输入"):
                write_index(result, path, path)
            with self.assertRaisesRegex(ValueError, ".md"):
                write_index(result, path, Path(temp_dir) / "index.txt")
            with self.assertRaisesRegex(ValueError, "目录必须已存在"):
                write_index(result, path, Path(temp_dir) / "missing" / "index.md")

    def test_existing_non_source_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.md"
            output = Path(temp_dir) / "other.md"
            source_text = "第一回 标题\n正文\n"
            output_text = "另一份已有资料，不得覆盖。\n"
            source.write_text(source_text, encoding="utf-8")
            output.write_text(output_text, encoding="utf-8")
            result = audit_file(source)
            with self.assertRaises(FileExistsError):
                write_index(result, source, output)
            self.assertEqual(source.read_text(encoding="utf-8"), source_text)
            self.assertEqual(output.read_text(encoding="utf-8"), output_text)

    def test_hardlinked_output_is_rejected_without_changing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.md"
            output = Path(temp_dir) / "hardlink.md"
            original = "第一回 标题\n正文\n"
            source.write_text(original, encoding="utf-8")
            result = audit_file(source)
            try:
                os.link(source, output)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"当前平台不支持临时目录硬链接：{exc}")
            with self.assertRaisesRegex(ValueError, "不得等于输入"):
                write_index(result, source, output)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_duplicate_chapter_index_notes_use_body_line_not_chapter_number(self) -> None:
        text = (
            "第一回 首回标题\n第二回 正确标题\n"
            "第一回 首回标题\n足够长的正文内容\n"
            "第二回 错误标题\n"
            "第二回 另一错误\n短\n"
            "第二回 正确标题\n足够长的正文内容\n"
        )
        rendered = render_index(analyze_text(text, short_chapter_threshold=5))
        rows = [line for line in rendered.splitlines() if line.startswith("| 第2回")]
        self.assertEqual(len(rows), 3)
        self.assertIn("空回线索", rows[0])
        self.assertNotIn("空回线索", rows[1])
        self.assertNotIn("空回线索", rows[2])
        self.assertNotIn("异常短回线索", rows[0])
        self.assertIn("异常短回线索", rows[1])
        self.assertNotIn("异常短回线索", rows[2])
        self.assertIn("目录/正文标题异常", rows[0])
        self.assertIn("目录/正文标题异常", rows[1])
        self.assertNotIn("目录/正文标题异常", rows[2])

    def test_markdown_cells_escape_backslashes_before_pipes(self) -> None:
        result = analyze_text("第一回 甲\\乙|丙\n正文", short_chapter_threshold=1)
        self.assertIn("甲\\\\乙\\|丙", render_index(result))

    def test_cli_json_index_and_strict_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.md"
            source.write_text("第一回\n甲\n第二回\n乙\n", encoding="utf-8")
            output = Path(temp_dir) / "index.md"
            command = [
                sys.executable,
                "-I",
                "-B",
                str(TOOLS_DIR / "source_audit.py"),
                str(source),
            ]
            completed = subprocess.run(
                [*command, "--expected-chapters", "2", "--index-output", str(output), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(len(payload["chapters"]), 2)
            self.assertTrue(output.is_file())

            invalid = Path(temp_dir) / "invalid.md"
            invalid.write_bytes(b"\xff\xfe")
            failed = subprocess.run(
                [*command[:-1], str(invalid), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("error", failed.stderr.lower())
            self.assertNotIn("Traceback", failed.stderr)

            same_file = subprocess.run(
                [*command, "--index-output", str(source)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(same_file.returncode, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), "第一回\n甲\n第二回\n乙\n")


if __name__ == "__main__":
    unittest.main()
