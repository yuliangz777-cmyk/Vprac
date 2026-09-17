"""命令列介面：`python3 -m ntucool <指令>`。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .client import CanvasClient
from .config import ALL_SECTIONS, Config, config_template, load_config
from .errors import AuthError, ConfigError, NtuCoolError
from .manifest import Manifest
from .report import human_size
from .scraper import Scraper

EPILOG = """\
範例：
  python3 -m ntucool init                     # 產生設定檔
  python3 -m ntucool whoami                   # 驗證權杖
  python3 -m ntucool courses                  # 列出這學期的課
  python3 -m ntucool sync                     # 全部課程：資訊 + 檔案
  python3 -m ntucool sync -c 演算法 --ext pdf,pptx
  python3 -m ntucool sync --only info,assignments --dry-run
  python3 -m ntucool sync --watch 6h          # 常駐，每 6 小時自動同步
  python3 -m ntucool web                      # 用瀏覽器操作（本機網頁介面）
"""


def parse_duration(value: str) -> float:
    """`90`、`30m`、`6h`、`1d` → 秒。"""
    text = str(value).strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if text and text[-1] in units:
        number, factor = text[:-1], units[text[-1]]
    else:
        number, factor = text, 1
    try:
        seconds = float(number) * factor
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"看不懂的時間長度：{value}（可用 90s / 30m / 6h / 1d）") from exc
    if seconds < 60:
        raise argparse.ArgumentTypeError("間隔至少 60 秒，以免對 NTU COOL 造成負擔")
    return seconds


def add_common_options(parser: argparse.ArgumentParser, *, suppress: bool = False) -> None:
    """全域選項。子指令用 SUPPRESS 當預設值，才不會把主指令上的設定洗掉。"""
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--config", type=Path, default=default, help="指定設定檔路徑")
    parser.add_argument("--token", default=default, help="存取權杖（建議改用環境變數 NTU_COOL_TOKEN）")
    parser.add_argument("--base-url", dest="base_url", default=default,
                        help="站台網址（預設 https://cool.ntu.edu.tw）")
    parser.add_argument("-q", "--quiet", action="store_true",
                        default=argparse.SUPPRESS if suppress else False, help="只輸出結果摘要")
    parser.add_argument("-v", "--verbose", action="store_true",
                        default=argparse.SUPPRESS if suppress else False, help="輸出每次重試／略過的細節")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ntucool",
        description="自動擷取 NTU COOL 課程資訊與檔案",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"ntucool {__version__}")
    add_common_options(parser)
    common = argparse.ArgumentParser(add_help=False)
    add_common_options(common, suppress=True)
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="產生設定檔範本", parents=[common])
    p_init.add_argument("--path", type=Path, default=Path("ntucool.config.json"))
    p_init.add_argument("--force", action="store_true", help="覆寫既有檔案")

    sub.add_parser("whoami", help="驗證權杖並顯示帳號", parents=[common])

    p_web = sub.add_parser("web", help="開啟本機網頁介面（用瀏覽器操作同步）", parents=[common])
    p_web.add_argument("-o", "--out", dest="out_dir", type=Path, help="輸出資料夾")
    p_web.add_argument("--port", type=int, default=8765, help="連接埠，預設 8765")
    p_web.add_argument("--new-key", action="store_true", dest="new_key",
                       help="重新產生存取金鑰（舊網址即失效）")
    p_web.add_argument("--host", default="127.0.0.1",
                       help="綁定位址，預設只接受本機連線；同網段其他裝置要連請用 0.0.0.0")

    for name, help_text in (("courses", "列出可擷取的課程"), ("sync", "擷取課程資訊與檔案")):
        p = sub.add_parser(name, help=help_text, parents=[common])
        p.add_argument("-c", "--course", dest="course_filters", action="append",
                       help="只處理符合的課程（課號／課名／ID，可重複）")
        p.add_argument("-t", "--term", dest="terms", action="append", help="只處理符合的學期，例如 113-2")
        p.add_argument("--enrollment-state", choices=["active", "completed", "invited", "all"],
                       help="修課狀態，預設 active（進行中）")
        p.add_argument("--json", action="store_true", help="以 JSON 輸出結果")
        if name == "sync":
            p.add_argument("-o", "--out", dest="out_dir", type=Path, help="輸出資料夾")
            p.add_argument("--only", dest="sections",
                           help=f"只擷取指定項目，逗號分隔：{','.join(ALL_SECTIONS)}")
            p.add_argument("--skip-files", action="store_true", help="只抓資訊，不下載檔案")
            p.add_argument("--ext", dest="extensions", help="只下載這些副檔名，例如 pdf,pptx,docx")
            p.add_argument("--max-file-mb", dest="max_file_mb", type=float, help="略過超過此大小的檔案")
            p.add_argument("-j", "--concurrency", type=int, help="同時下載數（預設 4）")
            p.add_argument("--force", action="store_true", help="忽略同步紀錄，全部重新下載")
            p.add_argument("-n", "--dry-run", action="store_true", help="只顯示會做什麼，不寫入檔案")
            p.add_argument("--watch", type=parse_duration, metavar="間隔",
                           help="常駐模式：每隔一段時間自動再同步一次（例如 6h）")
    return parser


def make_config(args) -> Config:
    overrides = {
        key: getattr(args, key, None)
        for key in (
            "token", "base_url", "out_dir", "enrollment_state", "terms", "course_filters",
            "sections", "extensions", "max_file_mb", "concurrency", "force", "dry_run",
            "verbose", "quiet",
        )
    }
    if getattr(args, "json", False):
        # JSON 要能直接餵給其他程式，進度訊息改走 stderr。
        overrides["extra"] = {"json": True}
    if getattr(args, "skip_files", False):
        overrides["sections"] = tuple(s for s in (overrides.get("sections") or ALL_SECTIONS) if s != "files")
    return load_config(config_path=getattr(args, "config", None), overrides=overrides).validate()


def make_logger(config: Config):
    stream = sys.stderr if config.extra.get("json") else sys.stdout

    def log(message=""):
        if not config.quiet:
            print(message, file=stream, flush=True)

    def debug(message=""):
        if config.verbose and not config.quiet:
            print(message, file=stream, flush=True)

    return log, debug


def make_scraper(config: Config) -> Scraper:
    log, debug = make_logger(config)
    client = CanvasClient(
        config.api_root,
        config.token,
        timeout=config.timeout,
        max_retries=config.max_retries,
        per_page=config.per_page,
        logger=debug,
    )
    return Scraper(config, client, Manifest.load(config.out_dir), log=log)


# ---- 各指令 --------------------------------------------------------------
def cmd_init(args) -> int:
    path: Path = args.path
    if path.exists() and not args.force:
        print(f"{path} 已存在（要覆寫請加 --force）", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config_template(), encoding="utf-8")
    print(f"已建立 {path}")
    print("請把權杖填進去，或改用環境變數：export NTU_COOL_TOKEN=...")
    print("取得權杖：NTU COOL → 右上角帳戶 → 設定 → 新增存取權杖")
    return 0


def cmd_whoami(args) -> int:
    config = make_config(args)
    scraper = make_scraper(config)
    profile = scraper.client.whoami()
    print(f"{profile.get('name')}（{profile.get('primary_email') or profile.get('login_id') or ''}）")
    print(f"站台：{config.base_url}")
    return 0


def cmd_web(args) -> int:
    from .web import create_server

    config = make_config(args)
    httpd, url = create_server(config, host=args.host, port=args.port, rotate_key=args.new_key)
    print("本機網頁介面已啟動，請在瀏覽器打開：")
    print(f"\n  {url}\n")
    if args.host not in ("127.0.0.1", "localhost"):
        print("注意：你綁定了對外位址，同網段的裝置都能連到這個網址（含金鑰才進得來）。")
    print("這個網址每次啟動都一樣，可以加到書籤。")
    print("按 Ctrl+C 結束。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已關閉")
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


def cmd_courses(args) -> int:
    config = make_config(args)
    scraper = make_scraper(config)
    courses = scraper.list_courses()
    if args.json:
        print(json.dumps(courses, ensure_ascii=False, indent=2))
        return 0
    if not courses:
        print("找不到符合條件的課程（試試 --enrollment-state all）")
        return 0
    width = max(len(str(c.get("course_code") or "")) for c in courses)
    for course in courses:
        teachers = "、".join(course.get("teachers") or [])
        print(
            f"{course['id']:>8}  {str(course.get('course_code') or ''):<{width}}  "
            f"{course.get('name')}  [{course.get('term') or '-'}]" + (f"  {teachers}" if teachers else "")
        )
    print(f"\n共 {len(courses)} 門課程")
    return 0


def _run_once(config: Config, as_json: bool) -> int:
    scraper = make_scraper(config)
    run = scraper.run()
    if as_json:
        print(json.dumps(
            {
                "started_at": run.started_at,
                "out_dir": str(run.out_dir),
                "requests": run.requests,
                "courses": [
                    {
                        "id": r.course.get("id"),
                        "name": r.course.get("name"),
                        "dir": r.dirname,
                        "files": r.files_total,
                        "downloaded": r.downloaded,
                        "skipped": r.skipped,
                        "bytes": r.bytes,
                        "failures": r.failures,
                    }
                    for r in run.results
                ],
            },
            ensure_ascii=False,
            indent=2,
        ))
    elif not config.quiet:
        # 沒取得的項目先講，摘要放最後 —— 小螢幕上最後一行最容易看到
        if run.failures:
            print(f"\n有 {len(run.failures)} 個項目沒取得：")
            for message in run.failures[:10]:
                print(f"  - {message}")
            if len(run.failures) > 10:
                print(f"  …另外還有 {len(run.failures) - 10} 項，詳見 {run.out_dir}/README.md")
        print(
            f"\n完成：{len(run.results)} 門課程，新增／更新 {run.downloaded} 個檔案"
            f"（{human_size(run.bytes)}），共 {run.requests} 次 API 呼叫"
        )
        print(f"輸出位置：{run.out_dir.resolve()}")
    return 0


def cmd_sync(args) -> int:
    config = make_config(args)
    interval = getattr(args, "watch", None)
    if not interval:
        return _run_once(config, args.json)
    log, _ = make_logger(config)
    log(f"常駐模式：每 {interval / 60:.0f} 分鐘同步一次，按 Ctrl+C 結束")
    while True:
        try:
            _run_once(config, args.json)
        except NtuCoolError as exc:
            print(f"這一輪失敗：{exc}", file=sys.stderr)
        next_at = (datetime.now().astimezone() + timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M")
        log(f"下次同步：{next_at}\n")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("已停止")
            return 0


COMMANDS = {
    "init": cmd_init,
    "whoami": cmd_whoami,
    "courses": cmd_courses,
    "sync": cmd_sync,
    "web": cmd_web,
}


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    try:
        return COMMANDS[args.command](args)
    except ConfigError as exc:
        print(f"設定有問題：{exc}", file=sys.stderr)
        return 2
    except AuthError as exc:
        print(f"權杖驗證失敗：{exc}", file=sys.stderr)
        return 3
    except NtuCoolError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
