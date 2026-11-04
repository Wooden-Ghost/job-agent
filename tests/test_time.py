"""时间换算：本地 → UTC，biz_date 不动；换算不可逆的输入要老实返回 None。"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
import unittest

from _util import FIXTURE_JOBS, ROOT, migrated_but_empty

sys.path.insert(0, str(ROOT / "etl"))
import import_jobhunt as etl  # noqa: E402

SAMPLES = [
    ("2026-11-04T07:10:13", "2026-11-03T23:10:13Z"),
    ("2026-11-04T15:11:31", "2026-11-04T07:11:31Z"),
    ("2026-11-04T15:12:35", "2026-11-04T07:12:35Z"),
]


class ToUtcTest(unittest.TestCase):
    def test_three_samples(self):
        for local, want in SAMPLES:
            self.assertEqual(etl.to_utc(local), want, f"{local} 换算错")

    def test_space_separator(self):
        self.assertEqual(etl.to_utc("2026-11-04 15:12:35"), "2026-11-04T07:12:35Z")

    def test_none_and_garbage(self):
        self.assertIsNone(etl.to_utc(None))
        self.assertIsNone(etl.to_utc(""))
        self.assertIsNone(etl.to_utc("不是时间"))

    def test_city_normalize(self):
        self.assertEqual(etl.normalize_city("成都"), "成都")
        self.assertEqual(etl.normalize_city("成都市"), "成都")
        self.assertEqual(etl.normalize_city(""), "remote")
        self.assertEqual(etl.normalize_city("远程"), "remote")


class BizDateUnchangedTest(unittest.TestCase):
    def test_biz_date_survives(self):
        db = migrated_but_empty()
        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            # 用多重集比对：job_key 新旧算法不同，不能按 key 对齐
            legacy = Counter(r["biz_date"] for r in conn.execute(
                "SELECT biz_date FROM jobs"))
            plan = etl.build_plan(etl.load_legacy(conn))
            etl.insert_all(conn, plan)
            conn.commit()
            new = Counter(r["biz_date"] for r in conn.execute("SELECT biz_date FROM job"))
            conn.close()
            self.assertEqual(sum(new.values()), FIXTURE_JOBS)
            self.assertEqual(new, legacy, "biz_date 分布被改了")
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
