# -*- coding: utf-8 -*-
"""页面状态机 + 采集主流程。

流程（见设计文档第 3 节）：
    自检 → 回首页 → 逐个 tab：每滑一屏就抓卡、就地点击（边滑边点）
        → 跳过库里已有的、跳过标题变灰（看过）的
        → 点前重取坐标 → 点进详情、抽 JD、写库、返回 → 滑下一屏
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import datetime

from job_agent import humanize as H
from job_agent import store, viewed

from job_agent.enrich import extract as extract_detail
from job_agent.enrich import wait_anchor
from job_agent.harvest import adb as _adb
from job_agent.harvest import dump_xml, harvest_screen, parse_nodes

APP_ACTIVITY = "com.zhaopin.social/.main.MainActivity"
_RE_SALARY = re.compile(r"\d\s*[-~－]\s*\d.*?(元|万)")
_TITLE_RID = "tv_position_name"


def _norm_title(s: str | None) -> str:
    """比对用的岗位名归一化。

    智联列表页用半角括号 `(AI Coding) `（还常带尾随空格），详情页用全角
    `（AI Coding）`。不归一化就会把同一条判成「点错了」，进而丢掉列表里的
    区/规模/融资阶段——2026-11-03 实测 7 次误判里有 4 次是这么来的。
    """
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", s)          # （）→()、ＮＦＫＣ 全角转半角
    return re.sub(r"[\s\u200b-\u200f]+", "", t)   # 空白与零宽字符全去掉

# 期望 tab 行的定位：先找「全部/最新/附近」这一行，tab 就在它上面那一行。
# （首页有搜索框时 tab 在 y≈164，结果页无搜索框时 tab 在 y≈80；
#   绝对坐标不可靠，只有相对「全部」那一行才稳。）
_TAB_EXCLUDE = {"添加", "全部", "最新", "附近", "筛选", "职位订阅", "城市"}
_SEG_WORDS = ("全部", "最新", "附近")


# ---------------------------------------------------------------- 日志

class Logger:
    """一次运行 = 一个文件夹里的两个文件：.jsonl（给程序看）+ .log（给人看）。"""

    # 日志里给人看的那一行，用中文说人话
    _HUMAN = {
        "start": "",
        "tabs": "",
        "screen": "划动",
        "stored": "采集到",
        "skip_exists": "跳过【已入库】",
        "skip_dup": "跳过【重复】",
        "skip_viewed": "跳过【已采集】",
        "card_gone": "跳过【列表已变】",
        "detail_timeout": "跳过【详情超时】",
        "title_mismatch": "跳过【点错了】",
        "store_error": "跳过【写库失败】",
        "recover": "回到首页",
        "relaunch": "重新打开智联",
        "tab_done": "标签采够",
        "tab_end": "标签到底",
        "stop": "提前停止",
        "done": "本轮结束",
        "anomaly": "异常截图",
    }

    @staticmethod
    def _fmt(kind: str, kw: dict) -> str:
        """把一条事件说成人话；认不出的退回中文名。"""
        g = kw.get
        if kind == "start":
            return "开始采集"
        if kind == "tabs":
            names = g("names") or []
            return f"找到 {len(names)} 个标签：{'、'.join(names)}"
        if kind == "screen":
            return (f"【{g('tab')}】第 {int(g('index', 0)) + 1} 屏："
                    f"{g('cards')} 个岗位，新增 {g('fresh')} 个")
        if kind == "stored":
            return f"{g('company')} · {g('title')}"
        if kind in ("skip_exists", "skip_dup", "skip_viewed", "card_gone",
                    "detail_timeout", "store_error"):
            return f"{g('company')} · {g('title')}"
        if kind == "title_mismatch":
            return f"想点【{g('expected')}】，实际进的是【{g('got')}】"
        if kind == "recover":
            return "回到首页"
        if kind == "relaunch":
            return "智联不在前台，重新打开"
        if kind == "tab_done":
            return f"【{g('tab')}】已采 {g('inserted')} 条，换下一个标签"
        if kind == "tab_end":
            return f"【{g('tab')}】已经划到底"
        if kind == "anomaly":
            return str(g("path") or "")
        if kind == "done":
            sec = int(g("seconds") or 0)
            return (f"新增 {g('inserted', 0)} 条 · 更新 {g('updated', 0)} 条 · "
                    f"跳过 {int(g('existed', 0)) + int(g('viewed_skip', 0))} 条 · "
                    f"失败 {g('failed', 0)} 条 · 用时 {sec // 60} 分 {sec % 60} 秒")
        if kind == "stop":
            why = {"cancelled": "你点了停止", "max_jobs": "到本轮的条数上限",
                   "deadline": "到本轮时间上限", "budget": "今天额度用完了"}.get(
                       str(g("reason")), "")
            return why or "已停止"
        return ""

    def __init__(self, log_dir: str, sink=None):
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(log_dir, f"run-{stamp}.jsonl")
        self.text_path = os.path.join(log_dir, f"run-{stamp}.log")
        #: 界面用：sink(kind, kw, 给人看的那一行)。GUI 从这里实时拿进度。
        self.sink = sink
        self._write_text(f"===== 智联招聘采集 Agent  {stamp} =====\n")

    def _write_text(self, line: str) -> None:
        try:
            with open(self.text_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def __call__(self, kind: str, **kw) -> None:
        now = datetime.now()
        rec = {"at": now.isoformat(timespec="seconds"), "kind": kind, **kw}
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

        label = self._HUMAN.get(kind, kind)
        text = self._fmt(kind, kw)
        line = f"{now:%H:%M:%S}  "
        if label and text:
            line += f"{label}：{text}"
        else:
            line += text or label
        self._write_text(line + "\n")
        if self.sink:
            try:
                self.sink(kind, kw, line)
            except Exception:  # noqa: BLE001  界面出问题不能拖垮采集
                pass


# ---------------------------------------------------------------- 环境

def anomaly_dir(cfg: dict | None = None) -> str:
    """异常截图放哪：默认是程序目录下的「异常记录」。"""
    cfg = cfg or {}
    base = cfg.get("anomalyDir") or "异常记录"
    if os.path.isabs(base):
        return base
    try:
        from job_agent.cli import _app_dir
        root = _app_dir()          # 打包后是 exe 所在目录，不会钻进 _internal
    except Exception:  # noqa: BLE001
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, base)


def snapshot(adb_path: str, serial: str, out_dir: str, tag: str = "异常") -> str | None:
    """截一张当前屏幕存到 out_dir，返回文件路径；失败返回 None（绝不抛）。"""
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{tag}.png"
    path = os.path.join(out_dir, name)
    try:
        data = _adb("exec-out", "screencap", "-p", adb_path=adb_path, serial=serial,
                    timeout=20)
    except Exception:  # noqa: BLE001  设备掉线时 adb 会抛，截图失败就算了
        return None
    if not data or len(data) < 1024 or not data.startswith(b"\x89PNG"):
        return None
    try:
        with open(path, "wb") as f:
            f.write(data)
    except OSError:
        return None
    return path


def resolve_adb(cfg: dict) -> str:
    """adb 探测：config → 环境变量 → PATH → 常见模拟器路径。"""
    cands = []
    if cfg.get("adbPath"):
        cands.append(cfg["adbPath"])
    if os.environ.get("LD_ADB"):
        cands.append(os.environ["LD_ADB"])
    from shutil import which
    for name in ("adb", "adb.exe"):
        p = which(name)
        if p:
            cands.append(p)
    cands += [
        r"D:\leidian\LDPlayer9\adb.exe",
        r"C:\leidian\LDPlayer9\adb.exe",
        r"D:\Program Files\Nox\bin\adb.exe",
        r"C:\Program Files\Nox\bin\adb.exe",
        r"C:\Program Files\MuMu\emulator\nemu\vmonitor\bin\adb_server.exe",
        r"D:\Program Files\MuMu\emulator\nemu\vmonitor\bin\adb_server.exe",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    raise RuntimeError(
        "找不到 adb。请启动模拟器（雷电/夜神/MuMu），或在 config.json 里填 adbPath。"
    )


def serial_of(adb_path: str, cfg: dict) -> str:
    if cfg.get("serial"):
        return cfg["serial"]
    out = _adb("devices", adb_path=adb_path, serial=None).decode("utf-8", "ignore")
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    raise RuntimeError("没有已连接的设备。请确认模拟器已启动且 adb 调试已开。")


def check_env(adb_path: str, serial: str) -> dict:
    ver = _adb("version", adb_path=adb_path, serial=serial).decode("utf-8", "ignore")
    pkgs = _adb("shell", "pm", "list", "packages", "com.zhaopin.social",
                adb_path=adb_path, serial=serial).decode("utf-8", "ignore")
    size = _adb("shell", "wm", "size", adb_path=adb_path,
                serial=serial).decode("utf-8", "ignore")
    return {
        "adb": adb_path,
        "serial": serial,
        "adbVersion": ver.strip().splitlines()[0] if ver.strip() else "",
        "screen": size.strip().splitlines()[-1] if size.strip() else "",
        "appInstalled": "com.zhaopin.social" in pkgs,
    }


# ---------------------------------------------------------------- 状态识别

def detect(nodes: list[dict]) -> str:
    t = [n["text"] for n in nodes if n["text"]]
    if "立即投递" in t or "先聊聊" in t:
        return "detail"
    if any(_RE_SALARY.search(x) for x in t):
        return "list"
    if any(x in t for x in ("首页", "我的", "消息")):
        return "home"
    return "unknown"


def screen_height(nodes: list[dict]) -> int:
    return max((n["bounds"][3] for n in nodes), default=1920)


def find_segment_row(nodes: list[dict]) -> dict | None:
    """「全部 / 最新 / 附近」这一行——首页与结果页都有，是最稳的锚点。"""
    for n in nodes:
        if n["text"] in _SEG_WORDS and n["cy"] < 400:
            return n
    return None


def find_tabs(nodes: list[dict]) -> list[dict]:
    """紧贴「全部」那一行上方的可点文字 = 求职期望 tab。"""
    seg = find_segment_row(nodes)
    if seg is None:
        return []
    y0 = seg["cy"]
    return [
        n for n in nodes
        if n["text"] and n["text"] not in _TAB_EXCLUDE
        and y0 - 130 <= n["cy"] <= y0 - 30
    ]


APP_PKG = "com.zhaopin.social"
_LAUNCHER_HINT = ("系统应用", "应用", "浏览器", "设置", "图库")


def in_app(nodes: list[dict]) -> bool:
    """当前前台是不是智联：直接看控件树里有没有它自己的包名。"""
    return any((n.get("pkg") or "").startswith(APP_PKG) for n in nodes)


def is_desktop(nodes: list[dict]) -> bool:
    """雷电/安卓桌面：包名是 launcher，或者有「系统应用」这个图标文字。"""
    if any("launcher" in (n.get("pkg") or "").lower() for n in nodes):
        return True
    texts = {n.get("text") for n in nodes if n.get("text")}
    return "系统应用" in texts


def is_home(nodes: list[dict]) -> bool:
    """首页/结果页判定：有「全部」行，且上面至少 2 个期望 tab。"""
    return find_segment_row(nodes) is not None and len(find_tabs(nodes)) >= 2


# ---------------------------------------------------------------- 复位

def ensure_home(adb_path: str, serial: str, log: Logger, tries: int = 5,
                shot_dir: str | None = None) -> list[dict]:
    """确保停在「有求职期望 tab」的页面上。

    判定全看控件树，不做图像识别：
      - 首页 = 有「全部/最新/附近」这一行 + 至少 2 个 tab
      - 在 App 里 = 树里有 com.zhaopin.social 的节点
      - 桌面 = launcher 包名，或有「系统应用」这个图标
    不在 App 里（桌面、开屏、别的 App）就 am start 拉起，然后每 ~3 秒看一眼。
    """
    nodes = parse_nodes(dump_xml(adb_path, serial))
    if is_home(nodes):
        return nodes

    state = detect(nodes)
    log("recover", attempt=0, state="desktop" if is_desktop(nodes) else state)

    # 已经在 App 里（列表/详情）→ 退一级回到首页
    for i in range(tries):
        if not in_app(nodes) or state in ("home",):
            break
        H.back(adb_path=adb_path, serial=serial)
        H.wait(1.0, 2.0)
        nodes = parse_nodes(dump_xml(adb_path, serial))
        if is_home(nodes):
            return nodes
        state = detect(nodes)
        log("recover", attempt=i + 1, state=state)

    # 不在 App 里：拉起来，然后每 3 秒复查
    log("relaunch", reason="not_in_app", state="desktop" if is_desktop(nodes) else state)
    _adb("shell", "am", "start", "-n", APP_ACTIVITY, adb_path=adb_path, serial=serial)

    deadline = time.time() + 45.0
    while time.time() < deadline:
        nodes = parse_nodes(dump_xml(adb_path, serial))
        if is_home(nodes):
            return nodes
        H.wait(2.4, 3.6)          # ≈ 每 3 秒看一次

    if shot_dir:
        shot = snapshot(adb_path, serial, shot_dir, "回不到首页")
        log("anomaly", reason="no_home", path=shot or "截图失败")
    raise RuntimeError("回不到首页，请人工看一眼模拟器当前画面（截图在异常记录里）。")


def locate_title(adb_path: str, serial: str, title: str) -> dict | None:
    """点之前重新 dump，找到这张卡**此刻**的标题节点。

    虚拟列表在点击瞬间可能已经重排/懒加载，早前算好的坐标会落到别的卡上
    （2026-11-03 实测 3 次真的点错、4 次重复采同一条）。所以坐标必须现取现用。
    """
    want = _norm_title(title)
    if not want:
        return None
    for n in parse_nodes(dump_xml(adb_path, serial)):
        if n.get("rid", "").endswith(_TITLE_RID) and _norm_title(n["text"]) == want:
            return n
    return None


def enrich_item(adb_path: str, serial: str, item: dict, tab: str,
                log: Logger, default_city: str = "成都",
                cancel=None) -> dict | None:
    """点进一张卡片，抽详情，返回合并后的记录；失败返回 None。"""
    x, y = item.get("tap") or (0, 0)
    if not x or not y:
        return None
    H.tap_point(x, y, adb_path=adb_path, serial=serial)
    H.wait_key()

    nodes = wait_anchor(adb_path, serial, cancel=cancel)
    if not nodes:
        log("detail_timeout", company=item.get("company"), title=item.get("title"))
        H.back(adb_path=adb_path, serial=serial)
        H.wait(2.0, 3.0)
        return None

    d = extract_detail(nodes)
    same = bool(_norm_title(d.get("title")) and _norm_title(item.get("title"))
                and _norm_title(d["title"]) == _norm_title(item["title"]))
    if not same:
        # 点开的不是列表里那一条（列表在点击前被刷新/重排了）。
        # 详情页的数据本身是自洽的，照存；但列表独有的字段不能用，否则会串行。
        log("title_mismatch", expected=item.get("title"), got=d.get("title"))

    location = (d.get("location") or "").replace("工作地点：", "")
    area = item.get("area") if same else None
    # 「工作城市」= 岗位所在地，不是公司注册地。
    # 详情页「公司信息」里那个 city 是公司所在城市（湖南公司会挂「长沙」，
    # 但岗位在成都郫都区），所以绝不能拿它当岗位城市。
    city = None
    if area and area.count(" ") == 2:
        city = area.split(" ")[0]        # "成都 武侯 桂溪" → 成都
    if not city:
        city = default_city

    rec = {
        "tab": tab,
        "company": d.get("companyFull") or (item.get("company") if same else None),
        "company_full": d.get("companyFull"),
        "title": d.get("title") or (item.get("title") if same else None),
        "salary_text": d.get("salary") or (item.get("salary") if same else None),
        "city": city,
        "company_city": d.get("city"),
        "district": location.split("·")[0].strip() if location else None,
        "area_text": area,
        "experience": d.get("experience"),
        "education": d.get("education"),
        "company_meta": d.get("companyMeta"),
        "hiring_count": d.get("hiringCount"),
        "company_size": item.get("companySize") if same else None,
        "company_stage": item.get("companyStage") if same else None,
        "jd": d.get("jd"),
        "raw": json.dumps({"list": item if same else None, "detail": d,
                           "sameCard": same}, ensure_ascii=False),
    }

    H.back(adb_path=adb_path, serial=serial)
    H.wait(2.0, 3.5)
    return rec


# ---------------------------------------------------------------- 主流程

def run(cfg: dict, conn, log: Logger, on_progress=None, cancel=None) -> dict:
    """跑一次采集。

    cancel: 可选的无参函数，返回 True 表示「用户要求停下」。
            在每个 tab、每张卡之前检查一次，停得干净（已抓到的都已入库）。
    """
    adb_path = resolve_adb(cfg)
    serial = serial_of(adb_path, cfg)
    log("start", adb=adb_path, serial=serial)

    def stopped() -> bool:
        return bool(cancel and cancel())


    started = datetime.now()
    deadline = started.timestamp() + cfg.get("maxRunMinutes", 60) * 60
    max_jobs = cfg.get("maxJobsPerRun", 60)
    screens = cfg.get("screensPerTab", 3)
    raw_quota = cfg.get("perTabJobs", 20)
    if isinstance(raw_quota, (list, tuple)):
        quotas = [int(x or 0) for x in raw_quota]
    else:
        quotas = [int(raw_quota or 0)] * 8

    def quota_for(i: int) -> int:
        """第 i 个标签要采几条；配置不够长就沿用最后一个。"""
        if not quotas:
            return 0
        return quotas[i] if i < len(quotas) else quotas[-1]
    shot_dir = anomaly_dir(cfg)

    nodes = ensure_home(adb_path, serial, log, shot_dir=shot_dir)
    tabs = find_tabs(nodes)
    if not tabs:
        raise RuntimeError("首页没找到求职期望 tab。请确认智联已登录且已配置期望。")
    log("tabs", names=[t["text"] for t in tabs])
    if on_progress:
        on_progress("tabs", [t["text"] for t in tabs])

    wanted = cfg.get("tabs") or [t["text"] for t in tabs]
    tabs = [t for t in tabs if t["text"] in wanted] or tabs
    # 每次从第一个 tab 开始，顺序固定（想打乱再打开 shuffleTabs）
    order = H.shuffled(tabs) if cfg.get("shuffleTabs", False) else tabs

    inserted = updated = existed = viewed_skip = gone = failed = 0
    skip_viewed = bool(cfg.get("skipViewed", True))
    op_counter = 0
    stop_logged = False

    for tab_i, tab in enumerate(order):
        if stopped():
            log("stop", reason="cancelled", inserted=inserted)
            break
        if time.time() > deadline or inserted >= max_jobs:
            if not stop_logged:
                log("stop", reason="budget")
                stop_logged = True
            break

        nodes = ensure_home(adb_path, serial, log, shot_dir=shot_dir)
        current = next((t for t in find_tabs(nodes) if t["text"] == tab["text"]), tab)

        # 边滑边点：每屏抓完立刻点这一屏的卡，坐标永远新鲜。
        # （早前版本先抓完 N 屏再滚回顶部，滚回时会触发下拉刷新导致列表重排，
        #   结果点开的是别的岗位——已在 2026-11-03 实测中踩到。）
        H.tap_node(current, adb_path=adb_path, serial=serial)
        H.wait_key()

        seen: set[tuple] = set()
        tab_inserted = 0
        tab_quota = quota_for(tab_i)
        if tab_quota <= 0:
            log("tab_done", tab=current["text"], inserted=0, reason="quota_zero")
            continue
        for idx in range(screens):
            if time.time() > deadline or inserted >= max_jobs:
                log("stop", reason="max_jobs" if inserted >= max_jobs else "deadline",
                    inserted=inserted, screen_index=idx)
                stop_logged = True
                break

            page = harvest_screen(adb_path, serial)
            items = []
            for it in page["items"]:
                k = (it.get("company"), it.get("title"), it.get("salary"))
                if k in seen:
                    log("skip_dup", company=it.get("company"), title=it.get("title"))
                    continue
                seen.add(k)
                it["tab"] = current["text"]
                items.append(it)
            log("screen", tab=current["text"], index=idx,
                cards=page["cardCount"], fresh=len(items))
            if idx > 0 and page["cardCount"] == 0:
                # 已经滑到列表底部，换下一个标签，别空转
                log("tab_end", tab=current["text"], reason="no_more_cards")
                break

            # 先剔掉库里已有的，剩下的才是「可能要点击」的候选。
            # 不在候选里的卡不值得为它截图。
            candidates = []
            for it in items:
                if store.has(conn, store.job_key(it.get("company"), it.get("title"))):
                    existed += 1
                    log("skip_exists", company=it.get("company"), title=it.get("title"))
                else:
                    candidates.append(it)

            # 一屏只截一次图，用来判「看过/没看过」
            pix = frame_w = None
            if candidates and skip_viewed:
                frame_w, _frame_h, pix = viewed.capture(adb_path, serial)

            for item in H.shuffled(candidates):
                if stopped():
                    log("stop", reason="cancelled", inserted=inserted)
                    break
                if time.time() > deadline or inserted >= max_jobs:
                    log("stop", reason="max_jobs" if inserted >= max_jobs else "deadline",
                        inserted=inserted)
                    stop_logged = True
                    break

                if pix is not None and viewed.is_viewed(pix, frame_w, item.get("titleBox")):
                    viewed_skip += 1
                    log("skip_viewed", company=item.get("company"),
                        title=item.get("title"))
                    continue

                # 坐标现取现用：列表可能在上一秒已经重排
                node = locate_title(adb_path, serial, item.get("title"))
                if node is None:
                    gone += 1
                    log("card_gone", company=item.get("company"),
                        title=item.get("title"))
                    continue
                item = dict(item, tap=[node["cx"], node["cy"]], title=node["text"])
            try:
                H._status(f"正在打开：{item.get('title', '')[:18]}")
            except Exception:  # noqa: BLE001
                pass

                rec = enrich_item(adb_path, serial, item, current["text"], log,
                                  cfg.get("defaultCity", "成都"), cancel=cancel)
                op_counter += 1
                H.maybe_pause(cfg.get("pauseEvery", 6), op_counter)

                if rec is None:
                    failed += 1
                    continue
                try:
                    result = store.upsert(conn, rec)
                    if result == "inserted":
                        inserted += 1
                        tab_inserted += 1
                    else:
                        updated += 1
                    log("stored", result=result, company=rec.get("company"),
                        title=rec.get("title"))
                    if on_progress and result == "inserted":
                        on_progress("stored", rec)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    log("store_error", error=str(exc), company=item.get("company"))

            if tab_quota and tab_inserted >= tab_quota:
                log("tab_done", tab=current["text"], inserted=tab_inserted,
                    reason="per_tab")
                break
            if idx < screens - 1:
                H.wait_short()
                h = screen_height(parse_nodes(dump_xml(adb_path, serial)))
                H.swipe_up(adb_path=adb_path, serial=serial, height=h)
                H.wait_short()

    ended = datetime.now()
    store.log_run(conn, started.isoformat(timespec="seconds"),
                  ended.isoformat(timespec="seconds"),
                  ",".join(t["text"] for t in order),
                  inserted, existed + viewed_skip, failed, log.path)
    summary = {
        "inserted": inserted,
        "updated": updated,
        "existed": existed,
        "viewed_skip": viewed_skip,
        "gone": gone,
        "failed": failed,
        "seconds": int((ended - started).total_seconds()),
        "log": log.path,
    }
    log("done", **summary)
    return summary
