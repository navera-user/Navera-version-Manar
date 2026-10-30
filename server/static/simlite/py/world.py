"""NAVERA Sim Lite — the browser side. The world is NAVERA Lite's own (navera_lite/sim/world.py, mission 31: the
same file as the headless simulator); this module only installs the student's files, builds the judge, adds the
page's needs (a route between two places, faults clicked during the flight, the flight script, a picture for the
map) and never leaves the page dead: a part that is missing or broken flies as the course's (the server chose
which files to send and says why in `parts`).

    REAL  the student's NAVERA Lite: mission 29's judge (Arbiter), mission 30's guard (GuardedArbiter), mission 28's
          Kalman filter in the autopilot, mission 31's decoder when it is written — or the course's parts.
    SIM   the truth, the GPS receiver, the cameras (an error profile: a browser cannot run PyTorch, so "my networks"
          uses the profile vision_check.py measured), the IMU, the autopilot (navera_lite/sim/world.py).
"""
import json
import math
import os
import sys
import traceback

PLACES = {
    "sousse": (35.8256, 10.6360), "sousse medina": (35.8270, 10.6380), "port el kantaoui": (35.8920, 10.5980),
    "monastir": (35.7643, 10.8113), "monastir harbour": (35.7778, 10.8317), "monastir marina": (35.7778, 10.8317),
    "monastir airport": (35.7581, 10.7547), "skanes": (35.7560, 10.7680), "hammam sousse": (35.8606, 10.5944),
    "kantaoui": (35.8920, 10.5980),
}
DEFAULTS = {"gps_timeout_s": 3.0, "day_timeout_s": 5.0, "night_timeout_s": 5.0, "celestial_timeout_s": 45.0,
            "future_tolerance_s": 0.5, "fix_max_sigma_m": 25.0, "min_stated_sigma_m": 0.01, "switch_holdoff_s": 2.0,
            "tick_hz": 5.0, "max_speed_mps": 100.0, "gps_jump_margin_m": 50.0, "vehicle": "drone"}
TOP_SPEED = {"drone": 30.0, "plane": 100.0, "boat": 20.0, "robot": 10.0}      # vehicle.VEHICLES (the jump gate)
PAGE_FAULT = {("camera", "failed"): "blackout", ("imu", "failed"): "off"}      # the page's buttons → the world's modes
SRC = {"gps": "GPS", "day": "DAY VISION", "night": "NIGHT VISION", "celestial": "CELESTIAL"}
ROOT = "/navera_lite_user"
INFO = {"parts": {}, "profile": None, "settings": dict(DEFAULTS)}


def place(where):
    if isinstance(where, (tuple, list)) and len(where) >= 2:
        return float(where[0]), float(where[1])
    key = str(where).strip().lower()
    if key in PLACES:
        return PLACES[key]
    raise ValueError(f"unknown place '{where}': use (lat, lon) or one of {sorted(PLACES)}")


def read_settings(text):
    """navera_lite.yaml's values (a ROS 2 params file: 'key: value  # comment' lines), on top of DEFAULTS. A browser
    has no PyYAML; numbers, true/false and quoted texts are enough for this file."""
    cfg = dict(DEFAULTS)
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        if k not in DEFAULTS or v == "":
            continue
        v = v.strip("\"'")
        try:
            cfg[k] = v if isinstance(DEFAULTS[k], str) else type(DEFAULTS[k])(float(v))
        except ValueError:
            pass
    return cfg


# ---------------------------------------------------------------- loading the student's NAVERA Lite
def install_lite(payload, root=ROOT):
    """payload: {"files": {"navera_lite/arbiter.py": text, …, "navera_lite.yaml": text}, "parts": {part: why},
    "profile": my_vision_profile.json's dict or None}. Writes the files, checks every .py compiles."""
    files = payload.get("files", payload)
    for mod in [m for m in list(sys.modules) if m == "navera_lite" or m.startswith("navera_lite.")]:
        del sys.modules[mod]
    for rel, text in files.items():
        if rel.endswith(".py"):
            try:
                compile(text, rel, "exec")
            except SyntaxError as e:
                raise SyntaxError(f"{rel}, line {e.lineno}: {e.msg}") from None
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    if root not in sys.path:
        sys.path.insert(0, root)
    import importlib
    importlib.invalidate_caches()
    INFO["parts"] = dict(payload.get("parts") or {})
    INFO["profile"] = payload.get("profile")
    INFO["settings"] = read_settings(files.get("navera_lite.yaml", ""))
    import navera_lite.sim.world  # noqa: F401  — fail now (with the student's file and line), not at ▶ Fly


def decoder_ready(out):
    """True when the student's parse_frames and decode_gps_input (mission 31, TODOs 1–2) are written."""
    import inspect
    for name in ("parse_frames", "decode_gps_input"):
        try:
            src = inspect.getsource(getattr(out, name))
        except (OSError, TypeError, AttributeError):
            return False
        if "# TODO: replace this line" in src or "# TODO: write your code" in src or 'NotImplementedError("TODO' in src:
            return False
    return True


def make_world_class():
    from navera_lite.sim import world as W

    class PageWorld(W.World):
        """The world plus what the page draws (sensor points, a trail), the onboard-map rule for day vision, and a
        direct link when the student's decoder is not written yet."""

        def __init__(self, *a, map_boxes=None, direct=False, **kw):
            self.gps_pts, self.vis_pts, self.trail, self.err_hist = [], [], [], []
            self.map_boxes, self.on_map, self.direct, self.fields = map_boxes, None, direct, []
            self.stopped = None
            super().__init__(*a, **kw)

        def gps_fix(self):
            n = len(self.arrivals)
            super().gps_fix()
            if len(self.arrivals) > n:
                est = self.arrivals[-1][1]
                self.gps_pts.append(None if not est.valid else
                                    (round(est.lat, 7), round(est.lon, 7), self.faults["gps"] != "ok"))

        def vision_fix(self):
            if self.faults["light"] == "day" and self.map_boxes is not None:
                lat, lon = self.frame.latlon(*self.truth)
                inside = any(b[0] <= lat <= b[2] and b[1] <= lon <= b[3] for b in self.map_boxes)
                if inside != self.on_map:
                    if not inside:
                        self.event("day vision: no onboard map here — no fix (day vision matches each photo "
                                   "against the prepared map of the area)")
                    elif self.on_map is not None:
                        self.event("day vision: back over the onboard map — fixes again")
                    self.on_map = inside
                if not inside:
                    return
            n = len(self.arrivals)
            super().vision_fix()
            if len(self.arrivals) > n:
                est = self.arrivals[-1][1]
                self.vis_pts.append((round(est.lat, 7), round(est.lon, 7), est.source))

        def send(self, fields):
            if self.direct:                      # the student's decoder is not written: no bytes on the link
                self.fields.append(dict(fields, lat=fields["lat"] / 1e7, lon=fields["lon"] / 1e7))
                self.seq = (self.seq + 1) % 256
                self.counts["frames"] += 1
                return
            super().send(fields)

        def autopilot(self, read_messages):
            if self.direct:
                msgs, self.fields = self.fields, []
                self.ap_update(msgs)
                return
            super().autopilot(read_messages)

        def move(self):
            if self.stopped:
                self.phase = "stopped"
            super().move()
            if self.k % 10 == 0:
                self.trail.append(tuple(round(v, 7) for v in self.frame.latlon(*self.truth)))
                if self.lite is not None and self.mission_t is not None:
                    self.err_hist.append((round(self.t, 1), round(self.dist_truth(self.lite[0], self.lite[1]), 1)))

    return PageWorld


# ---------------------------------------------------------------- the flight script's view
class _NavView:
    def __init__(self, run): self._r = run
    @property
    def state(self):
        d = self._r.world.decision
        return d.state if d else "STARTING"
    @property
    def source(self):
        d = self._r.world.decision
        return {"gps": "gps", "day": "vision", "night": "vision", "celestial": "celestial"}.get(d.source if d else None, "none")
    @property
    def error_m(self):
        e = self._r.error_m()
        return float("inf") if e is None else e
    @property
    def position(self): return self._r.lite_latlon()
    @property
    def reason(self):
        d = self._r.world.decision
        return d.reason if d else ""


class SimAPI:
    """`sim` in the student's flight script."""

    def __init__(self, run):
        self._r = run
        self.nav = _NavView(run)
        self.navera = self.nav                    # the name used by flight scripts saved before NAVERA Lite

    @property
    def t(self): return round(self._r.world.t, 1)
    @property
    def truth(self): return tuple(self._r.world.frame.latlon(*self._r.world.truth))
    @property
    def speed(self): return self._r.world.speed
    @property
    def phase(self): return self._r.world.phase
    @property
    def enroute_s(self): return self._r.world.mission_t

    def goto(self, where, speed=None, alt=None):
        w = self._r.world
        w.dest = w.frame.en(*place(where))
        if speed is not None:
            w.cruise = float(speed)
        if alt is not None:
            w.alt = float(alt)
        if w.phase == "arrived":
            w.phase, w.ap_mode, w.arrived_t = "enroute", "MISSION", None
            self._r.arrival = None
        w.event(f"new destination {where}" + (f" at {speed} m/s" if speed else ""))

    def stop(self, why="by the flight script"): self._r.stop(why)
    def set_speed(self, mps): self._r.world.cruise = float(mps)
    def jam_gps(self, **_): self._r.world.set_fault("gps", "jammed")
    def spoof_gps(self, kind="jump"): self._r.world.set_fault("gps", "spoof_jump" if kind == "jump" else "spoof_drift")
    def restore_gps(self): self._r.world.set_fault("gps", "ok")
    def gps_off(self): self._r.world.set_fault("gps", "off")
    def camera_fail(self): self._r.world.set_fault("camera", "blackout")
    def camera_ok(self): self._r.world.set_fault("camera", "ok")
    def camera_late(self): self._r.world.set_fault("camera", "late")
    def imu_bias(self): self._r.world.set_fault("imu", "bias")
    def imu_off(self): self._r.world.set_fault("imu", "off")
    def imu_ok(self): self._r.world.set_fault("imu", "ok")
    def night(self): self._r.world.set_fault("light", "night")
    def day(self): self._r.world.set_fault("light", "day")
    def log(self, *a): self._r.world.event("script: " + " ".join(str(x) for x in a))
    def distance_to(self, where):
        w = self._r.world
        e, n = w.frame.en(*place(where))
        return w.dist_truth(e, n)


def _short_tb():
    """The traceback from the student's script only (not the simulator's own frames)."""
    etype, e, tb = sys.exc_info()
    while tb is not None and tb.tb_frame.f_code.co_filename != "flight_script.py":
        tb = tb.tb_next
    lines = traceback.format_exception(etype, e, tb) if tb is not None else traceback.format_exception_only(etype, e)
    return "".join(lines)


def _level(text):
    if text.startswith("FAULT"):
        return "warn"
    if text.startswith("script: "):
        return "script"
    if "FAILSAFE" in text or "NO_FIX" in text or "really" in text and "arrived" not in text:
        return "bad"
    if "DEGRADED" in text or "no onboard map" in text or "reset" in text:
        return "warn"
    if "FIX" in text or text.startswith("arrived") or text.startswith("take-off"):
        return "ok"
    return "info"


# ---------------------------------------------------------------- one run
class Run:
    """A simulation: the world, the student's NAVERA Lite (or the course's parts), the optional flight script.
    cfg (from the page): vehicle, start, dest, profile ("measured" | "target" | "mine"), light, speed, max_speed,
    seed, map_boxes, and for a mission-31 scenario: scenario (my_scenario.json's dict: faults, duration_s, vision…)."""

    def __init__(self, cfg, script_text="", log=None):
        from navera_lite import arbiter, kalman, output
        from navera_lite.sim import world as W
        self.logs = []
        sc_in = cfg.get("scenario") or {}
        vehicle = sc_in.get("vehicle") or cfg.get("vehicle", "drone")
        settings = dict(INFO["settings"])
        settings["vehicle"] = vehicle
        settings["max_speed_mps"] = float(cfg.get("max_speed") or sc_in.get("max_speed_mps") or TOP_SPEED.get(vehicle, 30.0))
        judge = arbiter.Arbiter(settings)
        try:
            from navera_lite import spoof
            judge = spoof.GuardedArbiter(judge, spoof.SpoofGuard(settings))
            guard = True
        except ImportError:
            guard = False
        kind = sc_in.get("vision") or cfg.get("profile", "measured")
        if kind in ("mine", "profile"):
            prof = INFO["profile"]
            if prof:
                vision = W.ProfileVision("profile", prof)
                self.logs.append({"level": "info", "node": "vision",
                                  "text": "your networks' measured profile (my_vision_profile.json): a browser cannot "
                                          "run PyTorch, so the errors are drawn from what vision_check.py measured"})
            else:
                vision = W.ProfileVision("target")
                self.logs.append({"level": "warn", "node": "vision", "text": "no my_vision_profile.json yet (mission "
                                  "31, lab Step 11): flying the target profile instead"})
        else:
            vision = W.ProfileVision("target" if kind == "target" else "measured")
        start = place(cfg.get("start", "sousse"))
        dest = place(cfg.get("dest", "monastir"))
        self.frame = W.LocalFrame(*(place(cfg["origin"]) if cfg.get("origin") else start))   # mission 31: the corridor's
        sc = {"name": sc_in.get("name", "lite_run"), "vehicle": vehicle, "vision": kind, "seed": int(sc_in.get("seed",
              cfg.get("seed", 7))), "light": sc_in.get("light") or cfg.get("light", "day"),
              "faults": [list(f) for f in sc_in.get("faults", [])],
              "duration_s": float(sc_in.get("duration_s") or 1e9), "speed": sc_in.get("speed") or cfg.get("speed")}
        self.limit = float(sc_in["duration_s"]) if sc_in.get("duration_s") else None
        direct = not decoder_ready(output)
        PageWorld = make_world_class()
        self.world = PageWorld(sc, judge, output, kalman, vision, self.frame, (self.frame.en(*start), self.frame.en(*dest)),
                               map_boxes=cfg.get("map_boxes") if isinstance(cfg.get("map_boxes"), list) else None,
                               direct=direct)
        self.world.event(("guard (mission 30) in front of the judge" if guard else "no guard") + " · autopilot link: "
                         + ("YOUR decoder (bytes)" if not direct else "direct (your mission-31 decoder is not written "
                                                                       "yet)"))
        for part, why in INFO["parts"].items():
            self.logs.append({"level": "info", "node": "parts", "text": f"{part}: {why}"})
        self.read = self._reader(output)
        self.columns = W.COLUMNS
        self.api = SimAPI(self)
        self.script, self.script_error, self.error_sent = {}, None, False
        self.sent_ev = self.sent_rows = 0
        self.sent = {}
        self.arrival = None
        if script_text.strip():
            try:
                exec(compile(script_text, "flight_script.py", "exec"), self.script)
                if "on_start" in self.script:
                    self.script["on_start"](self.api)
            except Exception:
                self.script_error = _short_tb()
                self.world.event("flight script error — see the console (the flight goes on without your script)")

    @staticmethod
    def _reader(out):
        def read(data):
            msgs = []
            for fr in out.parse_frames(data) or []:
                if fr.get("msgid") == out.GPS_INPUT_ID and fr.get("crc_ok") is True:
                    msgs.append(out.decode_gps_input(fr["payload"]))
            return msgs
        return read

    def stop(self, why="stopped"):
        if not self.world.stopped:
            self.world.stopped = why
            self.world.event(f"mission stopped ({why})")

    def lite_latlon(self):
        w = self.world
        if w.lite is None or w.decision is None or w.decision.state not in ("FIX", "DEGRADED"):
            return None
        return w.frame.latlon(w.lite[0], w.lite[1])

    def error_m(self):
        w = self.world
        return None if w.lite is None else w.dist_truth(w.lite[0], w.lite[1])

    def fault(self, key, value):
        self.world.set_fault(key, PAGE_FAULT.get((key, value), value))

    def advance(self, seconds):
        w = self.world
        for _ in range(max(1, int(round(seconds / 0.1)))):
            w.step(self.read)
            tick = self.script.get("on_tick")
            if tick and not self.script_error:
                try:
                    tick(self.api, round(w.t, 1))
                except Exception:
                    self.script_error = _short_tb()
                    w.event("flight script error — see the console (the flight goes on without your script)")
            m = w.mission_t
            if self.limit is not None and m is not None and m >= self.limit:
                self.stop("scenario finished")
            if w.failsafe_t is not None and m is not None and m >= w.failsafe_t + 10.0:
                self.stop(f"autopilot failsafe ({w.ap_mode})")
            if w.arrived_t is not None and self.arrival is None:
                miss = math.hypot(w.dest[0] - w.truth[0], w.dest[1] - w.truth[1])
                radius = max(10.0, 1.5 * w.cruise)
                self.arrival = {"t": round(w.t, 1), "miss_m": round(miss, 1), "radius_m": round(radius),
                                "good": miss < radius + 30.0}
            if w.stopped or self.arrival:
                break
        return self.snapshot()

    def snapshot(self):
        w = self.world
        d = w.decision
        lat_lon = self.lite_latlon()
        err = self.error_m()
        phase = "stopped" if w.stopped else ("arrived" if self.arrival else ("flying" if w.phase == "enroute" else w.phase))
        page_faults = dict(w.faults)
        if page_faults["camera"] == "blackout":
            page_faults["camera"] = "failed"
        if page_faults["imu"] == "off":
            page_faults["imu"] = "failed"
        out = {"t": round(w.t, 1), "phase": phase, "truth": list(w.frame.latlon(*w.truth)), "heading": w.heading,
               "speed": round(w.speed, 1), "alt": w.alt,
               "belief": None if w.belief() is None else list(w.frame.latlon(*w.belief())),
               "nav": {"state": d.state if d else "STARTING", "source": SRC.get(d.source, "none") if d else "none",
                       "reason": d.reason if d else "", "lat": None if lat_lon is None else lat_lon[0],
                       "lon": None if lat_lon is None else lat_lon[1],
                       "age": None if w.lite is None else round(w.t - w.lite[3], 1)},
               "error_m": None if err is None else round(err, 1),
               "togo_m": round(math.hypot(w.dest[0] - w.truth[0], w.dest[1] - w.truth[1])), "faults": page_faults,
               "arrival": self.arrival, "gps_lost_for": None, "enroute_s": w.mission_t,
               "columns": list(self.columns)}
        s = self.sent
        for k in ("trail", "gps_pts", "vis_pts", "err_hist", "rows"):
            arr = getattr(w, k)
            out[k] = arr[s.get(k, 0):]
            s[k] = len(arr)
        if lat_lon is not None:
            out["nav_pts"] = [(round(lat_lon[0], 7), round(lat_lon[1], 7), d.source)]
        else:
            out["nav_pts"] = []
        evs = w.events[s.get("events", 0):]
        s["events"] = len(w.events)
        out["events"] = [{"t": t if m is None else m, "level": _level(text), "text": text} for t, m, text in evs]
        out["logs"], self.logs = self.logs, []
        out["script_error"] = self.script_error if not self.error_sent else None
        if self.script_error:
            self.error_sent = True
        return out
