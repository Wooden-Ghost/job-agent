# -*- coding: utf-8 -*-
"""人类化操作：随机等待 / 控件内随机落点 / 随机滑动。

纪律（写在设计文档第 6 节，属于硬性要求）：
    业务代码里**不允许**出现 time.sleep(常量) —— 一律调用这里的函数。
    坐标**不允许**写死像素 —— 一律从控件 bounds 里随机取点。
"""

from __future__ import annotations

import random
import time

from job_agent.harvest import adb as _adb


# ---------------------------------------------------------------- 状态行
# 界面要的「现在在干嘛」：一个回调，set_status 之后 wait() 会往里推进度。
# 界面自己决定怎么显示（我们是单行覆盖，不刷屏）。
STATUS = None


def set_status(fn) -> None:
    """注册状态回调；传 None 取消。"""
    global STATUS
    STATUS = fn


def _status(text: str) -> None:
    if STATUS is None:
        return
    try:
        STATUS(text)
    except Exception:  # noqa: BLE001  界面出问题不能拖垮采集
        pass


def sleep_report(total: float, label: str = "等待中") -> None:
    """睡 total 秒，期间每 0.25 秒把「还剩 Xs」推给界面（同一行覆盖）。"""
    left = max(0.0, float(total))
    step = 0.25
    while left > 0:
        _status(f"{label}，还剩 {max(1, int(round(left)))}s")
        chunk = min(step, left)
        time.sleep(chunk)
        left -= chunk
    _status("")


# ---------------------------------------------------------------- 等待

def wait(a: float = 1.2, b: float = 3.5, label: str = "等待中") -> None:
    """一般等待（带状态提示）。"""
    sleep_report(random.uniform(a, b), label)


def wait_key(label: str = "页面加载中") -> None:
    """关键页等待（进详情页、开期望页、切 tab）。"""
    sleep_report(random.uniform(3.0, 6.0), label)


def wait_short(label: str = "稍等") -> None:
    """页面内的微停顿（滑完看一眼）。"""
    sleep_report(random.uniform(0.8, 2.0), label)


def pause_long() -> None:
    """长停，模拟人手离开。"""
    sleep_report(random.uniform(20.0, 60.0), "休息一下")


def maybe_pause(every: int = 6, counter: int = 0) -> bool:
    """每 `every` 次操作插一次长停。返回是否真的停了。"""
    if every > 0 and counter > 0 and counter % every == 0:
        pause_long()
        return True
    return False


# ---------------------------------------------------------------- 点击

def tap_point(x: int, y: int, *, adb_path: str, serial: str | None = None,
              jitter: int = 10) -> None:
    """在坐标附近随机抖动一下再点。

    卡片标题只有中心点没有 bounds，所以用固定抖动半径——标题文字通常很宽，
    ±10px 一定还落在文字上。
    """
    jx = x + random.randint(-jitter, jitter)
    jy = y + random.randint(-jitter, jitter)
    _adb("shell", "input", "tap", str(jx), str(jy),
         adb_path=adb_path, serial=serial)


def tap_node(node: dict, *, adb_path: str, serial: str | None = None,
             inset: float = 0.08) -> None:
    """在控件 bounds 内随机取点（四边留 inset 比例的边距）。"""
    x1, y1, x2, y2 = node["bounds"]
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    ix, iy = int(w * inset), int(h * inset)
    lo_x, hi_x = x1 + ix, x2 - ix
    lo_y, hi_y = y1 + iy, y2 - iy
    if hi_x <= lo_x:
        lo_x = hi_x = (x1 + x2) // 2
    if hi_y <= lo_y:
        lo_y = hi_y = (y1 + y2) // 2
    _adb("shell", "input", "tap",
         str(random.randint(lo_x, hi_x)), str(random.randint(lo_y, hi_y)),
         adb_path=adb_path, serial=serial)


def back(*, adb_path: str, serial: str | None = None) -> None:
    _adb("shell", "input", "keyevent", "KEYCODE_BACK",
         adb_path=adb_path, serial=serial)


# ---------------------------------------------------------------- 滑动

def swipe_up(*, adb_path: str, serial: str | None = None, height: int = 1920) -> None:
    """从下往上滑一屏，起止点、横向偏移、时长全部随机。"""
    x = 540 + random.randint(-40, 40)
    y_from = int(height * 0.78) + random.randint(-150, 150)
    y_to = int(height * 0.30) + random.randint(-150, 150)
    y_from = max(400, min(height - 120, y_from))
    y_to = max(200, min(y_from - 200, y_to))
    dur = random.randint(280, 520)
    _adb("shell", "input", "swipe",
         str(x), str(y_from), str(x), str(y_to), str(dur),
         adb_path=adb_path, serial=serial)


# ---------------------------------------------------------------- 顺序

def shuffled(seq):
    """打散顺序（复制一份，不改原列表）。"""
    out = list(seq)
    random.shuffle(out)
    return out
