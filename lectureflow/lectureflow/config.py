"""Runtime configuration, read once at import time from the environment.

A local ``.env`` file next to the project root is loaded first so that a user
who filled in ``.env.example`` does not also have to export shell variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"


def load_dotenv(path: Path) -> None:
    """Populate ``os.environ`` from a KEY=VALUE file without overwriting."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # Real environment variables win over the file.
        os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    text_provider: str = "auto"
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: str = "low"
    openai_text_model: str = "gpt-4o-mini"
    openai_text_base_url: str = "https://api.openai.com/v1"

    transcribe_model: str = "gpt-4o-mini-transcribe"
    transcribe_base_url: str = "https://api.openai.com/v1"
    transcribe_api_key: str = ""
    transcribe_language: str = "zh"

    max_context_chars: int = 90_000
    max_upload_bytes: int = 25 * 1024 * 1024
    request_timeout: float = 90.0
    max_retries: int = 3

    host: str = "127.0.0.1"
    port: int = 8000

    # Filled in by ``resolve_text_provider`` below.
    resolved_text_provider: str = field(default="none")

    @property
    def text_model(self) -> str:
        if self.resolved_text_provider == "anthropic":
            return self.anthropic_model
        if self.resolved_text_provider == "openai":
            return self.openai_text_model
        return ""

    @property
    def transcribe_key(self) -> str:
        return self.transcribe_api_key or self.openai_api_key

    @property
    def transcribe_ready(self) -> bool:
        # A self-hosted OpenAI-compatible endpoint usually needs no key at all.
        return bool(self.transcribe_key) or not self.transcribe_base_url.startswith(
            "https://api.openai.com"
        )

    @property
    def text_ready(self) -> bool:
        return self.resolved_text_provider != "none"


def resolve_text_provider(requested: str, *, anthropic_key: str, openai_key: str) -> str:
    """Pick the text provider, honouring an explicit request when it is usable."""
    requested = (requested or "auto").lower()
    if requested == "anthropic":
        return "anthropic" if anthropic_key else "none"
    if requested == "openai":
        return "openai" if openai_key else "none"
    if anthropic_key:
        return "anthropic"
    if openai_key:
        return "openai"
    return "none"


def load_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env")

    anthropic_key = _env("ANTHROPIC_API_KEY")
    openai_key = _env("OPENAI_API_KEY")
    requested = _env("LECTUREFLOW_TEXT_PROVIDER", "auto")

    return Settings(
        anthropic_api_key=anthropic_key,
        openai_api_key=openai_key,
        text_provider=requested,
        anthropic_model=_env("LECTUREFLOW_ANTHROPIC_MODEL", "claude-opus-5"),
        anthropic_effort=_env("LECTUREFLOW_ANTHROPIC_EFFORT", "low"),
        openai_text_model=_env("LECTUREFLOW_OPENAI_TEXT_MODEL", "gpt-4o-mini"),
        openai_text_base_url=_env(
            "LECTUREFLOW_OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/"),
        transcribe_model=_env("LECTUREFLOW_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
        transcribe_base_url=_env(
            "LECTUREFLOW_TRANSCRIBE_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/"),
        transcribe_api_key=_env("LECTUREFLOW_TRANSCRIBE_API_KEY"),
        transcribe_language=_env("LECTUREFLOW_LANGUAGE", "zh"),
        max_context_chars=_env_int("LECTUREFLOW_MAX_CONTEXT_CHARS", 90_000),
        max_upload_bytes=_env_int("LECTUREFLOW_MAX_UPLOAD_BYTES", 25 * 1024 * 1024),
        request_timeout=float(_env_int("LECTUREFLOW_TIMEOUT_SECONDS", 90)),
        max_retries=_env_int("LECTUREFLOW_MAX_RETRIES", 3),
        host=_env("LECTUREFLOW_HOST", "127.0.0.1"),
        port=_env_int("LECTUREFLOW_PORT", 8000),
        resolved_text_provider=resolve_text_provider(
            requested, anthropic_key=anthropic_key, openai_key=openai_key
        ),
    )
