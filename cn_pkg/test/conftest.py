"""Test THIS checkout's cn_pkg (and its navera_tools simulator), not an installed copy that a sourced
install/setup.bash may put first on the path."""
import os
import sys

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.dirname(_PKG), _PKG):            # repository root (navera_tools), then cn_pkg
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
