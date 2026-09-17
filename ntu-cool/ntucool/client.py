"""Canvas REST API 用戶端（只用標準函式庫，不需要安裝任何套件）。"""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import __version__
from .errors import ApiError, AuthError, ForbiddenError, NotFoundError, RateLimitError

USER_AGENT = f"ntucool/{__version__} (+https://github.com/yuliangz777-cmyk/Vprac)"

_LINK_RE = re.compile(r'<(?P<url>[^>]+)>\s*;\s*rel="(?P<rel>[^"]+)"')

RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def bearer_header(token: str | None) -> str:
    """組出 Authorization 標頭。

    HTTP 標頭只吃 latin-1，所以權杖裡混到中文或全形字元時要在這裡講清楚，
    而不是讓 http.client 在底層丟 UnicodeEncodeError。
    """
    token = (token or "").strip()
    if not token:
        raise AuthError("沒有提供存取權杖")
    try:
        token.encode("latin-1")
    except UnicodeEncodeError:
        raise AuthError(
            "權杖含有不合法的字元（可能複製到多餘的中文或全形符號），請重新複製一次"
        ) from None
    return f"Bearer {token}"


def parse_link_header(value: str | None) -> dict[str, str]:
    """把 Canvas 的 `Link` 標頭解析成 {rel: url}。"""
    if not value:
        return {}
    return {m.group("rel"): m.group("url") for m in _LINK_RE.finditer(value)}


def encode_params(params: dict | None) -> str:
    """Canvas 的陣列參數要寫成 `include[]=a&include[]=b`。"""
    if not params:
        return ""
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            name = key if key.endswith("[]") else f"{key}[]"
            pairs.extend((name, str(v)) for v in value)
        elif isinstance(value, bool):
            pairs.append((key, "true" if value else "false"))
        else:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs)


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self):
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))


class CanvasClient:
    """薄薄一層 Canvas API 包裝：自動重試、分頁、限流退避。"""

    def __init__(
        self,
        api_root: str,
        token: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 4,
        per_page: int = 100,
        opener=None,
        sleep=time.sleep,
        logger=None,
    ):
        self.api_root = api_root.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.per_page = per_page
        self._opener = opener or urllib.request.build_opener()
        self._sleep = sleep
        self._log = logger or (lambda *_: None)
        self.request_count = 0

    # ---- 低階 ------------------------------------------------------------
    def _url(self, path: str, params: dict | None = None) -> str:
        url = path if path.startswith("http") else f"{self.api_root}/{path.lstrip('/')}"
        query = encode_params(params)
        if query:
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        return url

    def _raise_for_status(self, status: int, url: str, body: bytes):
        text = body.decode("utf-8", "replace")[:500]
        lowered = text.lower()
        if status == 401:
            raise AuthError("存取權杖無效或已過期（401）", status=status, url=url, body=text)
        if status == 403:
            if "rate limit" in lowered:
                raise RateLimitError("被 Canvas 限流（403 Rate Limit Exceeded）", status=status, url=url, body=text)
            raise ForbiddenError("沒有權限讀取此資源（403）", status=status, url=url, body=text)
        if status == 404:
            raise NotFoundError("資源不存在（404）", status=status, url=url, body=text)
        if status == 429:
            raise RateLimitError("請求過於頻繁（429）", status=status, url=url, body=text)
        raise ApiError(f"API 回應 {status}", status=status, url=url, body=text)

    def _auth_header(self) -> str:
        return bearer_header(self.token)

    def request(self, path: str, *, params: dict | None = None, method: str = "GET", raw: bool = False) -> Response:
        """送出一次請求，失敗時依退避策略重試。"""
        url = self._url(path, params)
        authorization = self._auth_header()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, method=method)
            req.add_header("Authorization", authorization)
            req.add_header("User-Agent", USER_AGENT)
            if not raw:
                req.add_header("Accept", "application/json")
            try:
                self.request_count += 1
                with self._opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    headers = dict(resp.headers.items())
                    self._respect_rate_limit(headers)
                    return Response(resp.status, headers, body)
            except urllib.error.HTTPError as exc:  # 4xx / 5xx
                body = exc.read() if hasattr(exc, "read") else b""
                if exc.code in RETRY_STATUSES and attempt < self.max_retries:
                    delay = self._retry_delay(attempt, exc.headers)
                    self._log(f"  · {exc.code} {url} → {delay:.1f}s 後重試")
                    last_error = exc
                    self._sleep(delay)
                    continue
                self._raise_for_status(exc.code, url, body)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < self.max_retries:
                    delay = self._retry_delay(attempt, None)
                    self._log(f"  · 連線失敗（{exc}）→ {delay:.1f}s 後重試")
                    last_error = exc
                    self._sleep(delay)
                    continue
                raise ApiError(f"連線失敗：{exc}", url=url) from exc
        raise ApiError(f"重試 {self.max_retries} 次仍失敗：{last_error}", url=url)

    def _retry_delay(self, attempt: int, headers) -> float:
        if headers is not None:
            retry_after = headers.get("Retry-After") if hasattr(headers, "get") else None
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass
        return min(30.0, (2**attempt)) + random.random() * 0.3

    def _respect_rate_limit(self, headers: dict):
        """Canvas 會回報剩餘額度，快用完時主動放慢，避免整包 403。"""
        remaining = headers.get("X-Rate-Limit-Remaining")
        if remaining is None:
            return
        try:
            value = float(remaining)
        except ValueError:
            return
        if value < 100:
            self._log(f"  · 額度僅剩 {value:.0f}，暫停 1 秒")
            self._sleep(1.0)

    # ---- 高階 ------------------------------------------------------------
    def get(self, path: str, params: dict | None = None):
        return self.request(path, params=params).json()

    def paginate(self, path: str, params: dict | None = None, *, max_pages: int = 200):
        """走訪所有分頁（跟著 `Link: rel="next"`），逐筆吐出項目。"""
        params = dict(params or {})
        params.setdefault("per_page", self.per_page)
        url: str | None = self._url(path, params)
        seen = 0
        while url and seen < max_pages:
            resp = self.request(url)
            seen += 1
            data = resp.json()
            if isinstance(data, dict):
                # 少數端點把清單包在物件裡
                data = next((v for v in data.values() if isinstance(v, list)), [data])
            for item in data or []:
                yield item
            url = parse_link_header(resp.headers.get("Link") or resp.headers.get("link")).get("next")

    def paginate_safe(self, path: str, params: dict | None = None, *, label: str = "") -> list:
        """跟 `paginate` 一樣，但權限不足／不存在時回傳空清單而不是中斷。"""
        try:
            return list(self.paginate(path, params))
        except (ForbiddenError, NotFoundError) as exc:
            self._log(f"  · 略過{label or path}（{exc}）")
            return []

    def whoami(self) -> dict:
        return self.get("users/self/profile")

    def download(self, url: str, dest, *, expected_size: int | None = None, chunk: int = 1 << 16) -> int:
        """下載檔案到 `dest`（先寫暫存檔再改名，中斷不會留下半個檔）。"""
        dest = os.fspath(dest)
        tmp = f"{dest}.part"
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url)
                # 檔案網址已含簽章；但同網域的請求帶上權杖也無妨。
                if url.startswith(self.api_root.rsplit("/api/", 1)[0]):
                    req.add_header("Authorization", self._auth_header())
                req.add_header("User-Agent", USER_AGENT)
                self.request_count += 1
                written = 0
                with self._opener.open(req, timeout=self.timeout) as resp, open(tmp, "wb") as fh:
                    while True:
                        block = resp.read(chunk)
                        if not block:
                            break
                        fh.write(block)
                        written += len(block)
                if expected_size and written != expected_size:
                    raise ApiError(f"下載大小不符（預期 {expected_size}，實得 {written}）", url=url)
                os.replace(tmp, dest)
                return written
            except Exception as exc:  # noqa: BLE001 — 下載失敗一律退避重試
                last_error = exc
                if os.path.exists(tmp):
                    os.unlink(tmp)
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in RETRY_STATUSES:
                    raise ApiError(f"下載失敗（{exc.code}）：{url}", status=exc.code, url=url) from exc
                if attempt < self.max_retries:
                    self._sleep(self._retry_delay(attempt, None))
                    continue
                raise ApiError(f"下載失敗：{exc}", url=url) from exc
        raise ApiError(f"下載失敗：{last_error}", url=url)
