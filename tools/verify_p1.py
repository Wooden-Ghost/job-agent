# -*- coding: utf-8 -*-
r"""P1 验收脚本：数字 / 搜索三例 / 导出回读 / 状态可逆 / 真库校验和。

只在开发副本上跑（默认 .tmp\p1\jobs.db）。
    set JOBAGENT_DB=D:\Projects\job-agent\.tmp\p1\jobs.db
    python tools\verify_p1.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from job_agent import store  # noqa: E402

REAL_DB = ROOT / "data" / "jobs.db"
OUT = ROOT / ".tmp" / "p1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    os.environ.setdefault("JOBAGENT_DB", str(OUT / "jobs.db"))
    db = Path(store.resolve_db_path())
    print(f"[db]    {db}")
    print(f"[real]  sha256={sha(REAL_DB)}")
    print(f"[real]  mtime={REAL_DB.stat().st_mtime_ns}")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    if not store.has_v7(conn):
        print("[FATAL] 不是 v7 库")
        return 2

    st = store.stats_v7(conn)
    print(f"\n[1] 数字：{st}")
    print(f"    company={conn.execute('SELECT COUNT(*) FROM company').fetchone()[0]} "
          f"job={conn.execute('SELECT COUNT(*) FROM job').fetchone()[0]}")

    print("\n[2] 搜索三例")
    for q in ("数据分析", "算法", "zzz不存在"):
        rows = store.list_jobs(conn, query=q, limit=100000)
        mode = "FTS(trigram)" if len(q) >= 3 else "LIKE"
        print(f"    {q!r:12} → {len(rows):3d} 命中   [{mode}]"
              + (f"   例：{rows[0]['title']} / {rows[0]['company']}" if rows else ""))

    print("\n[3] 导出回读")
    xlsx = OUT / "岗位导出.xlsx"
    ok, path, n = store.export_xlsx_v7(conn, str(xlsx))
    from openpyxl import load_workbook
    wb = load_workbook(path)
    ws = wb.active
    head = [c.value for c in ws[1]]
    hidden = [k for k, d in ws.column_dimensions.items() if d.hidden]
    print(f"    导出 {n} 行 → {path}")
    print(f"    表头 {len(head)} 列：{head[:4]} …")
    print(f"    隐藏列：{hidden}")
    print(f"    读回行数（不含表头）：{ws.max_row - 1}")

    print("\n[4] 状态可逆（JD过短 → 正常 → 改回）")
    short = conn.execute(
        "SELECT id, title, COALESCE(status,'open') FROM job "
        "WHERE status='jd_too_short' AND deleted_at IS NULL LIMIT 1").fetchone()
    if short is None:
        print("    没有 jd_too_short 行可测")
    else:
        jid, title = short[0], short[1]
        before = store.stats_v7(conn)
        v2 = store.set_job_status(conn, jid, "open")
        mid = store.stats_v7(conn)
        v3 = store.set_job_status(conn, jid, "jd_too_short")
        after = store.stats_v7(conn)
        print(f"    {title[:24]}  version 1→{v2}→{v3}")
        print(f"    池 before={before['pool']} → 改正常后={mid['pool']} → 改回={after['pool']}")
        assert after == before, "改回后数字应与初始一致"

    print("\n[5] 真库二次校验")
    print(f"    sha256={sha(REAL_DB)}")
    print(f"    mtime={REAL_DB.stat().st_mtime_ns}")
    conn.close()

    print(f"\n[report] 数字快照：{json.dumps(st, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
