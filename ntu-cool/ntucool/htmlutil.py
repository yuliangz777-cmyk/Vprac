"""處理 Canvas 回傳的 HTML 內文：轉純文字、挖出內嵌的檔案連結。"""

from __future__ import annotations

import html
import re

_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_BR = re.compile(r"<br\s*/?>", re.I)
_BLOCK_END = re.compile(r"</(p|div|li|tr|h[1-6]|blockquote|table)\s*>", re.I)
_LI = re.compile(r"<li\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_BLANKS = re.compile(r"\n{3,}")

# Canvas 內文裡的檔案連結：/courses/123/files/456 或 /files/456
_FILE_LINK = re.compile(r"/(?:courses/(?P<course>\d+)/)?files/(?P<file>\d+)")


def html_to_text(raw: str | None) -> str:
    """把 HTML 轉成看得懂的純文字（給 Markdown 摘要用）。"""
    if not raw:
        return ""
    text = _SCRIPT_STYLE.sub("", str(raw))
    text = _BR.sub("\n", text)
    text = _LI.sub("- ", text)
    text = _BLOCK_END.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    lines = [line.rstrip() for line in text.splitlines()]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()


def extract_file_ids(raw: str | None, *, course_id=None) -> list[int]:
    """找出內文中引用到的檔案 ID（老師常把講義直接貼在公告／作業說明裡）。"""
    if not raw:
        return []
    found: list[int] = []
    for match in _FILE_LINK.finditer(str(raw)):
        owner = match.group("course")
        if owner and course_id is not None and str(owner) != str(course_id):
            continue  # 別的課程的檔案，通常沒有權限
        file_id = int(match.group("file"))
        if file_id not in found:
            found.append(file_id)
    return found
