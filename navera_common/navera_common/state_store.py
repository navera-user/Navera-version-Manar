"""Small facts NAVERA must remember across a restart of its services (in flight too).

A service restarted in the air (watchdog, crash, power blip) must not start from
scratch: the ground altitude taken at power-on and the last position it was sure of
are written here and read back if still recent. One JSON file per fact, replaced
atomically, in NAVERA_STATE_DIR (default /var/lib/navera, else ~/.local/state/navera).
"""
import json
import os
import time
from typing import Optional


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
        tmp = f"{path}.tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(dict(data, saved_at=time.time()), f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def load(name: str, max_age_s: float, directory: Optional[str] = None) -> Optional[dict]:
    """The saved fact if written less than max_age_s ago (and not in the future), else None."""
    path = os.path.join(directory or state_dir(), f"{name}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        age = time.time() - float(data["saved_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return data if 0.0 <= age <= max_age_s else None
