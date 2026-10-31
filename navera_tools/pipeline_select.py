#!/usr/bin/env python3
"""pipeline_select.py — NAVERA picks its vision pipeline by itself: day, night or celestial.

Run by navera-pipeline-select.service (root: it starts and stops the pipeline units). Every
NAVERA_PIPELINE_CHECK_S seconds (default 60) it looks at:
  - the sun: its elevation at the vehicle's position (the operator view's last position;
    NAVERA always starts with GPS; the last one is kept for a reboot; before any, the centre of
    the downloaded satellite map) and the box clock;
  - the cameras plugged in and their roles (navera-discover / navera-hotplug, or navera.env):
    day (ground, colour), thermal (ground) and star (looking up, NAVERA_STAR_CAMERA_*).
and chooses:
  sun above -3 deg (day)          day camera -> day     | else thermal -> night
  sun -3 .. -12 deg (twilight)    thermal -> night      | else day camera -> day
  sun below -12 deg (dark)        thermal -> night      | else star camera -> celestial | else day
  no camera yet                   by the sun alone: day, or night after dusk (the pipeline waits
                                  for its camera; one plugged in later is used at once)
A new choice must hold for NAVERA_PIPELINE_HOLD checks in a row (default 3) and is never applied
while the vehicle flies (the web page's in-flight rule): a switch stops the running pipeline. The
first choice after boot applies at once. A pipeline that fails to start is replaced by the one
that ran before.
NAVERA_PIPELINE_MODE=day|night|cn forces one pipeline; auto (default) chooses.
The running pipeline goes to /var/lib/navera/pipeline.env (NAVERA_PIPELINE_ACTIVE: the web page
follows it; navera-web is restarted on a switch) and, with the reason, to
/var/lib/navera/pipeline.json (the dashboard shows it).

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
WEB_UNIT = "navera-web.service"
WRITTEN_ENV = ("/etc/navera/navera.env", "/var/lib/navera/settings.env")    # written by people
FOUND_ENV = "/var/lib/navera/discovered.env"                                 # written by discovery
STATE = "/var/lib/navera/pipeline.json"
ACTIVE_ENV = "/var/lib/navera/pipeline.env"
SUN_DAY_DEG = -3.0
SUN_DARK_DEG = -12.0
POSITION_MAX_AGE_S = 7 * 86400          # a stored position older than this is not trusted
CAMERA_KEYS = ("DEVICE", "TOPIC", "GST_PIPELINE", "NAME")
ROLE_PREFIX = {"day": "NAVERA_CAMERA_", "thermal": "NAVERA_THERMAL_CAMERA_", "star": "NAVERA_STAR_CAMERA_"}


def read_env(paths) -> dict:
    """The settings of these files, later files overriding earlier ones (as the units load them)."""
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


def _device_gone(value: str) -> bool:
    """A /dev path that no longer exists (camera unplugged since discovery)."""
    return value.startswith("/dev/") and not os.path.exists(value)


def cameras(written: dict, found: dict) -> dict:
    """{"day", "thermal", "star": bool}: the camera roles that have a camera now.

    A role counts when a person chose its input (NAVERA_<ROLE>INPUT other than auto/none, e.g.
    csi or ros with their default device), or when a camera is named for it (device, topic,
    stream, name) in the settings or by discovery — unless its /dev device is gone. Discovery
    writes NAVERA_CAMERA_INPUT=usb even when it found no camera: an input alone from discovery
    does not count. The Insta360 kit is a day (ground) camera.
    """
    env = dict(found, **written)
    out = {}
    for role, pre in ROLE_PREFIX.items():
        dev = env.get(pre + "DEVICE", "")
        if dev and _device_gone(dev):
            out[role] = False
            continue
        chosen = written.get(pre + "INPUT", "").lower() not in ("", "auto", "none", "off")
        out[role] = chosen or any(env.get(pre + k) for k in CAMERA_KEYS)
    if env.get("NAVERA_CAMERA_INPUT", "").lower() == "insta360":
        out["day"] = True
    return out


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
        return forced, f"forced in the settings (NAVERA_PIPELINE_MODE={forced})"
    if not any(cams.values()):
        if sun_deg is None:
            return "day", "no camera found yet"
        return ("day", f"daylight (sun {sun_deg:+.0f}°), waiting for a camera") if sun_deg > SUN_DAY_DEG else \
               ("night", f"night (sun {sun_deg:+.0f}°), waiting for a thermal camera")
    if sun_deg is None:
        return ("day", "position not known yet, day camera") if cams["day"] else \
               ("night", "position not known yet, thermal camera") if cams["thermal"] else \
               ("cn", "position not known yet, star camera only")
    s = f"sun {sun_deg:+.0f}°"
    if sun_deg > SUN_DAY_DEG:
        if cams["day"]:
            return "day", f"daylight ({s}), day camera"
        if cams["thermal"]:
            return "night", f"daylight ({s}), thermal camera only"
        return "day", f"daylight ({s}), star camera only: no ground view"
    if cams["thermal"]:
        return "night", f"{'twilight' if sun_deg > SUN_DARK_DEG else 'night'} ({s}), thermal camera"
    if sun_deg <= SUN_DARK_DEG and cams["star"]:
        return "cn", f"night ({s}), stars visible, star camera"
    if cams["day"]:
        return "day", f"{'twilight' if sun_deg > SUN_DARK_DEG else 'night'} ({s}), day camera only"
    return "cn", f"twilight ({s}), star camera only"


def valid_pos(lat, lon):
    """(lat, lon) as floats if they are a real position, else None."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or (lat, lon) == (0.0, 0.0):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _get_json(port: str, path: str):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as r:
            d = json.load(r)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def position(port: str):
    """(lat, lon) from the operator view's last real position (not a simulated one), or None."""
    d = _get_json(port, "/api/operator_position")
    if not d or d.get("simulated"):
        return None
    return valid_pos(d.get("lat"), d.get("lon"))


def flying(port: str) -> bool:
    """True when the web page says the vehicle flies (armed or moving): no switch then."""
    d = _get_json(port, "/api/mission/state")
    return bool(d and d.get("in_flight_refusal"))


def map_centre(mbtiles: str):
    """(lat, lon) of the downloaded satellite map's centre (MBTiles metadata), or None."""
    import sqlite3
    if not mbtiles or not os.path.isfile(mbtiles):
        return None
    try:
        con = sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True, timeout=2)
        try:
            meta = dict(con.execute("SELECT name, value FROM metadata WHERE name IN ('center', 'bounds')"))
        finally:
            con.close()
        if meta.get("center"):
            lon, lat = (float(x) for x in meta["center"].split(",")[:2])
            return valid_pos(lat, lon)
        if meta.get("bounds"):
            w, s, e, n = (float(x) for x in meta["bounds"].split(",")[:4])
            return valid_pos((s + n) / 2, (w + e) / 2)
    except Exception:
        pass
    return None


def stored_position():
    """(position, its time) kept in the state file (for a reboot), if recent enough; (None, 0)."""
    try:
        with open(STATE) as f:
            old = json.load(f)
        t = float(old.get("pos_time") or 0) if isinstance(old, dict) else 0.0
        pos = valid_pos(old.get("lat"), old.get("lon")) if t else None
        return (pos, t) if pos and time.time() - t <= POSITION_MAX_AGE_S else (None, 0.0)
    except (OSError, ValueError, TypeError, AttributeError):
        return None, 0.0


def running() -> list:
    """The pipelines whose unit is active now."""
    return [n for n, u in UNITS.items()
            if subprocess.run(["systemctl", "is-active", "--quiet", u]).returncode == 0]


def start(name: str) -> bool:
    subprocess.run(["systemctl", "start", UNITS[name]], capture_output=True)
    time.sleep(3)
    return subprocess.run(["systemctl", "is-active", "--quiet", UNITS[name]]).returncode == 0


def stop_others(keep: str) -> None:
    for name, unit in UNITS.items():
        if name != keep:
            subprocess.run(["systemctl", "stop", unit], capture_output=True)


def write_active_env(name: str) -> bool:
    """/var/lib/navera/pipeline.env for the web page; True when it changed."""
    text = f"# written by navera-pipeline-select: the pipeline the web page follows\nNAVERA_PIPELINE_ACTIVE={name}\n"
    try:
        with open(ACTIVE_ENV) as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    try:
        with open(ACTIVE_ENV + ".tmp", "w") as f:
            f.write(text)
        os.chmod(ACTIVE_ENV + ".tmp", 0o644)
        os.replace(ACTIVE_ENV + ".tmp", ACTIVE_ENV)
        return True
    except OSError as e:
        print(f"pipeline_select: cannot write {ACTIVE_ENV}: {e}", file=sys.stderr)
        return False


def switch(to: str, prev: str) -> str:
    """Run `to` alone (one vision pipeline at a time: GPU memory); returns what really runs."""
    stop_others(to)
    if start(to):
        return to
    print(f"pipeline_select: {UNITS[to]} did not start", file=sys.stderr, flush=True)
    if prev and prev != to:
        stop_others(prev)
        if start(prev):
            return prev
    return ""


def save(state: dict) -> None:
    try:
        with open(STATE + ".tmp", "w") as f:
            json.dump(state, f)
        os.chmod(STATE + ".tmp", 0o644)
        os.replace(STATE + ".tmp", STATE)
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
    last_pos, pos_time = stored_position()
    while True:
        written, found = read_env(WRITTEN_ENV), read_env((FOUND_ENV,))
        port = written.get("NAVERA_WEB_PORT") or "8181"
        forced = (written.get("NAVERA_PIPELINE_MODE") or "auto").lower()
        if forced not in UNITS and forced != "auto":
            print(f"pipeline_select: NAVERA_PIPELINE_MODE={forced} unknown (day, night, cn or auto): auto",
                  file=sys.stderr)
            forced = "auto"
        pos = position(port)
        if pos:
            last_pos, pos_time = pos, time.time()
        where = last_pos or map_centre(written.get("NAVERA_MBTILES", ""))
        sun = sun_elevation(where[0], where[1], dt.datetime.now(dt.timezone.utc)) if where else None
        cams = cameras(written, found)
        want, why = choose(sun, cams, forced)
        active = running()
        now = active[0] if len(active) == 1 else (want if want in active else (active[0] if active else ""))
        waiting = ""
        if want == now:
            pending, count = None, 0
            if len(active) > 1 and not a.dry_run:
                stop_others(now)                  # a second pipeline left running: one at a time
        else:
            count = count + 1 if want == pending else 1
            pending = want
            due = first or not now or count >= hold_n or forced in UNITS
            if due and now and flying(port):
                due, waiting = False, "waits for the vehicle to land"
            if due:
                print(f"pipeline_select: {now or 'none'} -> {want} ({why})", flush=True)
                if not a.dry_run:
                    now = switch(want, now)
                pending, count = None, 0
        if not a.dry_run and now and write_active_env(now):
            subprocess.run(["systemctl", "try-restart", WEB_UNIT], capture_output=True)   # page follows
        first = False
        state = {"pipeline": now, "chosen": want, "reason": why, "auto": forced not in UNITS,
                 "sun_deg": None if sun is None else round(sun, 1), "cameras": cams,
                 "waiting": waiting, "switch_in_checks": (hold_n - count) if pending else 0,
                 "lat": last_pos[0] if last_pos else None, "lon": last_pos[1] if last_pos else None,
                 "pos_time": pos_time or None, "time": int(time.time())}
        if not a.dry_run:
            save(state)
        if a.once:
            print(json.dumps(dict(state, running=active)))
            return 0
        time.sleep(period)


if __name__ == "__main__":
    raise SystemExit(main())
