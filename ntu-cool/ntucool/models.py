"""把 Canvas 原始 JSON 收斂成穩定、好讀的欄位。

只保留用得到的欄位：既讓輸出的 course.json 好讀，也避免 API 改版時到處爆炸。
"""

from __future__ import annotations

from datetime import datetime, timezone

from .htmlutil import html_to_text


def _get(obj, *keys, default=None):
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return default


def local_time(value: str | None) -> str:
    """把 ISO-8601（UTC）轉成本地時間字串，給人看用。"""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def parse_iso(value: str | None) -> datetime | None:
    """把 Canvas 的 ISO-8601 字串轉成 datetime（帶時區）。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_course(raw: dict) -> dict:
    term = raw.get("term") or {}
    teachers = [t.get("display_name") or t.get("name") for t in raw.get("teachers") or []]
    enrollment = next((e for e in raw.get("enrollments") or [] if e.get("type") == "student"), None)
    enrollment = enrollment or (raw.get("enrollments") or [{}])[0]
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "course_code": raw.get("course_code"),
        "term": term.get("name") or "",
        "term_id": term.get("id"),
        "start_at": raw.get("start_at") or term.get("start_at"),
        "end_at": raw.get("end_at") or term.get("end_at"),
        "teachers": [t for t in teachers if t],
        "enrollment_state": enrollment.get("enrollment_state") or "",
        "url": raw.get("html_url") or "",
        "total_students": raw.get("total_students"),
        "score": enrollment.get("computed_current_score"),
        "grade": enrollment.get("computed_current_grade"),
    }


def normalize_file(raw: dict, *, folder_path: str = "") -> dict:
    return {
        "id": raw.get("id"),
        "name": _get(raw, "display_name", "filename", default=f"file-{raw.get('id')}"),
        "folder_path": folder_path,
        "size": raw.get("size"),
        "content_type": _get(raw, "content-type", "content_type", default=""),
        "updated_at": _get(raw, "updated_at", "modified_at", default=""),
        "created_at": raw.get("created_at"),
        "url": raw.get("url") or "",
        "locked": bool(raw.get("locked_for_user") or raw.get("hidden_for_user")),
        "lock_explanation": raw.get("lock_explanation") or "",
    }


def normalize_assignment(raw: dict) -> dict:
    submission = raw.get("submission") or {}
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "due_at": raw.get("due_at"),
        "unlock_at": raw.get("unlock_at"),
        "lock_at": raw.get("lock_at"),
        "points_possible": raw.get("points_possible"),
        "submission_types": raw.get("submission_types") or [],
        "url": raw.get("html_url") or "",
        "description_text": html_to_text(raw.get("description")),
        "description_html": raw.get("description") or "",
        "submitted": bool(submission.get("submitted_at")),
        "submitted_at": submission.get("submitted_at"),
        "score": submission.get("score"),
        "grade": submission.get("grade"),
        "workflow_state": submission.get("workflow_state") or raw.get("workflow_state"),
    }


def normalize_announcement(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "posted_at": _get(raw, "posted_at", "created_at", default=""),
        "author": (raw.get("author") or {}).get("display_name") or raw.get("user_name") or "",
        "url": raw.get("html_url") or "",
        "message_text": html_to_text(raw.get("message")),
        "message_html": raw.get("message") or "",
        "attachment_ids": [a.get("id") for a in raw.get("attachments") or [] if a.get("id")],
    }


def normalize_module(raw: dict) -> dict:
    items = []
    for item in raw.get("items") or []:
        items.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "content_id": item.get("content_id"),
                "page_url": item.get("page_url"),
                "external_url": item.get("external_url"),
                "url": item.get("html_url") or "",
                "indent": item.get("indent", 0),
            }
        )
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "position": raw.get("position"),
        "state": raw.get("state") or raw.get("workflow_state") or "",
        "unlock_at": raw.get("unlock_at"),
        "items": items,
    }


def normalize_event(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "start_at": raw.get("start_at"),
        "end_at": raw.get("end_at"),
        "location": _get(raw, "location_name", "location_address", default=""),
        "url": raw.get("html_url") or "",
        "description_text": html_to_text(raw.get("description")),
        "all_day": bool(raw.get("all_day")),
    }


def normalize_page(raw: dict, body: str | None = None) -> dict:
    html_body = body if body is not None else raw.get("body")
    return {
        "page_id": raw.get("page_id"),
        "title": raw.get("title"),
        "url_slug": raw.get("url"),
        "updated_at": raw.get("updated_at"),
        "published": raw.get("published", True),
        "url": raw.get("html_url") or "",
        "body_text": html_to_text(html_body),
        "body_html": html_body or "",
    }
