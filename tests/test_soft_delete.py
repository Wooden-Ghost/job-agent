"""软删 + 部分唯一索引：deleted_at IS NULL 的行才占位，删掉之后同名可以重建。"""
from __future__ import annotations

import sqlite3
import unittest

from _util import empty_db_from_schema

TS = "2026-11-04T00:00:00Z"

BASE_COMPANY = (
    "INSERT INTO company (id,name,norm_name,first_seen,last_seen,created_at,updated_at) "
    "VALUES (?,?,?,?,?,?,?)"
)


def _add_company(conn, cid, name, norm):
    conn.execute(BASE_COMPANY, (cid, name, norm, TS, TS, TS, TS))


def _add_job(conn, jid, cid, key, title, title_norm, city_norm):
    conn.execute(
        "INSERT INTO job (id,company_id,job_key,title,title_norm,city,city_norm,biz_date,"
        "first_seen,last_seen,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (jid, cid, key, title, title_norm, "成都", city_norm, "2026-11-04", TS, TS, TS, TS))


class CompanySoftDeleteTest(unittest.TestCase):
    def setUp(self):
        self.db = empty_db_from_schema()
        self.conn = sqlite3.connect(self.db)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def tearDown(self):
        self.conn.close()
        self.db.unlink(missing_ok=True)

    def test_two_live_same_norm_conflict(self):
        _add_company(self.conn, "c1", "甲公司", "甲公司")
        with self.assertRaises(sqlite3.IntegrityError):
            _add_company(self.conn, "c2", "甲公司", "甲公司")

    def test_soft_deleted_frees_the_name(self):
        _add_company(self.conn, "c1", "甲公司", "甲公司")
        self.conn.execute("UPDATE company SET deleted_at=? WHERE id='c1'", (TS,))
        _add_company(self.conn, "c2", "甲公司", "甲公司")  # 不该冲突
        live = self.conn.execute(
            "SELECT count(*) FROM company WHERE norm_name='甲公司' AND deleted_at IS NULL"
        ).fetchone()[0]
        self.assertEqual(live, 1)

    def test_two_soft_deleted_same_norm_ok(self):
        _add_company(self.conn, "c1", "甲公司", "甲公司")
        _add_company(self.conn, "c2", "甲公司", "甲公司") if False else None
        self.conn.execute("UPDATE company SET deleted_at=? WHERE id='c1'", (TS,))
        _add_company(self.conn, "c2", "甲公司", "甲公司")
        self.conn.execute("UPDATE company SET deleted_at=? WHERE id='c2'", (TS,))
        total = self.conn.execute("SELECT count(*) FROM company").fetchone()[0]
        self.assertEqual(total, 2)


class JobSoftDeleteTest(unittest.TestCase):
    def setUp(self):
        self.db = empty_db_from_schema()
        self.conn = sqlite3.connect(self.db)
        self.conn.execute("PRAGMA foreign_keys = ON")
        _add_company(self.conn, "c1", "甲公司", "甲公司")

    def tearDown(self):
        self.conn.close()
        self.db.unlink(missing_ok=True)

    def test_two_live_same_triple_conflict(self):
        _add_job(self.conn, "j1", "c1", "k1", "数据分析师", "数据分析师", "成都")
        with self.assertRaises(sqlite3.IntegrityError):
            _add_job(self.conn, "j2", "c1", "k2", "数据分析师", "数据分析师", "成都")

    def test_soft_deleted_allows_same_triple(self):
        _add_job(self.conn, "j1", "c1", "k1", "数据分析师", "数据分析师", "成都")
        self.conn.execute("UPDATE job SET deleted_at=? WHERE id='j1'", (TS,))
        _add_job(self.conn, "j2", "c1", "k2", "数据分析师", "数据分析师", "成都")
        live = self.conn.execute(
            "SELECT count(*) FROM job WHERE deleted_at IS NULL").fetchone()[0]
        self.assertEqual(live, 1)

    def test_same_title_different_city_different_job(self):
        _add_job(self.conn, "j1", "c1", "k1", "数据分析师", "数据分析师", "成都")
        _add_job(self.conn, "j2", "c1", "k2", "数据分析师", "数据分析师", "重庆")
        n = self.conn.execute("SELECT count(*) FROM job").fetchone()[0]
        self.assertEqual(n, 2, "城市不同应是两个岗位（city 进唯一键）")


if __name__ == "__main__":
    unittest.main()
