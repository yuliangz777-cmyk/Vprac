"""設定載入：CLI 參數 > 環境變數 > .env > 設定檔 > 預設值。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from .errors import ConfigError

DEFAULT_BASE_URL = "https://cool.ntu.edu.tw"

#: 依序尋找的設定檔位置（找到第一個就停）。
CONFIG_CANDIDATES = (
    Path("ntucool.config.json"),
    Path(".ntucool.json"),
    Path.home() / ".config" / "ntucool" / "config.json",
)

#: 依序尋找的 .env 位置。
ENV_CANDIDATES = (Path(".env"), Path.home() / ".config" / "ntucool" / ".env")

ALL_SECTIONS = ("info", "syllabus", "files", "assignments", "announcements",
                "calendar", "modules", "pages")


@dataclass
class Config:
    """一次執行所需的全部設定。"""

    token: str = ""
    base_url: str = DEFAULT_BASE_URL
    out_dir: Path = Path("ntu-cool-data")
    enrollment_state: str = "active"
    terms: tuple[str, ...] = ()
    course_filters: tuple[str, ...] = ()
    sections: tuple[str, ...] = ALL_SECTIONS
    extensions: tuple[str, ...] = ()
    max_file_mb: float = 0.0  # 0 = 不限
    concurrency: int = 4
    timeout: float = 30.0
    max_retries: int = 4
    per_page: int = 100
    force: bool = False
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    source: str = "defaults"
    extra: dict = field(default_factory=dict)

    # ---- 衍生屬性 -------------------------------------------------------
    @property
    def api_root(self) -> str:
        return self.base_url.rstrip("/") + "/api/v1"

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * 1024 * 1024) if self.max_file_mb > 0 else 0

    def wants(self, section: str) -> bool:
        return section in self.sections

    def validate(self) -> "Config":
        if not self.token:
            raise ConfigError(
                "找不到存取權杖。請設定環境變數 NTU_COOL_TOKEN、寫進 .env，"
                "或執行 `ntucool init` 產生設定檔。取得方式見 README。"
            )
        try:
            self.token.encode("latin-1")
        except UnicodeEncodeError:
            raise ConfigError(
                "權杖含有不合法的字元（可能複製到多餘的中文或全形符號），請重新複製一次"
            ) from None
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigError(f"base_url 必須以 http(s):// 開頭，目前是：{self.base_url!r}")
        if self.enrollment_state not in ("active", "completed", "invited", "all"):
            raise ConfigError(f"不支援的 enrollment_state：{self.enrollment_state!r}")
        unknown = [s for s in self.sections if s not in ALL_SECTIONS]
        if unknown:
            raise ConfigError(f"不認得的擷取項目：{', '.join(unknown)}；可用：{', '.join(ALL_SECTIONS)}")
        if self.concurrency < 1:
            raise ConfigError("concurrency 至少要是 1")
        return self


def parse_env_file(text: str) -> dict[str, str]:
    """極簡 .env 解析：`KEY=VALUE`，支援 `export`、`#` 註解與引號。"""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _load_env_files(candidates=None) -> dict[str, str]:
    for path in ENV_CANDIDATES if candidates is None else candidates:
        try:
            if path.is_file():
                return parse_env_file(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return {}


def _load_config_file(path: Path | None, candidates=None) -> tuple[dict, str]:
    paths = [path] if path else list(CONFIG_CANDIDATES if candidates is None else candidates)
    for candidate in paths:
        if candidate and candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ConfigError(f"設定檔 {candidate} 不是合法 JSON：{exc}") from exc
            if not isinstance(data, dict):
                raise ConfigError(f"設定檔 {candidate} 最外層必須是物件")
            return data, str(candidate)
    if path:
        raise ConfigError(f"找不到設定檔：{path}")
    return {}, ""


def _as_tuple(value) -> tuple[str, ...]:
    """把 "a,b"、["a", "b, c"] 之類的寫法統一攤平成 tuple。"""
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else list(value)
    out: list[str] = []
    for item in items:
        out.extend(part.strip() for part in str(item).replace(",", " ").split() if part.strip())
    return tuple(out)


def load_config(
    *,
    config_path: Path | None = None,
    environ: dict[str, str] | None = None,
    overrides: dict | None = None,
    config_candidates=None,
    env_candidates=None,
) -> Config:
    """組出最終設定。`overrides` 是 CLI 傳進來的值（None 代表沒指定）。"""
    environ = dict(os.environ if environ is None else environ)
    file_data, file_source = _load_config_file(config_path, config_candidates)
    env_file = _load_env_files(env_candidates)

    def pick(*keys, default=None):
        """環境變數 > .env > 設定檔。"""
        for key in keys:
            if environ.get(key):
                return environ[key]
        for key in keys:
            if env_file.get(key):
                return env_file[key]
        for key in keys:
            short = key.removeprefix("NTU_COOL_").lower()
            if file_data.get(short) not in (None, ""):
                return file_data[short]
            if file_data.get(key) not in (None, ""):
                return file_data[key]
        return default

    token = str(pick("NTU_COOL_TOKEN", "CANVAS_TOKEN", default="") or "").strip()
    token_file = pick("NTU_COOL_TOKEN_FILE")
    if not token and token_file:
        # 讓權杖可以只存在一個檔案裡（手機、cron、systemd 都用得上）
        try:
            token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"讀不到權杖檔 {token_file}：{exc}") from exc

    cfg = Config(
        token=token,
        base_url=str(pick("NTU_COOL_BASE_URL", default=DEFAULT_BASE_URL)).strip(),
        out_dir=Path(str(pick("NTU_COOL_OUT", default="ntu-cool-data"))),
        enrollment_state=str(pick("NTU_COOL_ENROLLMENT_STATE", default="active")),
        terms=_as_tuple(pick("NTU_COOL_TERMS")),
        course_filters=_as_tuple(pick("NTU_COOL_COURSES")),
        sections=_as_tuple(pick("NTU_COOL_SECTIONS")) or ALL_SECTIONS,
        extensions=tuple(e.lower().lstrip(".") for e in _as_tuple(pick("NTU_COOL_EXTENSIONS"))),
        max_file_mb=float(pick("NTU_COOL_MAX_FILE_MB", default=0) or 0),
        concurrency=int(pick("NTU_COOL_CONCURRENCY", default=4) or 4),
        timeout=float(pick("NTU_COOL_TIMEOUT", default=30) or 30),
        max_retries=int(pick("NTU_COOL_MAX_RETRIES", default=4) or 4),
        source=file_source or ("env" if environ.get("NTU_COOL_TOKEN") else "defaults"),
    )

    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key in ("terms", "course_filters", "sections", "extensions"):
            value = _as_tuple(value)
            if not value:
                continue
            if key == "extensions":
                value = tuple(e.lower().lstrip(".") for e in value)
        if key == "out_dir":
            value = Path(value)
        cfg = replace(cfg, **{key: value})
    return cfg


#: 網頁介面「登入」之後把權杖寫在這裡；load_config 的 ENV_CANDIDATES 會自動找到它
USER_ENV_PATH = Path.home() / ".config" / "ntucool" / ".env"


def save_token_to_env(token: str, path: Path | None = None) -> Path:
    """把權杖寫進使用者層級的 .env，之後每次執行都會自動讀到。"""
    path = path or USER_ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.is_file():
        existing = parse_env_file(path.read_text(encoding="utf-8"))
    existing["NTU_COOL_TOKEN"] = token.strip()
    body = "".join(f"{key}={value}\n" for key, value in existing.items())
    path.write_text(body, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def clear_saved_token(path: Path | None = None) -> bool:
    """登出：把存起來的權杖移除（其他設定保留）。"""
    path = path or USER_ENV_PATH
    if not path.is_file():
        return False
    existing = parse_env_file(path.read_text(encoding="utf-8"))
    if existing.pop("NTU_COOL_TOKEN", None) is None:
        return False
    path.write_text("".join(f"{k}={v}\n" for k, v in existing.items()), encoding="utf-8")
    return True


def config_template(token: str = "") -> str:
    """`ntucool init` 寫出的設定檔內容。"""
    return json.dumps(
        {
            "token": token or "在此貼上 NTU COOL 存取權杖",
            "base_url": DEFAULT_BASE_URL,
            "out_dir": "ntu-cool-data",
            "enrollment_state": "active",
            "terms": [],
            "courses": [],
            "sections": list(ALL_SECTIONS),
            "extensions": [],
            "max_file_mb": 0,
            "concurrency": 4,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"
