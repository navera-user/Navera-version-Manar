"""scenarios.py — seven GPS attacks, as lists of timed fixes (you don't need to change this file).

The vehicle flies east at 15 m/s from (0, 0). Positions are metres (x east, y north).
Each step is (t, kind, x, y, sigma, gps_offset_m):
    kind "gps"     a GPS fix (one per second); gps_offset_m = how far the spoofer put it
    kind "vision"  an independent vision fix (every 2 s) at the TRUE position + a little
                   noise; sigma = the accuracy vision STATES (15 m), or None = unknown
"""
import math

SPEED = 15.0
NAMES = ["jump", "patient", "patient_vision", "drift", "drift_novision", "jamspoof", "jamspoof_novision"]
DESCRIPTION = {
    "jump": "a spoofer takes over: GPS jumps 2 km north for 30 s (no vision)",
    "patient": "the same 2 km spoof, but the spoofer stays 100 s (no vision)",
    "patient_vision": "the patient 2 km spoof, with vision stating 15 m",
    "drift": "GPS pulled north slowly, 4 m/s, with vision stating 15 m",
    "drift_novision": "the same slow drift, vision of UNKNOWN accuracy",
    "jamspoof": "GPS jammed 80 s, then back 2 km off (spoofed), then true — with vision 15 m",
    "jamspoof_novision": "jam then spoof, vision of UNKNOWN accuracy",
}
MAX_SPEED = {n: 30.0 for n in NAMES}


def _noise(t, k):
    """Small deterministic 'noise' (metres) so that every run is the same."""
    return 2.0 * math.sin(0.7 * t + k) + 1.0 * math.sin(2.3 * t + 3 * k)


def _truth(t):
    return SPEED * t, 0.0


def _steps(end, offset_at, gps_on=lambda t: True, vision_sigma=15.0):
    out = []
    for i in range(int(end) + 1):
        t = float(i)
        x, y = _truth(t)
        if i % 2 == 0:
            out.append((t - 0.01, "vision", x + 4 * _noise(t, 1), y + 4 * _noise(t, 2), vision_sigma, 0.0))
        if gps_on(t):
            off = offset_at(t)
            out.append((t, "gps", x + _noise(t, 3), y + off + _noise(t, 4), None, off))
    return out


def build(name):
    if name == "jump":
        return _steps(60, lambda t: 2000.0 if 20 <= t < 50 else 0.0, vision_sigma=None)
    if name == "patient":
        return _steps(140, lambda t: 2000.0 if 20 <= t < 120 else 0.0, vision_sigma=None)
    if name == "patient_vision":
        return _steps(140, lambda t: 2000.0 if 20 <= t < 120 else 0.0)
    if name in ("drift", "drift_novision"):
        sig = 15.0 if name == "drift" else None
        return _steps(100, lambda t: 4.0 * (t - 10) if 10 <= t < 80 else 0.0, vision_sigma=sig)
    if name in ("jamspoof", "jamspoof_novision"):
        sig = 15.0 if name == "jamspoof" else None
        return _steps(140, lambda t: 2000.0 if 100 <= t < 120 else 0.0,
                      gps_on=lambda t: not (20 <= t < 100), vision_sigma=sig)
    raise ValueError(f"unknown scenario {name}")
