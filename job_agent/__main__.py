# -*- coding: utf-8 -*-
"""让 `python -m job_agent ...` 可用。"""

import sys

from job_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
