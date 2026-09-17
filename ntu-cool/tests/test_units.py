"""純函式單元測試：命名、設定、HTML、狀態檔。"""

import json
import tempfile
import unittest
from pathlib import Path

import _support  # noqa: F401

from ntucool.cli import build_parser, parse_duration
from ntucool.config import ALL_SECTIONS, load_config, parse_env_file
from ntucool.errors import ConfigError
from ntucool.htmlutil import extract_file_ids, html_to_text
from ntucool.manifest import Manifest
from ntucool.naming import course_dirname, safe_name, safe_relpath, unique_path


class TestNaming(unittest.TestCase):
    def test_strips_path_and_control_characters(self):
        self.assertEqual(safe_name("第一週/投影片:講義?.pdf"), "第一週_投影片_講義_.pdf")
        self.assertEqual(safe_name("a\x00b.txt"), "a_b.txt")

    def test_keeps_extension_when_truncating(self):
        name = safe_name("中" * 200 + ".pdf")
        self.assertTrue(name.endswith(".pdf"))
        self.assertLessEqual(len(name.encode("utf-8")), 120)

    def test_windows_reserved_names(self):
        self.assertEqual(safe_name("CON.txt"), "_CON.txt")
        self.assertEqual(safe_name("  "), "untitled")

    def test_relpath_drops_traversal(self):
        self.assertEqual(safe_relpath("course files/講義//../第一週"), Path("course files/講義/第一週"))
        self.assertEqual(safe_relpath(""), Path())

    def test_course_dirname_includes_id(self):
        name = course_dirname({"id": 101, "course_code": "CSIE1212", "name": "資料結構"})
        self.assertEqual(name, "CSIE1212-資料結構-101")
        self.assertEqual(course_dirname({"id": 7}), "course-7")

    def test_unique_path_avoids_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.pdf"
            target.write_text("x")
            self.assertEqual(unique_path(target).name, "a-2.pdf")
            self.assertEqual(unique_path(Path(tmp) / "b.pdf", {Path(tmp) / "b.pdf"}).name, "b-2.pdf")


class TestHtml(unittest.TestCase):
    def test_html_to_text(self):
        text = html_to_text("<p>第一週<br>說明</p><ul><li>A</li><li>B</li></ul><script>ignore()</script>")
        self.assertEqual(text, "第一週\n說明\n- A\n- B")
        self.assertEqual(html_to_text(None), "")

    def test_extract_file_ids_scoped_to_course(self):
        body = '<a href="/courses/101/files/5100">講義</a><a href="/courses/999/files/1">別課</a>'
        self.assertEqual(extract_file_ids(body, course_id=101), [5100])
        self.assertEqual(extract_file_ids('<a href="/files/42/download">x</a>', course_id=101), [42])


class TestConfig(unittest.TestCase):
    def test_env_file_parsing(self):
        parsed = parse_env_file('# 註解\nexport NTU_COOL_TOKEN="abc 123"\nNTU_COOL_OUT=out\n壞掉的行\n')
        self.assertEqual(parsed, {"NTU_COOL_TOKEN": "abc 123", "NTU_COOL_OUT": "out"})

    def test_precedence_cli_over_env_over_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "c.json"
            config_file.write_text(json.dumps({"token": "from-file", "out_dir": "from-file-dir"}), encoding="utf-8")
            cfg = load_config(
                config_path=config_file,
                environ={"NTU_COOL_TOKEN": "from-env"},
                overrides={"out_dir": "from-cli", "terms": None},
                env_candidates=(),
            )
            self.assertEqual(cfg.token, "from-env")
            self.assertEqual(cfg.out_dir, Path("from-cli"))
            self.assertEqual(cfg.sections, ALL_SECTIONS)

    def test_validate_requires_token(self):
        cfg = load_config(environ={}, config_candidates=(), env_candidates=())
        with self.assertRaises(ConfigError):
            cfg.validate()

    def test_validate_rejects_unknown_section(self):
        cfg = load_config(
            environ={"NTU_COOL_TOKEN": "t"}, overrides={"sections": ("files", "nope")},
            config_candidates=(), env_candidates=(),
        )
        with self.assertRaises(ConfigError):
            cfg.validate()

    def test_list_values_accept_comma_or_space(self):
        cfg = load_config(
            environ={"NTU_COOL_TOKEN": "t"}, overrides={"extensions": ["PDF, .pptx"]},
            config_candidates=(), env_candidates=(),
        )
        self.assertEqual(cfg.extensions, ("pdf", "pptx"))


class TestCli(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(parse_duration("6h"), 21600)
        self.assertEqual(parse_duration("90"), 90)
        with self.assertRaises(Exception):
            parse_duration("30s")  # 低於 60 秒

    def test_skip_files_removes_section(self):
        args = build_parser().parse_args(["sync", "--skip-files"])
        self.assertTrue(args.skip_files)


class TestManifest(unittest.TestCase):
    def test_roundtrip_and_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = Manifest.load(out)
            remote = {"id": 5001, "updated_at": "2026-02-20T03:00:00Z", "size": 3, "display_name": "a.pdf"}
            dest = out / "a.pdf"
            dest.write_bytes(b"abc")
            self.assertFalse(manifest.is_current(101, remote, dest))
            manifest.record_file(101, remote, dest, 3)
            manifest.save()

            reloaded = Manifest.load(out)
            self.assertTrue(reloaded.is_current(101, remote, dest))
            # 遠端更新時間變了 → 要重抓
            self.assertFalse(reloaded.is_current(101, {**remote, "updated_at": "2026-03-01T00:00:00Z"}, dest))
            # 本地檔案被刪掉 → 要重抓
            dest.unlink()
            self.assertFalse(reloaded.is_current(101, remote, dest))

    def test_corrupt_state_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / ".ntucool-state.json").write_text("{壞掉的 JSON", encoding="utf-8")
            self.assertEqual(Manifest.load(out).files, {})


if __name__ == "__main__":
    unittest.main()
