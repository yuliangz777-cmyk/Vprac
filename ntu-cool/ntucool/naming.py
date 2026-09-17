"""檔名與資料夾命名：跨平台安全、可讀、不會互相覆蓋。"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")
# Windows 保留字（即使在 macOS/Linux 產生，同步到 Windows 也會壞掉）
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(name: str, *, max_len: int = 120, default: str = "untitled") -> str:
    """把任意字串變成安全檔名（保留中文，砍掉控制字元與路徑符號）。"""
    if not name:
        return default
    name = unicodedata.normalize("NFC", str(name))
    name = _ILLEGAL.sub("_", name)
    name = _SPACES.sub(" ", name).strip(" .")
    if not name:
        return default
    stem, dot, ext = name.rpartition(".")
    if dot and len(ext) <= 10 and stem:
        if stem.upper() in _RESERVED:
            stem = f"_{stem}"
        budget = max_len - len(ext) - 1
        name = f"{_truncate(stem, max(1, budget))}.{ext}"
    else:
        if name.upper() in _RESERVED:
            name = f"_{name}"
        name = _truncate(name, max_len)
    return name or default


def _truncate(text: str, limit: int) -> str:
    """以 UTF-8 位元組長度截斷（多數檔案系統限制的是位元組數）。"""
    if len(text.encode("utf-8")) <= limit:
        return text
    out = []
    used = 0
    for ch in text:
        size = len(ch.encode("utf-8"))
        if used + size > limit:
            break
        out.append(ch)
        used += size
    return "".join(out).rstrip(" .") or text[:1]


def safe_relpath(path: str, *, max_len: int = 120) -> Path:
    """把 Canvas 的資料夾路徑（`course files/講義/第一週`）轉成安全相對路徑。"""
    parts = []
    for part in str(path or "").replace("\\", "/").split("/"):
        part = part.strip()
        if not part or part in (".", ".."):
            continue
        parts.append(safe_name(part, max_len=max_len))
    return Path(*parts) if parts else Path()


def course_dirname(course: dict, *, max_len: int = 120) -> str:
    """課程資料夾名：`課號-課名`，缺課號就退回 ID。"""
    code = (course.get("course_code") or "").strip()
    name = (course.get("name") or "").strip()
    cid = course.get("id")
    if code and name and name != code:
        base = f"{code}-{name}"
    else:
        base = name or code or f"course-{cid}"
    if cid and str(cid) not in base:
        base = f"{base}-{cid}"
    return safe_name(base, max_len=max_len, default=f"course-{cid}")


def unique_path(path: Path, taken: set[Path] | None = None) -> Path:
    """若檔名已被佔用（磁碟上或本次執行中），加上 `-2`、`-3`…。"""
    taken = taken if taken is not None else set()
    if path not in taken and not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for n in range(2, 1000):
        candidate = path.with_name(f"{stem}-{n}{suffix}")
        if candidate not in taken and not candidate.exists():
            return candidate
    raise RuntimeError(f"無法為 {path} 找到可用檔名")
