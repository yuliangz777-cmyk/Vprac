import json
from contextlib import contextmanager
from typing import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient

from lectureflow.api import create_app
from lectureflow.config import Settings
from lectureflow.providers import ProviderError, request_with_retry


class StubTranscriber:
    def __init__(self, text="這是轉錄結果。", error=None):
        self.text = text
        self.error = error
        self.calls = []

    async def transcribe(self, audio, filename, content_type, *, hint=""):
        self.calls.append({"bytes": len(audio), "filename": filename, "hint": hint})
        if self.error:
            raise self.error
        return self.text


class StubText:
    def __init__(self, reply="", pieces=(), error=None):
        self.reply = reply
        self.pieces = pieces
        self.error = error
        self.calls = []

    async def complete(self, system, user, *, max_tokens=4000):
        self.calls.append(user)
        if self.error:
            raise self.error
        return self.reply

    async def stream(self, system, user, *, max_tokens=4000) -> AsyncIterator[str]:
        self.calls.append(user)
        for piece in self.pieces:
            yield piece
        if self.error:
            raise self.error


@contextmanager
def make_client(*, transcriber=None, text=None, settings=None):
    """A live app whose providers are swapped for stubs.

    The swap happens inside the lifespan context: entering the TestClient is
    what runs startup, and startup is what installs the real providers.
    """
    settings = settings or Settings(openai_api_key="test-key", resolved_text_provider="openai")
    with TestClient(create_app(settings)) as client:
        if transcriber is not None:
            client.app.state.transcriber = transcriber
        if text is not None:
            client.app.state.text = text
        yield client


class TestStatus:
    def test_reports_a_configured_install(self):
        with make_client() as client:
            body = client.get("/api/status").json()
        assert body["transcribe_ready"] is True
        assert body["text_ready"] is True
        assert body["text_provider"] == "openai"
        assert body["text_model"] == "gpt-4o-mini"

    def test_reports_an_unconfigured_install(self):
        with make_client(settings=Settings()) as client:
            body = client.get("/api/status").json()
        assert body["configured"] is False
        assert body["text_ready"] is False

    def test_health(self):
        with make_client() as client:
            assert client.get("/healthz").json()["status"] == "ok"


class TestTranscribe:
    def test_returns_cleaned_text(self):
        stub = StubTranscriber("  今天講供給曲線。 ")
        with make_client(transcriber=stub) as client:
            body = client.post(
                "/api/transcribe",
                files={"file": ("seg-0.wav", b"RIFFfake", "audio/wav")},
                data={"hint": "先前內容"},
            ).json()
        assert body == {"text": "今天講供給曲線。", "filtered": False}
        assert stub.calls[0]["hint"] == "先前內容"

    def test_flags_a_filtered_hallucination(self):
        with make_client(transcriber=StubTranscriber("謝謝觀看")) as client:
            body = client.post(
                "/api/transcribe", files={"file": ("a.wav", b"RIFFfake", "audio/wav")}
            ).json()
        assert body == {"text": "", "filtered": True}

    def test_rejects_empty_audio(self):
        with make_client(transcriber=StubTranscriber()) as client:
            assert client.post(
                "/api/transcribe", files={"file": ("a.wav", b"", "audio/wav")}
            ).status_code == 400

    def test_rejects_oversized_audio(self):
        settings = Settings(openai_api_key="k", max_upload_bytes=10)
        with make_client(transcriber=StubTranscriber(), settings=settings) as client:
            assert client.post(
                "/api/transcribe", files={"file": ("a.wav", b"x" * 64, "audio/wav")}
            ).status_code == 413

    def test_surfaces_a_provider_failure(self):
        stub = StubTranscriber(error=ProviderError(429, "rate limited"))
        with make_client(transcriber=stub) as client:
            response = client.post(
                "/api/transcribe", files={"file": ("a.wav", b"RIFF", "audio/wav")}
            )
        assert response.status_code == 502
        assert "rate limited" in response.json()["detail"]

    def test_requires_a_key(self):
        with make_client(settings=Settings()) as client:
            assert client.post(
                "/api/transcribe", files={"file": ("a.wav", b"RIFF", "audio/wav")}
            ).status_code == 503


class TestSummarize:
    def test_parses_model_json(self):
        reply = json.dumps({"summary": ["重點一"], "latest": "在講需求"}, ensure_ascii=False)
        with make_client(text=StubText(reply=reply)) as client:
            body = client.post("/api/summarize", json={"transcript": "課堂內容"}).json()
        assert body["summary"] == ["重點一"]
        assert body["latest"] == "在講需求"
        assert body["concepts"] == []

    def test_clips_an_over_long_transcript(self):
        stub = StubText(reply="{}")
        settings = Settings(openai_api_key="k", resolved_text_provider="openai", max_context_chars=50)
        with make_client(text=stub, settings=settings) as client:
            client.post("/api/summarize", json={"transcript": "字" * 5000})
        assert "字" * 51 not in stub.calls[0]

    def test_rejects_an_empty_transcript(self):
        with make_client(text=StubText(reply="{}")) as client:
            assert client.post("/api/summarize", json={"transcript": ""}).status_code == 422

    def test_without_a_key(self):
        with make_client(settings=Settings()) as client:
            assert client.post("/api/summarize", json={"transcript": "x"}).status_code == 503


class TestAsk:
    def test_returns_an_answer(self):
        with make_client(text=StubText(reply="老師的結論是甲。")) as client:
            body = client.post("/api/ask", json={"transcript": "課堂", "question": "結論?"}).json()
        assert body["answer"] == "老師的結論是甲。"

    def test_streams_deltas(self):
        with make_client(text=StubText(pieces=["老師", "的結論", "是甲。"])) as client:
            response = client.post(
                "/api/ask/stream", json={"transcript": "課堂", "question": "結論?"}
            )
        assert response.status_code == 200
        deltas = [
            json.loads(line[5:])["delta"]
            for line in response.text.splitlines()
            if line.startswith("data:") and "delta" in line
        ]
        assert "".join(deltas) == "老師的結論是甲。"
        assert response.text.rstrip().endswith("data: [DONE]")

    def test_stream_reports_a_mid_flight_error_and_still_terminates(self):
        stub = StubText(pieces=["部分"], error=ProviderError(500, "boom"))
        with make_client(text=stub) as client:
            response = client.post(
                "/api/ask/stream", json={"transcript": "課堂", "question": "為何?"}
            )
        assert '"error"' in response.text
        assert "boom" in response.text
        assert response.text.rstrip().endswith("data: [DONE]")


class TestRetry:
    @pytest.mark.anyio
    async def test_retries_then_succeeds(self):
        attempts = []

        def handler(request):
            attempts.append(request)
            if len(attempts) < 3:
                return httpx.Response(503, json={"error": {"message": "busy"}})
            return httpx.Response(200, json={"text": "ok"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await request_with_retry(
                client, "POST", "https://example.test/x", max_retries=3
            )
        assert response.json() == {"text": "ok"}
        assert len(attempts) == 3

    @pytest.mark.anyio
    async def test_does_not_retry_a_client_error(self):
        attempts = []

        def handler(request):
            attempts.append(request)
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError) as info:
                await request_with_retry(client, "POST", "https://example.test/x", max_retries=3)
        assert info.value.status == 401
        assert "bad key" in info.value.message
        assert len(attempts) == 1

    @pytest.mark.anyio
    async def test_gives_up_after_the_retry_budget(self):
        attempts = []

        def handler(request):
            attempts.append(request)
            return httpx.Response(429, json={"error": {"message": "slow down"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError) as info:
                await request_with_retry(client, "POST", "https://example.test/x", max_retries=1)
        assert info.value.status == 429
        assert len(attempts) == 2


@pytest.fixture
def anyio_backend():
    return "asyncio"
