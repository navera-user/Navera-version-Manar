"""Raw camera recording (insta360_usb.RawRecorder) and its replay (field/replay360.py), on a synthetic packet
stream in the camera's own framing: H.264 from PyAV, 500 Hz IMU packets, a keepalive."""
import json
import math
import os
import struct
import time

import numpy as np
import pytest

from navera_tools.field import insta360_usb as iu
from navera_tools.field import replay360 as rp

av = pytest.importorskip("av")


def _h264(n=30, gop=10):
    """Annex-B access units of n tiny frames, a key frame every gop."""
    c = av.CodecContext.create("libx264", "w")
    c.width, c.height, c.pix_fmt, c.gop_size = 64, 32, "yuv420p", gop
    c.framerate = 18
    c.options = {"bframes": "0", "keyint_min": str(gop), "sc_threshold": "0"}
    out = []
    for i in range(n):
        f = av.VideoFrame.from_ndarray(np.full((32, 64, 3), (i * 7) % 255, np.uint8), format="bgr24")
        f.pts = i
        out += [bytes(p) for p in c.encode(f)]
    out += [bytes(p) for p in c.encode(None)]
    return out


def _stream(kind, cam_ms, body):
    return b"\x01\x00\x00" + bytes([kind]) + struct.pack("<I", cam_ms) + b"\x00" * 4 + body


def _packets(seconds=4.0):
    """(arrival time, packet): IMU every 20 ms (10 rows, camera tilted 5 deg, still), video every 1/18 s."""
    t0, out = 1_800_000_000.0, []
    up = np.array([math.sin(math.radians(5)), 0.0, math.cos(math.radians(5))])
    rng = np.random.default_rng(1)
    for k in range(int(seconds / 0.02)):
        ms = 10_000 + k * 20
        rows = b"".join(iu.IMU_RECORD.pack(ms + 2 * j, *(up + rng.normal(0, 0.001, 3)), *rng.normal(0, 1e-4, 3))
                        for j in range(10))
        out.append((t0 + k * 0.02 + 0.003, _stream(iu.KIND_IMU, ms + 18, rows)))
    for i, au in enumerate(_h264(int(seconds * 18))):
        out.append((t0 + i / 18 + 0.01, _stream(iu.KIND_VIDEO, 10_000 + int(i / 18 * 1000) + 1500, au)))
    out.append((t0 + 1.0, b"\x05\x00\x00"))
    return sorted(out, key=lambda x: x[0])


def _live(packets, folder, **kw):
    """The driver's own USB path (_parse on the length-prefixed byte stream) with a recorder attached."""
    clock = rp.Clock(packets[0][0])
    saved, iu.time = iu.time, clock.module()
    try:
        d = rp.OfflineDriver(**kw)
        d.record(iu.RawRecorder(folder))
        for t, p in packets:
            clock.t = t
            d._buf += struct.pack("<i", len(p) + 4) + p
            d._parse()
        stats = d.stop_record()
        return d, stats
    finally:
        iu.time = saved


def test_recorded_packets_read_back_identical(tmp_path):
    pk = _packets()
    _, st = _live(pk, str(tmp_path))
    back = list(iu.read_raw(str(tmp_path)))
    assert st["drops"] == 0 and st["records"] == len(pk) == len(back)
    assert [(t, p) for t, _, _, p in back] == pk
    kinds = {k for _, k, _, _ in back}
    assert {iu.KIND_IMU, iu.KIND_VIDEO, 0} <= kinds
    assert all(ms == struct.unpack_from("<I", p, 4)[0] for _, k, ms, p in back if k)


def test_files_rotate_and_resume_numbering(tmp_path):
    pk = _packets(2.0)
    r = iu.RawRecorder(str(tmp_path), rotate_bytes=20_000)
    for t, p in pk:
        r.put(t, p)
    st = r.close()
    assert len(st["files"]) > 2
    assert [p for _, _, _, p in iu.read_raw(str(tmp_path))] == [p for _, p in pk]
    r2 = iu.RawRecorder(str(tmp_path))                     # a resumed test: new files, the old ones kept
    r2.put(1.0, b"\x05\x00\x00")
    assert r2.close()["files"][0] == f"raw360_{len(st['files']):04d}.bin"


def test_a_full_queue_counts_drops_and_never_blocks(tmp_path):
    r = iu.RawRecorder(str(tmp_path), max_queue_bytes=50)
    t0 = time.time()
    r.put(1.0, b"x" * 100)
    r.put(1.0, b"x" * 40)
    st = r.close()
    assert time.time() - t0 < 5 and st["drops"] == 1 and st["drop_mb"] == 0.0 and st["records"] == 1


def test_a_cut_last_record_is_skipped(tmp_path):
    pk = _packets(1.0)
    _live(pk, str(tmp_path))
    f = tmp_path / "raw360_0000.bin"
    f.write_bytes(f.read_bytes()[:-7])                     # power cut in the middle of the last packet
    assert len(list(iu.read_raw(str(tmp_path)))) == len(pk) - 1


def test_replay_gives_the_live_drivers_imu_gravity_and_frames(tmp_path):
    pk = _packets()
    live, _ = _live(pk, str(tmp_path))
    rows = rp.imu_rows(str(tmp_path))
    assert rows[-len(live._imu):] == list(live._imu)
    seen = list(rp.frames(str(tmp_path)))
    keys = sum(1 for _, p in pk if p[3:4] == bytes([iu.KIND_VIDEO]) and iu._has_keyframe(p, 12))
    assert len(seen) == keys and seen[-1][2].shape == (32, 64, 3)
    _, ms, _, d = seen[-1]
    g_live, g_rep = live.gravity(at_ms=ms - 600), d.gravity(at_ms=ms - 600)
    assert g_rep[0] is not None and np.allclose(g_live[0], g_rep[0]) and g_live[1] == g_rep[1]
    assert abs(math.degrees(math.acos(g_rep[0][2])) - 5.0) < 0.2
    every = list(rp.frames(str(tmp_path), every_frame=True))
    assert len(every) > len(seen)
    info = rp.info(str(tmp_path))
    assert info["key_frames"] == keys and info["imu_packets"] == 200


def test_the_server_records_raw_from_start_to_end(tmp_path):
    from navera_tools.field import server as sv

    class Cam:
        device, cal_path, hfov, error, latency_s = "fake 360", "none", None, None, 1.7

        def __init__(self):
            self.calls = []

        def latest(self):
            return None, 0.0

        def gravity(self, at_frame=False):
            return None, None, None

        def start_raw(self, folder):
            self.calls.append(("start", folder))

        def stop_raw(self):
            self.calls.append(("stop",))
            return {"mb": 1.0, "records": 3, "drops": 0, "files": ["raw360_0000.bin"], "folder": "x"}

        def raw_stats(self):
            return {"mb": 1.0, "drops": 0} if len(self.calls) == 1 else None

    cam = Cam()
    f = sv.Field(str(tmp_path), cam)
    f.start()
    sid = f.session.id
    assert cam.calls == [("start", os.path.join(str(tmp_path), sid, "raw"))] and f.state()["raw"]["mb"] == 1.0
    f.end()
    ev = [json.loads(x) for x in open(tmp_path / sid / "events.jsonl")]
    kinds = [e.get("kind") or e.get("event") for e in ev]
    assert "raw_start" in kinds and "raw_stop" in kinds and cam.calls[-1] == ("stop",)


def test_whole_test_replays_through_the_server(tmp_path):
    sess = tmp_path / "2026-10-19_2100"
    raw = sess / "raw"
    pk = _packets(6.0)
    _live(pk, str(raw))
    t0 = pk[0][0]
    json.dump({"id": sess.name, "started": t0, "ended": pk[-1][0] + 1, "interval_s": 2.0, "clock_offset_s": 0.5,
               "latency_s": 1.71, "calibration": "none"}, open(sess / "session.json", "w"))
    with open(sess / "phone.jsonl", "w") as fh:
        for k in range(7):
            fh.write(json.dumps({"t": t0 + k, "lat": 36.8, "lon": 10.2, "acc": 5, "speed": 0}) + "\n")
    out = rp.replay(str(sess), str(tmp_path / "replays"), log=lambda *_: None)
    frames = [json.loads(x) for x in open(os.path.join(out, "frames.jsonl"))]
    phone = [json.loads(x) for x in open(os.path.join(out, "phone.jsonl"))]
    assert frames and all(fr.get("mode") == "360" for fr in frames) and len(phone) >= 6
    assert os.path.exists(os.path.join(out, "report.json"))
