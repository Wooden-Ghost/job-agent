# -*- coding: utf-8 -*-
"""智联招聘采集 Agent —— 只做采集，不做判断。

模块划分
    humanize  随机化：等待 / 点击落点 / 滑动（反自动化硬性要求）
    store     SQLite 落地 + 导出 Excel
    flow      页面状态机与采集主流程
    cli       命令行入口

依赖：同级目录下的 harvest.py（列表解析）、enrich.py（详情解析）、公司名规范化.py。
"""

import os
import sys

# 让 `from harvest import ...` 这类同级导入在包内可用
_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

__version__ = "0.1.0"
