"""指令列層測試：參數有真的接到設定、輸出與離開碼正確。"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _support  # noqa: F401

from fake_canvas import TOKEN, FakeCanvas

from ntucool.cli import main


class TestCli(unittest.TestCase):
    def setUp(self):
        self.server = FakeCanvas()
        self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, *args, token=TOKEN):
        out, err = io.StringIO(), io.StringIO()
        argv = ["--token", token, "--base-url", self.server.base_url, *args]
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_no_command_prints_help(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("自動擷取 NTU COOL", out)

    def test_whoami(self):
        code, out, _ = self.run_cli("whoami")
        self.assertEqual(code, 0)
        self.assertIn("測試同學", out)

    def test_whoami_with_bad_token_exits_3(self):
        code, _, err = self.run_cli("whoami", token="wrong")
        self.assertEqual(code, 3)
        self.assertIn("權杖", err)

    def test_missing_token_exits_2(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--token", "", "--base-url", self.server.base_url, "--config", str(Path(self.tmp.name) / "none.json"), "whoami"])
        self.assertEqual(code, 2)

    def test_courses_json(self):
        code, out, _ = self.run_cli("courses", "--json")
        self.assertEqual(code, 0)
        courses = json.loads(out)
        self.assertEqual([c["id"] for c in courses], [101, 202])

    def test_courses_table_filtered(self):
        code, out, _ = self.run_cli("courses", "-c", "物理")
        self.assertEqual(code, 0)
        self.assertIn("普通物理學", out)
        self.assertNotIn("資料結構", out)
        self.assertIn("共 1 門課程", out)

    def test_sync_json_output_and_files(self):
        out_dir = Path(self.tmp.name) / "data"
        code, out, _ = self.run_cli("sync", "-o", str(out_dir), "-c", "CSIE1212", "--ext", "pdf", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["courses"][0]["downloaded"], 3)
        self.assertTrue((out_dir / "CSIE1212-資料結構與演算法-101" / "course.md").is_file())
        self.assertFalse(any(out_dir.rglob("*.zip")))

    def test_sync_skip_files(self):
        out_dir = Path(self.tmp.name) / "info-only"
        code, out, _ = self.run_cli("sync", "-o", str(out_dir), "--skip-files", "-c", "101")
        self.assertEqual(code, 0)
        self.assertIn("完成", out)
        self.assertFalse((out_dir / "CSIE1212-資料結構與演算法-101" / "files").exists())

    def test_global_flags_work_after_the_subcommand(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["whoami", "--token", TOKEN, "--base-url", self.server.base_url, "-v"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("測試同學", out.getvalue())

    def test_flags_before_the_subcommand_are_not_overwritten(self):
        out_dir = Path(self.tmp.name) / "quiet"
        code, out, _ = self.run_cli("-q", "sync", "-o", str(out_dir), "-c", "101")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")
        self.assertTrue((out_dir / "README.md").is_file())

    def test_init_creates_template_and_refuses_overwrite(self):
        path = Path(self.tmp.name) / "conf.json"
        code, out, _ = self.run_cli("init", "--path", str(path))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["base_url"], "https://cool.ntu.edu.tw")
        code, _, err = self.run_cli("init", "--path", str(path))
        self.assertEqual(code, 1)
        self.assertIn("已存在", err)


if __name__ == "__main__":
    unittest.main()
