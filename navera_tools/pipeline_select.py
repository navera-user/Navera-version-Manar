#!/usr/bin/env python3
"""pipeline_select.py — NAVERA picks its vision pipeline by itself: day, night or celestial.

Run by navera-pipeline-select.service (root: it starts and stops the pipeline units). Every
NAVERA_PIPELINE_CHECK_S seconds (default 60) it looks at:
  - the sun: its elevation at the vehicle's position (the operator view's last position;
    NAVERA always starts with GPS) and the box clock;
  - the cameras: the roles found by navera-discover / navera-hotplug (discovered.env) or
    written in navera.env: day (ground, colour), thermal (ground), star (looking up); the
    Insta360 kit gives both a ground view (day) and a sky view (celestial).
and chooses:
  sun above -3 deg (day)          day camera -> day     | else thermal -> night
  sun -3 .. -12 deg (twilight)    thermal -> night      | else day camera -> day
  sun below -12 deg (dark)        thermal -> night      | else sky view -> celestial | else day
  no camera at all                day (the pipeline waits for a camera; nothing to choose)
A new choice must hold for NAVERA_PIPELINE_HOLD checks in a row (default 3) before NAVERA
switches (no flapping at dusk); the first choice after boot applies at once.
NAVERA_PIPELINE=day|night|cn forces one pipeline; auto (default) chooses.
The choice and its reason go to /var/lib/navera/pipeline.json (the dashboard shows them).

    python3 navera_tools/pipeline_select.py --once --dry-run    # print the choice, change nothing
"""
import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
import urllib.request

UNITS = {"day": "navera-pipeline-day.service", "night": "navera-pipeline-night.service",
         "cn": "navera-pipeline-cn.service"}
ENV_FILES = ("/etc/navera/navera.env", "/var/lib/navera/settings.env", "/var/lib/navera/discovered.env")
STATE = "/var/lib/navera/pipeline.json"
SUN_DAY_DEG = -3.0
SUN_DARK_DEG = -12.0


def read_env(paths=ENV_FILES) -> dict:
    """The NAVERA settings, later files overriding earlier ones (as the units load them)."""
    env = {}
    for p in paths:
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    return env


def cameras(env: dict) -> dict:
    """{"day": bool, "thermal": bool, "star": bool} from the camera roles."""
    def has(pre):
        return any(env.get(pre + k) for k in ("DEVICE", "TOPIC", "GST_PIPELINE", "NAME"))
    kit = env.get("NAVERA_CAMERA_INPUT", "").lower() == "insta360"
    return {"day": kit or has("NAVERA_CAMERA_"), "thermal": has("NAVERA_THERMAL_CAMERA_"),
            "star": kit or has("NAVERA_STAR_CAMERA_")}


def sun_elevation(lat: float, lon: float, when: dt.datetime) -> float:
    """Sun elevation in degrees (NOAA approximation, within ~0.5 deg: enough to tell day from night)."""
    when = when.astimezone(dt.timezone.utc)
    doy = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60 + when.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    tst = hour * 60 + eqt + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cz))))


def choose(sun_deg, cams: dict, forced: str = "auto"):
    """(pipeline, reason). sun_deg None = unknown position: daylight rules if a day camera, else night."""
    if forced in UNITS:
        return forced, f"forced in the settings (NAVERA_PIPELINE={forced})"
    if not any(cams.values()):
        return "day", "no camera found yet"
    if sun_deg is None:
        return ("day", "position not known yet, day camera") if cams["day"] else \
               ("night", "position not known yet, thermal camera") if cams["thermal"] else \
               ("cn", "position not known yet, sky camera only")
    s = f"sun {sun_deg:+.0f}°"
    if sun_deg > SUN_DAY_DEG:
        if cams["day"]:
            return "day", f"daylight ({s}), day camera"
        if cams["thermal"]:
            return "night", f"daylight ({s}), thermal camera only"
        return "day", f"daylight ({s}), sky camera only: no ground view"
    if cams["thermal"]:
        return "night", f"{'twilight' if sun_deg > SUN_DARK_DEG else 'night'} ({s}), thermal camera"
    if sun_deg <= SUN_DARK_DEG and cams["star"]:
        return "cn", f"night ({s}), stars visible, sky camera"
    if cams["day"]:
        return "day", f"{'twilight' if sun_deg > SUN_DARK_DEG else 'night'} ({s}), day camera only"
    return "cn", f"twilight ({s}), sky camera only"


def position(port: str):
    """(lat, lon) from the operator view's last position, or None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/operator_position", timeout=3) as r:
            d = json.load(r)
        lat, lon = float(d.get("lat")), float(d.get("lon"))
        if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0):
            return lat, lon
    except Exception:
        pass
    return None


def active() -> str:
    for name, unit in UNITS.items():
        if subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0:
            return name
    return ""


def switch(to: str, dry: bool) -> None:
    """Start the chosen pipeline, stop the others (one vision pipeline at a time: GPU memory)."""
    if dry:
        return
    for name, unit in UNITS.items():
        if name != to:
            subprocess.run(["systemctl", "stop", unit], capture_output=True)
    subprocess.run(["systemctl", "start", UNITS[to]], capture_output=True)


def save(state: dict) -> None:
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, STATE)
    except OSError as e:
        print(f"pipeline_select: cannot write {STATE}: {e}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true", help="decide once and exit")
    ap.add_argument("--dry-run", action="store_true", help="print the choice; start or stop nothing")
    a = ap.parse_args(argv)
    hold_n = max(1, int(os.environ.get("NAVERA_PIPELINE_HOLD", "3") or 3))
    period = max(10, int(os.environ.get("NAVERA_PIPELINE_CHECK_S", "60") or 60))
    pending, count, first = None, 0, True
    last_pos = None
    try:                                     # the last known position survives a reboot
        with open(STATE) as f:
            old = json.load(f)
        if old.get("lat") is not None:
            last_pos = (float(old["lat"]), float(old["lon"]))
    except (OSError, ValueError, TypeError):
        pass
    while True:
        env = read_env()
        forced = (env.get("NAVERA_PIPELINE") or "auto").lower()
        pos = position(env.get("NAVERA_WEB_PORT") or "8181") or last_pos
        last_pos = pos or last_pos
        sun = sun_elevation(pos[0], pos[1], dt.datetime.now(dt.timezone.utc)) if pos else None
        cams = cameras(env)
        want, why = choose(sun, cams, forced)
        now = active()
        if want == now:
            pending, count = None, 0
        else:
            count = count + 1 if want == pending else 1
            pending = want
            if first or count >= hold_n or forced in UNITS:
                print(f"pipeline_select: {now or 'none'} -> {want} ({why})", flush=True)
                switch(want, a.dry_run)
                now, pending, count = want, None, 0
        first = False
        if not a.dry_run:
            save({"pipeline": now or want, "chosen": want, "reason": why, "auto": forced not in UNITS,
                  "sun_deg": None if sun is None else round(sun, 1), "cameras": cams,
                  "lat": pos[0] if pos else None, "lon": pos[1] if pos else None,
                  "switch_in_checks": (hold_n - count) if pending else 0, "time": int(time.time())})
        if a.once:
            print(json.dumps({"chosen": want, "reason": why, "sun_deg": sun, "cameras": cams, "active": now}))
            return 0
        time.sleep(period)


if __name__ == "__main__":
    raise SystemExit(main())
