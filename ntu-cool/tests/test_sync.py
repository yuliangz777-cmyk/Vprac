"""端到端：對假 Canvas 站台跑完整同步，檢查產出的資料夾內容。"""

import json
import tempfile
import unittest
from pathlib import Path

import _support  # noqa: F401

from fake_canvas import PDF_BYTES, TOKEN, ZIP_BYTES, FakeCanvas

from ntucool.client import CanvasClient
from ntucool.config import load_config
from ntucool.manifest import Manifest
from ntucool.scraper import Scraper


class SyncTestCase(unittest.TestCase):
    def setUp(self):
        self.server = FakeCanvas()
        self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "data"

    def make_scraper(self, **overrides) -> Scraper:
        config = load_config(
            environ={"NTU_COOL_TOKEN": TOKEN},
            overrides={"base_url": self.server.base_url, "out_dir": self.out, **overrides},
            config_candidates=(),
            env_candidates=(),
        ).validate()
        client = CanvasClient(config.api_root, config.token, max_retries=1, sleep=lambda *_: None)
        return Scraper(config, client, Manifest.load(config.out_dir))

    @property
    def course_dir(self) -> Path:
        return self.out / "CSIE1212-資料結構與演算法-101"


class TestCourseListing(SyncTestCase):
    def test_skips_restricted_courses(self):
        courses = self.make_scraper().list_courses()
        self.assertEqual([c["id"] for c in courses], [101, 202])

    def test_course_filter_matches_code_name_or_id(self):
        for needle, expected in (("CSIE", [101]), ("物理", [202]), ("101", [101])):
            self.assertEqual([c["id"] for c in self.make_scraper(course_filters=(needle,)).list_courses()], expected)

    def test_term_filter(self):
        self.assertEqual(len(self.make_scraper(terms=("113-2",)).list_courses()), 2)
        self.assertEqual(self.make_scraper(terms=("112-1",)).list_courses(), [])


class TestFullSync(SyncTestCase):
    def test_downloads_files_and_writes_documents(self):
        run = self.make_scraper().run()
        result = next(r for r in run.results if r.course["id"] == 101)

        # 檔案分頁 2 個可下載 + 單元引用 1 個 + 公告附件 1 個
        self.assertEqual(result.downloaded, 4)
        files_dir = self.course_dir / "files"
        self.assertEqual((files_dir / "講義" / "第一週" / "week1-投影片.pdf").read_bytes(), PDF_BYTES)
        self.assertEqual((files_dir / "講義" / "課程大綱.pdf").read_bytes(), PDF_BYTES)
        self.assertEqual((files_dir / "講義" / "補充教材.zip").read_bytes(), ZIP_BYTES)
        self.assertTrue((files_dir / "附件" / "公告附件.pdf").exists())

        # 鎖住的檔案要被記錄成「沒取得」，而不是默默消失
        self.assertTrue(any("鎖住的期末考卷" in f for f in result.failures))

        for name in ("course.json", "course.md", "assignments.md", "announcements.md"):
            self.assertTrue((self.course_dir / name).is_file(), name)
        self.assertTrue((self.course_dir / "pages" / "課程公告.md").is_file())
        self.assertTrue((self.out / "README.md").is_file())

    def test_course_json_contents(self):
        self.make_scraper().run()
        data = json.loads((self.course_dir / "course.json").read_text(encoding="utf-8"))
        self.assertEqual(data["course"]["teachers"], ["王教授"])
        self.assertEqual(data["course"]["term"], "113-2")
        self.assertIn("評分方式", data["syllabus_text"])
        self.assertEqual(data["assignments"][0]["name"], "HW1 複雜度證明")
        self.assertTrue(data["assignments"][0]["submitted"])
        self.assertEqual(data["announcements"][0]["title"], "第一次上課須知")
        self.assertEqual(data["modules"][0]["items"][0]["title"], "投影片")
        self.assertIn("本課程使用 C++", data["pages"][0]["body_text"])
        self.assertNotIn("_announcement_attachments", data)

    def test_calendar_events_are_fetched_and_filtered(self):
        self.make_scraper().run()
        data = json.loads((self.course_dir / "course.json").read_text(encoding="utf-8"))
        titles = [e["title"] for e in data["events"]]
        self.assertEqual(titles, ["期中考"])          # 已刪除的事件不該出現
        event = data["events"][0]
        self.assertEqual(event["location"], "資訊館 104")
        self.assertIn("第 1–6 週", event["description_text"])
        self.assertIn("行事曆", (self.course_dir / "course.md").read_text(encoding="utf-8"))

    def test_calendar_can_be_skipped(self):
        self.make_scraper(sections=("info", "files")).run()
        data = json.loads((self.course_dir / "course.json").read_text(encoding="utf-8"))
        self.assertNotIn("events", data)

    def test_markdown_summary_has_key_facts(self):
        self.make_scraper().run()
        text = (self.course_dir / "course.md").read_text(encoding="utf-8")
        self.assertIn("王教授", text)
        self.assertIn("HW1 複雜度證明", text)
        self.assertIn("第一次上課須知", text)
        index = (self.out / "README.md").read_text(encoding="utf-8")
        self.assertIn("資料結構與演算法", index)

    def test_course_without_files_tab_still_syncs_info(self):
        run = self.make_scraper(course_filters=("PHYS1001",)).run()
        result = run.results[0]
        self.assertEqual(result.downloaded, 0)
        self.assertTrue((self.out / "PHYS1001-普通物理學-202" / "course.md").is_file())
        self.assertTrue(any("檔案" in f for f in result.failures))


class TestIncrementalSync(SyncTestCase):
    def test_second_run_skips_unchanged_files(self):
        first = self.make_scraper().run()
        self.assertEqual(first.downloaded, 4)

        second = self.make_scraper().run()
        self.assertEqual(second.downloaded, 0)
        self.assertEqual(sum(r.skipped for r in second.results), 4)

    def test_force_redownloads_everything(self):
        self.make_scraper().run()
        forced = self.make_scraper(force=True).run()
        self.assertEqual(forced.downloaded, 4)

    def test_deleted_local_file_is_fetched_again(self):
        self.make_scraper().run()
        (self.course_dir / "files" / "講義" / "課程大綱.pdf").unlink()
        again = self.make_scraper().run()
        self.assertEqual(again.downloaded, 1)
        self.assertTrue((self.course_dir / "files" / "講義" / "課程大綱.pdf").exists())

    def test_updated_file_is_refetched_in_place(self):
        self.make_scraper().run()
        import fake_canvas

        original = fake_canvas.FILES[101][1]["updated_at"]
        fake_canvas.FILES[101][1]["updated_at"] = "2026-04-01T00:00:00Z"
        self.addCleanup(fake_canvas.FILES[101][1].__setitem__, "updated_at", original)

        again = self.make_scraper().run()
        self.assertEqual(again.downloaded, 1)
        # 更新是覆寫原檔，不該多出 -2 的副本
        self.assertFalse((self.course_dir / "files" / "講義" / "課程大綱-2.pdf").exists())


class TestOptions(SyncTestCase):
    def test_extension_filter(self):
        run = self.make_scraper(extensions=("zip",)).run()
        self.assertEqual(run.downloaded, 1)
        self.assertTrue((self.course_dir / "files" / "講義" / "補充教材.zip").exists())
        self.assertFalse((self.course_dir / "files" / "講義" / "課程大綱.pdf").exists())

    def test_max_file_size_filter(self):
        run = self.make_scraper(max_file_mb=0.00005).run()  # 約 52 bytes
        self.assertEqual(run.downloaded, 0)
        self.assertTrue(any("超過大小上限" in f for f in run.failures))

    def test_only_sections(self):
        self.make_scraper(sections=("info", "assignments")).run()
        data = json.loads((self.course_dir / "course.json").read_text(encoding="utf-8"))
        self.assertIn("assignments", data)
        self.assertNotIn("files", data)
        self.assertFalse((self.course_dir / "files").exists())

    def test_dry_run_writes_nothing(self):
        run = self.make_scraper(dry_run=True).run()
        self.assertEqual(run.downloaded, 4)  # 回報「會下載幾個」
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
