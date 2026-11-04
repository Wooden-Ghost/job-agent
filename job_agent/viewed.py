# -*- coding: utf-8 -*-
"""判断列表卡「看过 / 没看过」。

智联把看过的岗位标题显示成灰色（#999），没看过的显示成深色（#222）。
这个差异**不在控件树里**——灰卡和黑卡的 XML 属性完全一样，只有 text 不同，
所以只能取像素。

代价：`screencap` 在模拟器上要 0.6–0.9 秒，一屏截一次。
因此调用方应当只在「这一屏确实有要点击的新卡」时才截，且一屏只截一次。

用原始帧缓冲（`screencap` 不带 -p）而不是 PNG：PNG 虽然只有 300 KB，
但要解 zlib + 逐行反过滤（实测多数行是 Paeth），纯 Python 解起来比
多传 8 MB 还慢。原始帧缓冲是 4 字节/像素的裸 RGBA，可以按偏移直接取。
"""

from __future__ import annotations

import struct

from job_agent.harvest import adb

# 灰字 #999 的亮度 ≈ 153，黑字 #222 ≈ 34，中间取 110 作分界。
GREY_MIN_LUM = 110


def capture(adb_path: str, serial: str) -> tuple[int, int, memoryview]:
    """取一帧原始像素：12 字节头（宽、高、格式）+ w*h*4 字节 RGBA。"""
    raw = adb("exec-out", "screencap", adb_path=adb_path, serial=serial,
              timeout=60)
    if len(raw) < 16:
        raise RuntimeError(f"screencap 只回了 {len(raw)} 字节")
    w, h, _fmt = struct.unpack("<III", raw[:12])
    pix = memoryview(raw)[12:]
    if len(pix) < w * h * 4:
        raise RuntimeError(f"screencap 像素不足：{len(pix)} < {w * h * 4}")
    return w, h, pix


def min_lum(pix: memoryview, width: int, box, step: int = 2) -> int:
    """标题框里最暗的像素亮度。文字笔画够粗，隔行隔列采样不会漏。"""
    x1, y1, x2, y2 = (int(v) for v in box)
    best = 255
    for y in range(max(0, y1), y2, step):
        base = y * width * 4
        for x in range(max(0, x1), x2, step):
            i = base + x * 4
            lum = (pix[i] * 299 + pix[i + 1] * 587 + pix[i + 2] * 114) // 1000
            if lum < best:
                best = lum
                if best < 40:
                    return best
    return best


def is_viewed(pix: memoryview, width: int, box) -> bool:
    """标题是灰的 → 这条已经看过了。框太小/取不到 → 当作没看过（宁可多抓）。"""
    if not box or (box[3] - box[1]) < 10 or (box[2] - box[0]) < 20:
        return False
    return min_lum(pix, width, box) > GREY_MIN_LUM
