"""The Insta360 IMU publisher: shared protocol, clock mapping, bias at rest, mounting, replay of a
raw recording, the live USB source with a fake camera, and the ROS node end to end."""
import math
import os
import struct
import threading
import time

import numpy as np
import pytest

from navera_common import insta360_protocol as proto
from camera_pkg import insta360_imu as ii

CAL0 = (np.zeros(3), np.ones(3), np.zeros(3))          # neutral calibration (no file dependence)
REAL = os.path.expanduser("~/navera-field/2026-10-20_1150/raw")


# ── synthetic camera ─────────────────────────────────────────────────────
def imu_packet(ms0, n=50, accel=(1.0, 0.0, 0.0), gyro=(0.0, 0.0, 0.0), noise=0.0, rng=None, step_ms=2):
    """A KIND_IMU stream packet: n records from camera ms ms0, 2 ms apart."""
    body = b""
    for k in range(n):
        e = rng.normal(0.0, noise, 6) if rng is not None and noise else np.zeros(6)
        body += proto.IMU_RECORD.pack(ms0 + step_ms * k, *(np.array(accel + gyro, float) + e))
    return b"\x01\x00\x00" + bytes([proto.KIND_IMU]) + struct.pack("<I", ms0) + b"\x00" * 4 + body


def video_packet(ms):
    return b"\x01\x00\x00" + bytes([proto.KIND_VIDEO]) + struct.pack("<I", ms) + b"\x00" * 4 + b"\x00\x00\x01\x65xx"


def write_raw(path, records):
    """A raw recording (the field RawRecorder's format) of (arrival, packet)."""
    with open(path, "wb") as f:
        f.write(proto.RAW_MAGIC)
        for t, p in records:
            kind, ms = proto.stream_kind(p)
            f.write(proto.RAW_RECORD.pack(t, kind or 0, ms or 0, len(p)))
            f.write(p)


def synthetic_session(seconds=6.0, host0=1000.0, cam0=50_000, gyro=(0.0, 0.0, 0.0), seed=1, delay_ms=(2, 40)):
    """(arrival, packet) every 100 ms, arriving after the packet's last record + a random delay."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(int(seconds * 10)):
        ms0 = cam0 + 100 * i
        arrival = host0 + (ms0 + 98) / 1000.0 + rng.uniform(*delay_ms) / 1000.0
        out.append((arrival, imu_packet(ms0, gyro=gyro, noise=0.001, rng=rng)))
        out.append((arrival + 0.001, video_packet(ms0)))
    return out


# ── protocol (shared with the field driver) ──────────────────────────────
def test_field_driver_uses_the_shared_protocol():
    field = pytest.importorskip("navera_tools.field.insta360_usb")
    for name in ("IMU_RECORD", "RAW_MAGIC", "RAW_RECORD", "START_FULL", "read_raw", "load_imu_calibration"):
        assert getattr(field, name) is getattr(proto, name)


def test_packets_split_and_frame():
    a, b = proto.message_payload(proto.CMD_START_LIVE, 7, proto.START_FULL), proto.PKT_KEEPALIVE
    assert a[:3] == b"\x04\x00\x00" and a[3:5] == b"\x01\x00" and a[6:9] == b"\x07\x00\x00"
    buf = bytearray(proto.frame_packet(a) + proto.frame_packet(b) + proto.frame_packet(b"xyz")[:5])
    assert proto.split_packets(buf) == [a, b]
    assert len(buf) == 5                                   # the partial packet waits for the next read
    buf += proto.frame_packet(b"xyz")[5:]
    assert proto.split_packets(buf) == [b"xyz"] and not buf
    bad = bytearray(struct.pack("<i", 2) + b"zz" + proto.frame_packet(b))
    assert proto.split_packets(bad) == [] and not bad      # out of step: dropped


def test_imu_records_decode():
    p = imu_packet(1234, n=3, accel=(1.0, 0.1, 0.2), gyro=(0.01, 0.02, 0.03))
    assert proto.stream_kind(p) == (proto.KIND_IMU, 1234)
    recs = proto.imu_records(p)
    assert [r[0] for r in recs] == [1234, 1236, 1238]
    assert recs[0][1:] == pytest.approx((1.0, 0.1, 0.2, 0.01, 0.02, 0.03))
    assert proto.stream_kind(b"\x04\x00\x00abc") == (None, None)


# ── mounting ─────────────────────────────────────────────────────────────
def test_default_mount_camera_standing_left_circle_forward():
    R = ii.mount_rotation()
    assert R @ [1, 0, 0] == pytest.approx([0, 0, 1])       # camera up -> body up
    assert R @ [0, 1, 0] == pytest.approx([1, 0, 0])       # left circle -> forward
    assert np.linalg.det(R) == pytest.approx(1.0)
    assert ii.mount_rotation("-y,-z,+x") @ [0, -1, 0] == pytest.approx([1, 0, 0])
    assert ii.mount_rotation("+x,+y,+z", yaw_deg=90) @ [1, 0, 0] == pytest.approx([0, 1, 0])


@pytest.mark.parametrize("bad", ["+y,+y,+x", "+y,+x,+z", "+y,+z", "+q,+z,+x"])
def test_bad_mounts_are_refused(bad):
    with pytest.raises(ValueError):
        ii.axes_matrix(bad)


# ── clock ────────────────────────────────────────────────────────────────
def test_clock_finds_the_least_delayed_packet_and_never_goes_back():
    rng = np.random.default_rng(3)
    true_off = 1_700_000_000.0
    c = ii.CameraClock()
    prev = None
    for i in range(600):                                   # 60 s
        last_ms = 10_000 + 100 * i + 98
        c.update(true_off + last_ms / 1000 + rng.uniform(0.001, 0.09), last_ms)
        t = c.to_host(last_ms)
        if i > 50:
            assert t > prev
        prev = t
    assert c.offset - true_off == pytest.approx(0.001, abs=0.002)
    assert c.resets == 0


def test_clock_steps_and_camera_restart():
    c = ii.CameraClock()
    for i in range(50):
        c.update(100.0 + i * 0.1 + 0.005, 1000 + i * 100)
    assert c.offset == pytest.approx(99.005, abs=0.01)
    for i in range(50, 70):                                # host clock stepped back by 30 s
        c.update(70.0 + i * 0.1 + 0.005, 1000 + i * 100)
    assert c.offset == pytest.approx(69.005, abs=0.01) and c.resets == 1
    for i in range(70, 90):                                # stepped forward by 30 s (1 s to be sure)
        c.update(100.0 + i * 0.1 + 0.005, 1000 + i * 100)
    assert c.offset == pytest.approx(99.005, abs=0.01) and c.resets == 2
    c.update(110.0, 200)                                   # camera restarted: ms from 0 again
    assert c.offset == pytest.approx(109.8) and c.resets == 3


# ── bias at rest ─────────────────────────────────────────────────────────
def test_bias_measured_at_rest_not_while_turning():
    rng = np.random.default_rng(5)
    bias = np.radians([0.2, -0.1, 0.05])
    b = ii.BiasAtRest(np.zeros(3))
    for _ in range(1000):                                  # 2 s turning at 0.5 rad/s: no estimate
        b.add(np.array([0.5, 0, 0]) + rng.normal(0, 0.001, 3) * np.arange(1, 4) * rng.uniform(0, 3), [1, 0, 0])
    assert not b.calibrated
    for _ in range(1100):
        b.add(bias + rng.normal(0, np.radians(0.08), 3), np.array([1, 0, 0]) + rng.normal(0, 0.002, 3))
    assert b.calibrated
    assert np.degrees(b.bias - bias) == pytest.approx([0, 0, 0], abs=0.01)
    off = ii.BiasAtRest(np.ones(3), enabled=False)
    off.add(np.zeros(3), np.zeros(3))
    assert not off.calibrated and list(off.bias) == [1, 1, 1]


# ── stream and replay ────────────────────────────────────────────────────
def test_replay_of_a_raw_recording_gives_body_samples_on_the_host_clock(tmp_path):
    host0, cam0 = 1000.0, 50_000
    rate = np.radians(10.0)                                # a turn about the camera's up axis
    write_raw(tmp_path / "raw360_0000.bin", synthetic_session(6.0, host0, cam0, gyro=(rate, 0.0, 0.0)))
    st = ii.ImuStream(ii.mount_rotation(), decimation=5, calibration=CAL0, bias_at_rest=False)
    out = [s for t, p in ii.replay_packets(str(tmp_path), rate=0, clock="recorded") for s in st.feed(t, p)]
    assert len(out) >= 6 * 100 - 2 and st.records == 3000
    t = np.array([s.t for s in out])
    assert np.all(np.diff(t) > 0)
    true_t = host0 + np.array([s.cam_ms for s in out]) / 1000.0
    assert np.abs(t - true_t)[-300:].max() < 0.004        # the least delayed packet: 2 ms + slack
    acc = np.mean([s.accel for s in out], axis=0)
    assert acc == pytest.approx([0, 0, ii.G], abs=0.01)    # standing camera: gravity on body z
    assert np.mean([s.gyro for s in out], axis=0) == pytest.approx([0, 0, rate], abs=1e-3)


def test_replay_clock_now_and_pacing(tmp_path):
    rec = synthetic_session(2.0, 500.0)
    write_raw(tmp_path / "raw360_0000.bin", rec)
    clock = {"t": 9000.0}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    got = list(ii.replay_packets(str(tmp_path / "raw360_0000.bin"), rate=2.0, clock="now",
                                 now=lambda: clock["t"], sleep=sleep))
    assert len(got) == 20                                  # IMU packets only
    assert got[0][0] == pytest.approx(9000.0)
    assert got[-1][0] - got[0][0] == pytest.approx(rec[-2][0] - rec[0][0])   # recording timeline kept
    assert sum(sleeps) == pytest.approx((rec[-2][0] - rec[0][0]) / 2.0)      # paced at twice real time
    with pytest.raises(ValueError):
        next(ii.replay_packets(str(tmp_path), clock="gps"))


def test_camera_restart_in_a_stream():
    st = ii.ImuStream(np.eye(3), decimation=5, calibration=CAL0, bias_at_rest=False)
    out = []
    for i in range(10):
        out += st.feed(100.0 + 0.1 * i + 0.1, imu_packet(50_000 + 100 * i))
    for i in range(10):                                    # the camera restarted 1 s later, ms from 0
        out += st.feed(102.0 + 0.1 * i + 0.1, imu_packet(100 * i))
    t = [s.t for s in out]
    assert all(b > a for a, b in zip(t, t[1:])) and st.clock.resets == 1


@pytest.mark.skipif(not os.path.isdir(REAL), reason="field recording 2026-10-20_1150 not on this machine")
def test_real_recording_at_rest():
    st = ii.ImuStream(ii.mount_rotation(), decimation=5)
    out = [s for t, p in ii.replay_packets(REAL, rate=0, clock="recorded") for s in st.feed(t, p)]
    t = np.array([s.t for s in out])
    assert len(out) == 4100 and st.dropped_backwards == 0 and np.all(np.diff(t) > 0)
    assert len(out) / (t[-1] - t[0]) == pytest.approx(99.5, abs=0.5)
    assert np.mean([s.accel for s in out], axis=0)[2] == pytest.approx(ii.G, abs=0.05)
    assert st.bias.calibrated
    assert abs(math.degrees(np.mean([s.gyro[2] for s in out]))) < 0.01     # heading rate after the bias
    c = ii.characterize(ii.raw_imu_rows(REAL))
    assert max(c["gyro_noise_dps_rthz"]) < 0.005


def test_allan_deviation_of_white_noise():
    rng = np.random.default_rng(0)
    fs, sigma = 500.0, 0.08
    x = rng.normal(0, sigma, 200_000)
    ad = ii.allan_deviation(x, fs, [0.1, 1.0, 1000.0])
    assert ad[0] == pytest.approx(sigma / math.sqrt(fs * 0.1), rel=0.05)
    assert ad[1] == pytest.approx(sigma / math.sqrt(fs * 1.0), rel=0.1)
    assert math.isnan(ad[2])


def test_covariance_from_noise():
    cov = ii.covariance_diag(0.01, 5)
    assert cov[0] == cov[4] == cov[8] == pytest.approx(2e-5) and cov[1] == 0.0


# ── live source with a fake camera ───────────────────────────────────────
class FakeUsb:
    class USBTimeoutError(Exception):
        pass

    def __init__(self, chunks):
        self.chunks, self.written = list(chunks), []
        self.dev = self

    def find(self, idVendor):
        assert idVendor == proto.VENDOR
        return self

    def claim_interface(self, dev, n):
        pass

    release_interface = claim_interface

    def dispose_resources(self, dev):
        pass

    def write(self, ep, data, timeout):
        self.written.append(data)

    def read(self, ep, size, timeout):
        if not self.chunks:
            time.sleep(0.01)
            raise FakeUsb.USBTimeoutError()
        return self.chunks.pop(0)


def test_live_source_with_a_fake_camera():
    data = b"".join(proto.frame_packet(p) for p in (imu_packet(0), video_packet(0), imu_packet(100)))
    fake = FakeUsb([data[:1000], data[1000:]])             # a packet split across two USB reads
    got, done = [], threading.Event()

    def on_packet(t, p):
        got.append(p)
        if len(got) == 3:
            done.set()

    src = ii.UsbImuSource(on_packet, usb_core=fake, usb_util=fake)
    assert done.wait(2.0)
    src.close()
    assert [proto.stream_kind(p)[0] for p in got] == [proto.KIND_IMU, proto.KIND_VIDEO, proto.KIND_IMU]
    assert fake.written[0] == proto.frame_packet(proto.PKT_SYNC)
    assert fake.written[1] == proto.frame_packet(proto.message_payload(proto.CMD_START_LIVE, 1, proto.START_FULL))
    assert fake.written[-1] == proto.frame_packet(proto.message_payload(proto.CMD_STOP_LIVE, 2, b""))


# ── the ROS node ─────────────────────────────────────────────────────────
def test_node_replays_a_recording(tmp_path):
    rclpy = pytest.importorskip("rclpy")
    from rclpy.parameter import Parameter
    from sensor_msgs.msg import Imu
    from camera_pkg.nodes.insta360_imu_node import Insta360ImuNode

    write_raw(tmp_path / "raw360_0000.bin", synthetic_session(2.0, 2000.0))
    rclpy.init()
    try:
        sub_node = rclpy.create_node("insta360_imu_test")
        msgs = []
        sub_node.create_subscription(Imu, "/test/insta360/imu", msgs.append, 500)
        node = Insta360ImuNode(parameter_overrides=[         # real-time replay of 2 s, original stamps
            Parameter("replay_path", value=str(tmp_path)), Parameter("replay_clock", value="recorded"),
            Parameter("topic", value="/test/insta360/imu"),
            Parameter("calibration_file", value=str(tmp_path / "none.json"))])
        deadline = time.time() + 10.0
        while time.time() < deadline and (not node.finished.is_set() or len(msgs) < node.published):
            rclpy.spin_once(sub_node, timeout_sec=0.05)
        assert node.finished.is_set() and node.published >= 195
        assert len(msgs) >= 0.8 * node.published                 # all but those before discovery
        m = msgs[-1]
        assert m.header.frame_id == "insta360_imu_link" and m.orientation_covariance[0] == -1.0
        assert m.linear_acceleration.z == pytest.approx(ii.G, abs=0.05)
        assert m.angular_velocity_covariance[0] == pytest.approx(math.radians(0.085) ** 2 / 5)
        assert m.header.stamp.sec + m.header.stamp.nanosec * 1e-9 == pytest.approx(2000.0 + 50.0 + 1.998, abs=0.01)
        node.close()
        node.destroy_node()
        sub_node.destroy_node()
    finally:
        rclpy.shutdown()
