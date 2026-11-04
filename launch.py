# -*- coding: utf-8 -*-
"""打包入口：双击 JobAgent.exe 走这里。

只做一件事：把工作目录切到 exe 所在目录（这样 config.json / data / logs
都跟着程序走），然后交给 job_agent.ui.app。
"""

import os
import sys


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    sys.path.insert(0, _base_dir())
    from job_agent.ui import app

    app.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
