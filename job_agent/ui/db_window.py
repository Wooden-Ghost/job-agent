# -*- coding: utf-8 -*-
"""「数据库」独立窗口：只是个壳。

- `QMainWindow` 子类、非模态（从主窗口打开，关掉不影响采集）
- 根控件 objectName="Root"，样式全部来自 `theme.QSS`（QSS 挂在 QApplication 上，
  子窗口天然继承，不需要复制样式）
- 内容全在 `DbJobs` 里，这里只管窗口尺寸、标题和关闭时 flush
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout

from job_agent.ui.db_jobs import DbJobs


class DbWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据库 · 岗位")
        self.setWindowFlag(Qt.Window, True)
        self.setMinimumSize(1080, 700)

        self.body = DbJobs(conn, cfg, self)
        host = QWidget()
        host.setObjectName("DbRoot")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.body)
        self.setCentralWidget(host)

        self._center()

    def _center(self) -> None:
        screen = self.screen().availableGeometry() if self.screen() else None
        if not screen:
            self.resize(1240, 820)
            return
        w = min(1240, screen.width() - 120)
        h = min(860, screen.height() - 140)
        self.resize(w, h)
        self.move(screen.x() + (screen.width() - w) // 2,
                  screen.y() + (screen.height() - h) // 3)

    def closeEvent(self, e) -> None:  # noqa: N802
        try:
            self.body.flush_notes()     # 关窗口前把没存完的字存掉
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(e)
