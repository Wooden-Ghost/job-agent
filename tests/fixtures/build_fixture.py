"""生成测试用的合成 legacy 库（tests/fixtures/legacy_sample.db）。

为什么要有这个脚本：
    测试需要「有 legacy 数据的库」当模板，但真实库里有真实公司名、薪资和 JD，
    不能进仓库。所以这里用合成数据造一份结构完全相同的库：表结构照抄线上
    legacy 表，内容是 4 家公司 / 6 个岗位的假数据，JD 有长有短（覆盖
    jd_too_short 分支）。

用法（改了这个脚本或 schema 之后重新生成）：
    python tests/fixtures/build_fixture.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "legacy_sample.db"
MIGRATION_SQL = ROOT / "db" / "migrations" / "0002_initial_contract.sql"

LEGACY_DDL = """
CREATE TABLE jobs (
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
    raw            TEXT,
    biz_date       TEXT
);
CREATE INDEX idx_jobs_company ON jobs(company_norm);
CREATE INDEX idx_jobs_seen    ON jobs(last_seen);
CREATE INDEX idx_jobs_biz     ON jobs(biz_date);
CREATE TABLE runs (
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

JD_LONG = (
    "岗位职责：\n"
    "1. 负责业务系统的后端服务设计与开发，参与需求评审与技术方案评审；\n"
    "2. 负责数据链路的稳定性建设，包括采集、清洗、落库与监控告警；\n"
    "3. 参与系统性能优化，定位并解决线上问题；\n"
    "4. 编写技术文档，参与代码评审。\n"
    "任职要求：\n"
    "1. 本科及以上学历，计算机相关专业，3 年以上后端开发经验；\n"
    "2. 熟悉 Python 或 Go，熟悉常用 web 框架；\n"
    "3. 熟悉 MySQL / PostgreSQL，了解索引与事务；\n"
    "4. 有良好的工程习惯，能独立负责模块。"
)
JD_SHORT = "负责后端开发，熟悉 Python 即可。"

# (公司, 岗位, 薪资文本, 下限, 上限, 城市, 区, JD, 首次, 最近, 批次日)
ROWS = [
    ("甲乙数据科技有限公司", "后端开发工程师", "1.2-1.8万", 12000, 18000, "成都", "武侯区",
     JD_LONG, "2026-10-01T09:10:00", "2026-10-02T10:00:00", "2026-10-02"),
    ("甲乙数据科技有限公司", "数据开发工程师", "1.5-2.2万", 15000, 22000, "成都", "武侯区",
     JD_LONG, "2026-10-01T09:20:00", "2026-10-01T09:20:00", "2026-10-01"),
    ("丙丁网络科技有限公司", "Python 开发工程师", "8000-12000元", 8000, 12000, "成都", "高新区",
     JD_SHORT, "2026-10-02T11:00:00", "2026-10-02T11:00:00", "2026-10-02"),
    ("戊己智能科技有限公司", "算法工程师", "2-3万·14薪", 20000, 30000, "成都", "双流区",
     JD_LONG, "2026-10-03T14:30:00", "2026-10-04T08:00:00", "2026-10-04"),
    ("戊己智能科技有限公司", "机器学习工程师", "1.8-2.5万", 18000, 25000, "成都", "双流区",
     JD_LONG, "2026-10-03T15:00:00", "2026-10-03T15:00:00", "2026-10-03"),
    ("庚辛信息技术有限公司", "测试开发工程师", "1-1.5万", 10000, 15000, "成都", "青羊区",
     JD_SHORT, "2026-10-04T16:00:00", "2026-10-04T16:00:00", "2026-10-04"),
]


def build() -> Path:
    if OUT.exists():
        OUT.unlink()
    conn = sqlite3.connect(OUT)
    conn.executescript(LEGACY_DDL)
    # 跑一遍 0002：建 v7 空表并把 schema_version 置为 2（与真实库同一状态）
    conn.executescript(MIGRATION_SQL.read_text(encoding="utf-8"))

    for i, (company, title, sal, lo, hi, city, district, jd,
            first, last, biz) in enumerate(ROWS, start=1):
        key = f"{i:016x}"
        conn.execute(
            "INSERT INTO jobs (job_key, source, tab, title, title_norm, company,"
            " company_norm, company_full, salary_text, salary_min, salary_max, city,"
            " company_city, district, area_text, experience, education, company_meta,"
            " company_size, company_stage, hiring_count, jd, jd_len, first_seen,"
            " last_seen, seen_count, raw, biz_date)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, "示例招聘", "推荐", title, title, company, company, company, sal, lo, hi,
             city, city, district, "", "3-5年", "本科", "", "100-499人", "不需要融资",
             "招2人", jd, len(jd), first, last, 1, "{}", biz))

    conn.execute("INSERT INTO runs (started_at, ended_at, tabs, inserted, skipped, failed, note)"
                 " VALUES ('2026-10-01T09:00:00','2026-10-01T09:30:00','[\"推荐\"]',2,5,0,'fixture')")
    conn.commit()
    conn.close()
    return OUT


if __name__ == "__main__":
    p = build()
    c = sqlite3.connect(p)
    n_jobs = c.execute("SELECT count(*) FROM jobs").fetchone()[0]
    n_co = c.execute("SELECT count(DISTINCT company) FROM jobs").fetchone()[0]
    ver = [r[0] for r in c.execute("SELECT version FROM schema_version")]
    c.close()
    print(f"生成 {p}")
    print(f"  岗位 {n_jobs} 条 / 公司 {n_co} 家 / schema_version {ver} / {p.stat().st_size} 字节")
