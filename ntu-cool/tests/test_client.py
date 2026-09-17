"""用本機假 Canvas 站台測試 HTTP 層：分頁、重試、錯誤分類、下載。"""

import tempfile
import unittest
from pathlib import Path

import _support  # noqa: F401

from fake_canvas import PDF_BYTES, TOKEN, FakeCanvas

from ntucool.client import CanvasClient, encode_params, parse_link_header
from ntucool.errors import ApiError, AuthError, ForbiddenError, RateLimitError


class TestHelpers(unittest.TestCase):
    def test_parse_link_header(self):
        links = parse_link_header('<https://a/1?page=2>; rel="next",<https://a/1?page=9>; rel="last"')
        self.assertEqual(links["next"], "https://a/1?page=2")
        self.assertEqual(parse_link_header(None), {})

    def test_encode_array_params(self):
        self.assertEqual(encode_params({"include": ["term", "teachers"]}), "include%5B%5D=term&include%5B%5D=teachers")
        self.assertEqual(encode_params({"a": True, "b": None}), "a=true")


class TestClient(unittest.TestCase):
    def setUp(self):
        self.server = FakeCanvas(flaky_failures=2)
        self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.slept = []
        self.client = CanvasClient(
            self.server.api_root, TOKEN, max_retries=3, sleep=self.slept.append
        )

    def test_pagination_follows_link_header(self):
        courses = list(self.client.paginate("courses", {"enrollment_state": "active"}))
        self.assertEqual([c["id"] for c in courses], [101, 202, 303])

    def test_retries_on_server_error_then_succeeds(self):
        result = self.client.get("flaky")
        self.assertTrue(result["ok"])
        self.assertEqual(result["hits"], 3)  # 兩次 500 + 一次成功
        self.assertEqual(len(self.slept), 2)

    def test_gives_up_after_max_retries(self):
        client = CanvasClient(self.server.api_root, TOKEN, max_retries=1, sleep=self.slept.append)
        with self.assertRaises(ApiError):
            client.get("flaky")

    def test_bad_token_raises_auth_error(self):
        client = CanvasClient(self.server.api_root, "wrong", sleep=self.slept.append)
        with self.assertRaises(AuthError):
            client.whoami()

    def test_rate_limit_is_distinguished_from_forbidden(self):
        with self.assertRaises(RateLimitError):
            self.client.get("ratelimited")
        with self.assertRaises(ForbiddenError):
            self.client.get("courses/202/files")

    def test_paginate_safe_swallows_forbidden(self):
        self.assertEqual(self.client.paginate_safe("courses/202/files", label="檔案"), [])

    def test_download_writes_file_and_cleans_up_partials(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "sub" / "a.pdf"
            written = self.client.download(
                f"{self.server.base_url}/files/download/5001", dest, expected_size=len(PDF_BYTES)
            )
            self.assertEqual(written, len(PDF_BYTES))
            self.assertEqual(dest.read_bytes(), PDF_BYTES)
            self.assertFalse((Path(tmp) / "sub" / "a.pdf.part").exists())

    def test_truncated_download_is_retried_then_recovers(self):
        self.server.truncate_next_download(5002)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "b.pdf"
            written = self.client.download(
                f"{self.server.base_url}/files/download/5002", dest, expected_size=len(PDF_BYTES)
            )
            self.assertEqual(written, len(PDF_BYTES))
            self.assertEqual(dest.read_bytes(), PDF_BYTES)

    def test_missing_file_download_fails_without_leaving_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "missing.pdf"
            with self.assertRaises(ApiError):
                self.client.download(f"{self.server.base_url}/files/download/9999", dest)
            self.assertFalse(dest.exists())
            self.assertFalse(Path(f"{dest}.part").exists())


if __name__ == "__main__":
    unittest.main()
