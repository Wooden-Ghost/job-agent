"""薪资：新表的 min/max/months 必须能与 legacy 的 salary_text 对上，『面议』保持空。"""
from __future__ import annotations

import sqlite3
import sys
import unittest

from _util import ROOT, migrated_but_empty

sys.path.insert(0, str(ROOT / "etl"))
import import_jobhunt as etl  # noqa: E402

# (salary_text, salary_min, salary_max, salary_months)
EXPECT = [
    ("面议", None, None, None),
    ("5000-10000元", 5000, 10000, None),
    ("7000-12000元", 7000, 12000, None),
]


class SalaryParseTest(unittest.TestCase):
    def test_parse_months(self):
        self.assertEqual(etl.parse_months("8000-12000元·13薪"), 13)
        self.assertEqual(etl.parse_months("8000-12000元·14薪"), 14)
        self.assertIsNone(etl.parse_months("5000-10000元"))
        self.assertIsNone(etl.parse_months("面议"))
        self.assertIsNone(etl.parse_months(None))


class SalaryRowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = migrated_but_empty()
        conn = sqlite3.connect(cls.db)
        conn.row_factory = sqlite3.Row
        plan = etl.build_plan(etl.load_legacy(conn))
        etl.insert_all(conn, plan)
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.db.unlink(missing_ok=True)

    def test_samples_match(self):
        conn = sqlite3.connect(self.db)
        try:
            for text, lo, hi, months in EXPECT:
                row = conn.execute(
                    "SELECT salary_min, salary_max, salary_months FROM job "
                    "WHERE salary_text = ? LIMIT 1", (text,)).fetchone()
                if row is None:
                    continue  # 该样例不在本次数据里，跳过
                self.assertEqual((row[0], row[1]), (lo, hi), f"{text} 的金额对不上")
                self.assertIsNone(row[2], f"{text} 不该有月数")
        finally:
            conn.close()

    def test_13_month_rows_carry_months(self):
        conn = sqlite3.connect(self.db)
        try:
            rows = list(conn.execute(
                "SELECT salary_text, salary_months FROM job WHERE salary_text LIKE '%薪%'"))
        finally:
            conn.close()
        self.assertTrue(rows, "legacy 里应有带『薪』的样例")
        for text, months in rows:
            self.assertIsNotNone(months, f"{text!r} 的月数没解析出来")

    def test_salary_min_not_greater_than_max(self):
        conn = sqlite3.connect(self.db)
        try:
            bad = conn.execute(
                "SELECT count(*) FROM job WHERE salary_min IS NOT NULL "
                "AND salary_max IS NOT NULL AND salary_min > salary_max").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(bad, 0)


if __name__ == "__main__":
    unittest.main()
