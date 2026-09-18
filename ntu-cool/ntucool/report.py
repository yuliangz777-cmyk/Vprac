"""把擷取到的資料寫成人看得懂的 Markdown。"""

from __future__ import annotations

from .models import local_time


def human_size(size) -> str:
    if not size:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title}", "", *lines, ""] if lines else []


def course_markdown(data: dict) -> str:
    """單一課程的總覽（course.md）。"""
    course = data["course"]
    out: list[str] = [f"# {course.get('name') or course.get('course_code')}", ""]

    meta = [
        ("課號", course.get("course_code")),
        ("學期", course.get("term")),
        ("授課教師", "、".join(course.get("teachers") or [])),
        ("課程網址", course.get("url")),
        ("修課狀態", course.get("enrollment_state")),
        ("擷取時間", data.get("fetched_at")),
    ]
    out += [f"- **{k}**：{v}" for k, v in meta if v]
    out.append("")

    if data.get("syllabus_text"):
        out += _section("課程大綱", [data["syllabus_text"]])

    modules = data.get("modules") or []
    if modules:
        lines = []
        for module in modules:
            lines.append(f"### {module.get('name')}")
            lines.append("")
            for item in module.get("items") or []:
                prefix = "  " * int(item.get("indent") or 0)
                kind = item.get("type") or ""
                link = item.get("external_url") or item.get("url")
                title = item.get("title") or "(無標題)"
                lines.append(f"{prefix}- [{kind}] " + (f"[{title}]({link})" if link else title))
            lines.append("")
        out += _section("課程單元", lines)

    assignments = data.get("assignments") or []
    if assignments:
        lines = ["| 作業 | 截止 | 配分 | 我的狀態 |", "| --- | --- | --- | --- |"]
        for item in assignments:
            status = "已繳交" if item.get("submitted") else "未繳交"
            if item.get("score") is not None:
                status += f"（{item['score']} 分）"
            lines.append(
                f"| {item.get('name')} | {local_time(item.get('due_at')) or '-'} "
                f"| {item.get('points_possible') if item.get('points_possible') is not None else '-'} | {status} |"
            )
        out += _section("作業", lines)

    announcements = data.get("announcements") or []
    if announcements:
        lines = [
            f"- {local_time(a.get('posted_at'))}　**{a.get('title')}**"
            + (f"（{a.get('author')}）" if a.get("author") else "")
            for a in announcements
        ]
        out += _section("公告", lines)

    events = data.get("events") or []
    if events:
        lines = [
            f"- {local_time(e.get('start_at'))}　**{e.get('title')}**"
            + (f"（{e.get('location')}）" if e.get("location") else "")
            for e in events
        ]
        out += _section("行事曆", lines)

    files = data.get("files") or []
    if files:
        lines = ["| 檔案 | 位置 | 大小 | 更新時間 |", "| --- | --- | --- | --- |"]
        for item in files:
            lines.append(
                f"| {item.get('name')} | {item.get('folder_path') or '/'} "
                f"| {human_size(item.get('size'))} | {local_time(item.get('updated_at')) or '-'} |"
            )
        out += _section(f"檔案（{len(files)}）", lines)

    pages = data.get("pages") or []
    if pages:
        out += _section("頁面", [f"- {p.get('title')}（{local_time(p.get('updated_at'))}）" for p in pages])

    return "\n".join(out).rstrip() + "\n"


def assignments_markdown(assignments: list[dict]) -> str:
    out = ["# 作業與截止日", ""]
    for item in sorted(assignments, key=lambda a: (a.get("due_at") or "9999")):
        out.append(f"## {item.get('name')}")
        out.append("")
        out.append(f"- 截止：{local_time(item.get('due_at')) or '未設定'}")
        if item.get("points_possible") is not None:
            out.append(f"- 配分：{item['points_possible']}")
        if item.get("submission_types"):
            out.append(f"- 繳交方式：{'、'.join(item['submission_types'])}")
        out.append(f"- 狀態：{'已繳交' if item.get('submitted') else '未繳交'}")
        if item.get("url"):
            out.append(f"- 連結：{item['url']}")
        if item.get("description_text"):
            out += ["", item["description_text"]]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def announcements_markdown(announcements: list[dict]) -> str:
    out = ["# 公告", ""]
    for item in announcements:
        out.append(f"## {item.get('title')}")
        out.append("")
        meta = [local_time(item.get("posted_at")), item.get("author")]
        out.append("　".join(m for m in meta if m))
        if item.get("message_text"):
            out += ["", item["message_text"]]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def page_markdown(page: dict) -> str:
    out = [f"# {page.get('title')}", ""]
    if page.get("updated_at"):
        out += [f"更新於 {local_time(page['updated_at'])}", ""]
    out.append(page.get("body_text") or "")
    return "\n".join(out).rstrip() + "\n"


def index_markdown(results: list, *, started_at: str) -> str:
    """所有課程的總覽（out/README.md）。"""
    out = ["# NTU COOL 擷取結果", "", f"最後同步：{started_at}", ""]
    out += ["| 課程 | 學期 | 教師 | 檔案 | 新增/更新 | 作業 | 公告 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        course = r.course
        out.append(
            f"| [{course.get('course_code') or course.get('id')} {course.get('name')}]({r.dirname}/course.md) "
            f"| {course.get('term') or '-'} | {'、'.join(course.get('teachers') or []) or '-'} "
            f"| {r.files_total} | {r.downloaded} | {r.assignments} | {r.announcements} |"
        )
    total_new = sum(r.downloaded for r in results)
    total_bytes = sum(r.bytes for r in results)
    out += ["", f"共 {len(results)} 門課程，本次新增／更新 {total_new} 個檔案（{human_size(total_bytes)}）。", ""]
    failures = [(r, f) for r in results for f in r.failures]
    if failures:
        out += ["## 未取得的項目", ""]
        out += [f"- {r.course.get('name')}：{msg}" for r, msg in failures]
        out.append("")
    return "\n".join(out).rstrip() + "\n"
