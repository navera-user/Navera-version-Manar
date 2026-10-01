"""Mission preparation on the NAVERA box: vehicle settings, route, satellite map.

Used by the box's web service (navera_web_bridge, page /mission). No ROS here.

* Settings — the values an operator sets from the web page live in their own
  file, SETTINGS_FILE (default /var/lib/navera/settings.env), owned by the
  service user and loaded by every NAVERA unit AFTER /etc/navera/navera.env
  (systemd EnvironmentFile=-...), so they override it. Only the keys in
  SETTINGS are accepted, each validated; the file is replaced atomically.
* Route — from the autopilot's mission file (Mission Planner / QGC WPL 110
  ".waypoints", QGroundControl ".plan") or drawn on the map, split into
  <= 10 km great-circle legs (the map corridor follows what is flown).
* Map — prepare_area.py builds the area (corridor tiles from the onboard
  MBTiles, downloaded ones when a tile URL is configured, DINOv2 descriptors);
  "activate" points DAY_DATASET_DIR at it and restarts the day pipeline.
"""
import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Dict, List, Optional

from day_pkg.prepare_area import densify_route, plan_tiles, route_length_m

SETTINGS_FILE = os.environ.get("NAVERA_SETTINGS_FILE", "/var/lib/navera/settings.env")
BUFFER_M = 1000.0
DISK_MARGIN_MB = 2048.0
TILE_KB, DESC_KB = 20.0, 3.0
VEHICLE_TYPES = ("drone", "plane", "boat", "robot", "other")


def _num(lo, hi):
    def check(v):
        x = float(v)
        if not (math.isfinite(x) and lo <= x <= hi):
            raise ValueError(f"must be between {lo:g} and {hi:g}")
        return f"{x:g}"
    return check


def _rpy(v):
    parts = [p.strip() for p in str(v).split(",")]
    if len(parts) != 3:
        raise ValueError("must be roll,pitch,yaw in degrees")
    return ",".join(_num(-180, 180)(p) for p in parts)


def _vehicle(v):
    if str(v) not in VEHICLE_TYPES:
        raise ValueError(f"must be one of {', '.join(VEHICLE_TYPES)}")
    return str(v)


# key -> (validator, what it is). Empty value = remove the key (back to navera.env).
SETTINGS = {
    "NAVERA_VEHICLE_TYPE": (_vehicle, "vehicle type (label)"),
    "NAVERA_MAX_SPEED_KMH": (_num(4, 1890), "vehicle maximum speed, km/h"),
    "NAVERA_THERMAL_HFOV_DEG": (_num(5, 180), "thermal camera horizontal field of view, deg"),
    "NAVERA_DAY_HFOV_DEG": (_num(5, 180), "day camera horizontal field of view, deg"),
    "NAVERA_IMU_MOUNT_RPY": (_rpy, "IMU mounting roll,pitch,yaw, deg"),
    "NAVERA_DECLINATION_DEG": (_num(-90, 90), "magnetic declination until a position is known, deg"),
}
# Set by "activate", never typed by the operator.
INTERNAL = ("DAY_DATASET_DIR",)


def read_settings(path: str = SETTINGS_FILE) -> Dict[str, str]:
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k in SETTINGS or k in INTERNAL:
                        out[k] = v
    except FileNotFoundError:
        pass
    return out


def validate_settings(changes: Dict[str, object]) -> Dict[str, Optional[str]]:
    """{key: normalised value or None (= remove)}; raises ValueError naming the key."""
    out = {}
    for k, v in changes.items():
        if k not in SETTINGS:
            raise ValueError(f"{k}: not a setting of the web page")
        if v is None or str(v).strip() == "":
            out[k] = None
            continue
        try:
            out[k] = SETTINGS[k][0](v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"{k}: {e}") from None
    return out


def write_settings(changes: Dict[str, Optional[str]], path: str = SETTINGS_FILE) -> Dict[str, str]:
    """Apply validated changes (None removes a key); atomic replace. Returns the new settings."""
    cur = read_settings(path)
    for k, v in changes.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = v
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write("# NAVERA settings written by the box's web page (/mission).\n"
                "# Loaded after /etc/navera/navera.env, which they override. Do not edit by hand\n"
                "# while the web service runs.\n")
        for k in sorted(cur):
            f.write(f"{k}={cur[k]}\n")
    os.replace(tmp, path)
    return cur


# ── autopilot mission files ─────────────────────────────────────────────────
# MAV_CMDs whose latitude/longitude are a point the vehicle flies over.
_NAV_CMDS = {16, 17, 18, 19, 21, 22, 31, 82, 84, 85}   # waypoint, loiters, land, takeoff, spline, VTOL


def _valid(lat, lon):
    return math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180 \
        and not (lat == 0.0 and lon == 0.0)


def parse_mission(text: str) -> List[List[float]]:
    """Waypoints [[lat, lon], ...] of a Mission Planner / QGC mission file.

    Accepts "QGC WPL 110" text (.waypoints; the first row is the home position)
    and QGroundControl ".plan" JSON (mission.plannedHomePosition + items,
    including complex items' flown points when present). Raises ValueError."""
    text = text.strip()
    pts: List[List[float]] = []
    if text.startswith("QGC WPL"):
        for n, line in enumerate(text.splitlines()[1:], start=2):
            f = line.split("\t") if "\t" in line else line.split()
            if not f:
                continue
            if len(f) < 12:
                raise ValueError(f"line {n}: 12 fields expected")
            cmd, lat, lon = int(float(f[3])), float(f[8]), float(f[9])
            if (cmd in _NAV_CMDS or n == 2) and _valid(lat, lon):
                pts.append([lat, lon])
    elif text.startswith("{"):
        try:
            plan = json.loads(text)
            mission = plan["mission"]
        except (ValueError, KeyError, TypeError):
            raise ValueError("not a QGroundControl .plan file") from None
        home = mission.get("plannedHomePosition") or []
        if len(home) >= 2 and _valid(float(home[0]), float(home[1])):
            pts.append([float(home[0]), float(home[1])])
        for it in mission.get("items", []):
            if it.get("type") == "SimpleItem":
                p = it.get("params") or []
                if int(it.get("command", 0)) in _NAV_CMDS and len(p) >= 6 \
                        and p[4] is not None and p[5] is not None and _valid(float(p[4]), float(p[5])):
                    pts.append([float(p[4]), float(p[5])])
            else:                                         # survey / corridor scan
                for c in (it.get("TransectStyleComplexItem") or {}).get("VisualTransectPoints", []):
                    if len(c) >= 2 and _valid(float(c[0]), float(c[1])):
                        pts.append([float(c[0]), float(c[1])])
    else:
        raise ValueError("unknown mission file: expected 'QGC WPL 110' (.waypoints) or a .plan")
    # consecutive duplicates (e.g. takeoff at home) add nothing to the corridor
    route = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(route) < 2:
        raise ValueError("the mission has fewer than two positions")
    return route


# ── areas (satellite map of a route) ─────────────────────────────────────────
def area_id(route) -> str:
    legs = densify_route(route)
    key = json.dumps([[round(a, 5), round(b, 5)] for a, b in legs] + [BUFFER_M])
    return hashlib.sha1(key.encode()).hexdigest()[:12]


class AreaJobs:
    """Plans and prepares the areas of routes on the box; one preparation at a time."""

    def __init__(self, areas_dir: str, mbtiles: str, tile_url: str = "", cache: str = "",
                 prepare_cmd: Optional[List[str]] = None,
                 restart_cmd: Optional[List[str]] = None,
                 settings_file: str = SETTINGS_FILE,
                 log: Callable[[str, str], None] = lambda level, text: None):
        self.dir, self.mbtiles, self.tile_url, self.cache = areas_dir, mbtiles, tile_url, cache
        self.prepare_cmd = prepare_cmd or ["ros2", "run", "day_pkg", "prepare_area.py"]
        # allowed by deploy/sudoers/navera-web (exact command)
        self.restart_cmd = restart_cmd or ["sudo", "-n", "/usr/bin/systemctl", "restart",
                                           "navera-pipeline-day.service"]
        self.settings_file, self.log = settings_file, log
        self.lock = threading.Lock()
        self.plans: Dict[str, dict] = {}
        self.job: Optional[dict] = None
        self._proc = None

    def path(self, aid):
        return os.path.join(self.dir, aid)

    def is_prepared(self, aid):
        return os.path.exists(os.path.join(self.path(aid), "descriptors_cache.npz"))

    def plan(self, route) -> dict:
        legs = densify_route([[float(a), float(b)] for a, b in route])
        aid = area_id(legs)
        p = plan_tiles(self.mbtiles, legs, BUFFER_M, 17, self.cache or None)
        need_mb = ((len(p["missing"]) + len(p["needed"])) * TILE_KB + len(p["needed"]) * DESC_KB) / 1024.0
        os.makedirs(self.dir, exist_ok=True)
        free_mb = shutil.disk_usage(self.dir).free / 2 ** 20
        plan = dict(id=aid, route=legs, length_m=route_length_m(legs), tiles=len(p["needed"]),
                    in_base=p["in_base"], in_cache=p["in_cache"], missing_n=len(p["missing"]),
                    can_download=bool(self.tile_url), need_mb=need_mb, free_mb=free_mb,
                    no_space=need_mb + DISK_MARGIN_MB > free_mb, prepared=self.is_prepared(aid),
                    active=self.active_dir() == self.path(aid))
        with self.lock:
            self.plans[aid] = plan
        return plan

    def active_dir(self) -> str:
        return read_settings(self.settings_file).get("DAY_DATASET_DIR") or os.environ.get("DAY_DATASET_DIR", "")

    def start(self, aid: str) -> None:
        with self.lock:
            plan = self.plans.get(aid)
            if plan is None:
                raise ValueError("plan the route first")
            if self._proc and self._proc.poll() is None:
                raise ValueError("a map is already being generated")
            if plan["no_space"]:
                raise ValueError(f"not enough disk space: {plan['need_mb'] / 1024:.1f} GB needed, "
                                 f"{plan['free_mb'] / 1024:.1f} GB free")
            if plan["missing_n"] and not self.tile_url:
                self.log("warn", f"map: {plan['missing_n']} tiles of the route are not in the onboard "
                                 "map and no download source is configured (NAVERA_TILE_URL): "
                                 "vision will have no tiles there")
            cmd = self.prepare_cmd + ["--mbtiles", self.mbtiles, "--out", self.path(aid),
                                      "--buffer-m", str(BUFFER_M)]
            if self.tile_url:
                cmd += ["--fetch-url", self.tile_url] + (["--cache", self.cache] if self.cache else [])
            cmd += ["--route"] + [f"{a},{b}" for a, b in plan["route"]]
            self.job = dict(id=aid, status="running", stage="starting", done=0, total=plan["tiles"],
                            t_start=time.time(), error=None)
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          text=True, start_new_session=True)
        threading.Thread(target=self._read, args=(self._proc, aid), daemon=True).start()
        self.log("info", f"map: generating {plan['tiles']} tiles for a {plan['length_m'] / 1000:.1f} km route")

    def _read(self, proc, aid):
        tail = deque(maxlen=5)
        for line in proc.stdout:
            tail.append(line.strip())
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "stage" in d and d["stage"] != "warning":
                with self.lock:
                    self.job.update(stage=d["stage"], done=d.get("done", 0), total=d.get("total", 0))
        ok = proc.wait() == 0 and self.is_prepared(aid)
        with self.lock:
            self.job.update(status="done" if ok else "failed", error=None if ok else " / ".join(tail))
            if aid in self.plans:
                self.plans[aid]["prepared"] = ok
        self.log("ok" if ok else "error", "map: ready — activate it to use it" if ok
                 else f"map: generation failed ({' / '.join(tail)})")

    def cancel(self) -> bool:
        with self.lock:
            p = self._proc
        if p and p.poll() is None:
            p.terminate()
            return True
        return False

    def activate(self, aid: str) -> None:
        """Point day vision at this area and restart the day pipeline."""
        if not self.is_prepared(aid):
            raise ValueError("this map is not generated yet")
        write_settings({"DAY_DATASET_DIR": self.path(aid)}, self.settings_file)
        r = subprocess.run(self.restart_cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError("map selected, but the day pipeline could not be restarted "
                               f"({(r.stderr or r.stdout).strip()[:200]}) — restart the box")
        self.log("ok", f"map {aid} active: day pipeline restarted")

    def state(self) -> dict:
        with self.lock:
            job = dict(self.job) if self.job else None
        return dict(job=job, active=self.active_dir())
