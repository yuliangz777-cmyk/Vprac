"""同步狀態：記住每個檔案的版本，讓第二次之後只抓「新的／改過的」。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_FILENAME = ".ntucool-state.json"
STATE_VERSION = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Manifest:
    """記錄已下載檔案的清單，存成 out_dir/.ntucool-state.json。"""

    path: Path
    files: dict[str, dict] = field(default_factory=dict)
    courses: dict[str, dict] = field(default_factory=dict)
    last_sync: str = ""

    @classmethod
    def load(cls, out_dir: Path) -> "Manifest":
        path = Path(out_dir) / STATE_FILENAME
        if not path.is_file():
            return cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 狀態檔壞掉不該讓整個同步失敗，最多就是重抓一次。
            return cls(path=path)
        if data.get("version") != STATE_VERSION:
            return cls(path=path)
        return cls(
            path=path,
            files=data.get("files") or {},
            courses=data.get("courses") or {},
            last_sync=data.get("last_sync") or "",
        )

    def save(self) -> None:
        self.last_sync = now_iso()
        payload = {
            "version": STATE_VERSION,
            "last_sync": self.last_sync,
            "courses": self.courses,
            "files": self.files,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 原子寫入：避免中途中斷留下半個 JSON。
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---- 查詢／更新 ------------------------------------------------------
    @staticmethod
    def key(course_id, file_id) -> str:
        return f"{course_id}/{file_id}"

    def is_current(self, course_id, remote_file: dict, dest: Path) -> bool:
        """已存在、版本相同、檔案還在磁碟上 → 可以跳過。"""
        entry = self.files.get(self.key(course_id, remote_file.get("id")))
        if not entry:
            return False
        if entry.get("path") != str(dest):
            return False
        if not dest.exists():
            return False
        if entry.get("updated_at") != remote_file.get("updated_at"):
            return False
        size = remote_file.get("size")
        if size is not None and entry.get("size") != size:
            return False
        if size is not None and dest.stat().st_size != size:
            return False
        return True

    def record_file(self, course_id, remote_file: dict, dest: Path, written: int) -> None:
        self.files[self.key(course_id, remote_file.get("id"))] = {
            "path": str(dest),
            "name": remote_file.get("display_name") or remote_file.get("filename"),
            "size": remote_file.get("size", written),
            "updated_at": remote_file.get("updated_at"),
            "content_type": remote_file.get("content-type") or remote_file.get("content_type"),
            "synced_at": now_iso(),
        }

    def record_course(self, course: dict, stats: dict) -> None:
        self.courses[str(course.get("id"))] = {
            "name": course.get("name"),
            "course_code": course.get("course_code"),
            "synced_at": now_iso(),
            **stats,
        }

    def known_paths(self) -> set[Path]:
        return {Path(v["path"]) for v in self.files.values() if v.get("path")}
