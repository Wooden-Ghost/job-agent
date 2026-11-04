# -*- coding: utf-8 -*-
"""命令行入口。

    python -m job_agent            # 交互式菜单
    python -m job_agent check      # 环境自检
    python -m job_agent detect     # 环境探测（JSON，给界面用）
    python -m job_agent run --screens 3 --max 20
    python -m job_agent export
    python -m job_agent status
    python -m job_agent ui         # 打开图形界面
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from job_agent import flow, store
from job_agent.flow import Logger

def _app_dir() -> str:
    """程序所在目录：打包后是 exe 所在目录，开发时是项目根。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PROJECT_DIR = _app_dir()
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")

DEFAULTS = {
    "adbPath": "",
    "serial": "",
    "tabs": [],                 # 空 = 用 App 里现有的全部期望 tab
    "defaultCity": "成都",       # 岗位城市兜底（列表卡不写城市时用它）
    "screensPerTab": 3,
    "perTabJobs": [10, 10, 10],
    "maxJobsPerRun": 60,
    "maxJobsPerDay": 120,       # 一天最多入库多少条（自动采集按它算配额）
    "maxRunMinutes": 60,
    "pauseEvery": 6,
    "shuffleTabs": False,
    "skipViewed": True,
    "dbPath": os.path.join(PROJECT_DIR, "data", "jobs.db"),
    "logDir": os.path.join(PROJECT_DIR, "logs"),
    "exportDir": os.path.join(PROJECT_DIR, "exports"),
    "autoExport": True,
    "schedule": {"enabled": False, "times": ["09:00"]},
}


_PATH_KEYS = ("adbPath", "dbPath", "logDir", "exportDir")


def _abs_paths(cfg: dict) -> dict:
    """config 里写相对路径时，按程序目录解析——解压到哪就存哪。"""
    for k in _PATH_KEYS:
        v = cfg.get(k)
        if v and not os.path.isabs(v):
            cfg[k] = os.path.normpath(os.path.join(PROJECT_DIR, v))
    return cfg


def load_config(path: str | None = None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    cfg = dict(DEFAULTS)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    for k in _PATH_KEYS:      # 留空 = 用默认值，别让空串把默认路径顶掉
        if not cfg.get(k):
            cfg[k] = DEFAULTS[k]
    return _abs_paths(cfg)


def save_config(cfg: dict, path: str | None = None) -> str:
    # 把界面改过的设置写回 config.json
    path = path or DEFAULT_CONFIG_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def cmd_check(cfg: dict) -> int:
    adb = flow.resolve_adb(cfg)
    serial = flow.serial_of(adb, cfg)
    info = flow.check_env(adb, serial)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if not info["appInstalled"]:
        print("\n⚠️ 模拟器里没装智联招聘（com.zhaopin.social）", file=sys.stderr)
        return 2
    return 0


def export_all(cfg: dict, conn, date: str | None = None) -> list[str]:
    """导出 Excel + AI 用的 .md（同目录同前缀）。返回生成的文件路径。"""
    date = date or store.business_date()
    base = os.path.join(cfg["exportDir"], f"{date}-岗位采集")
    paths = []
    try:
        ok, path, _n = store.export_xlsx(conn, base + ".xlsx", date)
        if path:
            paths.append(path)
    except Exception as exc:  # noqa: BLE001
        print(f"（Excel 导出失败：{exc}）", file=sys.stderr)
    try:
        ok, path, _n = store.export_md(conn, base + ".md", date)
        if path:
            paths.append(path)
    except Exception as exc:  # noqa: BLE001
        print(f"（Markdown 导出失败：{exc}）", file=sys.stderr)
    return paths


def cmd_run(cfg: dict, args) -> int:
    if args.screens is not None:
        cfg["screensPerTab"] = args.screens
    if args.max is not None:
        cfg["maxJobsPerRun"] = args.max
    if args.minutes is not None:
        cfg["maxRunMinutes"] = args.minutes
    if args.tab:
        cfg["tabs"] = [t.strip() for t in args.tab.split(",") if t.strip()]

    conn = store.connect(cfg["dbPath"])
    log = Logger(cfg["logDir"])

    def progress(kind, payload):
        if kind == "tabs":
            print(f"tab：{' / '.join(payload)}", flush=True)
        elif kind == "stored":
            print(f"  + {payload.get('company_full') or payload.get('company')}"
                  f" | {payload.get('title')} | {payload.get('salary_text')}"
                  f" | JD {len(payload.get('jd') or '')} 字", flush=True)

    try:
        summary = flow.run(cfg, conn, log, on_progress=progress)
    except KeyboardInterrupt:
        print("\n已中断（已抓到的都写进库了）", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ {exc}", file=sys.stderr)
        return 2

    print("\n完成：" + json.dumps(summary, ensure_ascii=False))
    print(f"库：{cfg['dbPath']}")
    if cfg.get("autoExport", True):
        for p in export_all(cfg, conn):
            print(f"已生成：{p}")
    return 0


def cmd_export(cfg: dict, args) -> int:
    conn = store.connect(cfg["dbPath"])
    date = args.date or store.business_date()
    out = args.xlsx or os.path.join(cfg["exportDir"], f"{date}-岗位采集.xlsx")
    try:
        ok, path, n = store.export_xlsx(conn, out, date)
    except PermissionError:
        print(f"✗ 写不进去：{out}\n  这个文件正在 Excel/WPS 里开着，"
              f"关掉它再跑一次。", file=sys.stderr)
        return 3
    print(f"采集日 {date}（{date} 05:00 → 次日 05:00）共 {n} 条")
    print(("已导出 Excel：" if ok else "未装 openpyxl，已退化导出 CSV：") + path)
    return 0


def cmd_status(cfg: dict) -> int:
    conn = store.connect(cfg["dbPath"])
    print(json.dumps(store.stats(conn), ensure_ascii=False, indent=2))
    return 0


def cmd_detect(cfg: dict) -> int:
    from job_agent import detect
    rep = detect.detect(cfg)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["ready"] else 2


def cmd_ui(cfg: dict) -> int:
    from job_agent.ui import app
    return app.main(cfg)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="job-agent", description="智联招聘采集 Agent")
    ap.add_argument("--config", help="配置文件路径（默认 工具/config.json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="环境自检：adb / 设备 / App").set_defaults(fn=cmd_check)

    r = sub.add_parser("run", help="开始采集")
    r.add_argument("--screens", type=int, help="每个 tab 滑几屏")
    r.add_argument("--max", type=int, help="本次最多入库多少条")
    r.add_argument("--minutes", type=int, help="本次最多跑多少分钟")
    r.add_argument("--tab", help="只跑指定 tab，逗号分隔，如 Python,爬虫")
    r.set_defaults(fn=cmd_run)

    e = sub.add_parser("export", help="导出某一天的 Excel")
    e.add_argument("--xlsx", help="输出路径")
    e.add_argument("--date", help="采集日 YYYY-MM-DD（默认今天这一份，05:00 切日）")
    e.set_defaults(fn=cmd_export)

    sub.add_parser("status", help="看库里有多少条").set_defaults(fn=cmd_status)
    sub.add_parser("detect", help="环境探测（JSON，界面用）").set_defaults(fn=cmd_detect)
    sub.add_parser("ui", help="打开图形界面").set_defaults(fn=cmd_ui)
    return ap


def interactive() -> int:
    """不带参数运行时给一个中文菜单，双击 `运行Agent.bat` 就走这里。"""
    menu = [
        ("1", "自检（adb / 模拟器 / 智联 App 通不通）"),
        ("2", "开始采集（默认 3 屏、最多 60 条）"),
        ("3", "导出今天的 Excel"),
        ("4", "看库里一共多少条"),
        ("0", "退出"),
    ]
    while True:
        print("\n" + "=" * 46)
        print("  智联招聘采集 Agent")
        print("=" * 46)
        for k, v in menu:
            print(f"  {k}. {v}")
        try:
            choice = input("\n选一个（回车=2）：")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        choice = choice.strip().strip("\ufeff'\"").strip() or "2"
        if choice in ("0", "q", "Q", "quit", "exit"):
            return 0
        cmd = {"1": ["check"], "2": ["run"], "3": ["export"],
               "4": ["status"]}.get(choice)
        if cmd is None:
            print("没这个选项。")
            continue
        try:
            main(cmd)
        except KeyboardInterrupt:
            print("\n已中断")
        print()
        try:
            input("按回车回到菜单…")
        except (EOFError, KeyboardInterrupt):
            return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        return interactive()
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    if args.cmd == "run":
        return cmd_run(cfg, args)
    if args.cmd == "export":
        return cmd_export(cfg, args)
    return args.fn(cfg)


if __name__ == "__main__":
    sys.exit(main())
