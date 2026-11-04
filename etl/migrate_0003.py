# -*- coding: utf-8 -*-
r"""按列存在性执行 0003（ALTER 没有 IF NOT EXISTS，只能先在 Python 侧判）。

    python etl\migrate_0003.py            # 干跑，只报告缺什么
    python etl\migrate_0003.py --apply    # 真写

真写过一次就幂等：三列已存在时只跑状态改名与记账。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "jobs.db"

NEW_COLS = ("analysis", "fail_reason", "advice")
STATUS_MAP = {"open": "pending", "jd_too_short": "excluded"}


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="0003：加三列 + 状态改名（默认干跑）")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.exists():
        print(f"[FATAL] 库不存在：{db}")
        return 2

    conn = sqlite3.connect(f"file:{db}?mode={'rw' if args.apply else 'ro'}", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = columns(conn, "job")
        missing = [c for c in NEW_COLS if c not in cols]
        print(f"[db]      {db}")
        print(f"[job]     {len(cols)} 列；缺 {missing or '无'}")

        before = dict(conn.execute(
            "SELECT status, count(*) FROM job GROUP BY 1").fetchall())
        print(f"[status]  迁移前 {before}")

        if not args.apply:
            print("[dry-run] 未写库。加 --apply 才落盘。")
            return 0

        conn.execute("BEGIN IMMEDIATE")
        for col in missing:
            conn.execute(f"ALTER TABLE job ADD COLUMN {col} TEXT")
            print(f"[alter]   + job.{col}")
        for old, new in STATUS_MAP.items():
            n = conn.execute("UPDATE job SET status=? WHERE status=?", (new, old)).rowcount
            if n:
                print(f"[status]  {old} → {new}：{n} 行")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (3)")
        conn.commit()

        after = dict(conn.execute(
            "SELECT status, count(*) FROM job GROUP BY 1").fetchall())
        cols = columns(conn, "job")
        print(f"[status]  迁移后 {after}")
        print(f"[job]     {len(cols)} 列；三列就位 = "
              f"{all(c in cols for c in NEW_COLS)}")
        ver = [r[0] for r in conn.execute("SELECT version FROM schema_version")]
        print(f"[schema_version] {ver}")
        print(f"[integrity] {conn.execute('PRAGMA integrity_check').fetchone()[0]}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
