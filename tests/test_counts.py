"""迁移 + 导入后的计数闸：4 家公司 / 6 个岗位 / 各 6 条来源与版本，schema_version=2。"""
from __future__ import annotations

import sqlite3
import sys
import unittest

from _util import FIXTURE_COMPANIES, FIXTURE_JOBS, ROOT, counts, migrated_but_empty

sys.path.insert(0, str(ROOT / "etl"))
import import_jobhunt as etl  # noqa: E402

EXPECT = {"company": FIXTURE_COMPANIES, "job": FIXTURE_JOBS,
          "job_source": FIXTURE_JOBS, "job_revision": FIXTURE_JOBS, "screening": 0}


class CountsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = migrated_but_empty()
        conn = sqlite3.connect(cls.db)
        conn.row_factory = sqlite3.Row
        legacy = etl.load_legacy(conn)
        cls.legacy_n = len(legacy)
        plan = etl.build_plan(legacy)
        cls.stats = etl.insert_all(conn, plan)
        conn.commit()
        cls.ver = [r[0] for r in conn.execute("SELECT version FROM schema_version")]
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.db.unlink(missing_ok=True)

    def test_legacy_rows(self):
        self.assertEqual(self.legacy_n, FIXTURE_JOBS)

    def test_counts(self):
        got = counts(self.db)
        self.assertEqual(got, EXPECT, f"计数不符：{got}")

    def test_schema_version(self):
        self.assertEqual(self.ver, [2])

    def test_alias_is_empty(self):
        """合成数据里 company == company_full，没有一条别名可推断。"""
        self.assertEqual(counts(self.db, ("company_alias",))["company_alias"], 0)

    def test_second_run_is_noop(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        plan = etl.build_plan(etl.load_legacy(conn))
        stats = etl.insert_all(conn, plan)
        conn.commit()
        conn.close()
        self.assertEqual(stats.get("company_insert", 0), 0, stats)
        self.assertEqual(stats.get("job_insert", 0), 0, stats)
        self.assertEqual(counts(self.db), EXPECT, "重跑后计数变了")

    def test_every_job_has_company_and_source(self):
        conn = sqlite3.connect(self.db)
        try:
            orphan = conn.execute(
                "SELECT count(*) FROM job j LEFT JOIN company c ON c.id = j.company_id "
                "WHERE c.id IS NULL").fetchone()[0]
            no_src = conn.execute(
                "SELECT count(*) FROM job j WHERE NOT EXISTS "
                "(SELECT 1 FROM job_source s WHERE s.job_id = j.id)").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(orphan, 0, "有 job 指向不存在的 company")
        self.assertEqual(no_src, 0, "有 job 没有 job_source")

    def test_times_are_utc(self):
        conn = sqlite3.connect(self.db)
        try:
            bad = conn.execute(
                "SELECT count(*) FROM job WHERE first_seen NOT LIKE '%Z' "
                "OR last_seen NOT LIKE '%Z'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(bad, 0, "job 的时间字段不是 UTC ISO8601（应以 Z 结尾）")


if __name__ == "__main__":
    unittest.main()
