# -*- coding: utf-8 -*-
r"""从安卓设备（雷电模拟器 / 真机）读招聘 App 的职位列表，抠成结构化 JSON。

设计原则
--------
1. **零安装**：只用 adb 自带的 `uiautomator dump`，不往设备装任何 app、不依赖
   uiautomator2 / playwright / OCR。文字是系统给出的原文，不是猜的。
2. **只读**：本脚本只 dump + 解析，不点、不滑、不投递。动作由调用方决定。
3. **失败即报**：拿不到控件树就抛错，绝不返回"半截数据"让上层当成真的。

用法
----
    # 抓当前屏幕上最多 3 张卡片，打印
    python harvest.py --limit 3

    # 存成 JSON
    python job_agent/harvest.py --limit 20 --json exports/zhilian.json

    # 换设备（真机序列号）
    python harvest.py --adb adb --serial 1234567890 --limit 3
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

DEFAULT_ADB = os.environ.get("LD_ADB") or r"D:\leidian\LDPlayer9\adb.exe"

# 控件树先落盘再 cat 回来，比 `exec-out ... /dev/tty` 稳
DEVICE_PATH = "/sdcard/ui_harvest.xml"

_TRAILER = re.compile(rb"UI hierchary dumped to:.*$", re.S)
_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

# 一行文字里的「薪资」长这样：4000-8000元 / 8000-12000元·13薪 / 1-1.8万 / 1.5-2.5万
_RE_SALARY = re.compile(r"\d\s*[-~－]\s*\d.*?(元|万)")
# 公司规模：20人以下 / 100-299人 / 10000人以上
_RE_SIZE = re.compile(r"^\d+(-\d+)?人(以上|以下)?$")
# 融资阶段
_RE_STAGE = re.compile(r"^(天使轮|A轮|B轮|C轮|D轮及以上|已上市|未融资|不需要融资|战略投资)$")
# 活跃度：今日活跃 / 今日回复50+次 / 本周活跃
_RE_ACTIVE = re.compile(r"^(今日|昨日|本周|最近|刚刚).*(活跃|回复|在线|登录)")
# 地区：广州 珠江、番禺 小谷围、天河 五山
_RE_AREA = re.compile(r"^\S+\s+\S+$")
# 控件树里混进来的零宽字符、占位方块（安卓把图片/表情渲成 ￼）
_RE_JUNK = re.compile(r"[\u200b-\u200f\ufffc\ue000-\uf8ff]")
# 底部导航栏的文字，永远不是职位卡片的一部分
_NAV_WORDS = {"首页", "职Q", "消息", "我的", "公司", "更多"}


def adb(*args: str, adb_path: str = DEFAULT_ADB, serial: str | None = None,
        timeout: int = 30) -> bytes:
    cmd = [adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        raise RuntimeError(
            f"adb {' '.join(args)} 失败 (rc={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def dump_xml(adb_path: str = DEFAULT_ADB, serial: str | None = None,
             attempts: int = 3) -> bytes:
    """先把 XML 落到设备上再 cat 回来。

    直接 `exec-out uiautomator dump /dev/tty` 在页面切换/加载中经常只吐一句
    trailer、一个节点都拿不到——这是整条链路最不稳的一环，实测落盘再读稳得多。
    """
    last = b""
    for i in range(attempts):
        try:
            adb("shell", "uiautomator", "dump", DEVICE_PATH,
                adb_path=adb_path, serial=serial)
            raw = adb("exec-out", "cat", DEVICE_PATH,
                      adb_path=adb_path, serial=serial)
            raw = _TRAILER.sub(b"", raw).strip()
            start = raw.find(b"<?xml")
            if start >= 0:
                return raw[start:]
            last = raw
        except Exception as exc:  # noqa: BLE001 - 重试期间任何异常都只是「这轮没成」
            last = repr(exc).encode("utf-8", "replace")
        # "null root node returned by UiTestAutomationBridge" 多半是界面正在
        # 转屏/动画/加载，等一下重试即可，不要直接判定失败
        if i < attempts - 1:
            time.sleep(1.5)
    raise RuntimeError(f"连续 {attempts} 次没拿到控件树，最后一次输出：{last[:300]!r}")


def parse_nodes(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    nodes = []
    for el in root.iter("node"):
        a = el.attrib
        m = _BOUNDS.match(a.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = (int(v) for v in m.groups())
        text = (a.get("text") or "").strip()
        desc = (a.get("content-desc") or "").strip()
        text = _RE_JUNK.sub("", text or desc).strip()
        if not text:
            continue
        nodes.append({
            "text": text or desc,
            "cls": a.get("class", ""),
            "rid": a.get("resource-id", ""),
            "pkg": a.get("package", ""),
            "bounds": [x1, y1, x2, y2],
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
            "clickable": a.get("clickable") == "true",
            "height": y2 - y1,
        })
    return nodes


def group_rows(nodes: list[dict], tol: int = 18) -> list[list[dict]]:
    """按纵坐标把节点聚成「视觉上的行」。"""
    rows: list[list[dict]] = []
    for n in sorted(nodes, key=lambda x: x["cy"]):
        if rows and abs(n["cy"] - rows[-1][0]["cy"]) <= tol:
            rows[-1].append(n)
        else:
            rows.append([n])
    for r in rows:
        r.sort(key=lambda x: x["cx"])
    return rows


def split_cards(rows: list[list[dict]], gap: int = 70) -> list[list[list[dict]]]:
    """行与行之间出现明显空白 → 说明换卡片了。

    另外做一道保险：有的卡片挨得太近（中间只隔一行「入选实力星」），
    整段会被并成一块，结果只认出上面那张、下面那张静默丢掉。
    凡是同一块里出现 2 个以上薪资行的，就在第二个薪资行处切开。
    """
    cards: list[list[list[dict]]] = []
    for r in rows:
        if not cards:
            cards.append([r])
            continue
        prev_cy = cards[-1][-1][0]["cy"]
        if r[0]["cy"] - prev_cy > gap:
            cards.append([r])
        else:
            cards[-1].append(r)

    out: list[list[list[dict]]] = []
    for card in cards:
        sal_rows = [r for r in card
                    if any(_RE_SALARY.search(n["text"]) for n in r)]
        if len(sal_rows) < 2:
            out.append(card)
            continue
        cut = card.index(sal_rows[1])
        if cut <= 0:
            out.append(card)
            continue
        out.append(card[:cut])
        out.append(card[cut:])
    return out


def _first(nodes, pred):
    for n in nodes:
        if pred(n["text"]):
            return n
    return None


def classify_card(rows: list[list[dict]]) -> dict | None:
    """把一张卡片的若干行，翻译成结构化字段。认不出来就返回 None。"""
    if len(rows) < 2:
        return None

    title_row = rows[0]
    # 标题 = 第一行里「不是薪资」的最长文字
    title_node = None
    salary_node = None
    for n in title_row:
        if _RE_SALARY.search(n["text"]):
            salary_node = salary_node or n
        elif title_node is None or len(n["text"]) > len(title_node["text"]):
            title_node = n
    if title_node is None:
        return None

    company = None
    size = stage = None
    tags: list[str] = []
    hr = activity = area = None

    for row in rows[1:]:
        # 「· 人事经理」这一格需要把左边的人名一起认出来
        dot = next((n for n in row if "·" in n["text"]), None)
        consumed: set[int] = set()
        if dot is not None and hr is None:
            name = next((n for n in row if n is not dot and n["cx"] < dot["cx"]), None)
            hr = ((name["text"] + " ") if name else "") + dot["text"]
            consumed = {id(dot)} | ({id(name)} if name else set())
        for n in row:
            if id(n) in consumed:
                continue
            t = n["text"]
            if _RE_SIZE.match(t):
                size = size or t
            elif _RE_STAGE.match(t):
                stage = stage or t
            elif "·" in t and hr is None:
                hr = t
            elif _RE_ACTIVE.match(t):
                activity = activity or t
            elif _RE_AREA.match(t) and n["cx"] > 700:
                area = area or t
            elif company is None and not tags:
                company = t
            else:
                tags.append(t)

    if company is None:
        return None

    # 标签里混进来的「融资/规模」和底部导航剔掉
    tags = [t for t in tags
            if not _RE_SIZE.match(t) and not _RE_STAGE.match(t) and t not in _NAV_WORDS]

    return {
        "title": title_node["text"],
        "salary": salary_node["text"] if salary_node else None,
        "company": company,
        "companySize": size,
        "companyStage": stage,
        "tags": tags,
        "hr": hr,
        "activity": activity,
        "area": area,
        # 点这张卡片标题 = 进详情页（给下一步留的坐标）
        "tap": [title_node["cx"], title_node["cy"]],
        # 标题框：判「看过/没看过」要按这块去采样像素
        "titleBox": title_node["bounds"],
        "titleRid": title_node.get("rid", ""),
    }


def harvest_screen(adb_path: str = DEFAULT_ADB, serial: str | None = None,
                   limit: int = 0) -> dict:
    nodes = parse_nodes(dump_xml(adb_path, serial))
    pkg = next((n["pkg"] for n in nodes if n["pkg"]), None)
    if nodes:
        # 掐掉顶部标题栏（搜索框/筛选页签）和底部导航栏，它们会污染卡片字段
        height = max(n["bounds"][3] for n in nodes)
        nodes = [n for n in nodes if 250 < n["cy"] < height - 115]
    rows = group_rows(nodes)
    cards = split_cards(rows)

    items = []
    for rows_in_card in cards:
        rec = classify_card(rows_in_card)
        if not rec:
            continue
        # 顶部搜索栏/筛选栏也会被切成"卡片"，用"有没有薪资或公司规模"把它们筛掉
        if not (rec["salary"] or rec["companySize"] or rec["companyStage"]):
            continue
        items.append(rec)
        if limit and len(items) >= limit:
            break

    return {
        "source": "zhilian",
        "package": pkg,
        "capturedAt": None,       # 由调用方填
        "screenNodeCount": len(nodes),
        "blockCount": len(cards),
        "cardCount": len(items),
        "items": items,
    }


def swipe_up(adb_path: str = DEFAULT_ADB, serial: str | None = None,
             ms: int = 320, y_from: int = 1500, y_to: int = 520) -> None:
    """上滑一屏。给个几百毫秒的时长，滑动带惯性，比瞬时跳跃更像人。"""
    adb("shell", "input", "swipe", "540", str(y_from), "540", str(y_to), str(ms),
        adb_path=adb_path, serial=serial)


def harvest_screens(adb_path: str = DEFAULT_ADB, serial: str | None = None,
                    screens: int = 1, limit: int = 0,
                    pause: tuple[float, float] = (2.5, 5.0)) -> dict:
    """连续抓多屏：读 → 滑 → 读 …… 按「公司+岗位+薪资」去重。

    中途某一屏一条新的都没有，说明到底了，提前停。
    """
    seen: set[tuple] = set()
    items: list[dict] = []
    last: dict | None = None
    screens_read = 0

    for i in range(screens):
        page = harvest_screen(adb_path, serial, 0)
        # 刚滑完列表经常还在加载，解析出 0 张卡并不代表真的到底了——补一次
        if page["cardCount"] == 0 and i > 0:
            time.sleep(3.0)
            page = harvest_screen(adb_path, serial, 0)
        last = page
        screens_read += 1
        fresh = 0
        for it in page["items"]:
            key = (it["company"], it["title"], it["salary"])
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
            fresh += 1
            if limit and len(items) >= limit:
                break
        if limit and len(items) >= limit:
            break
        if i == screens - 1:
            break
        # 只有「这一屏读到了卡片、但全是旧的」才算到底；
        # 读出 0 张卡是加载问题，不该被当成终点
        if fresh == 0 and page["cardCount"] > 0 and i > 0:
            break
        swipe_up(adb_path, serial)
        time.sleep(random.uniform(*pause))

    return {
        "source": "zhilian",
        "package": last["package"] if last else None,
        "capturedAt": None,
        "screensRead": screens_read,
        "cardCount": len(items),
        "items": items,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="harvest", description="读招聘 App 当前屏幕的职位卡片")
    ap.add_argument("--adb", default=DEFAULT_ADB)
    ap.add_argument("--serial", default=None, help="多设备时指定序列号")
    ap.add_argument("--limit", type=int, default=0, help="最多返回多少条（0=全部）")
    ap.add_argument("--screens", type=int, default=1, help="连续抓几屏（>1 会自动上滑翻页）")
    ap.add_argument("--json", help="写到这个 JSON 文件")
    args = ap.parse_args(argv)

    if args.screens > 1:
        result = harvest_screens(args.adb, args.serial, args.screens, args.limit)
    else:
        result = harvest_screen(args.adb, args.serial, args.limit)
    if args.json:
        import datetime
        result["capturedAt"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"wrote {args.json}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["items"] else 2


if __name__ == "__main__":
    sys.exit(main())
