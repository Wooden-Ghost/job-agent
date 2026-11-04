# -*- coding: utf-8 -*-
"""四个页面：首页 / 环境配置 / 采集设置 / 数据（+ 使用教程、关于）。

界面只调 job_agent 里的逻辑层，不自己写采集代码：
    detect.detect(cfg)        环境报告
    store.connect / stats     数据库
    store.export_xlsx         导出 Excel
    flow.run(cfg, conn, log)  采集
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QFontMetrics, QColor, QDesktopServices, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme as T
from .widgets import (
    Card,
    ClickPill,
    FieldRow,
    HelpDot,
    IconButton,
    LinkLabel,
    PathField,
    Pill,
    Segmented,
    StepDot,
    Tile,
    ToggleSwitch,
    ToolCombo,
    chip_row,
    hline,
    label,
    toast,
)


def _btn(text: str, kind: str = "Secondary", w: int | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if w:
        b.setMinimumWidth(w)
    return b


def _bar(v: int) -> QProgressBar:
    b = QProgressBar()
    b.setObjectName("Bar")
    b.setTextVisible(False)
    b.setFixedHeight(6)
    b.setRange(0, 100)
    b.setValue(v)
    return b


def _open_path(path: str) -> None:
    if not path:
        return
    try:
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606
        elif os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except OSError:
        pass


# ---------------------------------------------------------------- 基类

class BasePage(QWidget):
    def __init__(self, title: str, desc: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 18)
        outer.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(10)
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(label(title, "PageTitle"))
        if desc:
            d = label(desc, "PageDesc")
            d.setMaximumWidth(720)
            box.addWidget(d)
        head.addLayout(box)
        head.addStretch(1)
        self.head = head
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("Root")
        self._inner = inner
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(0, 0, 6, 0)
        self.content.setSpacing(16)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def add_action(self, w: QWidget) -> QWidget:
        self.head.addWidget(w)
        return w


# ---------------------------------------------------------------- 首页

class LogView(QTextBrowser):
    """只读日志框。行里出现文件路径时自动变成链接，点一下打开它所在的文件夹。"""

    COLORS = {
        "info": T.DIM,
        "step": T.TEXT,
        "ok": T.OK,
        "warn": T.WARN,
        "err": T.ERR,
    }
    #: 路径（用来做可点击链接）：C:\a\b\c.png
    _PATH = re.compile(r"([A-Za-z]:\\[^\s<>\"']+?\.[A-Za-z0-9]{2,5})")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogBox")
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open_anchor)
        self.setFont(QFont(T.MONO, 9))
        self.setMinimumHeight(220)

    @staticmethod
    def _open_anchor(url: QUrl) -> None:
        QDesktopServices.openUrl(url)

    def _linkify(self, text: str) -> str:
        """把行里的路径换成一个链接，href 指向它所在的目录。"""
        out, pos = [], 0
        for m in self._PATH.finditer(text):
            full = m.group(1)
            folder = os.path.dirname(full) or full
            href = "file:///" + folder.replace("\\", "/")
            out.append(text[pos:m.start(1)])
            out.append(f'<a href="{href}" style="color:{T.ACCENT};'
                       f' text-decoration:underline;">{full}</a>')
            pos = m.end(1)
        out.append(text[pos:])
        return "".join(out)

    def add(self, kind: str, text: str) -> None:
        color = self.COLORS.get(kind, T.DIM)
        body = self._linkify(text)
        self.append(f'<span style="color:{color}">{body}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class HomePage(BasePage):
    def __init__(self, app, parent=None):
        super().__init__("首页", "", parent)
        self.app = app

        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(58)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 9, 14, 9)
        bl.setSpacing(10)
        bl.addWidget(label("招聘软件", "ToolName"))
        self.src = ToolCombo()
        self.src.setObjectName("ToolCombo")
        self.src.addItems(["智联招聘", "BOSS直聘（敬请期待）", "猎聘（敬请期待）"])
        self.src.setToolTip("另外两家还在测试，暂未支持")
        model = self.src.model()
        for i in (1, 2):
            it = model.item(i) if hasattr(model, "item") else None
            if it is not None:
                it.setEnabled(False)
                it.setToolTip("测试中，暂未支持")
        bl.addWidget(self.src)
        bl.addWidget(label("当前设备", "ToolName"))
        self.dev = ToolCombo()
        self.dev.setObjectName("ToolCombo")
        self.dev.setMinimumWidth(230)
        self.dev.addItem("未检测")
        bl.addWidget(self.dev)
        self.btn_refresh = IconButton("reload", "重新检测设备")
        self.btn_refresh.clicked.connect(self.app.redetect)
        bl.addWidget(self.btn_refresh)
        self.btn_gear = IconButton("gear", "打开采集设置")
        self.btn_gear.clicked.connect(lambda: self.app.go(2))
        bl.addWidget(self.btn_gear)
        bl.addStretch(1)
        self.stop = _btn("停止", w=72)
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.app.stop_run)
        self.start = _btn("开始采集", "Primary", w=104)
        self.start.clicked.connect(self.app.start_run)
        bl.addWidget(self.stop)
        bl.addWidget(self.start)
        self.content.addWidget(bar)

        c2 = Card("采集")
        self.status = Pill("未运行", "dim")
        c2.add_right(self.status)
        self.prog = _bar(0)
        c2.body.addWidget(self.prog)
        self.now = QLabel("")
        self.now.setObjectName("StatusLine")
        self.now.setText("")
        c2.body.addWidget(self.now)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.t_in = Tile("0", "已入库", T.OK)
        self.t_skip = Tile("0", "已跳过")
        self.t_fail = Tile("0", "失败", T.ERR)
        self.t_time = Tile("0:00", "已用时", T.ACCENT)
        for t in (self.t_in, self.t_skip, self.t_fail, self.t_time):
            tiles.addWidget(t, 1)
        c2.body.addLayout(tiles)
        self.content.addWidget(c2)

        c3 = Card("运行日志")
        self.export_now = _btn("导出本次结果", "Ghost", w=112)
        self.export_now.setVisible(False)
        self.export_now.clicked.connect(self.app.export_today)
        c3.add_right(self.export_now)
        clear = _btn("清空", "Ghost", w=56)
        clear.clicked.connect(lambda: self.log.clear())
        c3.add_right(clear)
        self.log = LogView()
        c3.body.addWidget(self.log, 1)
        self.content.addWidget(c3, 1)

        self.log.add("info", f"{datetime.now():%H:%M:%S}  程序已就绪")

    # -- 由 app 调用的状态更新
    def set_status(self, kind: str, text: str) -> None:
        self.status.set(kind, text)

    def set_device(self, text: str) -> None:
        self.dev.clear()
        self.dev.addItem(text)

    def set_counts(self, inserted=0, skipped=0, failed=0, seconds=0) -> None:
        self.t_in.set_value(str(inserted))
        self.t_skip.set_value(str(skipped))
        self.t_fail.set_value(str(failed))
        self.t_time.set_value(f"{seconds // 60}:{seconds % 60:02d}")

    def set_progress(self, value: int) -> None:
        self.prog.setValue(max(0, min(100, value)))

    def set_now(self, text: str) -> None:
        """单行覆盖当前进度（等待中，还剩 Xs）。"""
        self.now.setText(text or "")

    def set_running(self, running: bool) -> None:
        self.start.setEnabled(not running)
        self.start.setText("采集中…" if running else "开始采集")
        self.stop.setEnabled(running)


# ---------------------------------------------------------------- 环境配置

class EnvPage(BasePage):
    def __init__(self, app, parent=None):
        super().__init__("环境配置", "第一次用要把这两样准备好。", parent)
        self.app = app
        self._inner.setMaximumWidth(780)

        self.btn_check = _btn("重新检测", w=88)
        self.btn_check.clicked.connect(lambda: app.redetect("全部"))
        self.add_action(self.btn_check)

        c1 = Card("")

        def _row(pill, text, control, tip=""):
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 7, 0, 7)
            h.setSpacing(10)
            h.addWidget(pill)
            h.addWidget(label(text, "FieldLabel"))
            if tip:
                h.addWidget(HelpDot(tip))
            h.addStretch(1)
            h.addWidget(control)
            return box

        self.sim_pill = ClickPill("检测中", "dim", "重新检测")
        self.sim_pill.clicked.connect(lambda: app.redetect("模ulator"))
        self.sim_path = PathField("—", "选择模拟器目录", 300)
        self.sim_path.btn.clicked.connect(self.app.pick_emulator_dir)
        c1.body.addWidget(_row(
            self.sim_pill, "模拟器路径", self.sim_path,
            "装模拟器时选的安装目录，程序从这里找 adb"))

        c1.body.addWidget(hline())

        self.adb_pill = ClickPill("检测中", "dim", "重新检测")
        self.adb_pill.clicked.connect(lambda: app.redetect("adb"))
        self.adb_path = PathField("—", "选择 adb.exe", 300)
        self.adb_path.btn.clicked.connect(self.app.pick_adb)
        c1.body.addWidget(_row(
            self.adb_pill, "adb 连接", self.adb_path,
            "adb 是安卓调试通道，程序靠它读屏幕、点按钮"))
        self.content.addWidget(c1)

        c9 = Card("还是不行？", "按顺序试这三件事")
        for i, text in enumerate([
            "模拟器没开也没关系，点「开始采集」会自动拉起；想提前确认就点左边的状态点重新检测。",
            "杀毒软件有时会拦 adb，加白名单或允许一下再试。",
            "路径填错了就点路径框右边的文件夹图标，重新选到模拟器的安装目录，"
            "例如 D:\\leidian\\LDPlayer9。",
        ], start=1):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(StepDot(i), 0, Qt.AlignTop)
            row.addWidget(label(text, "PageDesc", wrap=True), 1)
            c9.body.addLayout(row)
        self.content.addWidget(c9)
        self.content.addStretch(1)

    def set_busy(self, busy: bool, who: str = "全部") -> None:
        """检测中：按钮禁用、相关状态点转圈（写成「检测中…」）。"""
        self.btn_check.setEnabled(not busy)
        self.btn_check.setText("检测中…" if busy else "重新检测")
        if not busy:
            return
        if who in ("模ulator", "模拟器"):
            self.sim_pill.set("dim", "检测中…")
        elif who == "adb":
            self.adb_pill.set("dim", "检测中…")
        else:
            self.sim_pill.set("dim", "检测中…")
            self.adb_pill.set("dim", "检测中…")

    def apply(self, rep: dict) -> None:
        adb = rep.get("adb") or {}
        app = rep.get("app") or {}
        dev = rep.get("device") or {}
        ok_adb = bool(adb.get("ok"))
        ok_app = bool(app.get("ok"))

        self.adb_path.setText(adb.get("path") or "未找到")
        if ok_adb and dev.get("serial"):
            self.adb_pill.set("ok", "已连接")
        elif ok_adb:
            # 模拟器没开很正常，点开始采集会自动拉起，这里不用报警
            self.adb_pill.set("dim", "未启动")
        else:
            self.adb_pill.set("err", "未找到")

        emus = rep.get("emulators") or []
        if ok_adb and emus:
            self.sim_path.setText(emus[0].get("dir") or "—")
            self.sim_pill.set("ok", "正常")
        elif ok_adb:
            self.sim_path.setText("没认出模拟器")
            self.sim_pill.set("warn", "未识别")
        else:
            self.sim_path.setText("未选择")
            self.sim_pill.set("err", "未找到")


# ---------------------------------------------------------------- 采集设置

class SettingsPage(BasePage):
    def __init__(self, app, parent=None):
        super().__init__("采集设置", "", parent)
        self.app = app
        self._inner.setMaximumWidth(760)
        self.add_action(_btn("恢复默认", w=88)).clicked.connect(app.reset_settings)
        save = _btn("保存设置", "Primary", w=92)
        save.clicked.connect(app.save_settings)
        self.add_action(save)

        c1 = Card("采集量")
        self.daily = self._spin(30, 5000, 120, 92)
        self.daily.valueChanged.connect(self._on_daily)
        c1.body.addWidget(FieldRow("每天上限", self._pair(self.daily, "条 / 天"),
                                   label_width=110))

        self.per = self._spin(1, 500, 60, 92)
        c1.body.addWidget(FieldRow("每次最多", self._pair(self.per, "条 / 次"),
                                   label_width=110))

        self.tab_quota = []
        for i in range(3):
            sp = self._spin(0, 200, 10, 72)
            self.tab_quota.append(sp)
            c1.body.addWidget(FieldRow(
                f"标签 {i + 1}", self._pair(sp, "条"), label_width=110,
                tip="按 App 里标签的顺序；填 0 表示跳过这个标签。实际标签少于 3 个时多的不生效"))

        self.skip_viewed = ToggleSwitch(True)
        c1.body.addWidget(FieldRow("跳过看过的", self.skip_viewed, label_width=110,
                                   tip="标题变灰的岗位不再点开，能省一半时间"))
        self.content.addWidget(c1)

        c2 = Card("模拟真人", "防止封控")
        self.speed = Segmented(["慢", "标准", "快"])
        self.speed.setCurrent("标准")
        c2.body.addWidget(FieldRow("操作速度", self.speed, label_width=110))
        self.wait_a = self._spin(0, 60, 1, 72)
        self.wait_b = self._spin(0, 60, 4, 72)
        pair = QWidget()
        pl = QHBoxLayout(pair)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        pl.addWidget(self.wait_a)
        pl.addWidget(label("–", "FieldValue"))
        pl.addWidget(self.wait_b)
        pl.addWidget(label("秒", "SectionHint"))
        c2.body.addWidget(FieldRow("随机等待", pair, label_width=110,
                                   sub="填 0 到 0 就是不等待"))
        self.content.addWidget(c2)

        c3 = Card("自动采集")
        self.auto = ToggleSwitch(False)
        c3.body.addWidget(FieldRow("定时采集", self.auto, label_width=110))
        self.time_host, self.time_chips = chip_row(["09:00", "20:00"])
        c3.body.addWidget(FieldRow("时间点", self.time_host, label_width=110))
        self.auto.toggled.connect(self._on_auto)
        self.content.addWidget(c3)

        c4 = Card("导出位置")
        self.export_link = LinkLabel("—")
        self.export_link.clicked.connect(lambda: _open_path(self.app.export_file()))
        self.export_path = PathField("—", "选导出目录", 380)
        self.export_path.btn.clicked.connect(self.app.pick_export_dir)
        row = QWidget()
        el = QHBoxLayout(row)
        el.setContentsMargins(0, 6, 0, 6)
        el.setSpacing(6)
        el.addWidget(label("生成", "FieldLabel"))
        el.addWidget(self.export_link)
        el.addWidget(label("导出至", "FieldLabel"))
        el.addWidget(self.export_path)
        el.addStretch(1)
        c4.body.addWidget(row)

        self.auto_export = ToggleSwitch(True)
        c4.body.addWidget(FieldRow(
            "跑完自动导出", self.auto_export, label_width=110,
            sub="每次采集结束自动生成 Excel + 一份给 AI 读的 .md，都放在上面的目录里"))
        self.content.addWidget(c4)

        self.content.addStretch(1)
        self._on_auto(False)

    def _spin(self, lo, hi, val, w):
        from .widgets import NoWheelSpinBox

        s = NoWheelSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setFixedSize(w, 34)
        return s

    def _pair(self, widget, unit):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(widget)
        h.addWidget(label(unit, "SectionHint"))
        return box

    def _on_daily(self, v):
        if v > 300 and not getattr(self, "_warned", False):
            self._warned = True
            toast(self, "测试中，上限可能出现异常或风险")

    def _on_auto(self, on):
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        eff = QGraphicsOpacityEffect(self.time_host)
        eff.setOpacity(1.0 if on else 0.4)
        self.time_host.setGraphicsEffect(eff)
        self.time_host.setEnabled(on)

    def load(self, cfg: dict) -> None:
        self.daily.setValue(int(cfg.get("maxJobsPerDay", 120)))
        self.per.setValue(int(cfg.get("maxJobsPerRun", 60)))
        quotas = cfg.get("perTabJobs", [10, 10, 10])
        if not isinstance(quotas, (list, tuple)):
            quotas = [int(quotas or 10)] * 3
        quotas = list(quotas) + [quotas[-1] if quotas else 10] * (3 - len(quotas))
        for sp, v in zip(self.tab_quota, quotas[:3]):
            sp.setValue(int(v or 0))
        self.skip_viewed.setChecked(bool(cfg.get("skipViewed", True)))
        self.speed.setCurrent({"slow": "慢", "fast": "快"}.get(
            cfg.get("speed", "normal"), "标准"))
        a, b = cfg.get("waitRange", [1, 4])
        self.wait_a.setValue(int(a))
        self.wait_b.setValue(int(b))
        sch = cfg.get("schedule") or {}
        self.auto.setChecked(bool(sch.get("enabled")))
        self.export_path.setText(cfg.get("exportDir", ""))
        self.auto_export.setChecked(bool(cfg.get("autoExport", True)))
        self.export_link.setText(self.app.export_name())

    def collect(self) -> dict:
        return {
            "maxJobsPerDay": self.daily.value(),
            "maxJobsPerRun": self.per.value(),
            "perTabJobs": [sp.value() for sp in self.tab_quota],
            "skipViewed": self.skip_viewed.isChecked(),
            "speed": {"慢": "slow", "标准": "normal", "快": "fast"}.get(
                self.speed.currentText(), "normal"),
            "waitRange": [self.wait_a.value(), self.wait_b.value()],
            "schedule": {
                "enabled": self.auto.isChecked(),
                "times": [c.text() for c in self.time_chips],
            },
            "exportDir": self.export_path.lbl.text(),
            "autoExport": self.auto_export.isChecked(),
        }


# ---------------------------------------------------------------- 数据

class _JobRowDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(0, 58)

    def paint(self, p: QPainter, option, index):
        val = index.data(Qt.UserRole)
        title, comp, score = (val if val else ("", "", 0))
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        if option.state & QStyle.State_Selected:
            p.fillRect(r, QColor(T.ACCENT_SOFT))
        elif option.state & QStyle.State_MouseOver:
            p.fillRect(r, QColor(T.FIELD))

        text_w = max(60, r.width() - 92)
        ft = QFont(T.FONT, 10, QFont.DemiBold)
        p.setFont(ft)
        p.setPen(QColor(T.TEXT))
        fm = QFontMetrics(ft)
        p.drawText(QRect(r.left() + 12, r.top() + 10, text_w, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(str(title), Qt.ElideRight, text_w))

        fc = QFont(T.FONT, 8)
        p.setFont(fc)
        p.setPen(QColor(T.MUTED))
        fm2 = QFontMetrics(fc)
        p.drawText(QRect(r.left() + 12, r.top() + 31, text_w, 18),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm2.elidedText(str(comp), Qt.ElideRight, text_w))

        if score:
            p.setFont(ft)
            p.setPen(QColor(T.OK if score >= 70 else T.MUTED))
            p.drawText(r.adjusted(0, 0, -14, 0), Qt.AlignRight | Qt.AlignVCenter,
                       str(score))
        p.restore()


class DataPage(BasePage):
    def __init__(self, app, parent=None):
        super().__init__("已采集的岗位", "", parent)
        self.app = app
        self.rows: list[dict] = []

        self.add_action(_btn("打开文件夹", w=100)).clicked.connect(
            lambda: _open_path(self.app.cfg.get("exportDir", "")))

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.tiles = []
        for text in ("库里共", "今日新增", "已分析公司"):
            t = Tile("0", text)
            self.tiles.append(t)
            stats.addWidget(t, 1)
        self.content.addLayout(stats)

        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 9, 14, 9)
        self.banner_text = QLabel("")
        self.banner_text.setObjectName("BannerText")
        bl.addWidget(self.banner_text)
        self.banner.setVisible(False)
        self.content.addWidget(self.banner)

        body = QHBoxLayout()
        body.setSpacing(16)

        left = Card("岗位列表", "共 0 条")
        self.list_sub = left.sub_label
        left.setFixedWidth(360)
        self.table = QTableWidget(0, 1)
        self.table.setObjectName("JobList")
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setItemDelegate(_JobRowDelegate(self.table))
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.itemSelectionChanged.connect(self._on_pick)
        left.body.addWidget(self.table, 1)
        body.addWidget(left, 0)

        right = Card("岗位详情")
        self.d_title = label("", "DetailTitle")
        right.body.addWidget(self.d_title)
        self.d_salary = label("", "DetailSalary")
        right.body.addWidget(self.d_salary)
        self.d_meta = label("", "SectionHint")
        right.body.addWidget(self.d_meta)
        right.body.addWidget(hline())
        self.d_jd = QTextEdit()
        self.d_jd.setObjectName("JdBox")
        self.d_jd.setReadOnly(True)
        right.body.addWidget(self.d_jd, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.b_copy = _btn("复制 JD", "Ghost", w=88)
        self.b_copy.clicked.connect(self._copy_jd)
        brow.addWidget(self.b_copy)
        right.body.addLayout(brow)
        body.addWidget(right, 1)

        self.content.addLayout(body, 1)

    def reload(self, stats: dict, rows: list[dict], last_date: str | None) -> None:
        self.rows = rows
        self.tiles[0].set_value(str(stats.get("total", 0)))
        self.tiles[1].set_value(str(stats.get("todayCount", 0)))
        self.tiles[2].set_value(str(stats.get("companies", 0)))

        if last_date and stats.get("todayCount", 0) == 0:
            try:
                d = datetime.strptime(last_date, "%Y-%m-%d")
                days = (datetime.now() - d).days
                self.banner_text.setText(
                    f"{last_date}，距离上次采集过去 {max(days, 0)} 天啦")
                self.banner.setVisible(True)
            except ValueError:
                self.banner.setVisible(False)
        else:
            self.banner.setVisible(False)

        self.table.setRowCount(0)
        for i, r in enumerate(rows):
            self.table.insertRow(i)
            item = QTableWidgetItem()
            item.setData(Qt.UserRole, (r.get("title") or "", r.get("company") or "",
                                       r.get("score") or 0))
            self.table.setItem(i, 0, item)
        self.list_sub.setText(f"共 {len(rows)} 条" if rows else "还没有数据")
        if rows:
            self.table.selectRow(0)
        else:
            self._show(None)

    def _on_pick(self):
        i = self.table.currentRow()
        self._show(self.rows[i] if 0 <= i < len(self.rows) else None)

    def _show(self, r):
        if not r:
            self.d_title.setText("")
            self.d_salary.setText("")
            self.d_meta.setText("")
            self.d_jd.setPlainText("左边选一条看详情。")
            return
        self.d_title.setText(r.get("title") or "")
        self.d_salary.setText(r.get("salary_text") or "")
        meta = " · ".join(x for x in (
            r.get("company_full") or r.get("company"),
            r.get("city"), r.get("company_meta"), r.get("company_stage")) if x)
        self.d_meta.setText(meta)
        self.d_jd.setPlainText(r.get("jd") or "（这条没有 JD）")

    def _copy_jd(self):
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.d_jd.toPlainText())
        toast(self, "JD 已复制")


# ---------------------------------------------------------------- 使用教程

class TutorialPage(BasePage):
    def __init__(self, app, parent=None):
        super().__init__("使用教程", "", parent)
        self._inner.setMaximumWidth(860)

        c1 = Card("三步开始", "不用懂代码")
        row = QHBoxLayout()
        row.setSpacing(18)
        for i, (t, d) in enumerate([
            ("装一个安卓模拟器", "推荐雷电模拟器 9，装完打开一次就行。"),
            ("装智联招聘并登录", "把安装包拖进模拟器窗口，装好用手机号登录一次。"),
            ("配好求职期望", "在 App 里填职位、城市、薪资，首页那几个标签就是它生成的。"),
        ], start=1):
            col = QVBoxLayout()
            col.setSpacing(6)
            head = QHBoxLayout()
            head.setSpacing(8)
            head.addWidget(StepDot(i))
            head.addWidget(label(t, "FieldLabel"))
            head.addStretch(1)
            col.addLayout(head)
            col.addWidget(label(d, "PageDesc", wrap=True))
            col.addStretch(1)
            row.addLayout(col, 1)
        c1.body.addLayout(row)
        self.content.addWidget(c1)

        c2 = Card("常见问题")
        for q, a in [
            ("模拟器是什么？",
             "一台跑在电脑里的虚拟手机，有屏幕、有网络、能装 App。"),
            ("一定要开着电脑吗？",
             "要。采集是在你电脑上跑的，关机或睡眠就停。启动任务后，程序会自动拉起模拟器。"),
            ("采集要多久？",
             "测试版本中。实测一个岗位约 15-20 秒（含看详情、随机停顿），"
             "默认每次 60 条，大约 20 分钟。"),
            ("采到的数据在哪？",
             "两个地方：本机数据库（给大模型读）+ 每天的 Excel（给人看）。都在「采集设置 → 导出位置」。"),
        ]:
            c2.body.addWidget(label(q, "FieldLabel"))
            ans = label(a, "PageDesc", wrap=True)
            ans.setMaximumWidth(720)
            c2.body.addWidget(ans)
            c2.body.addWidget(hline())
        self.content.addWidget(c2)
        self.content.addStretch(1)


# ---------------------------------------------------------------- 关于

class AboutPage(BasePage):
    def __init__(self, app, parent=None):
        super().__init__("关于", "", parent)
        self._inner.setMaximumWidth(860)

        hero = Card("")
        from .widgets import Mark

        row = QWidget()
        row.setFixedHeight(64)
        hrow = QHBoxLayout(row)
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.setSpacing(14)
        hrow.addWidget(Mark(44, 12, 17), 0, Qt.AlignVCenter)
        hcol = QVBoxLayout()
        hcol.setSpacing(2)
        hcol.addWidget(label("Job Agent", "Brand"))
        hcol.addWidget(label("招聘信息采集", "BrandSub"))
        hrow.addLayout(hcol)
        hrow.addStretch(1)
        ver = Pill(f"v{app.version}", "accent")
        ver.setFixedHeight(28)
        hrow.addWidget(ver, 0, Qt.AlignVCenter)
        hero.body.addWidget(row)
        self.content.addWidget(hero)

        c1 = Card("文件位置")
        for k, v in app.paths_for_about():
            row = QHBoxLayout()
            row.setSpacing(12)
            kk = label(k, "FieldLabel")
            kk.setFixedWidth(96)
            row.addWidget(kk)
            row.addWidget(label(v, "PageDesc"))
            row.addStretch(1)
            c1.body.addLayout(row)
        self.content.addWidget(c1)

        c2 = Card("注意事项")
        for text in [
            "需要提前人工登录:模拟器里先登录一次招聘 App。",
            "需要自己装好安卓模拟器，并在里面装好要用的招聘 App。",
            "采集期间电脑不能关机或睡眠。",
            "测试版本中，频率过高仍有账号风险，建议每天不超过 300 条。",
            "数据存在本机数据库里，换电脑前记得备份。",
        ]:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(label("·", "PageDesc"))
            row.addWidget(label(text, "PageDesc", wrap=True), 1)
            c2.body.addLayout(row)
        self.content.addWidget(c2)
        self.content.addStretch(1)
