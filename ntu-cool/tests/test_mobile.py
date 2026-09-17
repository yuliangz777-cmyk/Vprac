"""手機路徑測試：安裝腳本真的把檔案放對地方，捷徑入口真的能同步。"""

import importlib.util
import io
import os
import stat
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import _support  # noqa: F401

from fake_canvas import TOKEN, FakeCanvas

from ntucool import mobile

ROOT = Path(__file__).resolve().parents[1]


def load_ios_setup():
    """ios_setup.py 不在套件裡（它要能單獨下載執行），所以直接從路徑載入。"""
    spec = importlib.util.spec_from_file_location("ios_setup", ROOT / "mobile" / "ios_setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_repo_tarball(path: Path) -> Path:
    """做一個跟 GitHub 下載下來一模一樣結構的壓縮檔。"""
    archive = path / "repo.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        prefix = "Vprac-main/ntu-cool"
        for source in sorted((ROOT / "ntucool").glob("*.py")):
            tar.add(source, arcname=f"{prefix}/ntucool/{source.name}")
        for name in ("ios_sync.py", "ios_web.py", "ios_setup.py"):
            tar.add(ROOT / "mobile" / name, arcname=f"{prefix}/mobile/{name}")
        tar.add(ROOT / "README.md", arcname=f"{prefix}/README.md")          # 不該被安裝
        tar.add(ROOT / "tests" / "test_units.py", arcname=f"{prefix}/tests/test_units.py")
    return archive


class TestPathMapping(unittest.TestCase):
    def setUp(self):
        self.setup = load_ios_setup()

    def test_maps_package_and_launchers_only(self):
        base = "Vprac-branch/ntu-cool"
        self.assertEqual(self.setup.target_for(f"{base}/ntucool/cli.py"), "ntucool/cli.py")
        self.assertEqual(self.setup.target_for(f"{base}/mobile/ios_sync.py"), "ios_sync.py")
        self.assertEqual(self.setup.target_for(f"{base}/mobile/ios_web.py"), "ios_web.py")
        self.assertIsNone(self.setup.target_for(f"{base}/README.md"))
        self.assertIsNone(self.setup.target_for(f"{base}/tests/test_units.py"))
        self.assertIsNone(self.setup.target_for("Vprac-branch/index.html"))

    def test_rejects_path_traversal(self):
        self.assertIsNone(self.setup.target_for("Vprac-branch/ntu-cool/../../etc/passwd"))

    def test_archive_url(self):
        self.assertEqual(
            self.setup.archive_url("owner/repo", "main"),
            "https://codeload.github.com/owner/repo/tar.gz/refs/heads/main",
        )
        # 分支名含斜線時也要組得出正確網址
        self.assertEqual(
            self.setup.archive_url("owner/repo", "feature/x"),
            "https://codeload.github.com/owner/repo/tar.gz/refs/heads/feature/x",
        )

    def test_default_ref_is_main(self):
        self.assertEqual(self.setup.DEFAULT_REF, "main")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.setup = load_ios_setup()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def test_installs_package_and_launcher(self):
        archive = build_repo_tarball(self.tmp_path)
        dest = self.tmp_path / "install"
        count = self.setup.install(dest, archive.read_bytes())
        self.assertGreater(count, 5)
        self.assertTrue((dest / "ntucool" / "cli.py").is_file())
        self.assertTrue((dest / "ntucool" / "mobile.py").is_file())
        self.assertTrue((dest / "ios_sync.py").is_file())
        self.assertTrue((dest / "ios_web.py").is_file())
        self.assertFalse((dest / "README.md").exists())
        self.assertFalse((dest / "tests").exists())

    def test_reinstall_overwrites_in_place(self):
        archive = build_repo_tarball(self.tmp_path)
        dest = self.tmp_path / "install"
        self.setup.install(dest, archive.read_bytes())
        (dest / "ntucool" / "cli.py").write_text("stale", encoding="utf-8")
        self.setup.install(dest, archive.read_bytes())
        self.assertIn("argparse", (dest / "ntucool" / "cli.py").read_text(encoding="utf-8"))

    def test_rejects_archive_without_the_package(self):
        empty = self.tmp_path / "empty.tar.gz"
        with tarfile.open(empty, "w:gz") as tar:
            info = tarfile.TarInfo("other/thing.py")
            tar.addfile(info, io.BytesIO(b""))
        with self.assertRaises(ValueError):
            self.setup.install(self.tmp_path / "x", empty.read_bytes())


class TestToken(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.token_file = Path(self.tmp.name) / ".ntucool-token"

    def test_save_and_read_with_tight_permissions(self):
        mobile.save_token("  abc123\n", self.token_file)
        self.assertEqual(self.token_file.read_text(encoding="utf-8"), "abc123\n")
        mode = stat.S_IMODE(self.token_file.stat().st_mode)
        self.assertEqual(mode, 0o600)
        with mock.patch.dict(os.environ, {"NTU_COOL_TOKEN_FILE": str(self.token_file)}):
            self.assertEqual(mobile.read_token(), "abc123")
            self.assertEqual(mobile.token_path(), self.token_file)

    def test_missing_token_file_reads_as_empty(self):
        self.assertEqual(mobile.read_token(Path(self.tmp.name) / "nope"), "")


class TestMobileEntryPoint(unittest.TestCase):
    def setUp(self):
        self.server = FakeCanvas()
        self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.token_file = self.home / ".ntucool-token"
        self.out = self.home / "NTUCool"

    def env(self, **extra):
        return {
            "NTU_COOL_TOKEN_FILE": str(self.token_file),
            "NTU_COOL_BASE_URL": self.server.base_url,
            "NTU_COOL_OUT": str(self.out),
            **extra,
        }

    def test_sync_downloads_into_the_documents_folder(self):
        mobile.save_token(TOKEN, self.token_file)
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env()), redirect_stdout(out):
            code = mobile.main([])
        self.assertEqual(code, 0, out.getvalue())
        self.assertTrue((self.out / "README.md").is_file())
        self.assertTrue(any(self.out.rglob("week1-投影片.pdf")))
        self.assertIn("檔案", out.getvalue())

    def test_extra_arguments_are_passed_through(self):
        mobile.save_token(TOKEN, self.token_file)
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env()), redirect_stdout(out):
            code = mobile.main(["--ext", "zip"])
        self.assertEqual(code, 0)
        downloaded = [p.suffix for p in self.out.rglob("files/**/*") if p.is_file()]
        self.assertEqual(downloaded, [".zip"])  # 報表照樣產生，但只下載 zip

    def test_web_launcher_serves_the_interface_on_localhost(self):
        """手機上的網頁介面：用 127.0.0.1，Safari 才會把它當安全來源。"""
        import threading
        import urllib.request

        from ntucool.config import load_config
        from ntucool.web import create_server

        mobile.save_token(TOKEN, self.token_file)
        with mock.patch.dict(os.environ, self.env()):
            self.assertTrue(mobile.use_saved_token())
            config = load_config(overrides={"out_dir": mobile.data_dir()})
            httpd, url = create_server(config, host="127.0.0.1", port=0)
        try:
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            self.assertTrue(url.startswith("http://127.0.0.1:"))
            with urllib.request.urlopen(url, timeout=10) as resp:
                page = resp.read().decode("utf-8")
            self.assertIn("NTU COOL 同步", page)
            self.assertIn("apple-touch-icon", page)   # 加到主畫面要有 icon
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_token_from_the_web_login_also_counts(self):
        """在網頁上登入（寫進 .env）之後，捷徑同步也要認得。"""
        env_file = self.home / "user.env"
        env_file.write_text(f"NTU_COOL_TOKEN={TOKEN}\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"NTU_COOL_BASE_URL": self.server.base_url}, clear=True), \
             mock.patch("ntucool.mobile.token_path", return_value=self.home / "no-such-token"), \
             mock.patch("ntucool.config.ENV_CANDIDATES", (env_file,)):
            self.assertTrue(mobile.use_saved_token())

    def test_without_a_token_it_says_how_to_fix_it(self):
        out = io.StringIO()
        env = self.env()
        env.pop("NTU_COOL_TOKEN_FILE")
        with mock.patch.dict(os.environ, {**env, "NTU_COOL_TOKEN_FILE": str(self.home / "missing")}, clear=False):
            with mock.patch.dict(os.environ, {"NTU_COOL_TOKEN": ""}), redirect_stdout(out):
                code = mobile.main([])
        self.assertEqual(code, 2)
        self.assertIn("ios_setup.py", out.getvalue())
        self.assertIn("ios_web.py", out.getvalue())   # 兩條路都要講

    def test_data_dir_prefers_documents(self):
        documents = self.home / "Documents"
        documents.mkdir()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(Path, "home", lambda: self.home):
            self.assertEqual(mobile.data_dir(), documents / "NTUCool")


class TestSetupEndToEnd(unittest.TestCase):
    def setUp(self):
        self.setup = load_ios_setup()
        self.server = FakeCanvas()
        self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def test_full_offline_install_then_sync(self):
        archive = build_repo_tarball(self.tmp_path)
        dest = self.tmp_path / "ntucool-install"
        token_file = dest / ".ntucool-token"
        env = {
            "NTU_COOL_TOKEN_FILE": str(token_file),
            "NTU_COOL_BASE_URL": self.server.base_url,
            "NTU_COOL_OUT": str(self.tmp_path / "NTUCool"),
        }
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            code = self.setup.main(["--dir", str(dest), "--archive", str(archive), "--token", TOKEN])
        self.assertEqual(code, 0, out.getvalue())
        # 權杖驗證真的打了 API，而且印出捷徑指令
        self.assertIn("測試同學", out.getvalue())
        self.assertIn(str(dest / "ios_sync.py"), out.getvalue())
        self.assertEqual(stat.S_IMODE(token_file.stat().st_mode), 0o600)

        # 裝完之後，捷徑那一行指令要真的能跑
        sync_out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(sync_out):
            self.assertEqual(mobile.main([]), 0)
        self.assertTrue((Path(env["NTU_COOL_OUT"]) / "README.md").is_file())

    def test_bad_token_is_reported_before_the_shortcut_is_set_up(self):
        archive = build_repo_tarball(self.tmp_path)
        dest = self.tmp_path / "install2"
        env = {
            "NTU_COOL_TOKEN_FILE": str(dest / ".ntucool-token"),
            "NTU_COOL_BASE_URL": self.server.base_url,
        }
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            code = self.setup.main(["--dir", str(dest), "--archive", str(archive), "--token", "wrong"])
        self.assertEqual(code, 3)
        self.assertIn("權杖驗證失敗", out.getvalue())
        self.assertNotIn("加入主畫面", out.getvalue())


if __name__ == "__main__":
    unittest.main()
