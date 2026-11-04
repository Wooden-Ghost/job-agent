# -*- coding: utf-8 -*-
"""公司名 / 岗位名规范化 —— 只用于比对，不用于展示。

规则（2026-11-03 与陈柏安确认）：
- 去掉工商后缀：股份有限公司 / 有限责任公司 / 集团有限公司 / 有限公司 / 分公司
- 全角括号、全角空格 → 半角（unicodedata NFKC）
- 去掉所有空白与间隔号
- 去掉「(孪生公司，同上）」这类人工备注
- **保留城市前缀**，绝不删 —— 防「成都鸿达方略」与「鸿达方略(北京)」被误判为同一家

对外只暴露 normalize_company() / normalize_title() / fingerprint()。
判断（要不要复用、要不要背调）不在这个文件里做。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# 长后缀必须排在短后缀之前，否则「股份有限公司」会被「有限公司」先吃掉
_SUFFIXES: tuple[str, ...] = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "控股有限公司",
    "分公司",
    "有限公司",
)

# 人工备注式的括号内容：(孪生公司，同上）(疑似同一家) 等，不应参与比对
_PAREN_NOTE = re.compile(r"\([^()]*(?:孪生|同上|疑似|等同|同一家)[^()]*\)")

_WS = re.compile(r"[\s\u3000\u00b7\u30fb\u2022]+")


def normalize_company(name: str | None) -> str:
    """返回用于比对的公司名。空值返回空串。"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).strip()
    s = _PAREN_NOTE.sub("", s)
    s = _WS.sub("", s)
    for suf in _SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    # 只去两端空白：不要 strip 括号，否则「宏碁(重庆)」会被啃成「宏碁(重庆」
    return s.strip()


def normalize_title(title: str | None) -> str:
    """岗位名只做轻规范化。不做同义词合并 —— 合并会把「数据分析」和「数据分析师」搞混。"""
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", str(title)).strip().lower()
    s = _WS.sub("", s)
    return s


def fingerprint(company: str | None, title: str | None) -> str:
    """同一个「公司 + 岗位」组合的稳定指纹，用于拦重复刷到同一个岗。"""
    raw = f"{normalize_company(company)}|{normalize_title(title)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":  # 手工核对用
    import sys

    for arg in sys.argv[1:]:
        print(f"{arg!r}\n  company -> {normalize_company(arg)!r}\n  title   -> {normalize_title(arg)!r}")
