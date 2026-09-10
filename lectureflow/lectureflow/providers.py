"""Transcription and text-generation backends.

Two things matter for a live lecture: every call reuses one warm HTTP client
(a fresh TLS handshake per 8-second chunk is most of the latency budget), and
every call retries the transient failures that would otherwise punch a hole in
the transcript.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from .config import Settings

RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class ProviderError(Exception):
    """A failure worth showing the user, carrying an HTTP-ish status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def describe_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text[:400] or f"HTTP {response.status_code}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:400]
    if isinstance(error, str):
        return error[:400]
    return json.dumps(payload)[:400]


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int,
    **kwargs: Any,
) -> httpx.Response:
    delay = 0.8
    last: ProviderError | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = ProviderError(504, f"連線失敗：{exc}")
        else:
            if response.status_code < 400:
                return response
            detail = describe_response(response)
            if response.status_code not in RETRYABLE_STATUS:
                raise ProviderError(response.status_code, detail)
            last = ProviderError(response.status_code, detail)
        if attempt < max_retries:
            await asyncio.sleep(delay)
            delay *= 2
    assert last is not None
    raise last


class Transcriber:
    """OpenAI-compatible ``/audio/transcriptions``.

    Pointing ``LECTUREFLOW_TRANSCRIBE_BASE_URL`` at a local whisper.cpp or
    faster-whisper server keeps the whole pipeline offline and free.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    async def transcribe(
        self, audio: bytes, filename: str, content_type: str, *, hint: str = ""
    ) -> str:
        settings = self.settings
        headers = {}
        if settings.transcribe_key:
            headers["Authorization"] = f"Bearer {settings.transcribe_key}"

        data: dict[str, str] = {
            "model": settings.transcribe_model,
            "response_format": "json",
        }
        if settings.transcribe_language:
            data["language"] = settings.transcribe_language
        if hint.strip():
            # Priming with recent text markedly improves proper nouns.
            data["prompt"] = hint.strip()[-450:]

        response = await request_with_retry(
            self.client,
            "POST",
            f"{settings.transcribe_base_url}/audio/transcriptions",
            max_retries=settings.max_retries,
            headers=headers,
            data=data,
            files={"file": (filename, audio, content_type)},
        )
        payload = response.json()
        return str(payload.get("text") or "").strip()


class OpenAIText:
    """Chat Completions - also what most local/self-hosted servers speak."""

    name = "openai"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    @property
    def model(self) -> str:
        return self.settings.openai_text_model

    def _body(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def complete(self, system: str, user: str, *, max_tokens: int = 4000) -> str:
        response = await request_with_retry(
            self.client,
            "POST",
            f"{self.settings.openai_text_base_url}/chat/completions",
            max_retries=self.settings.max_retries,
            headers=self._headers(),
            json=self._body(system, user, max_tokens),
        )
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError(502, "文字模型沒有回傳內容。")
        return str(choices[0].get("message", {}).get("content") or "").strip()

    async def stream(
        self, system: str, user: str, *, max_tokens: int = 4000
    ) -> AsyncIterator[str]:
        body = self._body(system, user, max_tokens) | {"stream": True}
        async with self.client.stream(
            "POST",
            f"{self.settings.openai_text_base_url}/chat/completions",
            headers=self._headers(),
            json=body,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise ProviderError(response.status_code, describe_response(response))
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for choice in event.get("choices") or []:
                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        yield piece


class AnthropicText:
    """Claude via the official SDK.

    Server-side refusal fallbacks are requested when the installed SDK and the
    account support them; the flag is dropped permanently on the first refusal
    of the parameter itself so an older SDK still works.
    """

    name = "anthropic"
    _FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any = None
        self._supports_effort = True
        self._supports_fallbacks = True

    @property
    def model(self) -> str:
        return self.settings.anthropic_model

    def _sdk(self) -> Any:
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:  # pragma: no cover - depends on install
                raise ProviderError(
                    503,
                    "缺少 anthropic 套件，請執行 pip install -r requirements.txt。",
                ) from exc
            self._client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    def _kwargs(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self._supports_effort and self.settings.anthropic_effort:
            kwargs["output_config"] = {"effort": self.settings.anthropic_effort}
        if self._supports_fallbacks:
            kwargs["betas"] = [self._FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        return kwargs

    def _degrade(self, error: Exception) -> bool:
        """Drop an optional parameter the SDK or account rejected. True to retry."""
        text = str(error)
        if self._supports_fallbacks and (
            "fallback" in text or "betas" in text or "beta" in text
        ):
            self._supports_fallbacks = False
            return True
        if self._supports_effort and ("output_config" in text or "effort" in text):
            self._supports_effort = False
            return True
        if self._supports_fallbacks:
            self._supports_fallbacks = False
            return True
        if self._supports_effort:
            self._supports_effort = False
            return True
        return False

    def _messages(self, kwargs: dict[str, Any]) -> Any:
        client = self._sdk()
        return client.beta.messages if "betas" in kwargs else client.messages

    @staticmethod
    def _text_of(message: Any) -> str:
        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) or "unknown"
            raise ProviderError(422, f"模型拒絕回覆此請求（{category}）。")
        parts = [
            block.text
            for block in getattr(message, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(parts).strip()

    async def complete(self, system: str, user: str, *, max_tokens: int = 8000) -> str:
        import anthropic

        while True:
            kwargs = self._kwargs(system, user, max_tokens)
            try:
                message = await self._messages(kwargs).create(**kwargs)
            except (TypeError, anthropic.BadRequestError) as exc:
                if self._degrade(exc):
                    continue
                raise ProviderError(400, str(exc)) from exc
            except anthropic.APIStatusError as exc:
                raise ProviderError(exc.status_code, str(exc)) from exc
            except anthropic.APIConnectionError as exc:
                raise ProviderError(504, f"連線失敗：{exc}") from exc
            text = self._text_of(message)
            if not text:
                raise ProviderError(502, "文字模型沒有回傳可讀文字。")
            return text

    async def stream(
        self, system: str, user: str, *, max_tokens: int = 8000
    ) -> AsyncIterator[str]:
        import anthropic

        while True:
            kwargs = self._kwargs(system, user, max_tokens)
            try:
                async with self._messages(kwargs).stream(**kwargs) as stream:
                    async for piece in stream.text_stream:
                        yield piece
                    final = await stream.get_final_message()
                self._text_of(final)  # Surfaces a refusal after the stream ends.
                return
            except (TypeError, anthropic.BadRequestError) as exc:
                if self._degrade(exc):
                    continue
                raise ProviderError(400, str(exc)) from exc
            except anthropic.APIStatusError as exc:
                raise ProviderError(exc.status_code, str(exc)) from exc
            except anthropic.APIConnectionError as exc:
                raise ProviderError(504, f"連線失敗：{exc}") from exc


def build_text_provider(
    settings: Settings, client: httpx.AsyncClient
) -> AnthropicText | OpenAIText | None:
    if settings.resolved_text_provider == "anthropic":
        return AnthropicText(settings)
    if settings.resolved_text_provider == "openai":
        return OpenAIText(settings, client)
    return None
