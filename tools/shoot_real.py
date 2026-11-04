# -*- coding: utf-8 -*-
r"""真入口出图 + 数据库窗口自检（施工单 §5 七条）。

    set QT_QPA_PLATFORM=offscreen
    python tools\shoot_real.py

产物：docs\shots\db-list.png / db-detail-notes.png / db-status-pills.png
写库操作用**真实库**，每段测完立刻按原值还原（状态 / 三个文本框 / 薪资），
所以三张图里不会留下「（改）」这类测试痕迹。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from job_agent import cli, store  # noqa: E402
from job_agent.ui import app as uiapp  # noqa: E402
from job_agent.ui import theme as T  # noqa: E402

SHOTS = ROOT / "docs" / "shots"
NOTE_TEXT = {
    "analysis": "端侧机器人后端，主打设备通信 + 采集管线；考察点：并发模型、协议栈。",
    "fail_reason": "当时简历上没有设备协议经验，投了没回音。",
    "advice": "面试前补一下 MQTT/Modbus 的实战例子；空档期这块要准备一句解释。",
}
PILL_SEQ = ["pending", "recommend", "caution", "interviewing", "rejected", "declined"]


def pump(qapp, n: int = 6) -> None:
    for _ in range(n):
        qapp.processEvents()


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{('  ' + detail) if detail else ''}")
    return ok


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    cfg = cli.load_config()
    qapp = QApplication(sys.argv[:1])
    for cand in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(cand).exists():
            QFontDatabase.addApplicationFont(cand)
    qapp.setFont(QFont(T.FONT, 10))
    qapp.setStyleSheet(T.QSS)

    win = uiapp.MainWindow(cfg)
    win.resize(1280, 840)
    win.show()
    pump(qapp)

    print("[nav]", [t for t, _ in uiapp.NAV])
    check("导航已无「岗位/公司」，改为「数据库」",
          all(t not in ("岗位", "公司") for t, _ in uiapp.NAV)
          and ("数据库", -1) in uiapp.NAV)
    check("DataPage 未挂进 stack",
          win.data not in [win.stack.widget(i) for i in range(win.stack.count())])
    check("stack 页数 = 5", win.stack.count() == 5, str(win.stack.count()))

    win.go(3)
    pump(qapp, 10)
    db = win.db_win
    check("点「数据库」开出独立窗口", db is not None and db.isVisible())
    body = db.body
    check("窗口里有列表和详情", len(body.rows) > 0 and body.cur is not None,
          f"rows={len(body.rows)}")

    # ---- 图 1：干净状态
    db.grab().save(str(SHOTS / "db-list.png"))
    print("[shot] db-list.png")

    job = body.cur
    jid = job["id"]
    orig = {k: str(job.get(k) or "") for k in NOTE_TEXT}
    orig_salary = str(job.get("salary") or "")

    # ---- 验收 3：三个文本框自动保存，切走再切回仍在
    for k, text in NOTE_TEXT.items():
        body.note_edits[k].setPlainText(text)
    pump(qapp, 3)
    body.flush_notes()
    pump(qapp, 3)
    body.table.selectRow(min(1, len(body.rows) - 1))
    pump(qapp, 3)
    body.reload()
    body.table.selectRow(0)
    pump(qapp, 3)
    check("三个文本框写入后切走再切回仍在",
          {k: body.note_edits[k].toPlainText() for k in NOTE_TEXT} == NOTE_TEXT)

    # ---- 图 2：笔记写满
    db.grab().save(str(SHOTS / "db-detail-notes.png"))
    print("[shot] db-detail-notes.png")

    # ---- 验收 5：搜「空档期」命中笔记
    body.search.setText("空档期")
    pump(qapp, 3)
    body.reload()
    check("搜「空档期」命中写在投递建议里的记录",
          len(body.rows) >= 1 and any(r.get("note_hit") for r in body.rows),
          f"{len(body.rows)} 条")
    body.search.setText("")
    pump(qapp, 3)
    body.reload()

    # 还原笔记（截图已经拿到，不留痕）
    row = next((r for r in body.rows if r["id"] == jid), None)
    if row:
        store.update_user_fields(body.conn, jid, dict(orig), int(row["version"]))
    body.reload()
    pump(qapp, 2)

    # ---- 验收 2 / 6：六种状态药丸（先记原值，拍完立刻还原）
    ids = [r["id"] for r in body.rows[:6]]
    saved = {r["id"]: r["status"] for r in body.rows[:6]}
    for jid_i, st in zip(ids, PILL_SEQ):
        r = next(x for x in body.rows if x["id"] == jid_i)
        store.set_status_many(body.conn, [(r["id"], int(r["version"]))], st)
    body.reload()
    pump(qapp, 4)
    db.grab().save(str(SHOTS / "db-status-pills.png"))
    print("[shot] db-status-pills.png")
    check("六种状态都已落库",
          sorted(r["status"] for r in body.rows[:6]) == sorted(PILL_SEQ))

    body.f_status.setCurrentIndex(body.f_status.findData("rejected"))
    pump(qapp, 3)
    body.reload()
    check("按「已淘汰」筛选生效", len(body.rows) == 1, f"{len(body.rows)} 条")
    body.f_status.setCurrentIndex(0)
    pump(qapp, 3)
    body.reload()

    by_id = {r["id"]: r for r in body.rows}
    for jid_i, st in saved.items():
        r = by_id.get(jid_i)
        if r:
            store.set_status_many(body.conn, [(r["id"], int(r["version"]))], st)
    body.reload()
    pump(qapp, 3)
    check("六条状态已还原",
          all(r["status"] == saved.get(r["id"]) for r in body.rows[:6]))

    # ---- 验收 4：改薪资 -> 重载仍是新值 -> 还原
    row = next((r for r in body.rows if r["id"] == jid), body.rows[0])
    store.update_user_fields(body.conn, jid, {"salary_text": orig_salary + "（改）"},
                             int(row["version"]))
    body.reload()
    pump(qapp, 3)
    cur2 = next((r for r in body.rows if r["id"] == jid), body.rows[0])
    check("改薪资后重新载入仍是新值", cur2["salary"].endswith("（改）"), cur2["salary"])
    store.update_user_fields(body.conn, jid, {"salary_text": orig_salary},
                             int(cur2["version"]))
    body.reload()
    pump(qapp, 3)

    # ---- 验收 7：完整性 / legacy 不动
    integ = body.conn.execute("PRAGMA integrity_check").fetchone()[0]
    legacy = body.conn.execute("select count(*) from jobs").fetchone()[0]
    runs = body.conn.execute("select count(*) from runs").fetchone()[0]
    check("integrity_check = ok", integ == "ok", integ)
    check("legacy jobs 仍 58 行、runs 8 行", legacy == 58 and runs == 8,
          f"jobs={legacy} runs={runs}")
    check("没有留下测试痕迹",
          body.conn.execute(
              "select count(*) from job where salary_text like '%（改）' "
              "or coalesce(analysis,'')<>'' or coalesce(fail_reason,'')<>'' "
              "or coalesce(advice,'')<>''").fetchone()[0] == 0)

    print("[stats]", store.stats_v7(body.conn))
    db.close()
    win.close()
    qapp.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
