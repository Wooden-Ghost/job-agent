"""db/schema.sql 与 0002 迁移脚本必须产出同一套结构（防两处漂移）。"""
from __future__ import annotations

import unittest

from _util import empty_db_from_schema, apply_migration, schema_of, indexes_of


class SchemaParityTest(unittest.TestCase):
    def test_tables_parity(self):
        a = empty_db_from_schema()
        b = empty_db_from_schema()
        try:
            apply_migration(b)
            sa, sb = schema_of(a), schema_of(b)
            # 只比 v7 业务表；legacy 表不在 schema.sql 里
            want = {"company", "company_alias", "job", "job_source", "job_revision",
                    "due_diligence_evidence", "due_diligence_verdict", "screening",
                    "schema_version"}
            self.assertTrue(want <= set(sa), f"schema.sql 缺表: {want - set(sa)}")
            for t in sorted(want):
                self.assertIn(t, sb, f"迁移后缺表 {t}")
                self.assertEqual(sa[t], sb[t], f"表 {t} 的列定义不一致")
        finally:
            a.unlink(missing_ok=True)
            b.unlink(missing_ok=True)

    def test_index_parity(self):
        a = empty_db_from_schema()
        b = empty_db_from_schema()
        try:
            apply_migration(b)
            ia, ib = indexes_of(a), indexes_of(b)
            self.assertEqual(ia, ib, "两处建出来的索引集合不一致")
        finally:
            a.unlink(missing_ok=True)
            b.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
