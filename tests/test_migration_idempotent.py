"""迁移脚本幂等：连跑两次，结构不重复、schema_version 稳定。"""
from __future__ import annotations

import sqlite3
import unittest

from _util import apply_migration, empty_db_from_schema, migrated_but_empty


def _dump(path) -> tuple:
    conn = sqlite3.connect(path)
    try:
        tables = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        idx = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"))
        views = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"))
        ver = [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version")]
        return tables, idx, views, ver
    finally:
        conn.close()


class MigrationIdempotentTest(unittest.TestCase):
    def test_empty_db_twice(self):
        db = empty_db_from_schema()
        try:
            apply_migration(db)
            first = _dump(db)
            apply_migration(db)
            second = _dump(db)
            self.assertEqual(first, second, "两次迁移后结构应完全一致")
            self.assertEqual(second[3], [2])
        finally:
            db.unlink(missing_ok=True)

    def test_migrated_with_data_twice_keeps_rows(self):
        db = migrated_but_empty()
        try:
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO company (id,name,norm_name,first_seen,last_seen,created_at,updated_at) "
                "VALUES ('c1','甲公司','甲公司','2026-11-04T00:00:00Z','2026-11-04T00:00:00Z',"
                "'2026-11-04T00:00:00Z','2026-11-04T00:00:00Z')")
            conn.commit()
            conn.close()

            apply_migration(db)
            apply_migration(db)

            conn = sqlite3.connect(db)
            n = conn.execute("SELECT count(*) FROM company").fetchone()[0]
            conn.close()
            self.assertEqual(n, 1, "迁移不该清数据")
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
