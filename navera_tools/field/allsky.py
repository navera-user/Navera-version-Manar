"""The field tools' name for cn_pkg.allsky: the 360 solver lives in the flight package (cn_pkg) and is shared,
not copied. This module IS cn_pkg.allsky (the same module object), so a live knob the field server sets here
(server.LIVE_PARAMS, e.g. allsky.MAX_RMS_DEG or sky360.LENS_FILE) is the value the solver uses."""
import sys

from cn_pkg import allsky as _shared

sys.modules[__name__] = _shared
# a copy loaded by file path (celestial360_conditions --solver FILE) still gets every name
globals().update({k: v for k, v in vars(_shared).items() if not k.startswith("__")})
