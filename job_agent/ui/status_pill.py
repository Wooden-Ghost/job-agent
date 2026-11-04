# -*- coding: utf-8 -*-
"""状态药丸：数据库窗口里**唯一**允许出现颜色的地方。

其它所有行/文字保持中性灰，禁止整行标红标绿（施工单 §0）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from job_agent.ui import theme as T

# status → (中文, 底色, 字色)
STATUS_STYLE = {
    "pending":      ("待评估", "#FFF7E0", "#A26A00"),
    "recommend":    ("建议投", "#E8F5E9", "#1B7F3B"),
    "caution":      ("谨慎投", "#FFF3D6", "#9A6700"),
    "interviewing": ("面试中", "#E8F5E9", "#1B7F3B"),
    "rejected":     ("已淘汰", "#F2F3F5", "#8F959E"),
    "declined":     ("已拒绝", "#F2F3F5", "#8F959E"),
    "excluded":     ("已排除", "#F7F7F8", "#A6ABB2"),
}
FALLBACK = ("未知", "#F2F3F5", "#8F959E")

# 下拉框顺序（全部 + 七种）
FILTER_ORDER = ["pending", "recommend", "caution", "interviewing",
                "rejected", "declined", "excluded"]


def text_of(status: str | None) -> str:
    return STATUS_STYLE.get((status or "").strip(), FALLBACK)[0]


class StatusPill(QLabel):
    """小圆角药丸。set_status() 换色换字，字号比正文小一号。"""

    def __init__(self, status: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusPill")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self.set_status(status)

    def set_status(self, status: str | None) -> None:
        text, bg, fg = STATUS_STYLE.get((status or "").strip(), FALLBACK)
        self.setText(text)
        self.setStyleSheet(
            f"QLabel#StatusPill {{ background:{bg}; color:{fg};"
            f" border:none; border-radius:10px; padding:2px 8px;"
            f" font-size:{T.FONT_CAPTION}px; }}")
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance(text) + 26)
