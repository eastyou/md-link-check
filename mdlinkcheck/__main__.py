"""支持 ``python -m mdlinkcheck`` 运行。"""

import sys

from mdlinkcheck.cli import main

if __name__ == "__main__":
    sys.exit(main())
