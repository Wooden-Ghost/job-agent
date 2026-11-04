# -*- coding: utf-8 -*-
"""SQLite 落地 + 导出 Excel。

设计要点
    * 唯一键 = sha1(company_norm|title_norm)[:16] —— 天然去重、天然断点续跑
    * 每写一条立刻 commit —— 随时 Ctrl+C 都不丢
    * 取不到的字段一律留 NULL，不写「待补」「未知」
    * 「当天」按 05:00 切分，导出的是某一天的采集表
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timedelta

from job_agent.naming import normalize_company, normalize_title

# 「当天」按 05:00 切分：2026-11-03 的份 = 11-03 05:00 至 11-04 05:00
BIZ_PIVOT_HOUR = 5


def business_date(dt: datetime | None = None) -> str:
    """算这一条该落到哪一天的采集表里。"""
    dt = dt or datetime.now()
    return (dt - timedelta(hours=BIZ_PIVOT_HOUR)).strftime("%Y-%m-%d")


# 薪资解析：只在单位明确时才换算，没单位就留 NULL —— 不猜
_RE_SALARY_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[-~－—]\s*(\d+(?:\.\d+)?)\s*(万|千|K|k|元)?"
)
_UNIT = {"万": 10000, "千": 1000, "K": 1000, "k": 1000, "元": 1}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key        TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    tab            TEXT,
    title          TEXT,
    title_norm     TEXT,
    company        TEXT,
    company_norm   TEXT,
    company_full   TEXT,
    salary_text    TEXT,
    salary_min     INTEGER,
    salary_max     INTEGER,
    city           TEXT,
    company_city   TEXT,
    district       TEXT,
    area_text      TEXT,
    experience     TEXT,
    education      TEXT,
    company_meta   TEXT,
    company_size   TEXT,
    company_stage  TEXT,
    hiring_count   TEXT,
    jd             TEXT,
    jd_len         INTEGER,
    first_seen     TEXT,
    last_seen      TEXT,
    seen_count     INTEGER DEFAULT 1,
    biz_date       TEXT,
    raw            TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_norm);
CREATE INDEX IF NOT EXISTS idx_jobs_seen    ON jobs(last_seen);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    ended_at    TEXT,
    tabs        TEXT,
    inserted    INTEGER DEFAULT 0,
    skipped     INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0,
    note        TEXT
);
"""


# ---------------------------------------------------------------- 基础

def connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "company_city" not in cols:          # 老库补列
        conn.execute("ALTER TABLE jobs ADD COLUMN company_city TEXT")
    if "biz_date" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN biz_date TEXT")
        conn.commit()
        # 老数据按 first_seen 反推采集日
        for key, fs in conn.execute(
                "SELECT job_key, first_seen FROM jobs WHERE biz_date IS NULL").fetchall():
            try:
                dt = datetime.fromisoformat(fs)
            except (TypeError, ValueError):
                dt = datetime.now()
            conn.execute("UPDATE jobs SET biz_date = ? WHERE job_key = ?",
                         (business_date(dt), key))
    # biz_date 的索引必须在补列之后建（老库上 executescript 时这列还不存在）
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_biz ON jobs(biz_date)")
    conn.commit()
    return conn


def job_key(company: str, title: str) -> str:
    c = normalize_company(company or "")
    t = normalize_title(title or "")
    return hashlib.sha1(f"{c}|{t}".encode("utf-8")).hexdigest()[:16]


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    if not text or "面议" in text:
        return None, None
    m = _RE_SALARY_RANGE.search(text)
    if not m:
        return None, None
    unit = m.group(3)
    if not unit:
        return None, None
    mul = _UNIT[unit]
    lo = int(float(m.group(1)) * mul)
    hi = int(float(m.group(2)) * mul)
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def get(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE job_key = ?", (key,)).fetchone()


def has(conn: sqlite3.Connection, key: str) -> bool:
    return get(conn, key) is not None


# ---------------------------------------------------------------- 写入

FIELDS = [
    "job_key", "source", "tab", "title", "title_norm", "company", "company_norm",
    "company_full", "salary_text", "salary_min", "salary_max", "city",
    "company_city", "district", "area_text", "experience", "education",
    "company_meta", "company_size", "company_stage", "hiring_count", "jd",
    "jd_len", "first_seen", "last_seen", "seen_count", "biz_date", "raw",
]


def upsert(conn: sqlite3.Connection, rec: dict) -> str:
    """插入或只更新 last_seen / seen_count。返回 'inserted' / 'updated'。"""
    now = datetime.now().isoformat(timespec="seconds")
    key = job_key(rec.get("company"), rec.get("title"))
    row = get(conn, key)
    if row is not None:
        conn.execute(
            "UPDATE jobs SET last_seen = ?, seen_count = seen_count + 1 WHERE job_key = ?",
            (now, key),
        )
        conn.commit()
        return "updated"

    lo, hi = parse_salary(rec.get("salary_text") or rec.get("salary"))
    data = {
        "job_key": key,
        "source": rec.get("source") or "zhaopin",
        "tab": rec.get("tab"),
        "title": rec.get("title"),
        "title_norm": normalize_title(rec.get("title") or ""),
        "company": rec.get("company"),
        "company_norm": normalize_company(rec.get("company") or ""),
        "company_full": rec.get("company_full") or rec.get("companyFull"),
        "salary_text": rec.get("salary_text") or rec.get("salary"),
        "salary_min": lo,
        "salary_max": hi,
        "city": rec.get("city"),
        "company_city": rec.get("company_city"),
        "district": rec.get("district"),
        "area_text": rec.get("area_text") or rec.get("area"),
        "experience": rec.get("experience"),
        "education": rec.get("education"),
        "company_meta": rec.get("company_meta") or rec.get("companyMeta"),
        "company_size": rec.get("company_size") or rec.get("companySize"),
        "company_stage": rec.get("company_stage") or rec.get("companyStage"),
        "hiring_count": rec.get("hiring_count") or rec.get("hiringCount"),
        "jd": rec.get("jd"),
        "jd_len": len(rec.get("jd") or ""),
        "first_seen": now,
        "last_seen": now,
        "seen_count": 1,
        "biz_date": business_date(),
        "raw": rec.get("raw"),
    }
    conn.execute(
        f"INSERT INTO jobs ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})",
        [data.get(f) for f in FIELDS],
    )
    conn.commit()
    return "inserted"


def log_run(conn, started_at, ended_at, tabs, inserted, skipped, failed, note="") -> None:
    conn.execute(
        "INSERT INTO runs (started_at, ended_at, tabs, inserted, skipped, failed, note)"
        " VALUES (?,?,?,?,?,?,?)",
        (started_at, ended_at, tabs, inserted, skipped, failed, note),
    )
    conn.commit()


# ---------------------------------------------------------------- 查询

def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    today = business_date()
    today_count = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE biz_date = ?", (today,)
    ).fetchone()[0]
    last = conn.execute(
        "SELECT started_at, ended_at, inserted, skipped, failed FROM runs"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {
        "total": total,
        "bizDate": today,
        "todayCount": today_count,
        "lastRun": dict(last) if last else None,
    }


# ---------------------------------------------------------------- 导出

# 人工先看的列在前；薪资下限/上限是给 LLM 算区间用的，放最后不碍眼。
EXPORT_COLUMNS = [
    ("company_display", "公司名称"),
    ("title", "岗位"),
    ("salary_text", "薪资"),
    ("city", "工作城市"),
    ("company_meta_display", "公司规模/性质"),
    ("company_stage", "融资阶段"),
    ("tab", "来源tab"),
    ("jd", "JD全文"),
    ("salary_min", "薪资下限"),
    ("salary_max", "薪资上限"),
]


def counts(conn: sqlite3.Connection) -> dict:
    # 界面首页 / 数据页要的几个数：总数、今天、公司数、最后一次采集日
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    today = conn.execute("SELECT COUNT(*) FROM jobs WHERE biz_date = ?",
                         (business_date(),)).fetchone()[0]
    comps = conn.execute(
        "SELECT COUNT(DISTINCT COALESCE(company_full, company)) FROM jobs"
    ).fetchone()[0]
    last = conn.execute("SELECT MAX(biz_date) FROM jobs").fetchone()[0]
    return {"total": total, "todayCount": today,
            "companies": comps, "lastDate": last}


def recent(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    # 最近的岗位，给界面列表用
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY last_seen DESC, first_seen DESC "
        "LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]


def export_xlsx(conn: sqlite3.Connection, path: str,
                date: str | None = None) -> tuple[bool, str, int]:
    """导出某一天的采集表（05:00 切日）。date 为空 = 今天这一份。

    返回 (是否 xlsx, 实际路径, 行数)。
    """
    date = date or business_date()
    rows = conn.execute(
        "SELECT *,"
        "       COALESCE(company, company_full)            AS company_display,"
        "       COALESCE(NULLIF(company_meta, ''), company_size)"
        "                                                 AS company_meta_display"
        "  FROM jobs WHERE biz_date = ? ORDER BY first_seen",
        (date,),
    ).fetchall()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        csv_path = os.path.splitext(path)[0] + ".csv"
        import csv

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow([label for _, label in EXPORT_COLUMNS])
            for r in rows:
                w.writerow([r[k] for k, _ in EXPORT_COLUMNS])
        return False, csv_path, len(rows)

    wb = Workbook()
    ws = wb.active
    ws.title = date
    ws.append([label for _, label in EXPORT_COLUMNS])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r[k] for k, _ in EXPORT_COLUMNS])

    widths = {"公司名称": 30, "岗位": 24, "薪资": 16, "工作城市": 12,
              "公司规模/性质": 34, "JD全文": 90,
              "薪资下限": 10, "薪资上限": 10}
    for i, (_, label) in enumerate(EXPORT_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = \
            widths.get(label, 12)
    ws.freeze_panes = "A2"

    wb.save(path)
    return True, path, len(rows)


# ============================================================ P1 · v7 契约接口
# 说明：老接口（upsert/stats/recent/export_xlsx …）全部原样保留，服务于 legacy
# `jobs` 表；下面是 P1 新增的 v7 读写层，只在数据库里存在 `schema_version` 时生效。
# 命名上避开 export_xlsx，是因为那个名字已经被 legacy 导出占用，不能覆盖。

POOL_EXCLUDED = ("excluded",)          # 不进待评估池的状态；仍可查、可改回


def project_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_db_path(config_path: str | None = None) -> str:
    """按优先级定位数据库：env JOBAGENT_DB → config.json 的 db_path → 默认 data/jobs.db。

    默认值与 P1 之前完全一致（`<项目>\\data\\jobs.db`），不改变现有行为。
    """
    env = os.environ.get("JOBAGENT_DB")
    if env:
        return os.path.abspath(env)
    cfg_file = config_path or os.path.join(project_dir(), "config.json")
    try:
        import json
        with open(cfg_file, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        for key in ("db_path", "dbPath"):
            if cfg.get(key):
                p = cfg[key]
                return p if os.path.isabs(p) else os.path.join(project_dir(), p)
    except (OSError, ValueError):
        pass
    return os.path.join(project_dir(), "data", "jobs.db")


def has_v7(conn: sqlite3.Connection) -> bool:
    """库里有没有 v7 契约（schema_version ≥ 2）。"""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(row and row[0] and row[0] >= 2)


def _pool_sql(pool_only: bool) -> str:
    if not pool_only:
        return ""
    marks = ", ".join("?" * len(POOL_EXCLUDED))
    return f" AND COALESCE(j.status, 'open') NOT IN ({marks})"


def list_jobs(conn: sqlite3.Connection, query: str | None = None,
              city: str | None = None, status: str | None = None,
              pool_only: bool = False, limit: int = 500) -> list[dict]:
    """岗位列表。搜索四路并集：FTS5 + 标题/公司 LIKE + 笔记三列 LIKE + note LIKE。

    返回的 note_hit=1 表示「命中的是我写的笔记」，列表里给个淡色小点。
    """
    where: list[str] = ["1=1"]
    args: list = []
    select_extra = "0 AS note_hit"
    select_args: list = []

    q = (query or "").strip()
    if q:
        like = f"%{q}%"
        note_cols = ("COALESCE(j.analysis,'')", "COALESCE(j.fail_reason,'')",
                     "COALESCE(j.advice,'')", "COALESCE(j.note,'')")
        ors = ["j.title LIKE ?", "c.name LIKE ?", "COALESCE(j.jd_text,'') LIKE ?"]
        params: list = [like, like, like]
        ors += [f"{col} LIKE ?" for col in note_cols]
        params += [like] * len(note_cols)

        if len(q) >= 3:
            try:
                ids = [r[0] for r in conn.execute(
                    "SELECT job_id FROM job_fts WHERE job_fts MATCH ?", (q,)).fetchall()]
                if ids:
                    marks = ", ".join("?" * len(ids))
                    ors.append(f"j.id IN ({marks})")
                    params += ids
            except sqlite3.OperationalError:
                pass                      # FTS 语法不认，只留 LIKE

        where.append("(" + " OR ".join(ors) + ")")
        args += params
        select_extra = ("CASE WHEN " + " OR ".join(f"{col} LIKE ?" for col in note_cols)
                        + " THEN 1 ELSE 0 END AS note_hit")
        select_args = [like] * len(note_cols)

    if city:
        where.append("COALESCE(j.city_norm, j.city) = ?")
        args.append(city)
    if status:
        where.append("COALESCE(j.status, 'pending') = ?")
        args.append(status)
    if pool_only:
        marks = ", ".join("?" * len(POOL_EXCLUDED))
        where.append(f"COALESCE(j.status, 'pending') NOT IN ({marks})")
        args += list(POOL_EXCLUDED)

    sql = f"""
        SELECT j.id, j.title, COALESCE(c.name, '') AS company,
               COALESCE(j.city, '') AS city, COALESCE(j.salary_text, '') AS salary,
               COALESCE(j.salary_min, 0) AS salary_min,
               COALESCE(j.status, 'pending') AS status, j.first_seen,
               COALESCE(j.jd_len, 0) AS jd_len, COALESCE(j.is_starred, 0) AS starred,
               COALESCE(j.note, '') AS note,
               COALESCE(j.analysis, '') AS analysis,
               COALESCE(j.fail_reason, '') AS fail_reason,
               COALESCE(j.advice, '') AS advice,
               j.company_id, j.version, {select_extra}
          FROM job j LEFT JOIN company c ON c.id = j.company_id
         WHERE {' AND '.join(where)} AND j.deleted_at IS NULL
         ORDER BY j.first_seen DESC, j.title
         LIMIT ?
    """
    return [dict(r) for r in conn.execute(sql, select_args + args + [limit])]


def todo_jobs(conn: sqlite3.Connection, city: str | None = None,
              limit: int = 500) -> list[dict]:
    """待评估池：入库但排除了短 JD 等状态。"""
    return list_jobs(conn, city=city, pool_only=True, limit=limit)


def list_companies(conn: sqlite3.Connection) -> list[dict]:
    sql = """
        SELECT c.id, c.name, COALESCE(c.city, '') AS city,
               COALESCE(c.conclusion, '') AS conclusion,
               COALESCE(c.is_starred, 0) AS starred,
               (SELECT COUNT(*) FROM job j
                 WHERE j.company_id = c.id AND j.deleted_at IS NULL) AS jobs
          FROM company c
         WHERE c.deleted_at IS NULL
         ORDER BY jobs DESC, c.name
    """
    return [dict(r) for r in conn.execute(sql)]


def set_job_status(conn: sqlite3.Connection, job_id: str, status: str,
                   updated_by: str = "ui") -> int:
    """改岗位状态（「改回正常」用它）。返回新的 version；没这行抛 KeyError。"""
    row = conn.execute("SELECT version FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    ver = row[0]
    cur = conn.execute(
        "UPDATE job SET status = ?, version = version + 1, updated_by = ?, "
        "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id = ? AND version = ?", (status, updated_by, job_id, ver))
    if cur.rowcount == 0:
        raise RuntimeError("版本冲突，请刷新后重试")
    conn.commit()
    return ver + 1


class ConflictError(RuntimeError):
    """乐观锁冲突：这行在别处被改过。"""


USER_EDITABLE = (
    "status", "is_starred", "tags", "note", "salary_text",
    "analysis", "fail_reason", "advice",
)
STATUS_ALL = ("pending", "recommend", "caution", "interviewing",
              "rejected", "declined", "excluded")


def update_user_fields(conn: sqlite3.Connection, job_id: str, fields: dict,
                       expect_version: int) -> int:
    """按白名单改人工字段（就地编辑 / 右键改状态都走它）。返回新 version。

    - 只允许 USER_EDITABLE 里的列，别的一律抛 ValueError（采集事实不许手改）
    - 带乐观锁：版本不匹配抛 ConflictError，调用方刷新后由用户决定
    """
    bad = [k for k in fields if k not in USER_EDITABLE]
    if bad:
        raise ValueError(f"这些字段不允许手改：{bad}")
    if not fields:
        return expect_version

    sets = ", ".join(f"{k} = ?" for k in fields)
    args = list(fields.values()) + [job_id, expect_version]
    cur = conn.execute(
        f"UPDATE job SET {sets}, version = version + 1, updated_by = 'user', "
        f"updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        f"WHERE id = ? AND version = ?", args)
    if cur.rowcount == 0:
        conn.rollback()
        raise ConflictError("这条已被改过，已刷新为最新")
    conn.commit()
    return expect_version + 1


def set_status_many(conn: sqlite3.Connection, items: list[tuple[str, int]],
                    status: str) -> tuple[int, int]:
    """批量改状态。items = [(job_id, version), …]。返回 (成功数, 冲突数)。

    单事务：任何一条冲突都整批回滚，避免「改了一半」。
    """
    if status not in STATUS_ALL:
        raise ValueError(f"未知状态：{status}")
    ok = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for job_id, ver in items:
            cur = conn.execute(
                "UPDATE job SET status = ?, version = version + 1, updated_by = 'user', "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE id = ? AND version = ?", (status, job_id, ver))
            if cur.rowcount == 0:
                raise ConflictError("有行已被改过")
            ok += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ok, 0


def list_job_revisions(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    """这条岗位的 JD 变更历史（采集侧写的 job_revision）。"""
    try:
        rows = conn.execute(
            "SELECT jd_hash, jd_len, captured_at FROM job_revision "
            "WHERE job_id = ? ORDER BY captured_at DESC LIMIT 50", (job_id,)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def stats_v7(conn: sqlite3.Connection) -> dict:
    """页面顶部要的数：总数、待评估池、短 JD、公司数。"""
    jobs = conn.execute("SELECT COUNT(*) FROM job WHERE deleted_at IS NULL").fetchone()[0]
    marks = ", ".join("?" * len(POOL_EXCLUDED))
    short = conn.execute(
        f"SELECT COUNT(*) FROM job WHERE deleted_at IS NULL "
        f"AND COALESCE(status,'open') IN ({marks})", POOL_EXCLUDED).fetchone()[0]
    comps = conn.execute(
        "SELECT COUNT(*) FROM company WHERE deleted_at IS NULL").fetchone()[0]
    return {"jobs": jobs, "pool": jobs - short, "short_jd": short, "companies": comps}


EXPORT_V7_COLUMNS = [
    ("company", "公司"),
    ("title", "岗位"),
    ("salary", "薪资"),
    ("city", "城市"),
    ("status", "状态"),
    ("first_seen", "首次见"),
    ("jd_len", "JD字数"),
    ("starred", "星标"),
    ("note", "备注"),
]


def export_md(conn: sqlite3.Connection, path: str, date: str | None = None) -> tuple[bool, str, int]:
    """给 AI 读的纯文本摘要：和 xlsx 同目录同前缀，省得再建文件夹。"""
    import pathlib

    where, params = "", []
    if date:
        where = "WHERE j.biz_date = ?"
        params = [date]
    rows = conn.execute(
        f"""SELECT c.name, c.full_name, j.title, j.salary_text, j.salary_min,
                   j.city, j.status, j.analysis, j.fail_reason, j.advice,
                   j.jd_text, s.url, j.first_seen
              FROM job j LEFT JOIN company c ON c.id = j.company_id
              LEFT JOIN (SELECT job_id, MIN(url) AS url FROM job_source GROUP BY job_id) s
                     ON s.job_id = j.id
              {where}
             ORDER BY COALESCE(j.salary_min, 0) DESC, j.title""",
        params,
    ).fetchall()

    STATUS = {"pending": "待评估", "recommend": "建议投", "caution": "谨慎投",
              "interviewing": "面试中", "rejected": "已淘汰", "declined": "已拒绝",
              "excluded": "已排除"}
    lines = []
    kept = [r for r in rows if (r[6] or "") != "excluded"]
    dropped = len(rows) - len(kept)
    head = f"# 岗位采集 · {date or '全部'}"
    lines.append(head)
    lines.append("")
    lines.append(f"共 {len(kept)} 条" + (f"（另有 {dropped} 条 JD 过短已排除，未列出）" if dropped else ""))
    lines.append("")
    for i, (name, full, title, sal, smin, city, st, ana, fail, adv, jd, url, seen) in enumerate(kept, 1):
        lines.append(f"## {i}. {name or full or '（未知公司）'} · {title or '（无标题）'}")
        meta = []
        if sal:
            meta.append(f"薪资：{sal}")
        if city:
            meta.append(f"城市：{city}")
        meta.append(f"状态：{STATUS.get(st or '', st or '—')}")
        if seen:
            meta.append(f"首次见：{str(seen)[:10]}")
        lines.append("- " + " ｜ ".join(meta))
        if url:
            lines.append(f"- 链接：{url}")
        for label_, val in (("岗位评估", ana), ("失败原因", fail), ("投递建议", adv)):
            if val and str(val).strip():
                lines.append(f"\n**{label_}**：{str(val).strip()}")
        if jd and str(jd).strip():
            lines.append(f"\n**JD 原文**：\n\n```\n{str(jd).strip()}\n```")
        lines.append("")
    lines.append("---")
    lines.append("以上数据由 Job Agent 导出，可直接交给 AI 做岗位分析。")

    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return True, str(out), len(kept)


def export_xlsx_v7(conn: sqlite3.Connection, path: str) -> tuple[bool, str, int]:
    """导出岗位表；前两列 `_id` / `_version` 隐藏，为 P1.5 的受控回写铺路。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    rows = list_jobs(conn, limit=100000)
    wb = Workbook()
    ws = wb.active

    head = ["_id", "_version"] + [label for _, label in EXPORT_V7_COLUMNS]
    ws.append(head)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in rows:
        ws.append([r["id"], r["version"]] + [r.get(key, "") for key, _ in EXPORT_V7_COLUMNS])

    ws.column_dimensions["A"].hidden = True
    ws.column_dimensions["B"].hidden = True
    ws.freeze_panes = "C2"

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
    return True, path, len(rows)
