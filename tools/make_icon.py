# -*- coding: utf-8 -*-
"""生成 job-agent.ico（Mark 方块 + JA 字）。

Qt 渲染成 256×256 PNG，再套一层 ICO 头（ICO 允许直接内嵌 PNG）。
"""

import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "job-agent.ico")
ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"


def render(size: int) -> bytes:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    r = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    path = QPainterPath()
    path.addRoundedRect(r, size * 0.24, size * 0.24)
    p.fillPath(path, QColor(ACCENT))

    # 右下角压一层深色，做一点层次
    grad = QRectF(r.left(), r.top() + size * 0.55, r.width(), r.height() * 0.45)
    p.save()
    p.setClipPath(path)
    p.fillRect(grad, QColor(29, 78, 216, 70))
    p.restore()

    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(int(size * 0.42))
    f.setWeight(QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(r, Qt.AlignCenter, "JA")
    p.end()

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    png = render(256)
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    with open(OUT, "wb") as f:
        f.write(header + entry + png)
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
