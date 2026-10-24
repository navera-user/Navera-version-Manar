"""Small facts NAVERA must remember across a restart of its services (in flight too).

A service restarted in the air (watchdog, crash, power blip) must not start from
scratch: the ground altitude taken at power-on and the last position it was sure of
are written here and read back if still recent. One JSON file per fact, replaced
atomically and durably (temp + fsync + rename: a power cut leaves the old or the new
file, never a cut one; a damaged file reads as "nothing saved"), in
NAVERA_STATE_DIR (default /var/lib/navera, else ~/.local/state/navera).
"""
import json
import os
import time
from typing import Optional

from navera_common.atomic_io import atomic_write, read_json


def state_dir() -> str:
    d = os.environ.get("NAVERA_STATE_DIR")
    if d:
        return d
    if os.access("/var/lib/navera", os.W_OK):
        return "/var/lib/navera"
    return os.path.join(os.path.expanduser("~"), ".local", "state", "navera")


def save(name: str, data: dict, directory: Optional[str] = None) -> bool:
    """Write {..data, saved_at}; False (never raises) when the disk refuses."""
    d = directory or state_dir()
    path = os.path.join(d, f"{name}.json")
    try:
        os.makedirs(d, exist_ok=True)
        atomic_write(path, json.dumps(dict(data, saved_at=time.time())))   # temp + fsync + rename
        return True
    except (OSError, TypeError, ValueError):
        return False


def load(name: str, max_age_s: float, directory: Optional[str] = None) -> Optional[dict]:
    """The saved fact if written less than max_age_s ago (and not in the future), else None."""
    path = os.path.join(directory or state_dir(), f"{name}.json")
    data = read_json(path)                  # truncated / zero-filled / not a dict: None
    if data is None:
        return None
    try:
        age = time.time() - float(data["saved_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return data if 0.0 <= age <= max_age_s else None
