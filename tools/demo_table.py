#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据库窗口 · 演示界面（独立脚本，不并入正式版）

设计参照主流大厂表格规范（GitHub Primer / Ant Design 的 data table、字体与间距规范）：
- 行高 44、表头 36，字号 13 / 12，正文左对齐、数字右对齐
- 只留 1px 水平分隔线（#E8E9EB），无竖线、无外框、无斑马纹
- hover 浅灰 #F7F8FA，选中浅蓝 #F2F7FF
- 状态用 8px 圆点表达（GitHub 的状态点），淘汰/拒绝 → 圆点与整行文字都转 #C0C4CC，**不用删除线**

列：〔点〕公司名称 / 工作地址 / 岗位 / 薪资 / 匹配度 / 岗位评估
点任意一行 → 行下方展开抽屉：左 60% JD、右 40% 失败原因 + 投递建议（固定高 300）
岗位评估可在行内双击直接改，回车写库（写的是 %TEMP% 的副本，真库不动）
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QModelIndex, QPoint, QPointF, QRect, QSize, Qt,
                            QVariantAnimation)
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QSizePolicy, QGraphicsDropShadowEffect,
    QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QPushButton, QStyle, QStyledItemDelegate, QTableView, QTextBrowser, QToolButton,
    QTextEdit, QVBoxLayout, QWidget, QSplitter,
)
from PySide6.QtCore import QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- 设计令牌
BG = "#FFFFFF"
CARD = "#FFFFFF"
TEXT = "#1F2329"
SUB = "#646A73"
WEAK = "#8F959E"
DEAD = "#C0C4CC"
LINE = "#E8E9EB"
HOVER = "#F7F8FA"
SEL = "#F2F7FF"
FILL = "#F2F3F5"
INPUT_BG = "#F7F8FA"
FOCUS_LINE = "#B7D4FF"
OPEN_BG = "#F3F7FD"
EXPANDED = "#9BA2AB"

GREEN = "#1B7F3B"
ORANGE = "#B26B00"

ROW_H = 40
HEADER_H = 34
DRAWER_H = 300
DOT_W = 28
FONT = "Microsoft YaHei UI"

DOT = {                      # 状态点：8px、低饱和，别抢戏
    "pending": "#D5D8DD",
    "recommend": "#79AD86",
    "caution": "#D3B273",
    "interviewing": "#8AA6CE",
    "rejected": "#C6C9CF",
    "declined": "#C6C9CF",
    "excluded": "#D5D8DD",
}
DEAD_STATUS = ("rejected", "declined")

DEMO_SCORES = {  # 演示假分数：只为了让你看到三种颜色
    "05c0125acb5d": 86, "0917ed779271": 74, "8152ae9808bb": 62,
    "82187351d64e": 91, "9fd33c89948c": 55, "c5882aa256ea": 68,
}

ANALYSIS_POOL = {
    "device": [
        "端侧机器人方向，主打设备通信 + 采集管线；考察并发模型与协议栈。",
        "硬件配套的后端岗，设备接入、数据回传、边缘端部署一条龙。",
        "IoT 设备管理系统，重点看协议解析与长连接稳定性。",
    ],
    "data": [
        "数据标注/质检类，流程标准化程度高；问清是否外包派驻、项目周期。",
        "数据生产流水线，偏管理与验收，技术含量看自动化程度。",
        "标注平台运营岗，考察指标是产出量与抽检合格率。",
    ],
    "algo": [
        "偏算法平台而非业务闭环；亮点是自研 RAG，可聊一问。",
        "模型工程侧，训练/推理链路齐全；问清算力预算与上线方式。",
        "AI 应用开发，重点是把模型塞进现有业务流程。",
    ],
    "out": [
        "乙方外包形态，先问清是否驻场、甲方是谁、能否长期。",
        "人力派遣性质，薪资上限卡住；当作练手面试。",
    ],
    "base": [
        "栈基本匹配，方向偏平台；重点问清团队规模与上线节奏。",
        "常规业务后端，技术深度一般；看薪资与稳定性。",
        "岗位描述偏泛，需要面谈确认真实职责范围。",
    ],
}

STYLE = f"""
* {{ font-family: "{FONT}"; }}
QMainWindow, QWidget#Root {{ background: {BG}; }}
QLabel#Hint {{ color: {WEAK}; font-size: 12px; }}
QLineEdit#Search {{
    background: #F1F2F4; border: 1px solid #F1F2F4; border-radius: 6px;
    padding: 2px 8px; color: {TEXT}; font-size: 12px;
}}
QLineEdit#Search:focus {{ background: #FFFFFF; border: 1px solid {FOCUS_LINE}; }}
QToolButton#Cols {{ background: transparent; border: none; border-radius: 6px; }}
QToolButton#Cols:hover {{ background: {FILL}; }}
QTableView {{
    background: {CARD}; border: none; gridline-color: transparent;
    selection-background-color: {SEL}; selection-color: {TEXT};
    font-size: 13px;
}}
QTableView::item {{ padding: 0 16px; border: none;
    border-bottom: 1px solid {LINE}; }}
QHeaderView::section {{
    background: {CARD}; color: {WEAK}; border: none;
    border-bottom: 1px solid {LINE}; padding: 0 24px 0 16px;
    font-size: 12px; font-weight: 400;
}}
QTableView QTableCornerButton::section {{ background: {CARD}; border: none; }}
QTextBrowser#JD {{
    background: {CARD}; border: none; padding: 0; color: {SUB};
    font-size: 12px; line-height: 170%;
}}
QTextEdit#Note {{
    background: {INPUT_BG}; border: 1px solid {INPUT_BG}; border-radius: 6px;
    padding: 8px 10px; color: {TEXT}; font-size: 12px;
}}
QTextEdit#Note:focus {{ background: {INPUT_BG}; border: 1px solid {FOCUS_LINE}; }}
QPushButton#Tiny {{
    background: transparent; border: none; color: {WEAK}; font-size: 11px;
    padding: 0 4px;
}}
QPushButton#Tiny:hover {{ color: {TEXT}; }}
QLineEdit#Inline {{
    background: {CARD}; border: 1px solid {FOCUS_LINE}; border-radius: 6px;
    padding: 3px 8px; font-size: 12px; color: {TEXT};
}}
QSplitter::handle {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #D9DBE0; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


# ---------------------------------------------------------------- 数据
FAKE_COMPANIES = ["星野数据科技", "云梯网络科技", "砚山智能科技", "拾光信息技术",
                  "白鹭软件", "临风科技", "木石网络", "青禾数据"]
FAKE_TITLES = ["后端开发工程师", "数据开发工程师", "算法工程师", "Python 开发工程师",
               "机器学习工程师", "平台开发工程师", "数据平台工程师"]
FAKE_JD = (
    "岗位职责：\n"
    "1. 负责业务系统的服务端设计与开发，参与需求评审；\n"
    "2. 负责数据链路的稳定性建设，包括采集、清洗与落库；\n"
    "3. 参与性能优化与线上问题排查。\n"
    "任职要求：\n"
    "1. 本科及以上，3 年以上后端开发经验；\n"
    "2. 熟悉 Python 或 Go，熟悉常用框架与数据库；\n"
    "3. 有良好的工程习惯，能独立负责一个模块。"
)


FAKE_ANALYSIS = [
    "技术栈匹配度不错，方向偏平台；重点确认团队规模与上线节奏。",
    "偏算法平台而非业务闭环，亮点是自研检索，可以聊一问。",
    "岗位描述偏泛，需要面谈确认真实职责范围。",
    "数据链路完整，考察点是稳定性建设经验。",
    "常规业务后端，技术深度一般，看薪资与稳定性。",
]
FAKE_FAIL = [
    "示例：技术面第 2 轮差在并发经验。",
    "示例：简历投出去没回音，岗位年限偏高。",
    "示例：约面时间冲突，先放一放。",
]
FAKE_ADVICE = [
    "示例：补一个线上排障的完整案例。",
    "示例：准备一分钟的自我介绍，突出项目收益。",
    "示例：换官网直投，别等平台捞。",
]


def anonymize(conn) -> None:
    """把公司名/岗位/薪资/JD 换成假数据（只改临时副本，用于对外截图）。"""
    cids = [r[0] for r in conn.execute(
        "SELECT id FROM company ORDER BY name")]
    name_of = {}
    for i, cid in enumerate(cids):
        name = FAKE_COMPANIES[i % len(FAKE_COMPANIES)]
        conn.execute("UPDATE company SET name=?, full_name=? WHERE id=?",
                     (name, name, cid))
        name_of[cid] = name
    jids = [r[0] for r in conn.execute(
        "SELECT id FROM job ORDER BY salary_min DESC")]
    for i, jid in enumerate(jids):
        # 岗位名保留原样（都是通用职位名，不含个人信息）；唯一索引是
        # (company_id, title_norm, city_norm)，改名不影响它。
        conn.execute(
            "UPDATE job SET salary_text=?, salary_min=?, salary_max=?, district=?,"
            " jd_text=?, analysis=?, fail_reason=?, advice=? WHERE id=?",
            (f"{12 + i % 8}-{18 + i % 10}K", 12000 + (i % 8) * 1000,
             18000 + (i % 10) * 1000, "示例区", FAKE_JD,
             FAKE_ANALYSIS[i % len(FAKE_ANALYSIS)],
             FAKE_FAIL[i % len(FAKE_FAIL)],
             FAKE_ADVICE[i % len(FAKE_ADVICE)], jid))
    conn.commit()


def prepare_db() -> tuple[sqlite3.Connection, Path]:
    """真库 → 临时副本，顺便改两条状态演「已淘汰」。"""
    tmp = Path(tempfile.gettempdir()) / "jobagent-demo"
    tmp.mkdir(parents=True, exist_ok=True)
    dst = tmp / "demo.db"
    shutil.copyfile(ROOT / "data" / "jobs.db", dst)
    conn = sqlite3.connect(dst)
    top = [r[0] for r in conn.execute(
        "SELECT id FROM job WHERE deleted_at IS NULL ORDER BY salary_min DESC LIMIT 8")]
    demo_status = {1: "rejected", 3: "recommend", 5: "caution", 6: "interviewing"}
    for i, st in demo_status.items():
        if i < len(top):
            conn.execute("UPDATE job SET status=? WHERE id=?", (st, top[i]))
    conn.commit()
    if os.environ.get("JOBAGENT_DEMO_FAKE") == "1":
        anonymize(conn)
    return conn, dst


def pick_analysis(row: dict, seq: int = 0) -> str:
    blob = (str(row.get("title") or "") + str(row.get("jd") or "")).lower()
    if any(k in blob for k in ("机器人", "设备通信", "嵌入式", "iot", "固件")):
        bucket = "device"
    elif any(k in blob for k in ("标注", "质检", "数据工程")):
        bucket = "data"
    elif any(k in blob for k in ("算法", "大模型", "llm", "nlp", "推理")):
        bucket = "algo"
    elif any(k in blob for k in ("外包", "驻场", "乙方")):
        bucket = "out"
    else:
        bucket = "base"
    pool = ANALYSIS_POOL[bucket]
    return pool[seq % len(pool)]


SEED_FAIL = [
    "技术面挂在第 2 轮，缺设备协议的实际经验。",
    "面试官问过空档期，答得还行，等结果。",
    "简历投出去没回音，岗位要 5 年经验。",
]
SEED_ADVICE = [
    "补 MQTT / Modbus 的实操例子，讲清一次排障过程。",
    "准备一句空档期的解释，简短、别绕。",
    "换官网直投，别等平台捞。",
]


def seed_analysis(conn: sqlite3.Connection, rows: list[dict], n: int = 8) -> None:
    """给排在前面的几行写示例「岗位评估」（写临时副本）。"""
    last = ""
    for i, row in enumerate(rows[:n]):
        if row.get("analysis"):
            continue
        text = pick_analysis(row, i)
        if text == last:
            text = pick_analysis(row, i + 1)
        last = text
        conn.execute("UPDATE job SET analysis=? WHERE id=?", (text, row["id"]))
        row["analysis"] = text
    for row, fr, ad in zip(rows[1:4], SEED_FAIL, SEED_ADVICE):
        if row.get("fail_reason"):
            continue
        conn.execute("UPDATE job SET fail_reason=?, advice=? WHERE id=?",
                     (fr, ad, row["id"]))
        row["fail_reason"], row["advice"] = fr, ad
    conn.commit()


def load_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT j.id, j.job_key, j.title, j.status, j.salary_text, j.salary_min,
               COALESCE(c.name, '') AS company, COALESCE(j.city, '') AS city,
               COALESCE(j.district, '') AS district,
               COALESCE(j.analysis, '') AS analysis,
               COALESCE(j.fail_reason, '') AS fail_reason,
               COALESCE(j.advice, '') AS advice,
               COALESCE(j.jd_text, '') AS jd, j.jd_len, j.version
        FROM job j LEFT JOIN company c ON c.id = j.company_id
        WHERE j.deleted_at IS NULL
        ORDER BY j.salary_min DESC
    """).fetchall()
    out = []
    for (jid, key, title, status, sal_text, sal_min, company, city, district,
         analysis, fail_reason, advice, jd, jd_len, version) in rows:
        score = DEMO_SCORES.get(key)
        if score is None:
            score = 45 + (sum(ord(ch) for ch in (key or "")) % 50)
        out.append({
            "id": jid, "key": key, "title": title or "", "status": status or "",
            "salary_text": (sal_text or "").strip(), "salary_min": int(sal_min or 0),
            "company": company, "city": city, "district": district,
            "analysis": analysis, "fail_reason": fail_reason, "advice": advice,
            "jd": jd, "jd_len": jd_len or 0, "version": version, "score": score,
        })
    return out


# ---------------------------------------------------------------- 表格模型
COLS = ["公司名称", "岗位", "薪资", "匹配度", "岗位评估"]
COL_CO, COL_TITLE, COL_PAY, COL_SCORE, COL_NOTE = range(5)


class JobModel(QStandardItemModel):
    def __init__(self, conn: sqlite3.Connection, rows: list[dict]):
        super().__init__(0, len(COLS))
        self.conn = conn
        self.rows = rows
        self.on_row_changed = None
        self.setHorizontalHeaderLabels(COLS)
        for r in rows:
            self.appendRow([self._cell() for _ in range(len(COLS))])

    @staticmethod
    def _cell():
        from PySide6.QtGui import QStandardItem
        it = QStandardItem()
        it.setEditable(False)
        return it

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.TextAlignmentRole and orientation == Qt.Horizontal:
            if section in (COL_SCORE, COL_PAY):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        row = {}
        if index.isValid() and 0 <= index.row() < len(self.rows):
            row = self.rows[index.row()]
        if role == Qt.UserRole:
            return row
        if role in (Qt.DisplayRole, Qt.EditRole) and index.isValid():
            col = index.column()
            if col == COL_NOTE:
                return str(row.get("analysis") or "")
            if col == COL_SCORE:
                return str(row.get("score") or "")
            if col == COL_PAY:
                return str(row.get("salary_text") or "")
            if col == COL_TITLE:
                return str(row.get("title") or "")
            if col == COL_CO:
                return str(row.get("company") or "")
            return ""
        if role == Qt.ToolTipRole and index.isValid():
            col = index.column()
            if col == COL_NOTE:
                return str(row.get("analysis") or "")
            if col == COL_TITLE:
                return str(row.get("title") or "")
            if col == COL_CO:
                addr = str(row.get("city") or "")
                if row.get("district"):
                    addr = f"{addr} · {row['district']}"
                return f"{row.get('company') or ''}\n{addr}".strip()
            return ""
        if role == Qt.UserRole + 99 and index.isValid():
            col = index.column()
            if col == COL_SCORE:
                return int(row.get("score") or 0)
            if col == COL_PAY:
                return int(row.get("salary_min") or 0)
            if col == COL_CO:
                return str(row.get("company") or "")
            if col == COL_TITLE:
                return str(row.get("title") or "")
            return str(row.get("analysis") or "")
        return super().data(index, role)

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        if index.column() == COL_NOTE:            # 只有「岗位评估」列可编辑
            return base | Qt.ItemIsEditable
        return base & ~Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or index.column() != COL_NOTE:
            return False
        row = self.rows[index.row()]
        text = str(value or "").strip()
        self.conn.execute("UPDATE job SET analysis=?, updated_by='user', "
                          "updated_at=datetime('now'), version=version+1 WHERE id=?",
                          (text, row["id"]))
        self.conn.commit()
        row["analysis"] = text
        self.dataChanged.emit(index, index)
        if self.on_row_changed:
            self.on_row_changed(row)
        return True


# ---------------------------------------------------------------- 单元格绘制
class CellDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.vp_w = 0                      # 由窗口在 resize 时回填，保证末列不越界
        self.expanded_id: str | None = None

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, ROW_H)

    def paint(self, p, option, index) -> None:
        row = index.data(Qt.UserRole) or {}
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        face = QRect(rect.left(), rect.top(), rect.width(), ROW_H)   # 展开后仍画在顶部
        status = str(row.get("status") or "")
        dead = status in DEAD_STATUS
        col = index.column()
        pad = 16

        if option.state & QStyle.State_MouseOver:
            p.fillRect(face, QColor(HOVER))
        if option.state & QStyle.State_Selected:
            p.fillRect(face, QColor(SEL))

        # 展开中的那一行：整行换一块浅底，文字保持原样（不靠"变浅"表意）
        opened = bool(self.expanded_id) and str(row.get("id")) == self.expanded_id
        if opened and not dead:
            p.fillRect(face, QColor(OPEN_BG))
        text_color = DEAD if dead else TEXT
        sub_color = DEAD if dead else SUB

        if col == COL_CO:                                   # 状态点 + 公司名 / 城市·区
            color = DOT.get(status, "#D5D8DD")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QRect(face.left() + 3, face.top() + 12, 8, 8))

            f = QFont(FONT, 10)
            f.setWeight(QFont.Medium)
            p.setFont(f)
            p.setPen(QColor(text_color))
            w = face.width() - pad - 18
            p.drawText(QRect(face.left() + pad, face.top() + 2, w, 20),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(row.get("company") or "—",
                                                  Qt.ElideRight, w))

            f2 = QFont(FONT, 8)
            p.setFont(f2)
            p.setPen(QColor(sub_color))
            addr = str(row.get("city") or "")
            if row.get("district"):
                addr = f"{addr} · {row['district']}"
            p.drawText(QRect(face.left() + pad, face.top() + 20, w, 16),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(addr or "—", Qt.ElideRight, w))

        elif col == COL_TITLE:                              # 岗位
            f = QFont(FONT, 10)
            p.setFont(f)
            p.setPen(QColor(text_color))
            w = face.width() - pad - 12
            p.drawText(QRect(face.left() + pad, face.top(), w, face.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(row.get("title") or "—",
                                                  Qt.ElideRight, w))

        elif col == COL_PAY:                                # 薪资
            f = QFont(FONT, 9)
            p.setFont(f)
            p.setPen(QColor(sub_color))
            p.drawText(face.adjusted(pad, 0, -24, 0), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(row.get("salary_text") or "—",
                                                  Qt.ElideRight, face.width() - pad - 24))

        elif col == COL_SCORE:                              # 匹配度
            score = int(row.get("score") or 0)
            color = GREEN if score >= 80 else (SUB if score >= 60 else WEAK)
            if dead:
                color = DEAD
            elif opened:
                color = EXPANDED
            f = QFont(FONT, 10)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(face.adjusted(pad, 0, -24, 0), Qt.AlignRight | Qt.AlignVCenter,
                       str(score))

        else:                                               # 岗位评估
            f = QFont(FONT, 9)
            p.setFont(f)
            p.setPen(QColor(sub_color))
            vp_w = self.vp_w or (face.left() + face.width())
            w = max(40, min(face.width() - pad - 12, vp_w - face.left() - pad - 12))
            p.drawText(QRect(face.left() + pad, face.top(), w, face.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(row.get("analysis") or "—",
                                                  Qt.ElideRight, w))
        p.restore()


# ---------------------------------------------------------------- 表头（整列拖拽）
class HeaderBar(QHeaderView):
    """飞书式整列拖拽。

    - 按下表头：抓「表头切片 + 该列数据切片」拼成浮片，半透明 + 投影，随鼠标零延迟移动
    - 横向移动：目标列一变就立刻 moveSection（零延迟让位），落点轻闪一下作为到位反馈
    - 松开：浮片销毁，数据与视图始终一致，无闪烁；没拖动则当作普通点击（排序）
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.drag_enabled = False
        self._press = None
        self._src = -1
        self._hover = -1
        self._dragging = False
        self._ghost = None
        self._slide = None
        self._slide_dx = 0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(280)
        curve = QEasingCurve(QEasingCurve.BezierSpline)
        curve.addCubicBezierSegment(QPointF(0.34, 1.56), QPointF(0.64, 1.0), QPointF(1.0, 1.0))
        self._anim.setEasingCurve(curve)
        self._anim.valueChanged.connect(self._on_slide)
        self._anim.finished.connect(self._kill_slide)

    def _table(self):
        return self.parentWidget()

    # ---------------- 浮片（该列截图，半透明 + 投影）
    def _make_ghost(self, sec: int) -> None:
        table = self._table()
        if table is None:
            return
        x = self.sectionViewportPosition(sec)
        w = self.sectionSize(sec)
        box = QWidget(table)
        box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        box.setAttribute(Qt.WA_StyledBackground, True)
        box.setStyleSheet("background: #FFFFFF; border-radius: 6px;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QLabel()
        head.setPixmap(self._faded(self.grab(QRect(x, 0, w, self.height()))))
        body = QLabel()
        body.setPixmap(self._faded(table.viewport().grab(
            QRect(x, 0, w, table.viewport().height()))))
        for lab in (head, body):
            lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            lab.setStyleSheet("background: transparent;")
            lay.addWidget(lab)
        box.adjustSize()
        shadow = QGraphicsDropShadowEffect(box)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(15, 23, 42, 70))
        box.setGraphicsEffect(shadow)
        box.raise_()
        box.show()
        self._ghost = box

    @staticmethod
    def _faded(pm: QPixmap, alpha: float = 0.95) -> QPixmap:
        out = QPixmap(pm.size())
        out.setDevicePixelRatio(pm.devicePixelRatio())
        out.fill(Qt.transparent)
        pa = QPainter(out)
        pa.setOpacity(alpha)
        pa.drawPixmap(0, 0, pm)
        pa.end()
        return out

    def _move_ghost(self, pos) -> None:
        if self._ghost is None:
            return
        self._ghost.move(int(pos.x() - self._ghost.width() / 2),
                         self.mapTo(self._table(), QPoint(0, 0)).y() - 8)

    def _kill_ghost(self) -> None:
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None

    # ---------------- 推挤（旧图盖住新图，弹簧滑开一格）
    def _push(self, to_logical: int) -> None:
        table = self._table()
        if table is None:
            return
        vp = table.viewport()
        vp_pos = vp.mapTo(table, QPoint(0, 0))
        width = self.sectionSize(self._src)
        direction = 1 if to_logical > self._src else -1

        old_head = self.grab()
        old_body = vp.grab()
        self.moveSection(self.visualIndex(self._src), self.visualIndex(to_logical))
        new_head = self.grab()
        new_body = vp.grab()

        if self._slide is not None:
            self._slide.hide()
            self._slide.deleteLater()

        clip = QWidget(table)
        clip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        clip.setAttribute(Qt.WA_StyledBackground, True)
        clip.setStyleSheet("background: #FFFFFF;")
        clip.setGeometry(0, 0, table.width(), table.height())

        dpr = max(1.0, float(new_head.devicePixelRatio() or 1.0))
        for pm, y, h in ((new_head, 0, self.height()),
                         (new_body, vp_pos.y(), vp.height())):
            lab = QLabel(clip)
            lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            lab.setPixmap(pm)
            lab.setGeometry(vp_pos.x(), y, pm.width() / dpr, h)
            lab.show()

        inner = QWidget(clip)
        inner.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        inner.setGeometry(0, 0, table.width(), table.height())
        for pm, y, h in ((old_head, 0, self.height()),
                         (old_body, vp_pos.y(), vp.height())):
            lab = QLabel(inner)
            lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            lab.setPixmap(pm)
            lab.setGeometry(vp_pos.x(), y, pm.width() / dpr, h)
            lab.show()
        inner.show()
        clip.raise_()
        if self._ghost is not None:
            self._ghost.raise_()
        self._slide = clip
        self._slide_inner = inner
        self._slide_dx = direction * width
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _on_slide(self, value) -> None:
        inner = getattr(self, "_slide_inner", None)
        if inner is not None:
            inner.move(int(self._slide_dx * float(value)), 0)

    def _kill_slide(self) -> None:
        if self._slide is not None:
            self._slide.hide()
            self._slide.deleteLater()
            self._slide = None
        self._slide_inner = None

    def paintEvent(self, ev):  # noqa: N802
        super().paintEvent(ev)

    # ---------------- 事件
    def mousePressEvent(self, ev):  # noqa: N802
        if not self.drag_enabled or ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        sec = self.logicalIndexAt(ev.position().toPoint())
        if sec < 0:
            return super().mousePressEvent(ev)
        self._press = ev.position().toPoint()
        self._src = sec
        self._hover = sec
        self._dragging = False
        self.setCursor(Qt.ClosedHandCursor)
        ev.accept()

    def mouseMoveEvent(self, ev):  # noqa: N802
        if self._press is None:
            return super().mouseMoveEvent(ev)
        pos = ev.position().toPoint()
        if not self._dragging and (pos - self._press).manhattanLength() < 5:
            ev.accept()
            return
        if not self._dragging:
            self._dragging = True
            self._make_ghost(self._src)
        self._move_ghost(pos)
        hover = self.logicalIndexAt(pos)
        if hover >= 0 and hover != self._hover:
            self._push(hover)
            self._hover = hover
        ev.accept()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        if self._press is None:
            return super().mouseReleaseEvent(ev)
        dragged = self._dragging
        sec = self._src
        self._end()
        self.setCursor(Qt.OpenHandCursor if self.drag_enabled else Qt.ArrowCursor)
        if not dragged and sec >= 0:
            self.sectionClicked.emit(sec)         # 没拖 → 普通点击（排序）
        ev.accept()

    def _end(self) -> None:
        self._press = None
        self._src = -1
        self._hover = -1
        self._dragging = False
        self._kill_ghost()
        self._anim.stop()
        self._kill_slide()


# ---------------------------------------------------------------- 抽屉
class Drawer(QWidget):
    """行内展开：左 60% JD，右 40% 失败原因 + 投递建议（失焦静默存库）。"""

    def __init__(self, conn: sqlite3.Connection, on_collapse, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.on_collapse = on_collapse
        self.row: dict | None = None

        self.setObjectName("Drawer")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#Drawer {{ background: {CARD}; border-top: 1px solid {LINE}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 12, 24, 14)
        outer.setSpacing(8)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(16)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        cap = QLabel("JD 原文")
        cap.setStyleSheet(f"color:{WEAK};font-size:11px;")
        head.addWidget(cap)
        head.addStretch(1)
        ll.addLayout(head)
        self.jd = QTextBrowser()
        self.jd.setObjectName("JD")
        self.jd.document().setDocumentMargin(8)
        ll.addWidget(self.jd, 1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        self.edits: dict[str, QTextEdit] = {}
        for key, title, ph in (
            ("fail_reason", "失败原因", "为什么没投 / 挂在哪一轮"),
            ("advice", "投递建议", "补什么、话术怎么说"),
        ):
            lab = QLabel(title)
            lab.setStyleSheet(f"color:{WEAK};font-size:11px;")
            rl.addWidget(lab)
            ed = QTextEdit()
            ed.setObjectName("Note")
            ed.setPlaceholderText(ph)
            ed.installEventFilter(self)
            self.edits[key] = ed
            rl.addWidget(ed, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([600, 400])
        outer.addWidget(split, 1)

    def load(self, row: dict) -> None:
        self.row = row
        self.jd.setPlainText(row.get("jd") or "（这条没有 JD 正文）")
        self.jd.moveCursor(self.jd.textCursor().MoveOperation.Start)
        cur = self.conn.execute(
            "SELECT COALESCE(fail_reason,''), COALESCE(advice,'') FROM job WHERE id=?",
            (row["id"],)).fetchone()
        for key, val in zip(("fail_reason", "advice"), cur or ("", "")):
            self.edits[key].blockSignals(True)
            self.edits[key].setPlainText(val)
            self.edits[key].blockSignals(False)

    def eventFilter(self, obj, ev):  # noqa: N802
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.FocusOut and self.row is not None:
            key = next((k for k, e in self.edits.items() if e is obj), None)
            if key:
                self._save(key, obj.toPlainText())
        return False

    def _save(self, key: str, text: str) -> None:
        self.conn.execute(
            f"UPDATE job SET {key}=?, updated_by='user', updated_at=datetime('now'), "
            "version=version+1 WHERE id=?", (text, self.row["id"]))
        self.conn.commit()


class JobProxy(QSortFilterProxyModel):
    """按 公司名 / 岗位 / 城市 / 岗位评估 / 失败原因 过滤。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.needle = ""

    def set_needle(self, text: str) -> None:
        self.needle = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, src_row: int, src_parent: QModelIndex) -> bool:  # noqa: N802
        if not self.needle:
            return True
        idx = self.sourceModel().index(src_row, 0, src_parent)
        row = idx.data(Qt.UserRole) or {}
        hay = " ".join(str(row.get(k) or "") for k in
                       ("company", "title", "city", "analysis", "fail_reason")).lower()
        return self.needle in hay


# ---------------------------------------------------------------- 窗口
class Demo(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, db_path: Path):
        super().__init__()
        self.conn = conn
        self.expanded_id: str | None = None
        self.setWindowTitle("Job Agent · 数据库 演示 v4（去土味）")
        self.resize(1100, 720)

        root = QWidget()
        root.setObjectName("Root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self.cols_btn = QToolButton()
        self.cols_btn.setObjectName("Cols")
        self.cols_btn.setFixedSize(26, 26)
        self.cols_btn.setCursor(Qt.PointingHandCursor)
        self.cols_btn.setToolTip("开启拖拽列")
        self.cols_btn.clicked.connect(self.toggle_cols)
        self._cols_on = False
        self.cols_btn.setIcon(self._cols_icon(False))
        self.cols_btn.setIconSize(QSize(14, 14))
        bar.addWidget(self.cols_btn)
        bar.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("搜索")
        self.search.setFixedWidth(200)
        self.search.setFixedHeight(26)
        self.search.textChanged.connect(self.apply_filter)
        bar.addWidget(self.search)
        lay.addLayout(bar)

        self.model = JobModel(conn, load_rows(conn))
        self.model.on_row_changed = self._sync_drawer
        seed_analysis(conn, self.model.rows, 8)
        self.proxy = JobProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole + 99)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.delegate = CellDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_H)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QTableView.NoFrame)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        head = HeaderBar(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(head)
        head.setHighlightSections(False)
        head.setSectionsClickable(True)
        head.setFixedHeight(HEADER_H)
        head.setMinimumSectionSize(64)
        for c, w in ((COL_CO, 300), (COL_TITLE, 280),
                     (COL_PAY, 120), (COL_SCORE, 90)):
            head.setSectionResizeMode(c, QHeaderView.Fixed)
            self.table.setColumnWidth(c, w)
        head.setSectionResizeMode(COL_NOTE, QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(COL_PAY, Qt.DescendingOrder)
        self.table.clicked.connect(self.on_click)
        self.table.doubleClicked.connect(self.on_double)
        lay.addWidget(self.table, 1)

        self.drawer = Drawer(conn, self.collapse, self.table.viewport())
        self.drawer.hide()

        if os.environ.get("JOBAGENT_DEMO_FAKE") == "1":
            self.hint = QLabel("演示数据：公司、薪资、JD 均为虚构，仅用于展示界面。")
        else:
            self.hint = QLabel(
                "演示用：读的是真库副本（真库没动）；「匹配度」和部分「岗位评估」是示例数据。")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        self.hint.setToolTip(str(db_path))
        self.hint.setMinimumWidth(1)
        self.hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(self.hint)
        self.setCentralWidget(root)

        self.table.verticalScrollBar().valueChanged.connect(self.place_drawer)
        self.table.doubleClicked.connect(lambda *_: self.place_drawer())

    # -- 拖拽列开关
    def _cols_icon(self, on: bool):
        from PySide6.QtGui import QIcon, QPixmap
        pm = QPixmap(28, 28)
        pm.setDevicePixelRatio(2.0)
        pm.fill(Qt.transparent)
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(TEXT if on else SUB)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for i, h in enumerate((10, 14, 7)):
            x = 3 + i * 5
            p.drawRoundedRect(QRect(x, 7 + (14 - h) // 2, 3, h), 1.5, 1.5)
        p.end()
        return QIcon(pm)

    def toggle_cols(self) -> None:
        self._cols_on = not self._cols_on
        head = self.table.horizontalHeader()
        head.drag_enabled = self._cols_on
        head.setSectionsMovable(True)
        head.setCursor(Qt.OpenHandCursor if self._cols_on else Qt.ArrowCursor)
        self.cols_btn.setIcon(self._cols_icon(self._cols_on))
        self.cols_btn.setToolTip("关闭拖拽列" if self._cols_on else "开启拖拽列")
        self.table.viewport().setCursor(Qt.ArrowCursor)

    # -- 抽屉
    def row_of(self, job_id: str) -> int:
        for r in range(self.proxy.rowCount()):
            idx = self.proxy.index(r, 0)
            if (idx.data(Qt.UserRole) or {}).get("id") == job_id:
                return r
        return -1

    def on_click(self, index: QModelIndex) -> None:
        row = index.data(Qt.UserRole) or {}
        jid = row.get("id")
        if not jid:
            return
        if self.expanded_id == jid:
            self.collapse()
            return
        self.expanded_id = jid
        self.delegate.expanded_id = jid
        self.drawer.load(row)
        self.refresh_heights()
        self.place_drawer()
        self.table.viewport().update()

    def _sync_drawer(self, row: dict) -> None:
        if self.drawer.row and self.drawer.row.get("id") == row.get("id"):
            self.drawer.load(row)

    def collapse(self) -> None:
        self.expanded_id = None
        self.delegate.expanded_id = None
        self.drawer.hide()
        self.refresh_heights()
        self.table.viewport().update()

    def on_double(self, index: QModelIndex) -> None:
        if index.column() == COL_NOTE:            # 岗位评估：双击变输入框
            self.table.edit(index)

    def refresh_heights(self) -> None:
        for r in range(self.proxy.rowCount()):
            self.table.setRowHeight(r, ROW_H)
        if self.expanded_id:
            r = self.row_of(self.expanded_id)
            if r >= 0:
                self.table.setRowHeight(r, ROW_H + DRAWER_H)

    def place_drawer(self) -> None:
        if not self.expanded_id:
            self.drawer.hide()
            return
        r = self.row_of(self.expanded_id)
        if r < 0:
            self.drawer.hide()
            return
        rect = self.table.visualRect(self.proxy.index(r, 0))
        vp = self.table.viewport()
        top = rect.top() + ROW_H
        if top > vp.height() or rect.bottom() < 0:
            self.drawer.hide()
            return
        self.drawer.setGeometry(QRect(0, top, vp.width(), DRAWER_H))
        self.drawer.show()
        self.drawer.raise_()

    def apply_filter(self, text: str) -> None:
        self.proxy.set_needle(text)
        self.refresh_heights()
        self.place_drawer()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self._sync_vp()

    def _sync_vp(self) -> None:
        if getattr(self, "delegate", None) is not None:
            self.delegate.vp_w = self.table.viewport().width()
            self.table.viewport().update()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._sync_vp()
        self.place_drawer()


def main() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    conn, db_path = prepare_db()
    win = Demo(conn, db_path)
    scr = app.primaryScreen().availableGeometry()
    win.setMinimumSize(1160, 620)
    win.showMaximized()
    win._sync_vp()
    win.raise_()
    win.activateWindow()
    app.exec()


if __name__ == "__main__":
    main()
