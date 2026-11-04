"""可复用的界面零件。全部只做展示，不连真实逻辑。"""

import math
from pathlib import Path

from PySide6.QtCore import (
    Property, QPoint, QPointF, QRectF, QSize, Qt, QPropertyAnimation, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSlider, QSpinBox, QStyle, QToolTip, QVBoxLayout,
    QWidget,
)

from . import theme as T


# ---------------------------------------------------------------- 图标

_ICON_DIR = Path(__file__).with_name("icons")
_ICON_CACHE: dict = {}


def svg_renderer(name: str, color: str):
    """读取 icons/<name>.svg 并把颜色烘进去，返回 QSvgRenderer（矢量，画多大都清晰）。"""
    key = (name, color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = _ICON_DIR / f"{name}.svg"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    if not renderer.isValid():
        return None
    _ICON_CACHE[key] = renderer
    return renderer


# ---------------------------------------------------------------- 基础

def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("HLine")
    f.setFixedHeight(1)
    return f


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if wrap:
        lb.setWordWrap(True)
    return lb


class Card(QFrame):
    """白底圆角卡片：标题行 + 内容区。"""

    def __init__(self, title: str = "", sub: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 16)
        outer.setSpacing(10)

        self.head = QHBoxLayout()
        self.head.setSpacing(8)
        self.title_label = None
        self.sub_label = None
        if title:
            self.title_label = label(title, "CardTitle")
            self.head.addWidget(self.title_label)
        if sub:
            self.sub_label = label(sub, "CardSub")
            self.head.addWidget(self.sub_label)
        self.head.addStretch(1)
        outer.addLayout(self.head)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        outer.addLayout(self.body)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(15, 23, 42, 16))
        self.setGraphicsEffect(shadow)

    def add_right(self, w: QWidget) -> None:
        self.head.addWidget(w)

    def set_sub(self, text: str) -> None:
        if self.sub_label is not None:
            self.sub_label.setText(text)

    def set_title(self, text: str) -> None:
        if self.title_label is not None:
            self.title_label.setText(text)


class Pill(QLabel):
    """状态胶囊。"""

    STYLE = {
        "ok": (T.OK_SOFT, T.OK),
        "warn": (T.WARN_SOFT, T.WARN),
        "err": (T.ERR_SOFT, T.ERR),
        "dim": (T.LINE_SOFT, T.DIM),
        "accent": (T.ACCENT_SOFT, T.ACCENT),
    }

    def __init__(self, text: str = "", kind: str = "dim", parent=None):
        super().__init__(text, parent)
        self.set(kind, text)
        self.setAlignment(Qt.AlignCenter)

    def set(self, kind: str, text: str | None = None) -> None:
        bg, fg = self.STYLE.get(kind, self.STYLE["dim"])
        if text is not None:
            self.setText(text)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:9px;"
            f" padding:3px 10px; font-size:12px; font-weight:600;"
        )


class LinkLabel(QLabel):
    """像超链接一样的文字：蓝色、悬停下划线、点了能打开。"""

    clicked = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Link")
        self.setCursor(Qt.PointingHandCursor)

    def _underline(self, on: bool) -> None:
        f = self.font()
        f.setUnderline(on)
        self.setFont(f)

    def enterEvent(self, e):
        self._underline(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._underline(False)
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class ClickPill(Pill):
    """可点的状态胶囊：悬停给提示，点了重新检测。"""

    clicked = Signal()

    def __init__(self, text: str = "", kind: str = "dim", tip: str = "", parent=None):
        super().__init__(text, kind, parent)
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class HelpDot(QLabel):
    """一个小问号，悬停弹出说明。用 QToolTip 主动弹，不依赖 QSS 的 tooltip。"""

    def __init__(self, text: str, parent=None):
        super().__init__("?", parent)
        self._text = text
        self.setObjectName("HelpDot")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.WhatsThisCursor)

    def enterEvent(self, e):
        if self._text:
            QToolTip.showText(
                self.mapToGlobal(QPoint(self.width() // 2, self.height() + 6)),
                self._text, self)
        super().enterEvent(e)

    def leaveEvent(self, e):
        QToolTip.hideText()
        super().leaveEvent(e)


class NoWheelSlider(QSlider):
    """滚轮不拖动滑块，避免划页面时误改。"""

    def wheelEvent(self, e):
        e.ignore()


class NoWheelSpinBox(QSpinBox):
    """滚轮不改数值，避免划页面时误改。"""

    def wheelEvent(self, e):
        e.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, e):
        e.ignore()


class ToolCombo(NoWheelComboBox):
    """工具栏下拉：自绘一个三角箭头，禁用项在文案上标出来。"""

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(T.MUTED))
        p.setPen(Qt.NoPen)
        cx = self.width() - 15
        cy = self.height() / 2 - 1
        p.drawPolygon(QPolygonF([
            QPointF(cx - 4.2, cy - 2.0),
            QPointF(cx + 4.2, cy - 2.0),
            QPointF(cx, cy + 3.0),
        ]))


class PathField(QFrame):
    """仿 MAA「游戏路径」：圆角框里放路径 + 一个选文件夹的图标。

    点路径本身触发 clicked（比如打开文件/文件夹），点右边的图标才去选路径。
    """

    clicked = Signal()

    def __init__(self, text: str = "", tip: str = "选择文件夹", width: int = 380,
                 openable: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("PathField")
        self.setFixedSize(width, 34)
        self._openable = openable
        if openable:
            self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 4, 0)
        lay.setSpacing(4)
        self.lbl = QLabel(text)
        self.lbl.setObjectName("PathText")
        if openable:
            self.lbl.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.lbl, 1)
        self.btn = IconButton("folder", tip, size=26)
        lay.addWidget(self.btn)

    def mouseReleaseEvent(self, e):
        if (self._openable and e.button() == Qt.LeftButton
                and self.lbl.geometry().contains(e.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def setText(self, text: str) -> None:
        self.lbl.setText(text)


class IconButton(QPushButton):
    """自绘图标按钮：省空间，说明全部放 tooltip。"""

    def __init__(self, kind: str, tip: str = "", size: int = 32, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("IconBtn")
        if tip:
            self.setToolTip(tip)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def _color(self):
        return T.ACCENT if self.underMouse() else T.DIM

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse():
            # 自绘按钮会盖掉 QSS 的背景，悬停底色得自己画
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.LINE_SOFT))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)

        r = svg_renderer(self.kind, self._color())
        if r is not None:
            # 图标本身占满 24 的 viewBox，四周留一点白，视觉上跟文字更协调
            pad = self.width() * 0.11
            r.render(p, QRectF(pad, pad,
                               self.width() - 2 * pad, self.height() - 2 * pad))
            return

        # 统一在 32×32、原点居中的坐标系里画，换大小不用改任何数字
        k = min(self.width(), self.height()) / 32.0
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.scale(k, k)

        pen = QPen(QColor(self._color()), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        if self.kind == "refresh":
            # 缺口开在正上方，箭头贴在缺口右端、沿顺时针方向
            A = 100
            R = 9.6
            p.drawArc(QRectF(-R, -R, 2 * R, 2 * R), A * 16, -295 * 16)
            a = math.radians(A)
            sx, sy = math.cos(a) * R, -math.sin(a) * R
            tx, ty = math.sin(a), math.cos(a)          # 顺时针切线
            nx, ny = -ty, tx
            bx, by = sx - tx * 6.0, sy - ty * 6.0
            p.setBrush(QColor(self._color()))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([
                QPointF(sx, sy),
                QPointF(bx + nx * 3.3, by + ny * 3.3),
                QPointF(bx - nx * 3.3, by - ny * 3.3),
            ]))
        elif self.kind == "gear":
            # 三条带滑块的横线：比齿轮更好画，也不会被看成太阳
            p.setBrush(QColor(self._color()))
            for yy, kx in ((-5.4, -1.6), (0.0, 2.6), (5.4, -3.0)):
                p.drawLine(QPointF(-7.4, yy), QPointF(7.4, yy))
                p.drawEllipse(QPointF(kx, yy), 2.0, 2.0)
        elif self.kind == "folder":
            p.drawRoundedRect(QRectF(-7.4, -4.4, 14.8, 9.8), 2.0, 2.0)
            p.drawPolyline(QPolygonF([
                QPointF(-7.4, -4.4),
                QPointF(-7.4, -6.4),
                QPointF(-3.0, -6.4),
                QPointF(-1.4, -4.4),
            ]))
        elif self.kind == "device":
            p.drawRoundedRect(QRectF(-5.2, -7.2, 10.4, 12.8), 1.8, 1.8)
            p.drawLine(QPointF(-2.8, 7.6), QPointF(2.8, 7.6))


class Mark(QLabel):
    """方块 Logo。"""

    def __init__(self, size: int = 32, radius: int = 9, font_size: int = 13, parent=None):
        super().__init__("JA", parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background:{T.ACCENT}; color:#FFFFFF; border-radius:{radius}px;"
            f" font-size:{font_size}px; font-weight:700; letter-spacing:0.5px;")


class Tile(QFrame):
    """一个数字块：大数字 + 说明。"""

    def __init__(self, value: str, text: str, color: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("CardTight")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self.value = label(value, "TileValue")
        if color:
            self.value.setStyleSheet(f"color:{color};")
        lay.addWidget(self.value)
        lay.addWidget(label(text, "TileLabel"))

    def set_value(self, v: str) -> None:
        self.value.setText(v)


class ToggleSwitch(QWidget):
    """开关。Qt 的 QCheckBox 画不出好看的滑块，这里自己画。"""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._pos = 1.0 if checked else 0.0
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(130)

    # knob 属性驱动动画
    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool, emit: bool = False) -> None:
        if v == self._checked:
            return
        self._checked = v
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if v else 0.0)
        self._anim.start()
        if emit:
            self.toggled.emit(v)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.setChecked(not self._checked, emit=True)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT if self._checked else "#D5DAE1"))
        p.drawRoundedRect(QRectF(0, 1, 46, 24), 12, 12)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(2 + self._pos * 20, 3, 20, 20))


class Segmented(QFrame):
    """分段选择器（替代下拉框，点一下就切）。"""

    changed = Signal(str)

    def __init__(self, items: list[str], current: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("Seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._btns: list[QPushButton] = []
        for i, text in enumerate(items):
            b = QPushButton(text)
            b.setObjectName("SegItem")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(i == current)
            b.clicked.connect(lambda _=False, idx=i: self.select(idx))
            lay.addWidget(b)
            self._btns.append(b)
        self._index = current

    def select(self, idx: int) -> None:
        self._index = idx
        for i, b in enumerate(self._btns):
            b.setChecked(i == idx)
        self.changed.emit(self._btns[idx].text())

    def value(self) -> str:
        return self._btns[self._index].text()

    def currentText(self) -> str:
        return self.value()

    def setCurrent(self, value) -> None:
        # value 可以是下标，也可以是按钮文字；不会触发 changed
        idx = value if isinstance(value, int) else next(
            (i for i, b in enumerate(self._btns) if b.text() == value), 0)
        idx = max(0, min(idx, len(self._btns) - 1))
        self._index = idx
        for i, b in enumerate(self._btns):
            b.setChecked(i == idx)


class StepDot(QLabel):
    """左侧步骤序号圆点。"""

    def __init__(self, n: int, done: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignCenter)
        self.set(done, n)

    def set(self, done: bool, n: int = 1) -> None:
        if done:
            self.setText("✓")
            self.setStyleSheet(
                f"background:{T.OK}; color:#FFFFFF; border-radius:13px;"
                f" font-size:12px; font-weight:600;")
        else:
            self.setText(str(n))
            self.setStyleSheet(
                f"background:{T.LINE_SOFT}; color:{T.DIM}; border-radius:13px;"
                f" font-size:12px; font-weight:600;")


class EnvRow(QFrame):
    """环境检查的一行：状态点 + 名称 + 值 + 胶囊 + 操作 + 可展开说明。"""

    def __init__(self, name: str, value: str, hint: str,
                 actions: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("CardTight")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 14, 12)
        outer.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(12)
        top.addWidget(self.dot)

        self.name = label(name, "FieldValue")
        self.name.setFixedWidth(96)
        f = QFont(T.FONT)
        f.setBold(True)
        self.name.setFont(f)
        top.addWidget(self.name)

        self.value = label(value, "PageDesc")
        self.value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self.value, 1)

        self.pill = Pill("", "dim")
        self.pill.setFixedWidth(64)
        top.addWidget(self.pill)

        # 操作区固定宽度：每行只放一个按钮，其余用等宽占位撑住，
        # 这样四行的「胶囊 + 按钮 + 这是什么」在竖直方向上是对齐的。
        self._buttons: list[QPushButton] = []
        self.slot = QPushButton(actions[0][0]) if actions else QPushButton("")
        if actions:
            text, kind = actions[0]
            self.slot.setObjectName("Primary" if kind == "primary" else "Secondary")
        self.slot.setCursor(Qt.PointingHandCursor)
        self.slot.setFixedHeight(32)
        self.slot.setFixedWidth(88)
        self.slot.setVisible(bool(actions))
        top.addWidget(self.slot)
        if actions:
            self._buttons.append(self.slot)

        self.more = QPushButton("这是什么？")
        self.more.setObjectName("Ghost")
        self.more.setCursor(Qt.PointingHandCursor)
        self.more.setFixedHeight(32)
        self.more.setFixedWidth(84)
        self.more.clicked.connect(self._toggle_hint)
        top.addWidget(self.more)

        outer.addLayout(top)

        self.hint = label(hint, "SectionHint", wrap=True)
        self.hint.setContentsMargins(22, 0, 0, 0)
        self.hint.hide()
        outer.addWidget(self.hint)

    def _toggle_hint(self) -> None:
        visible = not self.hint.isVisible()
        self.hint.setVisible(visible)
        self.more.setText("收起" if visible else "这是什么？")

    def set_state(self, kind: str, value: str, pill: str,
                  dot_color: str | None = None) -> None:
        color = dot_color or {"ok": T.OK, "warn": T.WARN, "err": T.ERR,
                              "dim": T.MUTED}.get(kind, T.MUTED)
        self.dot.setStyleSheet(f"color:{color}; font-size:11px;")
        self.value.setText(value)
        self.pill.set(kind, pill)


class FieldRow(QWidget):
    """设置项一行：标签（可带 ? 帮助）+ 控件。

    align_right=True 时控件贴右边，整页看上就是一条整齐的右边界。
    """

    def __init__(self, text: str, widget: QWidget, hint: str = "",
                 label_width: int = 96, align_right: bool = False,
                 tip: str = "", sub: str = "", stacked: bool = False,
                 parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)

        def _dot() -> QLabel:
            return HelpDot(tip)

        if stacked:
            # 宽控件：标签单独一行，控件另起一行铺满
            inner = QVBoxLayout()
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setSpacing(6)
            head = QWidget()
            hl = QHBoxLayout(head)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)
            hl.addWidget(label(text, "FieldLabel"))
            if tip:
                hl.addWidget(_dot())
            if sub:
                hl.addWidget(label(sub, "FieldSub"))
            hl.addStretch(1)
            inner.addWidget(head)
            inner.addWidget(widget)
            lay.addLayout(inner)
            return

        if sub:
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            col.addWidget(label(text, "FieldLabel"))
            col.addWidget(label(sub, "FieldSub"))
            col.setAlignment(Qt.AlignVCenter)
            box = QWidget()
            box.setLayout(col)
            box.setFixedWidth(label_width + 120)
            lay.addWidget(box)
        else:
            lb = label(text, "FieldLabel")
            lb.setFixedWidth(label_width)
            lay.addWidget(lb)
        if tip:
            lay.addWidget(_dot())
        if align_right:
            lay.addStretch(1)
        lay.addWidget(widget)
        if hint:
            lay.addWidget(label(hint, "SectionHint"))
        if not align_right:
            lay.addStretch(1)



def chip_row(items: list[str], add: bool = True) -> tuple[QWidget, list[QPushButton]]:
    """一排可点的标签。"""
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    btns = []
    for it in items:
        b = QPushButton(it)
        b.setObjectName("Chip")
        b.setCheckable(True)
        b.setChecked(True)
        b.setCursor(Qt.PointingHandCursor)
        lay.addWidget(b)
        btns.append(b)
    if add:
        a = QPushButton("+ 添加")
        a.setObjectName("ChipAdd")
        a.setCursor(Qt.PointingHandCursor)
        lay.addWidget(a)
    lay.addStretch(1)
    return host, btns


def check(text: str, checked: bool = True) -> QCheckBox:
    c = QCheckBox(text)
    c.setChecked(checked)
    c.setCursor(Qt.PointingHandCursor)
    c.setStyleSheet(
        f"QCheckBox {{ color:{T.DIM}; font-size:13px; spacing:8px; }}"
        f"QCheckBox::indicator {{ width:16px; height:16px; border-radius:4px;"
        f" border:1px solid #C9D0D8; background:#FFFFFF; }}"
        f"QCheckBox::indicator:checked {{ background:{T.ACCENT};"
        f" border-color:{T.ACCENT}; }}")
    return c


class Toast(QLabel):
    """浮在窗口上的一行提示。不占布局，弹出后自动消失。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)
        self.setStyleSheet(
            "background:rgba(31,35,40,235); color:#FFFFFF; border-radius:8px;"
            " padding:10px 16px; font-size:13px;")
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ms: int = 3600) -> None:
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        if p is None:
            return
        x = (p.width() - self.width()) // 2
        y = p.height() - self.height() - 26
        self.move(max(12, x), max(12, y))
        self.show()
        self.raise_()
        self._timer.start(ms)


def toast(widget: QWidget, text: str, ms: int = 3600) -> None:
    """在窗口右下角弹出提示，不影响任何控件位置。"""
    win = widget.window()
    if win is None:
        return
    t = getattr(win, "_toast", None)
    if t is None:
        t = Toast(win)
        win._toast = t
    t.show_message(text, ms)

