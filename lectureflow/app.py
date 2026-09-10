"""Entry point: ``uvicorn app:app`` or ``python app.py``."""

from __future__ import annotations

from lectureflow import create_app
from lectureflow.config import load_settings

settings = load_settings()
app = create_app(settings)


def main() -> None:
    import uvicorn

    provider = settings.resolved_text_provider
    print(f"LectureFlow  http://{settings.host}:{settings.port}")
    print(f"  語音辨識：{settings.transcribe_model if settings.transcribe_ready else '未設定（改用瀏覽器辨識）'}")
    print(f"  筆記/問答：{settings.text_model or '未設定（改用本機規則）'}"
          + (f"  [{provider}]" if provider != "none" else ""))
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
