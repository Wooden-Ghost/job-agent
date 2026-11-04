"""schema.sql 建出来的库，结构该有的都有。"""
from __future__ import annotations

import sqlite3
import unittest

from _util import empty_db_from_schema

EXPECTED_TABLES = {
    "schema_version", "company", "company_alias", "job", "job_source", "job_revision",
    "due_diligence_evidence", "due_diligence_verdict", "screening", "job_fts",
}
EXPECTED_VIEWS = {"v_job_search", "v_todo_all"}
EXPECTED_INDEXES = {
    "ux_company_norm", "ux_alias_norm", "ix_alias_company",
    "ux_job_key3", "ix_job_key", "ix_job_biz", "ix_job_comp", "ix_job_legacy",
    "ux_source_ext", "ix_source_job",
    "ix_rev_job", "ix_evidence_company", "ix_verdict_company",
    "ix_screening_job", "ix_screening_company",
}
# v6/v7 删掉的表，绝不能出现
REMOVED_TABLES = {"candidate", "resume_version", "application",
                  "application_event", "interview", "evaluation"}


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self.db = empty_db_from_schema()
        self.conn = sqlite3.connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.db.unlink(missing_ok=True)

    def _names(self, kind: str) -> set[str]:
        return {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type=?", (kind,))}

    def test_tables_exist(self):
        have = self._names("table")
        missing = EXPECTED_TABLES - have
        self.assertFalse(missing, f"缺表: {missing}")

    def test_removed_tables_absent(self):
        have = self._names("table")
        leaked = REMOVED_TABLES & have
        self.assertFalse(leaked, f"v6 已删除的表又出现了: {leaked}")

    def test_views_exist(self):
        missing = EXPECTED_VIEWS - self._names("view")
        self.assertFalse(missing, f"缺视图: {missing}")

    def test_indexes_exist(self):
        have = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")}
        missing = EXPECTED_INDEXES - have
        self.assertFalse(missing, f"缺索引: {missing}")

    def test_user_writable_columns(self):
        """v7：company/job 各有 4 个用户侧字段；screening 有 note。"""
        for table in ("company", "job"):
            cols = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col in ("is_starred", "tags", "note", "updated_by"):
                self.assertIn(col, cols, f"{table} 缺 {col}")
            self.assertIn("version", cols)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(screening)")}
        for col in ("note", "fail_reason", "suggestion", "conclusion", "total"):
            self.assertIn(col, cols, f"screening 缺 {col}")

    def test_version_default_is_one(self):
        self.conn.execute(
            "INSERT INTO company (id,name,norm_name,first_seen,last_seen,created_at,updated_at) "
            "VALUES ('c1','甲公司','甲公司','2026-11-04T00:00:00Z','2026-11-04T00:00:00Z',"
            "'2026-11-04T00:00:00Z','2026-11-04T00:00:00Z')")
        v = self.conn.execute("SELECT version FROM company WHERE id='c1'").fetchone()[0]
        self.assertEqual(v, 1)

    def test_fts_is_usable(self):
        self.conn.execute(
            "INSERT INTO company (id,name,norm_name,first_seen,last_seen,created_at,updated_at) "
            "VALUES ('c1','甲公司','甲公司','2026-11-04T00:00:00Z','2026-11-04T00:00:00Z',"
            "'2026-11-04T00:00:00Z','2026-11-04T00:00:00Z')")
        self.conn.execute(
            "INSERT INTO job (id,company_id,job_key,title,title_norm,biz_date,"
            "first_seen,last_seen,created_at,updated_at) VALUES "
            "('j1','c1','k1','数据分析师','数据分析师','2026-11-04',"
            "'2026-11-04T00:00:00Z','2026-11-04T00:00:00Z',"
            "'2026-11-04T00:00:00Z','2026-11-04T00:00:00Z')")
        self.conn.execute(
            "INSERT INTO job_fts (job_id,title,jd_text) VALUES "
            "('j1','数据分析师','基于大模型构建智能开发应用，会 Python 与 正则')")
        # ≥3 字：trigram 命中
        n = self.conn.execute(
            "SELECT count(*) FROM job_fts WHERE job_fts MATCH ?", ("大模型",)).fetchone()[0]
        self.assertEqual(n, 1)
        # 2 字：trigram 命中 0，必须靠 LIKE 兜底
        n2 = self.conn.execute(
            "SELECT count(*) FROM job_fts WHERE job_fts MATCH ?", ("国企",)).fetchone()[0]
        self.assertEqual(n2, 0)
        like = self.conn.execute(
            "SELECT count(*) FROM job WHERE title LIKE ?", ("%数据%",)).fetchone()[0]
        self.assertEqual(like, 1)


if __name__ == "__main__":
    unittest.main()
