"""测试公用工具：造一个干净的、带 legacy jobs 的临时库。

策略：以 `tests/fixtures/legacy_sample.db` 为模板（**合成数据**，4 家公司 / 6 个岗位，
已跑过 0002 迁移），复制一份，再把新表清空 —— 每个测试都从「legacy 有数据、新表为空」
的确定状态开始，既不依赖真库 `data/jobs.db`，仓库里也不会有任何真实岗位数据。

模板由 `tests/fixtures/build_fixture.py` 生成；改了结构就重跑它。
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEMPLATE = ROOT / "tests" / "fixtures" / "legacy_sample.db"
SCHEMA_SQL = ROOT / "db" / "schema.sql"
MIGRATION_SQL = ROOT / "db" / "migrations" / "0002_initial_contract.sql"

# 模板里有多少数据（改 build_fixture.py 的 ROWS 时要同步这两个数）
FIXTURE_JOBS = 6
FIXTURE_COMPANIES = 4

NEW_TABLES = ("company_alias", "job_source", "job_revision",
              "due_diligence_evidence", "due_diligence_verdict",
              "screening", "job", "company")


def _fresh_path() -> Path:
    """一个还不存在的临时 .db 路径（Windows 上不能先 mkstemp 再 unlink，句柄没关就锁着）。"""
    d = Path(tempfile.mkdtemp(prefix="jag-p0-"))
    return d / "t.db"


def empty_db_from_schema() -> Path:
    """按 db/schema.sql 建一个全新空库（无 legacy 表）。"""
    name = _fresh_path()
    conn = sqlite3.connect(name)
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return name


def migrated_but_empty() -> Path:
    """带 legacy jobs、新表已建但为空（导入前的状态）。"""
    if not TEMPLATE.exists():
        raise RuntimeError(
            f"缺少测试模板 {TEMPLATE}\n先跑：python tests/fixtures/build_fixture.py")
    name = _fresh_path()
    shutil.copy2(TEMPLATE, name)
    conn = sqlite3.connect(name)
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in NEW_TABLES:
        try:
            conn.execute(f"DELETE FROM {t}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("DELETE FROM job_fts")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
    return Path(name)


def apply_migration(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATION_SQL.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def counts(path: Path, tables=("company", "job", "job_source", "job_revision", "screening")) -> dict:
    conn = sqlite3.connect(path)
    try:
        return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        conn.close()


def schema_of(path: Path) -> dict[str, list[tuple]]:
    """{表名: [(列名, 类型, notnull, pk), ...]}，用于同构比对。"""
    conn = sqlite3.connect(path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'job_fts_%' ORDER BY name")]
        return {t: [tuple(r[1:5]) for r in conn.execute(f"PRAGMA table_info({t})")]
                for t in tables}
    finally:
        conn.close()


def indexes_of(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")}
    finally:
        conn.close()
