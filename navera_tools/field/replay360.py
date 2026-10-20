#!/usr/bin/env python3
"""Replay a 360 field test from its raw camera recording (<session>/raw/raw360_*.bin, written by the server
through insta360_usb.RawRecorder): every camera packet as it arrived, so the whole drive can be run again
offline through the real server code with any setting changed.

    python3 -m navera_tools.field.replay360 <session folder> [--out DIR] [--every-frame] [--set NAME=VALUE ...]
    python3 -m navera_tools.field.replay360 <session folder> --export-frames DIR [--stops-only] [--every-frame]
    python3 -m navera_tools.field.replay360 <session folder> --info

Replay: the recorded packets go through the camera driver's own parsing (insta360_usb.Insta360Usb._packet) on a
simulated clock (the Jetson arrival times), the phone's recorded GPS track is fed back with the test's clock
offset, and server.Field runs its loop body once a simulated second, as live. A solve takes its real time on
this machine and the simulated clock is held meanwhile, then moves on (packets in that time are still parsed,
as live). The new test is written to --out (default <session>_replay_<time>), report included.

--set changes a module constant first, e.g. --set server.STOPPED_SOLVE_GAP_S=1 --set allsky.MIN_MATCHED=10
(modules: server, allsky, sky360, insta360_usb). --every-frame decodes every video frame instead of the key
frames only (the live server decodes key frames: ~2 a second).

--export-frames writes lossless PNG frames (and index.csv: arrival time, camera ms of the exposure, stopped,
'up' in the IMU frame) for star work; --stops-only keeps the frames the driver's stillness test calls stopped.
"""
import argparse
import ast
import collections
import csv
import json
import os
import sys
import time as _time
import types


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field import insta360_usb  # noqa: E402
from navera_tools.field.insta360_usb import KIND_IMU, KIND_VIDEO, IMU_RECORD, read_raw  # noqa: E402


class Clock:
    """A time module whose time() is the replay's simulated Jetson time."""

    def __init__(self, t0: float):
        self.t = t0

    def module(self):
        m = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")})
        m.time = lambda: self.t
        m.sleep = lambda s: _time.sleep(min(s, 0.01))     # threads that wait must not stall the replay
        return m


class OfflineDriver(insta360_usb.Insta360Usb):
    """The camera driver without the camera: packets are fed with feed(); video is decoded as it comes."""

    def __init__(self, keyframes_only: bool = True, max_rate_dps: float = 3.0):
        self._init_state(max_rate_dps, keyframes_only)
        import av
        self._codec = av.CodecContext.create("h264", "r")
        self._codec.thread_type = "SLICE"
        self.frames_decoded = 0
        self.decode_errors = 0
        self.new_frames = []                        # (arrival, exposure ms, frame) since the caller last took them

    def feed(self, t: float, packet: bytes):
        self._packet(packet, t)

    def _on_video(self, now: float, data, cam_ms: int):
        """As the live driver's decoder thread: a frame out of the decoder is stamped with the packet that was
        being fed (the rule FRAME_STAMP_LAG_MS was measured with)."""
        try:
            for pkt in (self._codec.parse(data) if data is not None else [None]):
                self._on_video_packet(now, pkt, cam_ms)
        except Exception as e:                      # a damaged packet: the next key frame resyncs, as live
            self.error = f"decode: {e}"
            self.decode_errors += 1

    def flush(self, now: float, cam_ms: int):
        """The frames still inside the parser and the decoder at the end of the recording."""
        try:
            for pkt in self._codec.parse(b""):
                self._on_video_packet(now, pkt, cam_ms)
        except Exception:
            pass
        self._on_video(now, None, cam_ms)

    def _on_video_packet(self, now, pkt, cam_ms):
        for fr in self._codec.decode(pkt):
            img = fr.to_ndarray(format="bgr24")
            ms = cam_ms - insta360_usb.FRAME_STAMP_LAG_MS
            with self._lock:
                self._frame, self._frame_t, self._frame_ms = img, now, ms
            self._keep_for_stack(img, ms)
            self.frames_decoded += 1
            self.new_frames.append((now, ms, img))

    def close(self):
        pass


class ReplayCamera:
    """server.Camera360's interface over the offline driver (the same methods, the same freshness rule)."""
    device = "insta360-usb replay"
    hfov = None

    def __init__(self, driver: OfflineDriver, cal_path: str, latency_s: float):
        self.cam, self.cal_path, self.latency_s = driver, cal_path, latency_s
        self.error, self.frame_ms = None, None
        self._mod = insta360_usb

    def latest(self):
        import cv2
        f, t, ms = self.cam.latest_stamped()
        if f is None or insta360_usb.time.time() - t > 3.0:
            return None, 0.0
        self.frame_ms = ms
        return (cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f), t - self.latency_s

    def gravity(self, at_frame=False):
        return self.cam.gravity(at_ms=self.frame_ms) if at_frame and self.frame_ms is not None else self.cam.gravity()

    def imu_age(self):
        return self.cam.imu_age()

    def stopped(self, at_frame=False):
        return self.cam.stopped(at_ms=self.frame_ms) if at_frame and self.frame_ms is not None else self.cam.stopped()


def imu_rows(raw_dir: str):
    """Every IMU row as the driver stores it: (Jetson arrival time, camera ms, ax, ay, az g, gx, gy, gz rad/s)."""
    out = []
    for t, kind, _, p in read_raw(raw_dir):
        if kind == KIND_IMU and p[:1] == b"\x01":
            body = p[12:]
            for k in range(0, len(body) - IMU_RECORD.size + 1, IMU_RECORD.size):
                out.append((t,) + IMU_RECORD.unpack_from(body, k))
    return out


def frames(raw_dir: str, every_frame: bool = False):
    """(arrival time, camera ms of the exposure, BGR frame) of every decoded video frame (key frames only unless
    every_frame), with the driver that saw the packets up to it (its IMU history: gravity/stopped at that frame)."""
    d = OfflineDriver(keyframes_only=not every_frame)
    clock = Clock(0.0)
    saved = insta360_usb.time
    insta360_usb.time = clock.module()
    try:
        t, last_ms, last_yield = None, 0, -1
        for t, kind, cam_ms, p in read_raw(raw_dir):
            clock.t = t
            d.feed(t, p)
            if kind == KIND_VIDEO:
                last_ms = cam_ms
            while d.new_frames:
                ft, ms, f = d.new_frames.pop(0)
                if ms <= last_yield:
                    continue                             # released together with an earlier one: its own time is unknown
                last_yield = ms
                yield ft, ms, f, d
        if t is not None:
            d.flush(t, last_ms)
            while d.new_frames:
                ft, ms, f = d.new_frames.pop(0)
                if ms > last_yield:                      # the flush stamps what it releases with the last packet's ms
                    last_yield = ms
                    yield ft, ms, f, d
    finally:
        insta360_usb.time = saved


def info(raw_dir: str) -> dict:
    kinds = collections.Counter()
    nbytes, t0, t1, keys = 0, None, None, 0
    for t, kind, _, p in read_raw(raw_dir):
        kinds[kind] += 1
        nbytes += len(p)
        t0 = t if t0 is None else t0
        t1 = t
        if kind == KIND_VIDEO and insta360_usb._has_keyframe(p, 12):
            keys += 1
    dur = (t1 - t0) if t0 is not None else 0.0
    return {"seconds": round(dur, 1), "mb": round(nbytes / 1e6, 1), "mb_per_min": round(nbytes / 1e6 / max(dur, 1e-9) * 60, 1),
            "video_packets": kinds[KIND_VIDEO], "key_frames": keys, "imu_packets": kinds[KIND_IMU],
            "video_fps": round(kinds[KIND_VIDEO] / max(dur, 1e-9), 1),
            "other": {hex(k): v for k, v in kinds.items() if k not in (KIND_VIDEO, KIND_IMU)}}


def export_frames(raw_dir: str, out: str, stops_only: bool, every_frame: bool) -> int:
    import cv2
    os.makedirs(out, exist_ok=True)
    n = 0
    with open(os.path.join(out, "index.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "t_arrival", "cam_ms_exposure", "stopped", "up_x", "up_y", "up_z", "accel_g"])
        for t, ms, f, d in frames(raw_dir, every_frame):
            st = d.stopped(at_ms=ms)
            if stops_only and not st.get("stopped"):
                continue
            up, g, _ = d.gravity(at_ms=ms)
            name = f"frame_{int(ms)}.png"
            cv2.imwrite(os.path.join(out, name), f)
            w.writerow([name, f"{t:.3f}", int(ms), int(bool(st.get("stopped")))]
                       + ([f"{v:.6f}" for v in up] if up is not None else ["", "", ""]) + [f"{g:.5f}" if g else ""])
            n += 1
    return n


def apply_sets(sets):
    from navera_tools.field import allsky, server, sky360
    mods = {"server": server, "allsky": allsky, "sky360": sky360, "insta360_usb": insta360_usb}
    done = {}
    for s in sets or []:
        name, _, value = s.partition("=")
        mod, _, attr = name.partition(".")
        if mod not in mods or not hasattr(mods[mod], attr):
            raise SystemExit(f"--set {s}: unknown (modules: {', '.join(mods)})")
        try:
            v = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            v = value
        setattr(mods[mod], attr, v)
        done[name] = v
    return done


def replay(session: str, out_root: str, every_frame: bool = False, sets=None, log=print) -> str:
    """Run the whole test again from session/raw through server.Field; returns the new test's folder."""
    from navera_tools.field import server, store
    from navera_tools.field.store import read_jsonl
    raw_dir = os.path.join(session, "raw")
    meta = json.load(open(os.path.join(session, "session.json")))
    phone = sorted((r for r in read_jsonl(os.path.join(session, "phone.jsonl")) if isinstance(r, dict) and r.get("t")),
                   key=lambda r: r["t"])
    off = float(meta.get("clock_offset_s") or 0.0)
    changed = apply_sets(sets)
    recs = read_raw(raw_dir)
    first = next(recs, None)
    if first is None:
        raise SystemExit(f"{raw_dir}: no raw recording")
    clock = Clock(first[0])
    saved = (server.time, store.time, insta360_usb.time)
    server.time = store.time = insta360_usb.time = clock.module()
    try:
        driver = OfflineDriver(keyframes_only=not every_frame)
        cam = ReplayCamera(driver, meta.get("calibration") or insta360_usb.IMU_CALIBRATION,
                           float(meta.get("latency_s") or server.Camera360.latency_s))

        class QuietField(server.Field):
            def _loop(self):
                return
        os.makedirs(out_root, exist_ok=True)
        f = QuietField(out_root, cam)
        f.interval_s = float(meta.get("interval_s") or f.interval_s)
        pi = 0

        def feed_phone(upto):
            nonlocal pi
            while pi < len(phone) and phone[pi]["t"] <= upto:
                d = dict(phone[pi])
                d["phone_t_ms"] = int((d["t"] - off) * 1000)
                f.on_phone(d)
                pi += 1
        feed_phone(first[0])
        f.start()
        f.session.event("replay", source=os.path.basename(os.path.normpath(session)), every_frame=every_frame,
                        settings={k: repr(v) for k, v in changed.items()})
        driver.feed(first[0], first[3])
        next_tick, hold_until = first[0], first[0]
        end_t = meta.get("ended")
        n = 0
        for t, _, _, p in recs:
            if end_t and t > end_t:
                break
            clock.t = t
            feed_phone(t)
            driver.feed(t, p)
            n += 1
            if t < next_tick or t < hold_until:
                continue
            next_tick = t + 1.0                           # the server's loop: once a second
            img, texp = cam.latest()
            if img is None:
                continue
            f._live360(img, texp)
            f._maybe_solve(img, texp)
            if f.solving:                                 # a solve takes its real time here: the clock waits, then jumps
                w0 = _time.time()
                while f.solving:
                    _time.sleep(0.02)
                hold_until = t + (_time.time() - w0)
            if n % 20000 == 0:
                log(f"  {t - first[0]:7.0f} s replayed, {f.frame_idx} frames, {f.n_fixes} fixes")
        feed_phone(float("inf"))
        sid = f.session.id
        f.end()
        return os.path.join(out_root, sid)
    finally:
        server.time, store.time, insta360_usb.time = saved


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--out", default="")
    ap.add_argument("--every-frame", action="store_true")
    ap.add_argument("--set", action="append", default=[], metavar="MODULE.NAME=VALUE")
    ap.add_argument("--export-frames", default="")
    ap.add_argument("--stops-only", action="store_true")
    ap.add_argument("--info", action="store_true")
    a = ap.parse_args()
    raw_dir = os.path.join(a.session, "raw")
    if a.info:
        print(json.dumps(info(raw_dir), indent=1))
        return 0
    if a.export_frames:
        n = export_frames(raw_dir, a.export_frames, a.stops_only, a.every_frame)
        print(f"{n} frames written to {a.export_frames}")
        return 0
    out = a.out or os.path.normpath(a.session) + "_replay_" + _time.strftime("%Y%m%d_%H%M%S")
    folder = replay(a.session, out, a.every_frame, a.set)
    print("replayed test:", folder)
    rep = os.path.join(folder, "report.json")
    if os.path.exists(rep):
        r = json.load(open(rep))
        print(json.dumps({k: r.get(k) for k in ("verdict", "frames", "solved")}, indent=1))
    sys.stdout.flush()
    os._exit(0)                                           # solver threads must not hold the exit


if __name__ == "__main__":
    sys.exit(main())
