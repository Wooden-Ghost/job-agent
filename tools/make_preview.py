"""生成 README 用的界面预览图。

重要：这里用的数据库是 `data/jobs.db` 的**临时副本**，并且先经过 `anonymize()`
把公司名 / 岗位 / 薪资 / JD 全部替换成假数据 —— 仓库里不会出现任何真实岗位信息。

用法：
    python tools/make_preview.py

产物：
    docs/preview/ui-table.png    列表（含展开行）
    docs/preview/ui-drawer.png   抽屉展开：JD + 记录框
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["JOBAGENT_DEMO_FAKE"] = "1"          # 关键：强制合成数据

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import demo_table as D  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(D.STYLE)

    conn, db_path = D.prepare_db()
    win = D.Demo(conn, db_path)
    win.resize(1400, 800)
    win.show()
    for _ in range(20):
        app.processEvents()

    out = ROOT / "docs" / "preview"
    out.mkdir(parents=True, exist_ok=True)

    # 第一张：干净列表
    win.collapse()
    for _ in range(10):
        app.processEvents()
    win.grab().save(str(out / "ui-table.png"))

    # 第二张：展开一行，看 JD 与三个记录框
    win.on_click(win.proxy.index(2, 0))
    for _ in range(20):
        app.processEvents()
    win.grab().save(str(out / "ui-drawer.png"))

    conn.close()
    for name in ("ui-table.png", "ui-drawer.png"):
        p = out / name
        print(f"{p}  {p.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
