# -*- coding: utf-8 -*-
"""点进职位详情页，把 JD 全文和公司四要素抓回来。

做法（全部实测过，见 `智联自动化-实测说明.md`）：
    列表 tap 卡片 → 等「立即投递」锚点出现 → dump 一次 → 取字段 → BACK

详情页结构非常干净：整页 14 个文字节点，JD 全文是**一个 855 字符的 TextView**。
所以不需要滚动、不需要 OCR，一次 dump 就够。

用法：
    # 从 harvest.py 产出的列表 JSON 里取前 3 条
    python enrich.py --from-list "D:\\Projects\\job-agent\\exports\\2026-11-03-zhilian-成都-爬虫.json" --top 3

    # 或者只探当前屏幕上的一张（不点，只看）
    python enrich.py --inspect
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from job_agent.harvest import DEFAULT_ADB, adb, dump_xml, parse_nodes  # noqa: E402

_RE_META = re.compile(r"·.*?人")
_RE_HIRING = re.compile(r"在招\s*\d+\s*个职位")
_RE_COMPANY = re.compile(r"(有限公司|有限责任公司|集团|研究院|事务所|中心)$")
_RE_SALARY = re.compile(r"\d\s*[-~－]\s*\d.*?(元|万)")
_RE_EXP = re.compile(r"^(经验不限|无经验|应届生?|在校/应届|\d+\s*年以内|\d+\s*[-~]\s*\d+\s*年|\d+\s*年以上)$")
_RE_EDU = re.compile(r"^(初中|高中|中专|中技|大专|本科|硕士|博士|学历不限|MBA|EMBA)$")
_ANCHOR_BUTTONS = ("立即投递", "先聊聊")
# 详情页底部/导航类文字，取公司名时一律跳过
_SKIP = {
    "先聊聊", "立即投递", "公司信息", "职位描述", "猜你想问", "快聘榜",
    "公司问答", "查看更多", "展开", "举报", "收藏", "分享", "岗位职责", "任职要求",
}


def texts_of(nodes: list[dict]) -> list[str]:
    return [n["text"] for n in nodes if n["text"]]


def wait_anchor(adb_path: str, serial: str | None,
                timeout: float = 15.0, interval: float = 1.2,
                cancel=None) -> list[dict] | None:
    """等到详情页真正渲染出来（出现「立即投递/先聊聊」或一条超长 JD），再返回节点。

    cancel 一返回 True 就立刻放弃等待，别让「停止」按钮卡在这里。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancel and cancel():
            return None
        try:
            nodes = parse_nodes(dump_xml(adb_path, serial, attempts=1))
        except Exception:  # noqa: BLE001 - 还没渲染好，继续等
            nodes = []
        if nodes:
            ts = texts_of(nodes)
            if any(b in ts for b in _ANCHOR_BUTTONS) or any(len(t) > 200 for t in ts):
                return nodes
        try:
            from job_agent import humanize as H
            H._status(f"打开详情页，还剩 {max(1, int(deadline - time.time()))}s")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(interval)
    return None


def extract(nodes: list[dict]) -> dict:
    """从详情页节点里抽字段。

    实测结构（1080x1920 竖屏）：
        [最上面]        岗位名
        [岗位名下]      薪资
        ...             经验 / 学历 / 工作地点：xx区 · xx
        [· 公司名]      HR 卡片，注意带前导「· 」
        职位描述 / 标签 / **JD 全文（一个节点，可能上千字）**
        猜你想问 ...
        公司信息 / 公司全名 / 性质·规模·行业 / 城市 / 在招N个职位
        先聊聊 / 立即投递

    所以全部用「位置关系」取，不用正则猜结尾——公司名不一定带「有限公司」。
    """
    ts = [n["text"] for n in nodes if n["text"]]
    jd = max(ts, key=len) if ts else ""

    # 岗位名 = 纵坐标最靠上的那条文字
    top = min((n for n in nodes if n["text"]), key=lambda n: n["bounds"][1], default=None)
    title = top["text"] if top else ""

    salary = next((t for t in ts if _RE_SALARY.search(t) and len(t) <= 24), "")
    if not salary and top:
        # 兜底：岗位名正下方那一行，通常是薪资（含「面议」「元/天」这类写法）
        below = sorted(
            (n for n in nodes if n["text"] and n["bounds"][1] > top["bounds"][3]),
            key=lambda n: n["bounds"][1],
        )
        for n in below[:2]:
            t = n["text"]
            if len(t) <= 20 and any(k in t for k in ("元", "万", "面议", "薪", "K", "k")):
                salary = t
                break
    location = next((t for t in ts if t.startswith("工作地点")), "")
    exp = next((t for t in ts if _RE_EXP.fullmatch(t)), "")
    edu = next((t for t in ts if _RE_EDU.fullmatch(t)), "")

    # 公司四要素：全部锚在「公司信息」之后，避免命中上方 HR 卡片里的 · 公司名
    company_full = company_meta = city = hiring = ""
    if "公司信息" in ts:
        tail = ts[ts.index("公司信息") + 1:]
        company_full = next(
            (t for t in tail
             if t not in _SKIP and len(t) > 2 and "·" not in t
             and "?" not in t and "？" not in t
             and not _RE_HIRING.search(t)),
            "",
        )
        company_meta = next((t for t in tail if "·" in t and "人" in t), "")
        if company_meta in tail:
            after = tail[tail.index(company_meta) + 1:]
            city = next((t for t in after if 1 <= len(t) <= 6 and "·" not in t
                         and t not in _SKIP and not _RE_HIRING.search(t)), "")
        hiring = next((t for t in tail if _RE_HIRING.search(t)), "")

    # 兜底：有些岗位没有「公司信息」区块，公司名只能从 HR 卡片那句「· xxx公司」拿
    if not company_full:
        hr_company = next((t for t in ts if t.strip().startswith("·")), "")
        company_full = hr_company.strip().lstrip("·").strip()

    return {
        "title": title,
        "jd": jd,
        "jdLength": len(jd),
        "salary": salary,
        "location": location,
        "experience": exp,
        "education": edu,
        "companyFull": company_full,
        "companyMeta": company_meta,
        "city": city,
        "hiringCount": _RE_HIRING.search(hiring).group(0) if hiring else "",
        "nodeCount": len(nodes),
    }


def back(adb_path: str, serial: str | None) -> None:
    adb("shell", "input", "keyevent", "KEYCODE_BACK", adb_path=adb_path, serial=serial)


def tap(adb_path: str, serial: str | None, x: int, y: int) -> None:
    adb("shell", "input", "tap", str(x), str(y), adb_path=adb_path, serial=serial)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="enrich", description="点进详情页抓 JD 全文")
    ap.add_argument("--adb", default=DEFAULT_ADB)
    ap.add_argument("--serial", default=None)
    ap.add_argument("--from-list", help="harvest.py 产出的列表 JSON")
    ap.add_argument("--top", type=int, default=3, help="只测前几条")
    ap.add_argument("--inspect", action="store_true", help="只解析当前页面，不点任何东西")
    ap.add_argument("--json", help="结果写到这个文件")
    args = ap.parse_args(argv)

    if args.inspect:
        nodes = parse_nodes(dump_xml(args.adb, args.serial))
        rec = extract(nodes)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return 0

    if not args.from_list:
        ap.error("要么给 --from-list，要么用 --inspect")

    with open(args.from_list, encoding="utf-8") as f:
        listing = json.load(f)
    items = listing["items"][: args.top] if args.top else listing["items"]
    print(f"列表共 {len(listing['items'])} 条，本次测 {len(items)} 条\n", flush=True)

    out = []
    for i, it in enumerate(items, 1):
        x, y = it["tap"]
        print(f"[{i}/{len(items)}] 点进：{it['company']} / {it['title']}", flush=True)
        tap(args.adb, args.serial, x, y)
        nodes = wait_anchor(args.adb, args.serial)
        if not nodes:
            print("    ✗ 15 秒没等到详情页锚点，跳过\n", flush=True)
            back(args.adb, args.serial)
            time.sleep(2.0)
            continue
        rec = extract(nodes)
        rec["fromList"] = {
            k: it.get(k) for k in ("company", "title", "salary", "area", "tags")
        }
        out.append(rec)
        print(f"    ✓ {rec['title']}", flush=True)
        print(f"      薪资：{rec['salary'] or '(无)'}  "
              f"经验：{rec['experience'] or '(无)'}  "
              f"学历：{rec['education'] or '(无)'}", flush=True)
        print(f"      公司：{rec['companyFull'] or '(未取到)'}  "
              f"{rec['companyMeta']}  城市：{rec['city'] or '(无)'}  {rec['hiringCount']}", flush=True)
        print(f"      地点：{rec['location'] or '(无)'}", flush=True)
        print(f"      JD：{rec['jdLength']} 字符  节点数：{rec['nodeCount']}", flush=True)
        print(f"      JD 开头：{rec['jd'][:80]}\n", flush=True)
        back(args.adb, args.serial)
        time.sleep(2.2)

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"count": len(out), "items": out}, f, ensure_ascii=False, indent=2)
        print(f"wrote {args.json}")
    return 0 if out else 2


if __name__ == "__main__":
    sys.exit(main())
