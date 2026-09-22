#!/usr/bin/env python3
"""確認 ACADEMIC_OFFICE.md 仍然涵蓋原始 workpack 的每一條必要內容。

壓縮很容易「順手」弄丟一條規則。這個檢查器把必須存在的元素列成清單，
每次改動 spec 之後跑一次：  python3 check_spec.py
"""

import re
import sys
from pathlib import Path

SPEC = Path(__file__).with_name("ACADEMIC_OFFICE.md")

REQUIRED = {
    "指令": ["BOOTSTRAP", "SYNC_ALL", "DAILY_BRIEF", "DOWNLOAD_SYNC", "DEADLINES",
             "PROGRESS_AUDIT", "WEEKLY_REVIEW", "COURSE <name> UPDATE",
             "PREP_EXAM <name>", "PROJECT <name>"],
    "HQ 角色": ["Chief of Staff", "Registrar", "Deadline\nManager|Deadline Manager",
                "QA/Source Controller", "Router"],
    "來源階層": ["graduation-progress Sheet", "official NTU records", "COOL membership",
                 "current syllabus", "instructor·TA email", "user tracker",
                 "instructor slides"],
    "狀態模型": ["last_sync", "next_deadline", "current_topics", "lecture_log", "assignments",
                 "projects", "exams", "mastery", "risks", "unresolved", "next_actions",
                 "needs_user_decision"],
    "截止記錄": ["due_at", "source_date", "confirmed", "not_started|planned|in_progress",
                 "dependencies"],
    "來源記錄": ["COOL|WEBMAIL|DRIVE|OFFICIAL_NTU|COURSE_CHAT|MANUAL", "observed_at",
                 "routes_to", "conflicts_with", "announcement|syllabus|lecture"],
    "精熟標籤": ["not_started", "exposed", "practiced", "weak", "exam_ready"],
    "門檻": ["≤ 3d", "≤ 7d", "≤ 28d", "≥ 2 unprocessed"],
    "工作流": ["BOOTSTRAP", "SYNC_ALL", "COOL ingestion", "Branch refresh",
               "Progress audit", "Project & exam"],
    "COOL 可靠性": ["one file at a time", "Bulk download is unreliable", "verify it landed"],
    "Drive 結構": ["00_Headquarters", "01_Inbox", "02_Courses", "99_Archive",
                   "YYYY-MM-DD__COURSE__TYPE"],
    "簡報格式": ["立即處理", "未來 7 天", "課程狀態", "本次新增", "待確認", "需要你決定"],
    "種子課程": ["策略管理", "行銷管理", "金融科技與創新", "財務管理",
                 "高科技企業經營管理實務", "數位行銷", "整合行銷傳播", "體育課",
                 "管理決策會計", "學生方程式賽車培訓"],
    "稽核待辦": ["Linear Algebra", "Service Learning", "9 credits"],
    "分支種子": ["TSMC", "ORP", "eSCM", "CoWoS", "BPR"],
    "限制": ["CORS", "SSO", "background crawler", "Sessions expire"],
    "鐵律": ["Never invent", "confirmed | probable | unresolved", "never silently pick one",
             "Never delete or overwrite", "dropped course goes inactive",
             "exactly one primary branch", "verified to exist",
             "unless a source was actually accessed", "No invented percentages"],
}


def main() -> int:
    text = SPEC.read_text(encoding="utf-8")
    missing = []
    checked = 0
    for group, items in REQUIRED.items():
        for item in items:
            checked += 1
            found = (re.search(item, text) if any(c in item for c in "|\\") else item in text)
            if not found:
                missing.append(f"{group} → {item}")

    print(f"檢查 {checked} 個必要元素")
    if missing:
        print(f"\n缺少 {len(missing)} 項：")
        for item in missing:
            print(f"  ✗ {item}")
        return 1
    tokens = sum(1 for c in text if '　' <= c <= '鿿') + \
        (len(text) - sum(1 for c in text if '　' <= c <= '鿿')) // 4
    print(f"全部通過。spec 約 {tokens:,} tokens（原始 workpack 約 8,779）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
