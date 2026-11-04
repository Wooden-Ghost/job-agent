# -*- coding: utf-8 -*-
# PyInstaller 打包脚本：python tools/build_exe.py
# 产物：dist\JobAgent\JobAgent.exe（onedir，启动快、体积稳）
#
# 重新打包会先保留用户数据（config.json / data / logs / exports），
# 打完再搬回去——否则 --clean 会把已采集的库和配置一起删掉。

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "JobAgent"
ICON = os.path.join(ROOT, "assets", "job-agent.ico")
KEEP = ("config.json", "data", "logs", "exports")


def _stash(dist_dir: str):
    """把用户数据临时挪走，返回 (临时目录, 已挪走的名称列表)。"""
    if not os.path.isdir(dist_dir):
        return None, []
    tmp = tempfile.mkdtemp(prefix="jobagent-keep-")
    moved = []
    for name in KEEP:
        src = os.path.join(dist_dir, name)
        if os.path.exists(src):
            dst = os.path.join(tmp, name)
            shutil.move(src, dst)
            moved.append(name)
    return tmp, moved


def _restore(dist_dir: str, tmp: str, moved) -> None:
    for name in moved:
        src = os.path.join(tmp, name)
        dst = os.path.join(dist_dir, name)
        if os.path.exists(dst):
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            else:
                os.remove(dst)
        shutil.move(src, dst)
    if tmp and os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    os.chdir(ROOT)
    dist = os.path.join(ROOT, "dist", NAME)
    tmp, moved = _stash(dist)

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        f"--name={NAME}",
        f"--icon={ICON}",
        "--add-data", f"{os.path.join(ROOT, 'job_agent', 'ui', 'icons')};job_agent/ui/icons",
        "--collect-submodules", "PySide6",
        "--exclude-module", "tkinter",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQml",
        os.path.join(ROOT, "launch.py"),
    ]
    print(" ".join(args))
    r = subprocess.run(args)
    if r.returncode != 0:
        _restore(dist, tmp, moved)
        return r.returncode

    _restore(dist, tmp, moved)

    # 首次打包（没有旧数据）时补一份「相对路径」配置，解压到哪就存哪
    if "config.json" not in moved:
        src = os.path.join(ROOT, "config.example.json")
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dist, "config.json"))
    for d in ("data", "logs", "exports"):
        os.makedirs(os.path.join(dist, d), exist_ok=True)

    kept = "、".join(moved) if moved else "无（首次打包）"
    print(f"\n保留的旧数据：{kept}")
    print(f"打包完成：{os.path.join(dist, NAME + '.exe')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
