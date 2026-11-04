#!/usr/bin/env python
"""把 legacy `jobs` 表搬进 v7 目标 schema（company / job / job_source / job_revision）。

设计约束（来自 v7 计划 §5）：
  * 只写**副本库**。真库 `data\\jobs.db` 只读，默认参数就指向 `.tmp\\p0\\jobs.copy.db`。
  * 时间换算必须走 Python（假设本地时间 = Asia/Shanghai，UTC+8），不在 SQL 里写时间函数。
  * 幂等：按唯一键先查后插，重复执行不产生新行。
  * 单事务：一批要么全落，要么一行不落。

用法：
    python etl/import_jobhunt.py                       # 干跑（默认），只读、不写
    python etl/import_jobhunt.py --apply               # 真写（仅副本库）
    python etl/import_jobhunt.py --db X --apply        # 指定库
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from job_agent import naming  # noqa: E402  只读引用，不改它

DEFAULT_DB = ROOT / ".tmp" / "p0" / "jobs.copy.db"
MIGRATION = ROOT / "db" / "migrations" / "0002_initial_contract.sql"
JOBHUNT_DIR = Path(r"D:\Projects\Job-hunt")

SOURCE_APP = {"zhaopin": "智联招聘", "boss": "BOSS直聘", "liepin": "猎聘"}
LOCAL_TZ = timezone(timedelta(hours=8))
EXPECTED = {"company": 45, "job": 58, "job_source": 58, "job_revision": 58, "screening": 0}

NEW_TABLES = ("company", "company_alias", "job", "job_source", "job_revision",
              "due_diligence_evidence", "due_diligence_verdict", "screening")


# ---------------------------------------------------------------- helpers
def new_id() -> str:
    return uuid.uuid4().hex


def to_utc(local_ts: str | None) -> str | None:
    """'2026-11-03T22:41:04'（本地）→ '2026-11-03T14:41:04Z'（UTC）。"""
    if not local_ts:
        return None
    s = local_ts.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=LOCAL_TZ)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


_CITY_TAIL = ("市", "区", "县")


def normalize_city(raw: str | None) -> str:
    """成都/成都市→成都；空或远程 → remote。"""
    if not raw:
        return "remote"
    s = str(raw).strip()
    if not s or s in {"远程", "remote", "Remote"}:
        return "remote"
    for tail in _CITY_TAIL:
        if len(s) > 2 and s.endswith(tail):
            s = s[: -len(tail)]
            break
    return s or "remote"


def jd_min_len() -> int:
    """JD 短于这个长度就排除出待评估池（只排除、不删除）。默认 300。"""
    cfg = ROOT / "config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        v = int(data.get("jdMinLen") or 300)
        return v if v > 0 else 300
    except Exception:  # noqa: BLE001  配置坏了就用默认值，不阻断导入
        return 300


def parse_months(salary_text: str | None) -> int | None:
    """'8000-12000元·13薪' → 13。拿不到就 None。"""
    if not salary_text:
        return None
    import re
    m = re.search(r"[·x×*]\s*(\d{2})\s*薪", salary_text)
    return int(m.group(1)) if m else None


def sha16(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- 读取 legacy
def load_legacy(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs ORDER BY job_key").fetchall()
    return [dict(r) for r in rows]


def build_plan(legacy: list[dict]) -> dict:
    JD_MIN = jd_min_len()
    """把 legacy 行算成四张新表的待插数据（纯函数，不碰库）。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in legacy:
        norm = naming.normalize_company(r.get("company")) or (r.get("company_norm") or "")
        groups[norm].append(r)

    companies, company_by_norm = [], {}
    for norm, rows in sorted(groups.items()):
        cid = new_id()
        names = [x.get("company") or "" for x in rows if x.get("company")]
        fulls = [x.get("company_full") or "" for x in rows if x.get("company_full")]
        first = min((x.get("first_seen") or "") for x in rows)
        last = max((x.get("last_seen") or "") for x in rows)
        companies.append({
            "id": cid, "name": sorted(names)[0], "norm_name": norm,
            "full_name": sorted(fulls)[0] if fulls else None,
            "source": sorted({x.get("source") or "" for x in rows if x.get("source")})[0]
            if any(x.get("source") for x in rows) else None,
            "city": rows[0].get("city"), "industry": None,
            "founded_year": None, "capital": None, "insured_count": None,
            "first_seen": to_utc(first), "last_seen": to_utc(last),
            "created_at": to_utc(first), "updated_at": to_utc(last),
        })
        company_by_norm[norm] = cid

    jobs, sources, revisions = [], [], []
    for r in legacy:
        norm = naming.normalize_company(r.get("company")) or (r.get("company_norm") or "")
        jid = new_id()
        first = to_utc(r.get("first_seen"))
        last = to_utc(r.get("last_seen"))
        jd = r.get("jd") or ""
        jobs.append({
            "id": jid,
            "company_id": company_by_norm[norm],
            "legacy_key": r.get("job_key"),
            "job_key": naming.fingerprint(r.get("company"), r.get("title")),
            "title": r.get("title") or "",
            "title_norm": naming.normalize_title(r.get("title")),
            "salary_text": r.get("salary_text"),
            "salary_min": r.get("salary_min"),
            "salary_max": r.get("salary_max"),
            "salary_months": parse_months(r.get("salary_text")),
            "city": r.get("city"),
            "city_norm": normalize_city(r.get("city")),
            "district": r.get("district"),
            "area": r.get("area_text"),
            "experience": r.get("experience"),
            "education": r.get("education"),
            "jd_text": jd,
            "jd_len": r.get("jd_len") or len(jd),
            "jd_hash": sha16(jd),
            "needs_manual_check": 0,
            "company_meta": r.get("company_meta"),
            "company_size": r.get("company_size"),
            "company_stage": r.get("company_stage"),
            "hiring_count": r.get("hiring_count"),
            "source_keyword": None,          # tab 是渠道名，不是搜索词，一律 NULL
            "status": "jd_too_short" if (r.get("jd_len") or len(jd)) < JD_MIN else "open",
            "is_starred": 0, "tags": None, "note": None, "updated_by": "migrated",
            "biz_date": r.get("biz_date"),
            "seen_count": r.get("seen_count") or 1,
            "first_seen": first, "last_seen": last,
            "created_at": first, "updated_at": last,
        })
        sources.append({
            "id": new_id(), "job_id": jid,
            "source_app": SOURCE_APP.get((r.get("source") or "").lower(),
                                         r.get("source") or "unknown"),
            "external_id": None, "url": (json.loads(r["raw"]).get("url")
                                         if r.get("raw") and "url" in r["raw"] else None),
            "salary_text": r.get("salary_text"),
            "salary_month_lo": r.get("salary_min"),
            "salary_month_hi": r.get("salary_max"),
            "first_seen": first, "last_seen": last,
            "seen_count": r.get("seen_count") or 1,
        })
        revisions.append({
            "id": new_id(), "job_id": jid,
            "jd_hash": sha16(jd), "jd_len": len(jd), "captured_at": last,
        })

    aliases = []
    for c in companies:
        full = (c.get("full_name") or "").strip()
        name = (c.get("name") or "").strip()
        if full and name and full != name:
            norm_alias = naming.normalize_company(full)
            if norm_alias and norm_alias != c["norm_name"]:
                aliases.append({"id": new_id(), "company_id": c["id"],
                                "alias": full, "norm_alias": norm_alias,
                                "source": "migrated", "created_at": c["created_at"]})

    return {"companies": companies, "jobs": jobs, "sources": sources,
            "revisions": revisions, "aliases": aliases}


# ---------------------------------------------------------------- 写库
def sync_jd_status(conn: sqlite3.Connection, min_len: int) -> dict:
    """按 jd_len 重新派生 status；只动 updated_by='migrated' 的行，幂等。"""
    to_short = conn.execute(
        "UPDATE job SET status='jd_too_short' "
        "WHERE jd_len < ? AND status='open' AND updated_by='migrated'", (min_len,)).rowcount
    to_open = conn.execute(
        "UPDATE job SET status='open' "
        "WHERE jd_len >= ? AND status='jd_too_short' AND updated_by='migrated'", (min_len,)).rowcount
    return {"to_short": to_short, "to_open": to_open}


def insert_all(conn: sqlite3.Connection, plan: dict) -> dict:
    st = Counter()
    by_norm = {r["norm_name"]: r["id"]
               for r in conn.execute("SELECT id, norm_name FROM company WHERE deleted_at IS NULL")}
    for c in plan["companies"]:
        if c["norm_name"] in by_norm:
            st["company_skip"] += 1
            continue
        conn.execute(
            """INSERT INTO company (id,name,norm_name,full_name,founded_year,capital,insured_count,
                    city,industry,source,conclusion,summary,is_starred,tags,note,updated_by,
                    version,first_seen,last_seen,created_at,updated_at,deleted_at)
               VALUES (:id,:name,:norm_name,:full_name,:founded_year,:capital,:insured_count,
                    :city,:industry,:source,NULL,NULL,0,NULL,NULL,:updated_by,
                    1,:first_seen,:last_seen,:created_at,:updated_at,NULL)""",
            {**c, "updated_by": "migrated"})
        by_norm[c["norm_name"]] = c["id"]
        st["company_insert"] += 1

    seen_jobs = {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT company_id, title_norm, city_norm FROM job WHERE deleted_at IS NULL")}
    # 重跑时公司已存在、用的是旧 id；plan 里给的是新 uuid，必须重映射，否则 FK 失败
    id_remap = {c["id"]: by_norm[c["norm_name"]] for c in plan["companies"]}
    for j in plan["jobs"]:
        j["company_id"] = id_remap.get(j["company_id"], j["company_id"])
        key = (j["company_id"], j["title_norm"], j["city_norm"])
        if key in seen_jobs:
            st["job_skip"] += 1
            continue
        conn.execute(
            """INSERT INTO job (id,company_id,legacy_key,job_key,title,title_norm,
                    salary_text,salary_min,salary_max,salary_months,city,city_norm,district,area,
                    experience,education,jd_text,jd_len,jd_hash,needs_manual_check,company_meta,
                    company_size,company_stage,hiring_count,source_keyword,status,
                    is_starred,tags,note,updated_by,biz_date,seen_count,version,
                    first_seen,last_seen,created_at,updated_at,deleted_at)
               VALUES (:id,:company_id,:legacy_key,:job_key,:title,:title_norm,
                    :salary_text,:salary_min,:salary_max,:salary_months,:city,:city_norm,:district,:area,
                    :experience,:education,:jd_text,:jd_len,:jd_hash,:needs_manual_check,:company_meta,
                    :company_size,:company_stage,:hiring_count,:source_keyword,:status,
                    0,NULL,NULL,:updated_by,:biz_date,:seen_count,1,
                    :first_seen,:last_seen,:created_at,:updated_at,NULL)""", j)
        conn.execute(
            """INSERT INTO job_source (id,job_id,source_app,external_id,url,salary_text,
                    salary_month_lo,salary_month_hi,first_seen,last_seen,seen_count,version,deleted_at)
               VALUES (:id,:job_id,:source_app,:external_id,:url,:salary_text,
                    :salary_month_lo,:salary_month_hi,:first_seen,:last_seen,:seen_count,1,NULL)""",
            plan["sources"] and next(
                s for s in plan["sources"] if s["job_id"] == j["id"]))
        conn.execute(
            """INSERT INTO job_revision (id,job_id,jd_hash,jd_len,captured_at)
               VALUES (:id,:job_id,:jd_hash,:jd_len,:captured_at)""",
            next(rv for rv in plan["revisions"] if rv["job_id"] == j["id"]))
        conn.execute("INSERT INTO job_fts (job_id,title,jd_text) VALUES (?,?,?)",
                     (j["id"], j["title"], j["jd_text"]))
        seen_jobs.add(key)
        st["job_insert"] += 1
        st["source_insert"] += 1
        st["revision_insert"] += 1

    seen_alias = {r[0] for r in conn.execute(
        "SELECT norm_alias FROM company_alias WHERE deleted_at IS NULL")}
    for a in plan["aliases"]:
        if a["norm_alias"] in seen_alias:
            st["alias_skip"] += 1
            continue
        conn.execute(
            """INSERT INTO company_alias (id,company_id,alias,norm_alias,source,created_at,deleted_at)
               VALUES (:id,:company_id,:alias,:norm_alias,:source,:created_at,NULL)""", a)
        seen_alias.add(a["norm_alias"])
        st["alias_insert"] += 1
    return dict(st)


# ---------------------------------------------------------------- Job-hunt 只读闸
def jobhunt_gate(dirpath: Path) -> list[tuple[str, str]]:
    """只读 Job-hunt 的 xlsx，报计数；不写、不改。"""
    out = []
    xlsx = dirpath / "筛选公司记录.xlsx"
    if not xlsx.exists():
        return [("筛选公司记录.xlsx", "缺失")]
    try:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = [r for r in ws.iter_rows(min_row=2, values_only=True)
                if r and any(v not in (None, "") for v in r)]
        companies = {str(r[0]).strip() for r in rows if r and r[0]}
        out.append(("台账行数", str(len(rows))))
        out.append(("去重公司数", str(len(companies))))
        wb.close()
    except Exception as exc:  # noqa: BLE001  只读闸，失败不影响主流程
        out.append(("读取失败", f"{type(exc).__name__}: {exc}"))
    return out


# ---------------------------------------------------------------- main
def import_now(db_path: str) -> dict:
    """同进程跑一次完整导入（给界面「同步采集」按钮用），返回统计。

    幂等：已存在的公司/岗位一律跳过，只补新增行。
    """
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"库不存在：{db}")
    conn = sqlite3.connect(f"file:{db}?mode=rw", uri=True)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        has_new = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company'").fetchone()
        if not has_new:
            conn.executescript(MIGRATION.read_text(encoding="utf-8"))
            conn.commit()
        plan = build_plan(load_legacy(conn))
        conn.execute("BEGIN IMMEDIATE")
        stats = insert_all(conn, plan)
        conn.commit()
        synced = sync_jd_status(conn, jd_min_len())
        conn.commit()
    finally:
        conn.close()
    out = dict(stats)
    out["jd_too_short"] = synced["to_short"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="legacy jobs → v7 新表（默认干跑）")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="副本库路径")
    ap.add_argument("--apply", action="store_true", help="真写（不加则只干跑）")
    ap.add_argument("--jobhunt", default=str(JOBHUNT_DIR), help="Job-hunt 只读目录")
    ap.add_argument("--allow-real-db", action="store_true",
                    help="允许直接在真库 data\\jobs.db 上跑（切换用，需显式放行）")
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.exists():
        print(f"[FATAL] 库不存在：{db}")
        return 2
    if db.resolve() == (ROOT / "data" / "jobs.db").resolve() and not args.allow_real_db:
        print("[FATAL] 拒绝在真库上运行。副本请用 copy2；切换真库请加 --allow-real-db。")
        return 2

    conn = sqlite3.connect(f"file:{db}?mode={'rw' if args.apply else 'ro'}", uri=True)
    conn.execute("PRAGMA foreign_keys = ON")
    legacy = load_legacy(conn)
    print(f"[legacy] jobs = {len(legacy)} 行")

    # 新表还没建就先跑 0002（幂等脚本，单事务）；只在 --apply 时动手
    has_new = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company'").fetchone()
    if not has_new and args.apply:
        print("[migrate] 检测到新表不存在，先执行 0002_initial_contract.sql")
        conn.executescript(MIGRATION.read_text(encoding="utf-8"))
        conn.commit()
    elif not has_new:
        print("[migrate] 干跑：新表尚未创建（--apply 时会先跑 0002）")

    plan = build_plan(legacy)
    print(f"[plan]   company={len(plan['companies'])} job={len(plan['jobs'])} "
          f"job_source={len(plan['sources'])} job_revision={len(plan['revisions'])} "
          f"company_alias={len(plan['aliases'])}")

    before = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in NEW_TABLES if conn.execute(
                  "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()}
    print(f"[before] {before or '(新表尚未创建)'}")

    # 时间换算样例（各 3 行）
    print("[time] 本地 → UTC（biz_date 不转）")
    for r in legacy[:3]:
        print(f"   {r['first_seen']} → {to_utc(r['first_seen'])}   biz_date={r['biz_date']}")

    # 薪资样例（3 条）
    print("[salary] salary_text 与 min/max/month 对账")
    for j in plan["jobs"][:3]:
        print(f"   {j['salary_text']!r:20} min={j['salary_min']} max={j['salary_max']} "
              f"months={j['salary_months']}")

    print("[jobhunt] 只读闸")
    for k, v in jobhunt_gate(Path(args.jobhunt)):
        print(f"   {k}: {v}")

    if not args.apply:
        print("\n[dry-run] 未写库。加 --apply 才落盘。")
        conn.close()
        return 0

    try:
        conn.execute("BEGIN IMMEDIATE")
        stats = insert_all(conn, plan)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    after = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in NEW_TABLES}
    print(f"\n[apply] {stats}")

    synced = sync_jd_status(conn, jd_min_len())
    conn.commit()
    print(f"[jd-status] jd_len<{jd_min_len()} → jd_too_short {synced['to_short']} 条，"
          f"回收 {synced['to_open']} 条")
    print(f"[after] {after}")
    ver = [r[0] for r in conn.execute("SELECT version FROM schema_version")]
    print(f"[schema_version] {ver}")
    ok = all(after.get(k, 0) == v for k, v in EXPECTED.items() if k in after)
    print(f"[gate] 期望 {EXPECTED} → {'PASS' if ok else 'MISMATCH'}")
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
