# -*- coding: utf-8 -*-
"""正式界面：侧栏 + 六个页面 + 控制逻辑。

入口：
    python -m job_agent ui        （开发期）
    JobAgent.exe                  （打包后）
"""

from __future__ import annotations

from pathlib import Path

import sys
import threading
import time
import traceback

from PySide6.QtCore import QLockFile, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import cli, detect, flow, store
from . import theme as T
from .db_table import DbTableWindow
from .pages import AboutPage, DataPage, EnvPage, HomePage, SettingsPage, TutorialPage
from .widgets import Mark, Pill, label, toast

APP_NAME = "Job Agent"
APP_VERSION = "0.2.0"

# 侧栏顺序 → stack 下标。前六个页面（首页/环境配置/采集设置/数据/使用教程/关于）
# 在 stack 里仍是 0..5，新增的「岗位」「公司」放 6、7，绝不改动它们的顺序。
# 侧栏顺序 → stack 下标。-1 = 不切页，直接开独立窗口（数据库）。
NAV = [
    ("首页", 0),
    ("环境配置", 1),
    ("采集设置", 2),
    ("数据库", -1),
    ("使用教程", 4),
    ("关于", 5),
]


class Sidebar(QFrame):
    def __init__(self, on_pick, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(222)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 18, 14, 16)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(Mark())
        bcol = QVBoxLayout()
        bcol.setSpacing(0)
        bcol.addWidget(label(APP_NAME, "Brand"))
        bcol.addWidget(label("招聘信息采集", "BrandSub"))
        brand.addLayout(bcol)
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        for index, (text, _stack) in enumerate(NAV):
            b = QPushButton(text)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=index: on_pick(i))
            self.group.addButton(b, index)
            self.buttons.append(b)
            lay.addWidget(b)

        lay.addStretch(1)


class MainWindow(QMainWindow):
    version = APP_VERSION

    # worker 线程不能直接改界面：一律发信号，让 Qt 排队回主线程
    envReady = Signal(object, str)
    logLine = Signal(str, str)
    statusLine = Signal(str)
    progress = Signal(object)
    finished = Signal(object, object)
    launched = Signal(bool, str)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = dict(cfg)
        self.conn = store.connect(self.cfg["dbPath"])
        self.rep: dict = {}
        self._running = False
        self._cancel: threading.Event | None = None
        self._worker: threading.Thread | None = None
        self._t0 = 0.0
        self._done = 0
        self._launching = False
        self._pending_start = False
        self._detecting = False

        self.setWindowTitle(f"{APP_NAME} · 招聘信息采集")
        self.setMinimumSize(1120, 720)

        self.home = HomePage(self)
        self.env = EnvPage(self)
        self.settings = SettingsPage(self)
        self.data = DataPage(self)
        self.tutorial = TutorialPage(self)
        self.about = AboutPage(self)
        self.db_win: DbTableWindow | None = None

        self.stack = QStackedWidget()
        # 注意：DataPage 不再挂进 stack（入口改成独立窗口），但对象保留，
        # 因为 refresh_data() 还在用它算首页/窗口要的小字统计。
        for p in (self.home, self.env, self.settings,
                  self.tutorial, self.about):
            self.stack.addWidget(p)

        self.side = Sidebar(self.go)
        self.side.buttons[0].setChecked(True)

        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self._center()

        self.envReady.connect(self._apply_env)
        self.logLine.connect(self._log)
        self.statusLine.connect(self._on_status)
        self.progress.connect(self._apply_progress)
        self.finished.connect(self._finish)
        self.launched.connect(self._on_launched)

        self.settings.load(self.cfg)
        QTimer.singleShot(80, lambda: self.redetect("全部", quiet=True))
        QTimer.singleShot(160, self.refresh_data)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(1000)

    # ------------------------------------------------------------ 导航
    def go(self, nav_index: int) -> None:
        """nav_index 是侧栏序号，不是 stack 下标（两者顺序不同）。"""
        stack_index = NAV[nav_index][1]
        if stack_index < 0:
            self.open_db()
            for i, b in enumerate(self.side.buttons):   # 不把「数据库」留在选中态
                b.setChecked(i != nav_index and b.isChecked())
            return
        self.stack.setCurrentIndex(stack_index)
        for i, b in enumerate(self.side.buttons):
            b.setChecked(i == nav_index)
        if stack_index == 2:
            self.settings.export_link.setText(self.export_name())

    # ------------------------------------------------------------ 数据库窗口
    def open_db(self) -> None:
        """非模态独立窗口；关掉不影响采集。窗口引用必须留着，否则被 GC 回收。"""
        if self.db_win is None:
            self.db_win = DbTableWindow(self.conn, Path(self.cfg["dbPath"]))
        self.db_win.show()
        self.db_win.raise_()
        self.db_win.activateWindow()
        self.db_win.reload()

    # ------------------------------------------------------------ 环境
    def redetect(self, who: str = "全部", quiet: bool = False) -> None:
        """异步探测一下环境。who 只是给 Toast 用的说明；quiet 时不弹提示。"""
        if self._detecting:
            return
        self._quiet_detect = quiet
        self._detecting = True
        self.env.set_busy(True, who)

        def work() -> None:
            try:
                rep = detect.detect(self.cfg)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                rep = {}
            self.envReady.emit(rep, who)

        threading.Thread(target=work, daemon=True).start()

    def _apply_env(self, rep: dict, who: str) -> None:
        # 只在用户点「开始采集」时才拉起模拟器；开界面不做任何副作用。

        self._detecting = False
        self.rep = rep or {}
        adb = self.rep.get("adb") or {}
        dev = self.rep.get("device") or {}
        app = self.rep.get("app") or {}

        if dev.get("serial"):
            self.home.set_device(f"{dev.get('model') or '安卓设备'} "
                                 f"({dev['serial']})")
        elif adb.get("path"):
            self.home.set_device("没连上模拟器")
        else:
            self.home.set_device("没找到 adb")

        self.env.apply(self.rep)
        self.env.set_busy(False, who)
        quiet = self._quiet_detect
        self._quiet_detect = False

        # 结果只走轻提示，不写日志
        if dev.get("serial"):
            msg = f"{who}正常：{dev.get('model') or '安卓设备'} 已连接"
        elif adb.get("path"):
            msg = "模拟器没启动，点「开始采集」会自动拉起"
        else:
            msg = f"{who}没找到 adb"
        if quiet:
            return
        toast(self, msg)

    def pick_adb(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 adb.exe", self.cfg.get("adbPath") or "",
            "adb (adb.exe);;可执行文件 (*.exe)")
        if p:
            self.cfg["adbPath"] = p
            cli.save_config(self.cfg)
            self.redetect()

    def pick_emulator_dir(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "选择模拟器安装目录")
        if p:
            adb = None
            for name in ("adb.exe", "adb"):
                cand = f"{p}\\{name}" if "\\" in p else f"{p}/{name}"
                import os

                if os.path.isfile(cand):
                    adb = cand
            self.cfg["adbPath"] = adb or p
            cli.save_config(self.cfg)
            self.redetect()

    # ------------------------------------------------------------ 设置
    def save_settings(self) -> None:
        self.cfg.update(self.settings.collect())
        cli.save_config(self.cfg)
        self.settings.export_link.setText(self.export_name())
        toast(self, "设置已保存")

    def reset_settings(self) -> None:
        keep = {k: self.cfg.get(k) for k in
                ("adbPath", "dbPath", "logDir", "exportDir")}
        self.cfg.update(cli.DEFAULTS)
        self.cfg.update({k: v for k, v in keep.items() if v})
        self.settings.load(self.cfg)
        cli.save_config(self.cfg)
        toast(self, "已恢复默认")

    def pick_export_dir(self) -> None:
        p = QFileDialog.getExistingDirectory(
            self, "选择导出目录", self.cfg.get("exportDir") or "")
        if p:
            self.cfg["exportDir"] = p
            self.settings.export_path.setText(p)
            self.settings.export_link.setText(self.export_name())
            cli.save_config(self.cfg)

    # ------------------------------------------------------------ 导出
    def export_name(self) -> str:
        return f"{store.business_date()}_岗位采集.xlsx"

    def export_file(self) -> str:
        return f"{self.cfg['exportDir']}\\{self.export_name()}"

    def export_today(self) -> None:
        try:
            ok, path, n = store.export_xlsx(self.conn, self.export_file())
        except PermissionError:
            toast(self, "这个文件正在 Excel 里开着，关掉再试")
            return
        except Exception as exc:  # noqa: BLE001
            toast(self, f"导出失败：{exc}")
            return
        self.home.log.add("ok" if ok else "err",
                          f"{time.strftime('%H:%M:%S')}  导出 {n} 条 → {path}")
        self.settings.export_link.setText(self.export_name())

    # ------------------------------------------------------------ 采集
    def start_run(self) -> None:
        if self._running:
            return
        if not self.rep.get("ready"):
            # 模拟器没开是常见情况：直接替用户拉起来，而不是让他自己动手
            if not self._launching and detect.find_ldconsole(self.cfg):
                self._ensure_emulator(then_start=True)
                return
            problems = self.rep.get("problems") or []
            why = "；".join(
                f"{p.get('title')}（{p.get('detail')}）" for p in problems[:2]
            ) or "环境还没准备好"
            self.home.log.add("err", f"{time.strftime('%H:%M:%S')}  "
                                     f"没法开始：{why}")
            toast(self, "环境还没准备好，原因写在日志里了")
            self.redetect("重新检测")
            return

        done = store.counts(self.conn).get("todayCount", 0)
        quota = int(self.cfg.get("maxJobsPerDay", 120))
        left = max(0, quota - done)
        if left <= 0:
            toast(self, f"今天的上限 {quota} 条已经够了")
            return

        self._running = True
        self._cancel = threading.Event()
        self._t0 = time.time()
        self.home.set_running(True)
        self.home.set_status("accent", "采集中")
        self._done = 0
        self.home.set_progress(0)
        self.home.set_counts(0, 0, 0, 0)
        self.home.export_now.setVisible(False)
        self.home.log.add("step", f"{time.strftime('%H:%M:%S')}  开始采集，"
                                  f"今天还能采 {left} 条")

        def on_status(text: str) -> None:
            self.statusLine.emit(text)

        def sink(kind: str, kw: dict, line: str) -> None:
            # flow.Logger 给的那一行已经带 HH:MM:SS 了，别再补一次
            self.logLine.emit(kind, line)

        log = flow.Logger(self.cfg["logDir"], sink=sink)
        flow.H.set_status(on_status)

        def work() -> None:
            # sqlite 连接不能跨线程用：worker 自己开一个，界面那个留在主线程
            conn = None
            try:
                conn = store.connect(self.cfg["dbPath"])
                summary = flow.run(self.cfg, conn, log,
                                   on_progress=self._progress,
                                   cancel=lambda: bool(self._cancel and self._cancel.is_set()))
                if self.cfg.get("autoExport", True):
                    try:
                        for path in cli.export_all(self.cfg, conn):
                            self.logLine.emit(
                                "ok", f"{time.strftime('%H:%M:%S')}  已生成 {os.path.basename(path)}")
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self._shot_on_error()
                self.finished.emit(None, exc)
                return
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:  # noqa: BLE001
                    pass
            self.finished.emit(summary, None)

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def stop_run(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
            self.home.log.add("warn", f"{time.strftime('%H:%M:%S')}  已请求停止")

    def _ensure_emulator(self, then_start: bool = False) -> None:
        """后台把模拟器拉起来；成功后重新检测，需要的话接着开始采集。"""
        if self._launching:
            return
        self._launching = True
        self._pending_start = then_start
        ts = time.strftime("%H:%M:%S")
        self.home.log.add("step", f"{ts}  模拟器没开，正在替你启动，最长等 150 秒")
        toast(self, "模拟器没开，正在替你启动…")
        threading.Thread(target=self._launch_worker, daemon=True).start()

    def _launch_worker(self) -> None:
        ok, msg = detect.launch_emulator(self.cfg, wait_seconds=150)
        self.launched.emit(ok, msg)

    def _on_launched(self, ok: bool, msg: str) -> None:
        self._launching = False
        ts = time.strftime("%H:%M:%S")
        self.home.log.add("ok" if ok else "err", f"{ts}  {msg}")
        toast(self, msg)
        self.redetect("全部")
        if ok and self._pending_start:
            self._pending_start = False
            QTimer.singleShot(900, self.start_run)

    def _progress(self, kind: str, payload=None) -> None:
        """flow 的回调是 on_progress(kind, payload)，这里转成一个 dict 给界面。"""
        self.progress.emit({"kind": kind, "payload": payload})

    def _apply_progress(self, msg) -> None:
        """flow 每入库一条会回调一次 on_progress("stored", rec)。"""
        if not isinstance(msg, dict):
            return
        if msg.get("kind") != "stored":
            return
        self._done += 1
        limit = int(self.cfg.get("maxJobsPerRun", 60)) or 1
        self.home.set_progress(min(99, int(self._done * 100 / limit)))

    def _on_status(self, text: str) -> None:
        """等待进度：同一行覆盖显示，不往日志里刷。"""
        self.home.set_now(text)

    def _log(self, kind: str, text: str) -> None:
        """主线程里把一行写进首页日志（worker 通过 logLine 信号调到这里）。"""
        self.home.log.add(kind, text)

    def _shot_on_error(self) -> None:
        """出错了先截一张，把路径写进日志（界面上可以点开所在文件夹）。"""
        try:
            adb = flow.resolve_adb(self.cfg)
            serial = flow.serial_of(adb, self.cfg)
            shot = flow.snapshot(adb, serial, flow.anomaly_dir(self.cfg), "运行失败")
        except Exception:  # noqa: BLE001
            shot = None
        ts = time.strftime("%H:%M:%S")
        if shot:
            self.logLine.emit("warn", f"{ts}  异常截图  {shot}")
        else:
            self.logLine.emit("warn", f"{ts}  异常截图  没截到（设备可能已断开）")

    def _finish(self, summary: dict | None, exc: Exception | None) -> None:
        self._running = False
        try:
            flow.H.set_status(None)
        except Exception:  # noqa: BLE001
            pass
        self.home.set_now("")
        self.home.set_running(False)
        if exc is not None:
            self.home.set_status("err", "出错了")
            self.home.log.add("err", f"{time.strftime('%H:%M:%S')}  "
                                     f"{type(exc).__name__}: {exc}")
            self.home.export_now.setVisible(True)
            return

        s = summary or {}
        self.home.set_counts(
            inserted=int(s.get("inserted", 0)) + int(s.get("updated", 0)),
            skipped=int(s.get("existed", 0)) + int(s.get("viewed_skip", 0)),
            failed=int(s.get("failed", 0)),
            seconds=int(s.get("seconds", time.time() - self._t0)),
        )
        self.home.set_progress(100)
        self.home.set_status("ok", "已完成")
        self.export_today()
        self.refresh_data()

    def _on_tick(self) -> None:
        if self._running and self._t0:
            self.home.set_counts(seconds=int(time.time() - self._t0))

    # ------------------------------------------------------------ 数据
    def refresh_data(self) -> None:
        try:
            st = store.counts(self.conn)
            rows = store.recent(self.conn, limit=200)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return
        self.data.reload(st, rows, st.get("lastDate"))

    def _on_synced(self, msg: str) -> None:
        """同步采集完成后，首页日志留一行，跟采集记录放在一起。"""
        self.home.log.add("ok", f"{time.strftime('%H:%M:%S')}  {msg}")
        self.refresh_data()

    # ------------------------------------------------------------ 关于
    def paths_for_about(self):
        return [
            ("版本", APP_VERSION),
            ("运行环境", "自带（免安装 Python）+ 雷电模拟器 9"),
            ("数据库", self.cfg.get("dbPath", "")),
            ("导出目录", self.cfg.get("exportDir", "")),
            ("日志目录", self.cfg.get("logDir", "")),
        ]

    # ------------------------------------------------------------ 窗口
    def _center(self) -> None:
        screen = self.screen().availableGeometry()
        w = min(1280, screen.width() - 100)
        h = min(840, screen.height() - 120)
        self.resize(w, h)
        self.move(screen.x() + (screen.width() - w) // 2,
                  screen.y() + (screen.height() - h) // 4)

    def closeEvent(self, e):  # noqa: N802
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(e)


def main(cfg: dict | None = None) -> int:
    if cfg is None:
        cfg = cli.load_config()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont(T.FONT, 10))
    app.setStyleSheet(T.QSS)

    # 单实例：两个窗口同时写一个 sqlite 会互相踩，直接拦掉
    lock = QLockFile(str(Path(cfg["dbPath"]).with_suffix(".lock")))
    if not lock.tryLock(100):
        return 0          # 已经在跑了，安静退出；弹窗反而会留一个看不见的进程

    win = MainWindow(cfg)
    scr = app.primaryScreen().availableGeometry()
    win.resize(min(win.width(), scr.width() - 80), min(win.height(), scr.height() - 80))
    win.move(scr.center() - win.rect().center())     # 别让窗口跑到屏幕外面去
    win.show()
    rc = app.exec()
    lock.unlock()
    return rc


if __name__ == "__main__":
    sys.exit(main())
