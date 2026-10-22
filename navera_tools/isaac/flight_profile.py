"""The simulated flight shared by the Isaac Sim scene and the NAVERA link (SIMULATION only).

One deterministic function of time gives the vehicle's true state: the Isaac Sim script
(Windows, isaac_flight.py) poses the vehicle and its downward camera with it, the link
(WSL, isaac_link.py) derives the IMU, the GPS and the ground truth from the SAME function —
no state crosses between the two programs except the rendered frames and their time.

Frame: local ENU in metres about the scene origin (lat0, lon0) = Isaac Sim's world
(X east, Y north, Z up, ground at Z = 0). The map mosaic is laid with the same flat
projection (navera_common's metres per degree), so a position in the scene and its
lat/lon agree to well under a metre over the mosaic.

Route (`circuit`): a level circle of radius R flown counter-clockwise at constant speed
(the replay benches' 900 m circuit), banked for a coordinated turn, with wind-gust shake
(sum of incommensurate sines: deterministic, identical on both sides), a slow height
wave and a small lateral wander. `leg`: a straight 5 km leg with the same shake.

`Trajectory`: a flight recorded from ArduPilot SITL (sitl_record.py: the real autopilot
and its flight dynamics, wind and turbulence), interpolated; t = 0 when the vehicle is on
the circuit at height. Scene Z is then the altitude above sea level minus z_ref (the DEM
height at the scene origin), the scene's ground being the DEM.
"""
import bisect
import math
from dataclasses import dataclass
from typing import Tuple

M_PER_DEG = 111_320.0
G = 9.80665

# gust shake: (amplitude deg, frequency Hz, phase rad) per axis — 0.2-2.3 Hz, a few degrees
_ROLL = ((1.6, 0.31, 0.4), (0.9, 0.83, 1.9), (0.5, 1.7, 2.6), (0.25, 2.3, 0.7))
_PITCH = ((1.1, 0.27, 2.2), (0.6, 0.71, 0.3), (0.35, 1.9, 1.4))
_YAW = ((0.8, 0.13, 1.1), (0.4, 0.57, 2.8), (0.2, 1.3, 0.2))


def _shake(terms, t: float) -> Tuple[float, float]:
    """(value deg, rate deg/s) of a sum of sines."""
    v = sum(a * math.sin(2 * math.pi * f * t + p) for a, f, p in terms)
    r = sum(a * 2 * math.pi * f * math.cos(2 * math.pi * f * t + p) for a, f, p in terms)
    return v, r


@dataclass
class State:
    t: float
    e: float
    n: float
    u: float                      # scene Z, m (the analytic profiles: height above the flat ground)
    ve: float
    vn: float
    vu: float
    roll: float                   # deg, right wing down positive
    pitch: float                  # deg, nose up positive
    yaw: float                    # deg, ENU (counter-clockwise from east)
    p: float                      # body rates FLU, rad/s
    q: float
    r: float
    ae: float                     # acceleration ENU, m/s^2
    an: float
    au: float
    alt_msl: float = float("nan")  # m above sea level (Trajectory)
    rel_alt: float = float("nan")  # m above the take-off point (Trajectory)

    @property
    def heading(self) -> float:
        """Compass heading of the nose, deg clockwise from north."""
        return (90.0 - self.yaw) % 360.0

    def quat_enu(self) -> Tuple[float, float, float, float]:
        """(x, y, z, w) body FLU -> ENU, the convention of navera_common.camera_model."""
        return rpy_to_quat(self.roll, self.pitch, self.yaw)


def rpy_to_quat(roll_deg: float, pitch_deg: float, yaw_deg: float) -> Tuple[float, float, float, float]:
    """R = Rz(yaw) Ry(-pitch) Rx(roll) (FLU body: nose up is a negative rotation about +y)."""
    cr, sr = math.cos(math.radians(roll_deg) / 2), math.sin(math.radians(roll_deg) / 2)
    cp, sp = math.cos(-math.radians(pitch_deg) / 2), math.sin(-math.radians(pitch_deg) / 2)
    cy, sy = math.cos(math.radians(yaw_deg) / 2), math.sin(math.radians(yaw_deg) / 2)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


@dataclass
class Profile:
    route: str = "circuit"         # circuit | leg
    radius_m: float = 900.0
    speed_mps: float = 40.0
    height_m: float = 500.0
    leg_m: float = 5000.0
    leg_heading_deg: float = 60.0  # compass heading of the straight leg
    shake: float = 1.0             # gust shake scale (0 = smooth)

    def state(self, t: float) -> State:
        if self.route == "leg":
            return self._leg(t)
        return self._circuit(t)

    def duration_s(self, laps: float = 2.0) -> float:
        if self.route == "leg":
            return self.leg_m / self.speed_mps
        return laps * 2 * math.pi * self.radius_m / self.speed_mps

    def _common(self, t, e, n, ve, vn, ae, an, bank_deg, yaw_rate):
        s = self.shake
        h_wave, h_rate = 15.0 * math.sin(2 * math.pi * t / 90.0), 15.0 * 2 * math.pi / 90.0 * math.cos(2 * math.pi * t / 90.0)
        h_acc = -15.0 * (2 * math.pi / 90.0) ** 2 * math.sin(2 * math.pi * t / 90.0)
        dr, drr = _shake(_ROLL, t)
        dp, dpr = _shake(_PITCH, t)
        dy, dyr = _shake(_YAW, t)
        yaw = math.degrees(math.atan2(vn, ve)) + s * dy
        roll = bank_deg + s * dr
        pitch = 2.0 + s * dp                       # cruise angle of attack
        # body rates ~ Euler rates (small roll/pitch): enough for the IMU's gyro
        p = math.radians(s * drr)
        q = math.radians(-s * dpr)
        r = yaw_rate + math.radians(s * dyr)
        return State(t, e, n, self.height_m + h_wave, ve, vn, h_rate, roll, pitch, yaw, p, q, r, ae, an, h_acc)

    def _circuit(self, t: float) -> State:
        w = self.speed_mps / self.radius_m           # rad/s, counter-clockwise
        th = w * t                                    # start at the circle's east point, flying north
        e, n = self.radius_m * math.cos(th), self.radius_m * math.sin(th)
        ve, vn = -self.speed_mps * math.sin(th), self.speed_mps * math.cos(th)
        ae, an = -self.speed_mps * w * math.cos(th), -self.speed_mps * w * math.sin(th)
        bank = -math.degrees(math.atan(self.speed_mps ** 2 / (G * self.radius_m)))   # left turn: left wing down
        return self._common(t, e, n, ve, vn, ae, an, bank, w)

    def _leg(self, t: float) -> State:
        az = math.radians(self.leg_heading_deg)
        d = self.speed_mps * t - self.leg_m / 2.0       # centred on the origin
        ue, un = math.sin(az), math.cos(az)
        wander = 20.0 * math.sin(2 * math.pi * t / 60.0)  # lateral wander, m
        we = 20.0 * 2 * math.pi / 60.0 * math.cos(2 * math.pi * t / 60.0)
        e, n = d * ue + wander * un, d * un - wander * ue
        ve, vn = self.speed_mps * ue + we * un, self.speed_mps * un - we * ue
        acc = -20.0 * (2 * math.pi / 60.0) ** 2 * math.sin(2 * math.pi * t / 60.0)
        ae, an = acc * un, -acc * ue
        lat_acc = acc
        bank = math.degrees(math.atan(-lat_acc / G))
        return self._common(t, e, n, ve, vn, ae, an, bank, 0.0)


@dataclass
class GeoRef:
    lat0: float
    lon0: float

    def to_latlon(self, e: float, n: float) -> Tuple[float, float]:
        return (self.lat0 + n / M_PER_DEG,
                self.lon0 + e / (M_PER_DEG * math.cos(math.radians(self.lat0))))

    def to_en(self, lat: float, lon: float) -> Tuple[float, float]:
        return ((lon - self.lon0) * M_PER_DEG * math.cos(math.radians(self.lat0)),
                (lat - self.lat0) * M_PER_DEG)


class Trajectory:
    """A recorded flight (sitl_record.py CSV) as a function of time, same State as Profile."""

    def __init__(self, path: str, geo: "GeoRef", z_ref: float = 0.0):
        self.geo, self.z_ref, self.meta = geo, z_ref, {}
        cols, rows = None, []
        for line in open(path):
            line = line.strip()
            if line.startswith("#"):
                for kv in line[1:].split():
                    k, _, v = kv.partition("=")
                    self.meta[k] = v
            elif cols is None:
                cols = line.split(",")
            elif line:
                rows.append([float(v) for v in line.split(",")])
        t0 = float(self.meta.get("station_t", rows[0][0]))
        self.c = {k: [r[i] for r in rows] for i, k in enumerate(cols)}
        self.c["t"] = [v - t0 for v in self.c["t"]]
        en = [geo.to_en(la, lo) for la, lo in zip(self.c["lat"], self.c["lon"])]
        self.c["e"], self.c["n"] = [p[0] for p in en], [p[1] for p in en]
        self.vehicle = self.meta.get("vehicle", "plane")

    def duration_s(self, laps: float = 0.0) -> float:
        return self.c["t"][-1]

    def _at(self, key: str, i: int, f: float, angle: bool = False) -> float:
        a, b = self.c[key][i], self.c[key][i + 1]
        if angle:
            d = (b - a + 180.0) % 360.0 - 180.0
            return (a + f * d) % 360.0
        return a + f * (b - a)

    def _idx(self, t: float):
        ts = self.c["t"]
        t = min(max(t, ts[0]), ts[-1] - 1e-6)
        i = max(0, min(bisect.bisect_right(ts, t) - 1, len(ts) - 2))
        return i, (t - ts[i]) / max(ts[i + 1] - ts[i], 1e-9)

    def state(self, t: float) -> State:
        i, f = self._idx(t)
        g = lambda k: self._at(k, i, f)                       # noqa: E731
        vn, ve, vd = g("vn"), g("ve"), g("vd")
        dt = 0.1
        i1, f1 = self._idx(t + dt)
        i0, f0 = self._idx(t - dt)
        an = (self._at("vn", i1, f1) - self._at("vn", i0, f0)) / (2 * dt)
        ae = (self._at("ve", i1, f1) - self._at("ve", i0, f0)) / (2 * dt)
        au = -(self._at("vd", i1, f1) - self._at("vd", i0, f0)) / (2 * dt)
        heading = self._at("heading", i, f, angle=True)
        alt = g("alt_msl")
        return State(t, g("e"), g("n"), alt - self.z_ref, ve, vn, -vd, g("roll"), g("pitch"),
                     (90.0 - heading) % 360.0, g("p"), g("q"), g("r"), ae, an, au, alt, g("rel_alt"))


class LiveFeed:
    """The vehicle flown LIVE by ArduPilot SITL: state packets from sitl_demo.py (UDP JSON,
    one per SIM_STATE, t = seconds since the demo's t0 on this PC's clock), kept as a history
    so that state(t) answers like Trajectory (interpolated; held at the ends)."""

    def __init__(self, port: int, geo: "GeoRef", z_ref: float = 0.0, keep_s: float = 900.0,
                 host: str = "127.0.0.1"):
        import socket
        self.geo, self.z_ref, self.keep_s = geo, z_ref, keep_s
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))     # host 0.0.0.0: the truth from another machine (HIL)
        self.sock.setblocking(False)
        self.c = {k: [] for k in ("t", "e", "n", "alt", "rel", "vn", "ve", "vd", "roll", "pitch", "heading",
                                  "p", "q", "r")}
        self.last = None                    # the latest packet (dict)
        self.vehicle = "copter"
        self.meta = {}

    def poll(self) -> int:
        import json as _json
        n = 0
        while True:
            try:
                data = self.sock.recv(65536)
            except (BlockingIOError, OSError):
                return n
            d = _json.loads(data)
            self.last = d
            self.vehicle = d.get("vehicle", self.vehicle)
            if d.get("lat") is None or (self.c["t"] and d["t"] <= self.c["t"][-1]):
                continue
            e, nn = self.geo.to_en(d["lat"], d["lon"])
            for k, v in (("t", d["t"]), ("e", e), ("n", nn), ("alt", d["alt"]), ("rel", d.get("rel", 0.0)),
                         ("vn", d["vn"]), ("ve", d["ve"]), ("vd", d["vd"]), ("roll", d["roll"]),
                         ("pitch", d["pitch"]), ("heading", d["hdg"]), ("p", d["p"]), ("q", d["q"]), ("r", d["r"])):
                self.c[k].append(v)
            n += 1
            if self.c["t"][0] < d["t"] - self.keep_s:
                for v in self.c.values():
                    del v[:500]

    def ready(self) -> bool:
        return len(self.c["t"]) >= 2

    def latest_t(self) -> float:
        return self.c["t"][-1] if self.c["t"] else 0.0

    def duration_s(self, laps: float = 0.0) -> float:
        return float("inf")

    def _idx(self, t):
        ts = self.c["t"]
        t = min(max(t, ts[0]), ts[-1] - 1e-6)
        i = max(0, min(bisect.bisect_right(ts, t) - 1, len(ts) - 2))
        return i, (t - ts[i]) / max(ts[i + 1] - ts[i], 1e-9)

    def _at(self, key, i, f, angle=False):
        a, b = self.c[key][i], self.c[key][i + 1]
        if angle:
            return (a + f * ((b - a + 180.0) % 360.0 - 180.0)) % 360.0
        return a + f * (b - a)

    def state(self, t: float) -> State:
        i, f = self._idx(t)
        g = lambda k: self._at(k, i, f)                       # noqa: E731
        dt = 0.1
        i1, f1 = self._idx(t + dt)
        i0, f0 = self._idx(t - dt)
        an = (self._at("vn", i1, f1) - self._at("vn", i0, f0)) / (2 * dt)
        ae = (self._at("ve", i1, f1) - self._at("ve", i0, f0)) / (2 * dt)
        au = -(self._at("vd", i1, f1) - self._at("vd", i0, f0)) / (2 * dt)
        alt = g("alt")
        return State(t, g("e"), g("n"), alt - self.z_ref, g("ve"), g("vn"), -g("vd"), g("roll"), g("pitch"),
                     (90.0 - self._at("heading", i, f, angle=True)) % 360.0, g("p"), g("q"), g("r"),
                     ae, an, au, alt, g("rel"))
