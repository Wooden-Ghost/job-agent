# -*- coding: utf-8 -*-
"""数据库窗口的主体：左 40% 列表 + 右 60% 详情（施工单 §1）。

纪律（写死在这里，别在下游改）：
- 颜色只出现在状态药丸；列表 null 一律中性灰，不整行标红标绿。
- 不弹 Dialog：编辑就地完成，自动保存 800ms 防抖，切换/关闭时 flush。
- 只读字段：标题 / 公司名 / 城市 / JD 正文 / 首次见 / 来源。
- 每次写都带 version，冲突只在右侧淡色提示里说一句。
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QStyle,
    QLineEdit, QPushButton, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from job_agent import store
from job_agent.ui import theme as T
from job_agent.ui.status_pill import FALLBACK, FILTER_ORDER, STATUS_STYLE, StatusPill, text_of
from job_agent.ui.widgets import Card, hline, label, toast

ROW_H = 64
PILL_W = 64
SALARY_W = 116
EDITABLE_NOTE_FIELDS = ("analysis", "fail_reason", "advice")
NOTE_PLACEHOLDER = {
    "analysis": "记录这个岗位的核心业务和考察点",
    "fail_reason": "记录为何没投，或面试后为何挂掉",
    "advice": "记录面试前需要补什么课、话术怎么答",
}


class ClickArea(QWidget):
    """可以点的空白条：点一下就展开/收起。"""

    clicked = Signal()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class NoteRow(QWidget):
    """人工记录的一格：平时只占一行（标题 + 摘要 + 按钮），点开才出现输入框。"""

    def __init__(self, key: str, title: str, placeholder: str, on_change,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self._open = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.head = ClickArea(self)
        self.head.setFixedHeight(26)
        self.head.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(self.head)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.title = label(title, "DbSection")
        self.summary = label("", "DbHint")
        self.summary.setTextInteractionFlags(Qt.NoTextInteraction)
        self.btn = QPushButton("记一笔")
        self.btn.setObjectName("Ghost")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFixedWidth(60)
        h.addWidget(self.title, 0)
        h.addWidget(self.summary, 1)
        h.addWidget(self.btn, 0)
        lay.addWidget(self.head)

        self.edit = QTextEdit(self)
        self.edit.setObjectName("DbNote")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFrameShape(QFrame.NoFrame)
        self.edit.document().setDocumentMargin(10)
        self.edit.setFixedHeight(72)
        self.edit.setVisible(False)
        self.edit.textChanged.connect(self._on_text)
        self.edit.textChanged.connect(on_change)
        lay.addWidget(self.edit)

        self.btn.clicked.connect(self.toggle)
        self.head.clicked.connect(self.toggle)
        self._update_summary()

    # -- 内部
    def _on_text(self) -> None:
        doc_h = int(self.edit.document().size().height()) + 18
        self.edit.setFixedHeight(max(72, min(150, doc_h)))
        self._update_summary()

    def _update_summary(self) -> None:
        text = " ".join(self.edit.toPlainText().split())
        if self._open and text:
            self.summary.setText("")
            self.btn.setText("收起")
            return
        if not text:
            self.summary.setText("未记录")
            self.btn.setText("收起" if self._open else "记一笔")
            return
        self.summary.setText(text[:30] + ("…" if len(text) > 30 else ""))
        self.btn.setText("展开")

    # -- 外部
    def set_open(self, flag: bool) -> None:
        self._open = flag
        self.edit.setVisible(flag)
        if flag:
            self.edit.setFocus()
            cur = self.edit.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            self.edit.setTextCursor(cur)
        else:
            self.edit.clearFocus()
        self._update_summary()

    def toggle(self) -> None:
        self.set_open(not self._open)

    def refresh(self) -> None:
        self._update_summary()

    def set_value(self, text: str) -> None:
        self.edit.blockSignals(True)
        self.edit.setPlainText(text)
        self.edit.blockSignals(False)
        self._on_text()
        self.set_open(False)


# ---------------------------------------------------------------- 列表行绘制
class JobRowDelegate(QStyledItemDelegate):
    """两行行高 64：第一行公司名加粗，第二行 岗位 · 薪资 · 状态药丸。"""

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, ROW_H)

    def paint(self, p: QPainter, option, index) -> None:
        row = index.data(Qt.UserRole) or {}
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        if option.state & QStyle.State_Selected:
            p.fillRect(r, QColor(T.DB_SELECT))
        elif option.state & QStyle.State_MouseOver:
            p.fillRect(r, QColor(T.DB_HOVER))

        pill_w = PILL_W
        text_w = max(80, r.width() - pill_w - 40)

        # 第一行：公司名（加粗）。公司名可能是空的，退化到岗位名
        company = str(row.get("company") or "").strip() or "（未知公司）"
        f1 = QFont(T.FONT, 10, QFont.DemiBold)
        p.setFont(f1)
        p.setPen(QColor(T.TEXT))
        fm1 = QFontMetrics(f1)
        p.drawText(QRect(r.left() + 14, r.top() + 10, text_w, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm1.elidedText(company, Qt.ElideRight, text_w))

        # 第二行：岗位 · 薪资
        f2 = QFont(T.FONT, 9)
        p.setFont(f2)
        fm2 = QFontMetrics(f2)
        title = str(row.get("title") or "")
        salary = str(row.get("salary") or "")
        left2 = QRect(r.left() + 14, r.top() + 34, text_w, 18)
        title_txt = fm2.elidedText(title, Qt.ElideRight, max(60, text_w - SALARY_W - 16))
        p.setPen(QColor(T.DB_SUB))
        p.drawText(left2, Qt.AlignLeft | Qt.AlignVCenter, title_txt)
        used = fm2.horizontalAdvance(title_txt) + 18
        if salary:
            sal_rect = QRect(left2.left() + used, left2.top(),
                             max(60, left2.width() - used), 18)
            below = row.get("_below_expected")
            p.setPen(QColor(T.DB_WEAK if below else T.DIM))
            f3 = QFont(f2)
            p.setFont(f3)
            fm3 = QFontMetrics(f3)
            shown = fm3.elidedText(salary, Qt.ElideRight, sal_rect.width())
            p.drawText(sal_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
            if below:                      # 低于期望：字下面画一条淡线，不压字
                base = sal_rect.top() + (sal_rect.height() - fm3.height()) // 2 + fm3.ascent()
                p.setPen(QColor(T.DB_WEAK))
                p.drawLine(sal_rect.left(), base + 3,
                           sal_rect.left() + fm3.horizontalAdvance(shown), base + 3)

        # 右侧药丸
        txt, bg, fg = STATUS_STYLE.get(str(row.get("status") or ""), FALLBACK)
        f4 = QFont(T.FONT, 8)
        p.setFont(f4)
        fm4 = QFontMetrics(f4)
        pw = max(pill_w, fm4.horizontalAdvance(txt) + 24)
        pill = QRect(r.right() - pw - 14, r.top() + (ROW_H - 22) // 2, pw, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(pill, 10, 10)
        p.setPen(QColor(fg))
        p.drawText(pill, Qt.AlignCenter, txt)

        # 笔记命中的淡色小点（不喧哗）
        if row.get("note_hit"):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.DB_WEAK))
            p.drawEllipse(r.left() + 6, r.top() + (ROW_H - 5) // 2, 5, 5)
        p.restore()


# ---------------------------------------------------------------- 主体
class DbJobs(QWidget):
    """左列表 + 右详情。窗口只负责套壳，逻辑都在这儿。"""

    statusLine = Signal(str)

    def __init__(self, conn: sqlite3.Connection, cfg: dict, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.cfg = cfg or {}
        self.rows: list[dict] = []
        self.cur: dict | None = None
        self._loading = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.flush_notes)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.reload)
        self._editor: QLineEdit | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_left(), 4)
        body.addWidget(self._build_right(), 6)
        root.addLayout(body, 1)

        self.hint = QLabel("")
        self.hint.setObjectName("DbHint")
        root.addWidget(self.hint)

        self.reload()

    # ------------------------------------------------------------ 左栏
    def _build_left(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜公司名、岗位名，或你写过的笔记")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        bar.addWidget(self.search, 1)

        self.f_status = QComboBox()
        self.f_status.setObjectName("ToolCombo")
        self.f_status.addItem("全部状态", "")
        for s in FILTER_ORDER:
            self.f_status.addItem(text_of(s), s)
        self.f_status.currentIndexChanged.connect(lambda _: self.reload())
        bar.addWidget(self.f_status)

        self.f_city = QComboBox()
        self.f_city.setObjectName("ToolCombo")
        self.f_city.addItem("全部城市", "")
        for c in self._cities():
            self.f_city.addItem(c, c)
        self.f_city.currentIndexChanged.connect(lambda _: self.reload())
        bar.addWidget(self.f_city)
        lay.addLayout(bar)

        self.card = Card("")
        self.table = QTableWidget(0, 1)
        self.table.setObjectName("DbList")
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMouseTracking(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setItemDelegate(JobRowDelegate(self.table))
        self.table.verticalHeader().setDefaultSectionSize(ROW_H)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.itemSelectionChanged.connect(self._on_pick)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.card.body.addWidget(self.table, 1)
        lay.addWidget(self.card, 1)

        self.count_label = QLabel("")
        self.count_label.setObjectName("DbHint")
        lay.addWidget(self.count_label)
        return wrap

    # ------------------------------------------------------------ 右栏
    def _build_right(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        top = Card("")
        tl = top.body
        head = QHBoxLayout()
        self.d_title = QLabel("")
        self.d_title.setObjectName("DetailTitle")
        self.d_title.setWordWrap(True)
        head.addWidget(self.d_title, 1)
        self.pill = StatusPill(None)
        head.addWidget(self.pill, 0, Qt.AlignTop)
        tl.addLayout(head)

        self.d_meta = QLabel("")
        self.d_meta.setObjectName("DbHint")
        self.d_meta.setWordWrap(True)
        tl.addWidget(self.d_meta)

        jd_head = QHBoxLayout()
        jd_head.addWidget(label("JD 原文", "DbSection"))
        jd_head.addStretch(1)
        self.b_copy = QPushButton("复制 JD")
        self.b_copy.setObjectName("Ghost")
        self.b_copy.setCursor(Qt.PointingHandCursor)
        self.b_copy.clicked.connect(self._copy_jd)
        jd_head.addWidget(self.b_copy)
        tl.addLayout(jd_head)

        self.d_jd = QTextBrowser()
        self.d_jd.setObjectName("JdBox")
        self.d_jd.setMinimumHeight(180)
        tl.addWidget(self.d_jd, 1)
        lay.addWidget(top, 1)

        bottom = Card("人工记录")
        self.note_edits: dict[str, QTextEdit] = {}
        self.note_rows: dict[str, NoteRow] = {}
        bottom.body.setSpacing(8)
        for key in EDITABLE_NOTE_FIELDS:
            row = NoteRow(key, {"analysis": "岗位分析",
                                "fail_reason": "失败原因",
                                "advice": "投递建议"}[key],
                          NOTE_PLACEHOLDER[key], self._schedule_save)
            self.note_rows[key] = row
            self.note_edits[key] = row.edit
            bottom.body.addWidget(row)
        bottom.body.addSpacing(6)
        lay.addWidget(bottom, 0)
        return wrap

    # ------------------------------------------------------------ 数据
    def _cities(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT COALESCE(city,'') FROM job "
            "WHERE deleted_at IS NULL AND COALESCE(city,'')<>'' ORDER BY 1")
        return [r[0] for r in rows]

    def expected_min(self) -> int:
        try:
            return int(self.cfg.get("expectedSalaryMin") or 0)
        except (TypeError, ValueError):
            return 0

    def reload(self) -> None:
        keep_id = (self.cur or {}).get("id")
        q = self.search.text().strip()
        status = self.f_status.currentData() or None
        city = self.f_city.currentData() or None
        self.rows = store.list_jobs(self.conn, query=q or None, status=status,
                                    city=city, limit=2000)
        floor = self.expected_min()
        for r in self.rows:
            s_min = int(r.get("salary_min") or 0)
            r["_below_expected"] = bool(floor and s_min and s_min < floor)

        self._loading = True
        self.table.setRowCount(0)
        for i, r in enumerate(self.rows):
            self.table.insertRow(i)
            item = QTableWidgetItem()
            item.setData(Qt.UserRole, r)
            self.table.setItem(i, 0, item)
        self._loading = False

        if self.rows:
            idx = next((i for i, r in enumerate(self.rows) if r["id"] == keep_id), 0)
            self.table.selectRow(idx)
            self._show(self.rows[idx])
        else:
            self._show(None)
        try:
            st = store.stats_v7(self.conn)
            summary = (f"共 {st['jobs']} 条 · 待评估 {st['pool']} · "
                       f"已排除 {st['short_jd']} · {st['companies']} 家公司")
        except Exception:  # noqa: BLE001
            summary = f"共 {len(self.rows)} 条"
        if floor:
            summary += f"　·　期望 ≥{floor // 1000}K"
        self.count_label.setText(summary)
        self.count_label.setToolTip(
            f"期望薪资下限 {floor} 元（配置 expectedSalaryMin）。"
            "低于它的岗位只在薪资下画一条淡线，不自动淘汰。" if floor else "")

    def _on_pick(self) -> None:
        if self._loading:
            return
        self.flush_notes()          # 切走之前把当前行的字存掉
        i = self.table.currentRow()
        if 0 <= i < len(self.rows):
            self._show(self.rows[i])

    def _show(self, r: dict | None) -> None:
        self._loading = True
        self.cur = r
        if not r:
            self.d_title.setText("列表是空的")
            self.d_meta.setText("")
            self.pill.set_status(None)
            self.d_jd.setPlainText("")
            for row in self.note_rows.values():
                row.set_value("")
            self._loading = False
            return
        title = str(r.get("title") or "")
        company = str(r.get("company") or "")
        self.d_title.setText(f"{company} · {title}" if company else title)
        bits = [r.get("salary") or "面议", r.get("city") or "",
                f"首次见 {(r.get('first_seen') or '')[:10]}",
                "来源 智联招聘", f"JD {r.get('jd_len') or 0} 字"]
        self.d_meta.setText("　·　".join(b for b in bits if b.strip()))
        self.pill.set_status(r.get("status"))
        self.d_jd.setPlainText(self._jd_text(r))
        for key, row in self.note_rows.items():
            row.set_value(str(r.get(key) or ""))
        self.hint.setText("")
        self._loading = False

    def _jd_text(self, r: dict) -> str:
        row = self.conn.execute(
            "SELECT COALESCE(jd_text,'') FROM job WHERE id=?", (r["id"],)).fetchone()
        return (row[0] if row else "") or "（这条没有 JD 正文）"

    # ------------------------------------------------------------ 自动保存
    def _schedule_save(self) -> None:
        if self._loading or not self.cur:
            return
        self._save_timer.start()

    def flush_notes(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
        if self._loading or not self.cur:
            return
        fields = {}
        for key, ed in self.note_edits.items():
            val = ed.toPlainText()
            if val != str(self.cur.get(key) or ""):
                fields[key] = val
        if not fields:
            return
        self._write(fields, "已保存")

    def _write(self, fields: dict, ok_text: str = "") -> None:
        r = self.cur or {}
        try:
            ver = store.update_user_fields(self.conn, r["id"], fields, int(r["version"]))
        except store.ConflictError:
            self.hint.setText("这条已被改过，已刷新为最新（你的修改没有覆盖对方）")
            self.reload()
            return
        except Exception as exc:  # noqa: BLE001
            self.hint.setText(f"没存上：{exc}")
            return
        r.update(fields)
        r["version"] = ver
        for k, v in fields.items():
            if k in self.note_edits:
                self.cur[k] = v
        if "status" in fields:
            self.pill.set_status(fields["status"])
        for k in fields:
            if k in self.note_rows:
                self.note_rows[k].refresh()
        if ok_text:
            self.hint.setText(f"{ok_text} · 已写入本地库")

    # ------------------------------------------------------------ 交互
    def _copy_jd(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.d_jd.toPlainText())
        self.hint.setText("JD 已复制")

    def _on_double_click(self, index) -> None:
        """双击第二行的薪资区域 → 就地变输入框。"""
        row = index.data(Qt.UserRole) or {}
        if not row:
            return
        rect = self.table.visualRect(index)
        pos = self.table.viewport().mapFromGlobal(self.table.cursor().pos())
        salary_left = rect.left() + rect.width() - PILL_W - SALARY_W - 30
        if pos.x() < salary_left:
            return                      # 只认薪资那一小段，别处不响应
        ed = QLineEdit(self.table.viewport())
        ed.setObjectName("InlineEdit")
        ed.setText(str(row.get("salary") or ""))
        geo = QRect(salary_left, rect.top() + (ROW_H - 26) // 2,
                    max(90, PILL_W + SALARY_W - 20), 26)
        ed.setGeometry(geo)
        ed.show()
        ed.setFocus()
        ed.selectAll()
        self._editor = ed

        def commit() -> None:
            if self._editor is None:
                return
            val = self._editor.text().strip()
            self._editor.deleteLater()
            self._editor = None
            if val and val != str(row.get("salary") or ""):
                self._write_for(row, {"salary_text": val}, "薪资已改")

        ed.returnPressed.connect(commit)
        ed.editingFinished.connect(commit)

    def _write_for(self, row: dict, fields: dict, ok_text: str) -> None:
        try:
            ver = store.update_user_fields(self.conn, row["id"], fields,
                                           int(row["version"]))
        except store.ConflictError:
            self.hint.setText("这条已被改过，已刷新为最新")
            self.reload()
            return
        except Exception as exc:  # noqa: BLE001
            self.hint.setText(f"没存上：{exc}")
            return
        row.update(fields)
        row["version"] = ver
        self.hint.setText(f"{ok_text} · 已写入本地库")
        self.reload()

    def _context_menu(self, pos) -> None:
        """右键改状态（轻量菜单，不算弹窗）。"""
        from PySide6.QtWidgets import QMenu
        sel = self._selected_rows()
        if not sel:
            return
        m = QMenu(self)
        acts = []
        for s in FILTER_ORDER:
            name = STATUS_STYLE[s][0]
            pad = "  " if len(sel) == 1 else f"  （{len(sel)} 条）"
            a = m.addAction(f"标记为{name}{pad}")
            a.setData(s)
            acts.append(a)
        picked = m.exec(self.table.viewport().mapToGlobal(pos))
        if not picked:
            return
        self._apply_status(sel, picked.data())

    def _selected_rows(self) -> list[dict]:
        idxs = self.table.selectionModel().selectedRows(0) if self.table.selectionModel() else []
        out = []
        for i in idxs:
            r = self.table.item(i.row(), 0)
            if r:
                out.append(r.data(Qt.UserRole) or {})
        return [r for r in out if r]

    def _apply_status(self, rows: list[dict], status: str) -> None:
        items = [(r["id"], int(r["version"])) for r in rows]
        try:
            n, _ = store.set_status_many(self.conn, items, status)
        except store.ConflictError:
            self.hint.setText("有行已被改过，已刷新为最新")
            self.reload()
            return
        except Exception as exc:  # noqa: BLE001
            self.hint.setText(f"没改成：{exc}")
            return
        self.hint.setText(f"已把 {n} 条标记为「{STATUS_STYLE[status][0]}」")
        self.reload()

    # 键盘：Del / Ctrl+E 标淘汰；↑↓ 已在表格原生支持
    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key_Delete,) or (e.key() == Qt.Key_E and e.modifiers() & Qt.ControlModifier):
            sel = self._selected_rows()
            if sel:
                self._apply_status(sel, "rejected")
                return
        super().keyPressEvent(e)
