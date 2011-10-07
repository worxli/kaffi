#-*- coding: utf-8 -*-
from __future__ import absolute_import
import sys
import os, os.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from kaffi import main
    sys.exit(main() or 0)
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(127)
