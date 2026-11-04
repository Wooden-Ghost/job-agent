# -*- coding: utf-8 -*-
"""启动前的环境探测。

界面第一屏要回答三个问题，而且要给「查不到怎么办」：
    1. 本机有没有安卓模拟器？有没有在运行？
    2. 模拟器里装没装智联招聘、有没有登录过？
    3. 导出 Excel 的依赖在不在？

全部是本地探测，不联网、不弹权限，正常情况下 1–3 秒跑完。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import sys

#: 常见模拟器安装目录 → (显示名, 目录列表, 该目录下 adb 的文件名优先级)
EMULATORS = [
    ("雷电模拟器 9", [
        r"D:\leidian\LDPlayer9", r"C:\leidian\LDPlayer9",
        r"D:\Program Files\LDPlayer\LDPlayer9",
        r"C:\Program Files\LDPlayer\LDPlayer9",
        r"D:\Program Files\LDPlayer9", r"C:\Program Files\LDPlayer9",
    ], ("adb.exe",)),
    ("雷电模拟器 4", [
        r"D:\Program Files\dnplayer", r"C:\Program Files\dnplayer",
        r"D:\dnplayer", r"C:\dnplayer",
    ], ("adb.exe",)),
    ("夜神模拟器", [
        r"D:\Program Files\Nox\bin", r"C:\Program Files\Nox\bin",
        r"D:\Program Files (x86)\Nox\bin", r"C:\Program Files (x86)\Nox\bin",
    ], ("adb.exe", "nox_adb.exe")),
    ("MuMu 模拟器", [
        r"C:\Program Files\MuMu\emulator\nemu\vmonitor\bin",
        r"D:\Program Files\MuMu\emulator\nemu\vmonitor\bin",
        r"C:\Program Files\Netease\MuMuPlayer-12.0\shell",
        r"D:\Program Files\Netease\MuMuPlayer-12.0\shell",
    ], ("adb.exe", "adb_server.exe")),
]

APP_PACKAGE = "com.zhaopin.social"

_LEVEL_ERROR = "error"
_LEVEL_WARN = "warn"


def _run(cmd: list[str], timeout: int = 8) -> tuple[int, str]:
    """跑一个命令，返回 (返回码, 合并后的输出)。失败一律当 0 输出，不抛。"""
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    out = (p.stdout or b"") + (p.stderr or b"")
    return p.returncode, out.decode("utf-8", "ignore")


# ---------------------------------------------------------------- 单项探测

def find_emulators() -> list[dict]:
    """扫一遍常见安装目录，返回「装了的模拟器」。"""
    found: list[dict] = []
    seen: set[str] = set()
    for name, dirs, exe_names in EMULATORS:
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for exe in exe_names:
                p = os.path.join(d, exe)
                if os.path.isfile(p) and p.lower() not in seen:
                    seen.add(p.lower())
                    found.append({"emulator": name, "dir": d, "adb": p})
    return found


def find_adb_in_path() -> str | None:
    for name in ("adb", "adb.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def list_devices(adb: str) -> list[dict]:
    """`adb devices` 里处于 device 状态的设备。"""
    code, out = _run([adb, "devices"], timeout=10)
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            kind = "模拟器" if serial.startswith("emulator-") or ":" in serial else "真机"
            devices.append({"serial": serial, "kind": kind})
    return devices


def app_version(adb: str, serial: str) -> str | None:
    """装了返回版本号，没装返回 None。"""
    code, out = _run([adb, "-s", serial, "shell", "dumpsys", "package", APP_PACKAGE],
                     timeout=12)
    if APP_PACKAGE not in out:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            return line.split("=", 1)[1].strip()
    return "已安装"


def device_model(adb: str, serial: str) -> str:
    code, out = _run([adb, "-s", serial, "shell", "getprop", "ro.product.model"],
                     timeout=8)
    return out.strip() or "未知机型"


def python_info() -> dict:
    return {
        "version": "%d.%d.%d" % sys.version_info[:3],
        "exe": sys.executable,
        "ok": sys.version_info >= (3, 9),
    }


def openpyxl_info() -> dict:
    try:
        import openpyxl  # noqa: F401
        return {"ok": True, "version": getattr(openpyxl, "__version__", "?")}
    except Exception:  # noqa: BLE001
        return {"ok": False, "version": None}


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- 汇总


# ---------------------------------------------------------------- 拉起模拟器

def _ldconsole_near(adb: str | None) -> str | None:
    """adb.exe 同目录里一般就躺着 ldconsole.exe。"""
    if not adb:
        return None
    cand = os.path.join(os.path.dirname(os.path.abspath(adb)), "ldconsole.exe")
    return cand if os.path.isfile(cand) else None


def find_ldconsole(cfg: dict | None = None) -> str | None:
    """找到 ldconsole.exe：config 里指过的目录 → adb 同目录 → 常见安装路径。"""
    cfg = cfg or {}
    explicit = cfg.get("emulatorDir") or ""
    if explicit:
        cand = os.path.join(explicit, "ldconsole.exe")
        if os.path.isfile(cand):
            return cand
    adb = cfg.get("adbPath") or ""
    got = _ldconsole_near(adb)
    if got:
        return got
    for _name, dirs, _exe in EMULATORS:
        for d in dirs:
            cand = os.path.join(d, "ldconsole.exe")
            if os.path.isfile(cand):
                return cand
    return None


def resolve_adb_path(cfg: dict | None = None) -> str | None:
    """按 config → 环境变量 → 安装目录 找 adb。"""
    cfg = cfg or {}
    if cfg.get("adbPath"):
        return cfg["adbPath"]
    if os.environ.get("LD_ADB"):
        return os.environ["LD_ADB"]
    for _name, dirs, exe in EMULATORS:
        if isinstance(exe, (tuple, list)):      # 兼容 ("adb.exe",) 这种写法
            exe = exe[0]
        for d in dirs:
            cand = os.path.join(d, exe)
            if os.path.isfile(cand):
                return cand
    return find_adb_in_path()


def launch_emulator(cfg: dict | None = None, wait_seconds: int = 150) -> tuple[bool, str]:
    """确保模拟器在跑：已经在跑就直接返回；没跑就用 ldconsole 拉起来并等它连上。"""
    cfg = cfg or {}
    adb = resolve_adb_path(cfg)
    if adb:
        devs = list_devices(adb)
        if devs:
            return True, "模拟器已经在运行"

    exe = find_ldconsole(cfg)
    if not exe:
        return False, "没找到模拟器安装目录（找不到 ldconsole.exe）"

    flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([exe, "launch", "--index", "0"],
                         creationflags=flags, close_fds=True)
    except OSError as exc:
        return False, f"启动模拟器失败：{exc}"

    if not adb:
        return False, "模拟器已启动，但找不到 adb，无法确认设备"

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if list_devices(adb):
            return True, "模拟器已启动"
        time.sleep(2.0)
    return False, f"等 {wait_seconds} 秒还没连上模拟器"

def detect(cfg: dict) -> dict:
    """把上面这些拼成一份界面能直接画的报告。"""
    problems: list[dict] = []

    py = python_info()
    if not py["ok"]:
        problems.append({
            "level": _LEVEL_ERROR, "code": "python",
            "title": f"Python {py['version']} 太旧",
            "detail": "需要 Python 3.9 或更高版本。",
            "fix": "到 python.org 装 3.12，装的时候勾选 Add to PATH。",
        })

    ox = openpyxl_info()
    if not ox["ok"]:
        problems.append({
            "level": _LEVEL_WARN, "code": "openpyxl",
            "title": "没装 openpyxl，导不出 .xlsx",
            "detail": "仍然能跑到 CSV，但你看不了 Excel 格式。",
            "fix": "在命令行执行：python -m pip install openpyxl",
        })

    # adb：手动配置 > 环境变量 > PATH > 模拟器目录
    adbs = find_emulators()
    adb_path, adb_source = None, ""
    if cfg.get("adbPath") and os.path.isfile(cfg["adbPath"]):
        adb_path, adb_source = cfg["adbPath"], "你在设置里指定的"
    elif os.environ.get("LD_ADB") and os.path.isfile(os.environ["LD_ADB"]):
        adb_path, adb_source = os.environ["LD_ADB"], "环境变量 LD_ADB"
    elif find_adb_in_path():
        adb_path, adb_source = find_adb_in_path(), "系统 PATH"
    elif adbs:
        adb_path, adb_source = adbs[0]["adb"], f"{adbs[0]['emulator']} 安装目录"

    if not adb_path:
        problems.append({
            "level": _LEVEL_ERROR, "code": "adb",
            "title": "没找到安卓模拟器",
            "detail": "本机常见目录里都没有 adb，说明还没装模拟器。",
            "fix": "装一个安卓模拟器（推荐雷电模拟器 9），装好后点「重新检测」；"
                   "已经装了但装在别处，就在下面手动填 adb 路径。",
        })

    devices: list[dict] = []
    serial = None
    if adb_path:
        devices = list_devices(adb_path)
        if not devices:
            problems.append({
                "level": _LEVEL_WARN, "code": "device",
                "title": "模拟器没在运行",
                "detail": "找到了 adb，但没有已连接的设备。",
                "fix": "先把模拟器打开，等它进到桌面，再点「重新检测」。",
            })
        else:
            serial = next((d["serial"] for d in devices
                           if d["serial"].startswith("emulator-")), devices[0]["serial"])

    app_ver = None
    model = None
    if adb_path and serial:
        app_ver = app_version(adb_path, serial)
        model = device_model(adb_path, serial)
        if app_ver is None:
            problems.append({
                "level": _LEVEL_ERROR, "code": "app",
                "title": "模拟器里没装智联招聘",
                "detail": f"设备 {serial}（{model}）上没有 {APP_PACKAGE}。",
                "fix": "把智联招聘的安装包装进模拟器（直接拖进模拟器窗口即可），"
                       "装好并登录一次，再点「重新检测」。",
            })

    paths = {
        "db": cfg.get("dbPath", ""),
        "logs": cfg.get("logDir", ""),
        "exports": cfg.get("exportDir", ""),
    }
    for key, label in (("db", "数据库目录"), ("logs", "日志目录"),
                       ("exports", "导出目录")):
        p = paths[key]
        parent = p if key != "db" else os.path.dirname(p)
        if parent and not _writable(parent):
            problems.append({
                "level": _LEVEL_WARN, "code": f"path_{key}",
                "title": f"{label}写不进去",
                "detail": parent,
                "fix": "在设置里换一个目录。",
            })

    ready = bool(adb_path and serial and app_ver)
    return {
        "python": py,
        "openpyxl": ox,
        "emulators": adbs,
        "adb": {"ok": bool(adb_path), "path": adb_path, "source": adb_source},
        "devices": devices,
        "device": {"serial": serial, "model": model},
        "app": {"ok": bool(app_ver), "version": app_ver},
        "paths": paths,
        "problems": problems,
        "ready": ready,
    }
