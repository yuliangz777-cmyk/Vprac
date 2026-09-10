"""HTTP surface: static hosting plus the four endpoints the page calls."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import prompts, textproc
from .config import STATIC_DIR, Settings, load_settings
from .providers import ProviderError, Transcriber, build_text_provider

APP_VERSION = "2.0.0"


class TranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1)


class AskRequest(TranscriptRequest):
    question: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One pooled client for the process: connections stay warm between
        # chunks instead of paying a TLS handshake every few seconds.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout, connect=20.0),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        ) as client:
            app.state.http = client
            app.state.transcriber = Transcriber(settings, client)
            app.state.text = build_text_provider(settings, client)
            yield

    app = FastAPI(title="LectureFlow", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=800)
    app.state.settings = settings

    def text_provider(request: Request) -> Any:
        provider = request.app.state.text
        if provider is None:
            raise HTTPException(
                status_code=503,
                detail="尚未設定 ANTHROPIC_API_KEY 或 OPENAI_API_KEY，介面已切換為瀏覽器備援模式。",
            )
        return provider

    def clip(transcript: str) -> str:
        return transcript[-settings.max_context_chars :]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return {
            "version": APP_VERSION,
            "configured": settings.text_ready or settings.transcribe_ready,
            "transcribe_ready": settings.transcribe_ready,
            "text_ready": settings.text_ready,
            "text_provider": settings.resolved_text_provider,
            "text_model": settings.text_model,
            "transcribe_model": settings.transcribe_model,
            "language": settings.transcribe_language,
        }

    @app.post("/api/transcribe")
    async def transcribe(
        request: Request,
        file: UploadFile = File(...),
        hint: str = Form(""),
    ) -> dict[str, Any]:
        if not settings.transcribe_ready:
            raise HTTPException(
                status_code=503,
                detail="尚未設定語音辨識金鑰，介面已切換為瀏覽器備援模式。",
            )
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="收到空白音訊。")
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="單段音訊過大。")

        try:
            text = await request.app.state.transcriber.transcribe(
                raw,
                file.filename or "chunk.wav",
                file.content_type or "audio/wav",
                hint=hint,
            )
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=f"語音辨識失敗：{exc.message}")

        cleaned = textproc.clean_transcript_chunk(text)
        return {"text": cleaned, "filtered": bool(text) and not cleaned}

    @app.post("/api/summarize")
    async def summarize(request: Request, body: TranscriptRequest) -> dict[str, Any]:
        provider = text_provider(request)
        try:
            reply = await provider.complete(
                prompts.NOTES_SYSTEM,
                prompts.notes_user_prompt(clip(body.transcript)),
                max_tokens=8000,
            )
        except ProviderError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)
        return textproc.parse_notes(reply)

    @app.post("/api/ask")
    async def ask(request: Request, body: AskRequest) -> dict[str, str]:
        provider = text_provider(request)
        try:
            answer = await provider.complete(
                prompts.ASK_SYSTEM,
                prompts.ask_user_prompt(clip(body.transcript), body.question),
                max_tokens=4000,
            )
        except ProviderError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)
        return {"answer": answer}

    @app.post("/api/ask/stream")
    async def ask_stream(request: Request, body: AskRequest) -> StreamingResponse:
        provider = text_provider(request)

        async def events() -> AsyncIterator[str]:
            try:
                async for piece in provider.stream(
                    prompts.ASK_SYSTEM,
                    prompts.ask_user_prompt(clip(body.transcript), body.question),
                    max_tokens=4000,
                ):
                    yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
            except ProviderError as exc:
                yield f"data: {json.dumps({'error': exc.message}, ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001 - the stream must always close
                yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"}
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
