"""The Insta360 kit: attitude from the camera's own IMU (synthetic motion with truth, a real
recording at rest), the body-fixed nadir view from the dual fisheye, the kit's packet handling
(exposure stamps, key frames, a real H.264 frame), the heading sources, and the settings."""
import math
import os
import struct
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from navera_common import insta360_protocol as proto  # noqa: E402
from camera_pkg import insta360_attitude as att  # noqa: E402
from camera_pkg import insta360_imu as ii  # noqa: E402
from camera_pkg import insta360_kit as kit  # noqa: E402
from camera_pkg import insta360_view as view  # noqa: E402

motion = pytest.importorskip("navera_tools.sim.insta360_motion")
REAL = os.path.expanduser("~/navera-field/2026-10-20_1150/raw")
CAL0 = (np.zeros(3), np.ones(3), np.zeros(3))
LYING = "+x,+z,-y"


def run(m, speed=False, flt=None, every=None):
    """Feed a synthetic Motion (100 Hz means) to a filter; per-sample (t, tilt error, state)."""
    t, w, f = motion.decimate(m)
    flt = flt or att.AttitudeFilter()
    out = []
    for i in range(len(t)):
        j = i * 5 + 2
        sp = (m.speed[j], m.accel_fwd[j]) if speed else (None, None)
        s = flt.update(t[i], w[i], f[i], *sp)
        if every is not None:
            every(i, t[i], flt)
        if s is not None:
            out.append((t[i], motion.tilt_error_deg(m.R[j], flt.R), s))
    return flt, out


# ── attitude ─────────────────────────────────────────────────────────────
def test_still_camera_level_and_no_heading():
    m = motion.simulate("still", 30.0, seed=3)
    flt, out = run(m)
    errs = [e for t, e, _ in out if t > 1]
    assert max(errs) < 0.2
    last = out[-1][2]
    assert last.still and math.isinf(last.heading_sigma_deg)
    cov = last.covariance()
    assert cov[8] == pytest.approx(math.pi ** 2) and cov[0] == pytest.approx(math.radians(last.tilt_sigma_deg) ** 2)


def test_first_tilt_from_the_accelerometer():
    R = att.tilt_from_up(np.array([0.0, 0.0, 1.0]))
    true = motion._rz(np.array(0.3)) @ motion._ry(np.array(math.radians(-5))) @ motion._rx(np.array(math.radians(10)))
    f = true.T @ np.array([0.0, 0.0, att.G])
    flt = att.AttitudeFilter()
    for k in range(80):
        s = flt.update(k * 0.01, np.zeros(3), f)
    assert s.roll_deg == pytest.approx(10.0, abs=0.05) and s.pitch_deg == pytest.approx(-5.0, abs=0.05)
    assert R.shape == (3, 3)


@pytest.mark.parametrize("profile,secs,speed,max_err", [
    ("uav_survey", 200, True, 1.0), ("uav_survey", 200, False, 2.0),
    ("copter", 110, True, 1.0), ("copter", 110, False, 2.5),
    ("car", 120, True, 0.6), ("car", 120, False, 2.5)])
def test_moving_tilt_within_bounds_and_sigma_honest(profile, secs, speed, max_err):
    """Synthetic motion with the measured noise and a gyro bias left after the bias at rest; the
    tilt error stays bounded and inside 3 stated sigma (>= 95 % of the samples)."""
    m = motion.simulate(profile, secs, seed=7)
    _, out = run(m, speed=speed)
    e = np.array([x[1] for x in out if x[0] > 2])
    s = np.array([x[2].tilt_sigma_deg for x in out if x[0] > 2])
    assert e.max() < max_err
    assert np.mean(e <= 3 * s) >= 0.95


def test_coordinated_turn_trap_is_rejected():
    """In a coordinated turn the accelerometer reads 'level' while banked (D8): trusting it
    blindly levels the estimate; the gates keep the gyro's bank."""
    m = motion.simulate("uav_steep", 120, seed=2)
    _, blind = run(m, flt=att.AttitudeFilter(acc_gate_g=1.0, turn_gate_dps=1e6, rate_gate_dps=1e6, kp=0.2))
    _, gated = run(m)
    assert max(x[1] for x in blind) > 5.0
    assert max(x[1] for x in gated if x[0] > 2) < 2.5


def test_gap_forgets_the_heading_and_grows_the_tilt_sigma():
    flt = att.AttitudeFilter()
    f = np.array([0.0, 0.0, att.G])
    for k in range(100):
        flt.update(k * 0.01, np.zeros(3), f)
    assert flt.set_heading(0.9, 45.0, 2.0, "vision")
    s0 = flt.tilt_sigma
    s = flt.update(2.0, np.zeros(3), f)          # 1 s without samples
    assert math.isinf(s.heading_sigma_deg) and s.tilt_sigma_deg > s0 and flt.gaps == 1


# ── heading ──────────────────────────────────────────────────────────────
def _track(m, hz=5.0, lat0=36.8, lon0=10.2):
    step = int(round(500 / hz))
    for j in range(0, len(m.t), step):
        lat = lat0 + m.north[j] / 111_320.0
        lon = lon0 + m.east[j] / (111_320.0 * math.cos(math.radians(lat0)))
        yield m.t[j], lat, lon


def test_heading_from_gps_course_then_carried_and_vision_corrections():
    m = motion.simulate("uav_survey", 120, seed=4)
    course = att.GpsCourse()
    fixes = list(_track(m))
    k = [0]
    hist = []

    def every(i, t, flt):
        while k[0] < len(fixes) and fixes[k[0]][0] <= t:
            course.add_fix(*fixes[k[0]])
            course.maybe_set(flt)
            k[0] += 1
        s = flt.heading_sigma(t)
        if math.isfinite(s):
            hist.append((t, abs(att._wrap(att.heading_of(flt.R) - m.heading[i * 5 + 2])), s))

    flt, _ = run(m, speed=True, every=every)
    assert course.sets >= 1 and hist and hist[0][0] < 10.0                 # set on the first straight leg
    errs = np.array([h[1] for h in hist])
    sig = np.array([h[2] for h in hist])
    assert errs.max() < 5.0 and np.mean(errs <= 3 * sig) > 0.99          # course sigma 10 deg (crab)
    t = m.t[-1]
    # a vision heading: taken (blended), tighter sigma
    true_h = m.heading[-1]
    assert flt.set_heading(t, true_h, 2.0, "vision")
    assert flt.heading_sigma(t) < 2.0 and abs(att._wrap(att.heading_of(flt.R) - true_h)) < 1.0
    # a wrong-place match's rotation 60 deg off: refused
    assert not flt.set_heading(t, true_h + 60.0, 2.0, "vision")
    # the sigma grows with time (bias x time)
    assert flt.heading_sigma(t + 100.0) > 5.0


def test_course_ignored_when_turning_or_slow():
    m = motion.simulate("car", 40, seed=1)                                 # 0-10 s standing, then 15 m/s
    course = att.GpsCourse()
    flt, _ = run(m)
    for fx in _track(m):
        if fx[0] < 9.0:
            course.add_fix(*fx)
    assert course.maybe_set(flt) is None                                  # standing: no course


def test_vision_heading_pairs_status_with_its_frame():
    from camera_pkg.nodes.insta360_node import frame_top_offset_deg, vision_heading
    meta = {"frame_id": 7, "image_stamp_ns": 1_000_500_000_000}
    assert vision_heading(meta, {"success": True, "rotation_deg": 370.0, "inliers": 40}, 20) == (1000.5, 10.0)
    assert vision_heading(meta, {"success": True, "rotation_deg": 10.0, "inliers": 8}, 20) is None
    assert vision_heading(meta, {"success": False, "rotation_deg": 10.0, "inliers": 80}, 20) is None
    R = att.tilt_from_up(np.array([0.0, 0.0, 1.0]), heading_deg=33.0)
    assert abs(frame_top_offset_deg(R)) < 1e-6
    Rt = att.tilt_from_up(np.array([0.1, 0.05, 1.0]), heading_deg=250.0)
    assert abs(frame_top_offset_deg(Rt)) < 1.0


# ── the nadir view ───────────────────────────────────────────────────────
def lenses():
    L, src = view.load_lenses("/nonexistent")
    for x in L:                                                          # the 2026-10-19 calibration
        x.f, x.k1 = (560.87, 0.05386) if x.name == "left" else (555.61, 0.06896)
        x.cx, x.cy = (960.78, 959.43) if x.name == "left" else (2871.72, 962.63)
    return L


def test_lying_mount_looks_through_the_left_lens_centre():
    R = ii.mount_rotation(LYING)
    v = view.NadirView(lenses(), R, 100.0, 120, 90)
    assert v.coverage == 1.0 and v.centre_lens == "left" and v.centre_theta_deg < 1.0
    assert v.warning() is None
    # the centre pixel samples the left circle's centre
    assert v.mx[45, 60] == pytest.approx(960.78, abs=6) and v.my[45, 60] == pytest.approx(959.43, abs=6)
    # body forward (image top) is the camera's +x: in the left circle the camera top is image-left
    assert v.mx[0, 60] < v.mx[89, 60] or abs(v.mx[0, 60] - v.mx[89, 60]) > 50


def test_standing_mount_is_warned():
    v = view.NadirView(lenses(), ii.mount_rotation("+y,+z,+x"), 100.0, 120, 90)
    assert v.warning() is not None


def test_view_matches_the_celestial_lens_model():
    sky = pytest.importorskip("cn_pkg.sky360")
    L = lenses()
    S = sky.default_lenses("/nonexistent")
    for a, b in zip(L, S):
        b.f, b.k1, b.cx, b.cy = a.f, a.k1, a.cx, a.cy
        ray = np.array([[0.3, -0.2, 0.9]])
        pa = a.project(ray @ a.R_lens_imu.T)
        pb = b.project(ray @ b.R_lens_imu.T)
        assert np.allclose(pa[0], pb[0]) and np.allclose(pa[1], pb[1])


def test_view_samples_a_ground_point_where_the_lens_sees_it():
    """A point on the ground ahead-right of the camera lands in the view's right half, upper part."""
    R = ii.mount_rotation(LYING)
    v = view.NadirView(lenses(), R, 100.0, 300, 300)
    frame = np.zeros((view.FRAME_H, view.FRAME_W, 3), np.uint8)
    L = lenses()[0]
    ray_body = np.array([0.3, -0.3, -1.0])                               # forward, right, down
    x, y, _ = L.project((R.T @ ray_body) @ L.R_lens_imu.T)
    import cv2
    cv2.circle(frame, (int(round(float(x))), int(round(float(y)))), 6, (255, 255, 255), -1)
    out = v.apply(frame)
    ys, xs = np.nonzero(out[..., 0] > 128)
    assert len(xs) and xs.mean() > 150 and ys.mean() < 150


# ── the kit: packets, stamps, frames ─────────────────────────────────────
def imu_packet(ms0, n=50, accel=(0.0, 0.0, 0.0), gyro=(0.0, 0.0, 0.0)):
    body = b"".join(proto.IMU_RECORD.pack(ms0 + 2 * k, *accel, *gyro) for k in range(n))
    return b"\x01\x00\x00" + bytes([proto.KIND_IMU]) + struct.pack("<I", ms0) + b"\x00" * 4 + body


def make_kit(decoded):
    R = ii.mount_rotation(LYING)
    stream = ii.ImuStream(R, 5, CAL0, bias_at_rest=False)
    return kit.Insta360Kit(stream, att.AttitudeFilter(), view.NadirView(lenses(), R, 100.0, 60, 45),
                           decoder_factory=lambda: (lambda data: [decoded]))


def test_kit_publishes_attitude_and_stamps_frames_at_exposure():
    full = np.full((view.FRAME_H, view.FRAME_W, 3), 90, np.uint8)
    k = make_kit(full)
    host0, cam0 = 5000.0, 100_000
    # lying, left lens down: camera -y is up, so the accelerometer reads -1 g on y
    out = []
    for i in range(20):
        ms0 = cam0 + 100 * i
        out += k.feed(host0 + (ms0 + 98) / 1000.0, imu_packet(ms0, accel=(0.0, -1.0, 0.0)))
    assert out and abs(out[-1][1].roll_deg) < 0.1 and abs(out[-1][1].pitch_deg) < 0.1
    vid = kit.video_packet(cam0 + 1900, b"\x00\x00\x00\x01\x67xx\x00\x00\x01\x65yy")
    pframe = kit.video_packet(cam0 + 1950, b"\x00\x00\x00\x01\x41zz")
    k.feed(host0 + 2.0, vid)
    k.feed(host0 + 2.05, pframe)                                          # not a key frame: skipped
    frames = k.decode_pending()
    assert k.keyframes == 1 and len(frames) == 1
    fr = frames[0]
    assert fr.image.shape == (45, 60, 3) and fr.full_shape == (view.FRAME_H, view.FRAME_W)
    # exposure = the key frame's own packet camera ms - its lag (0 ms: 1.5 s measured through a
    # 3-key-frame decoder delay, 3 x 500 ms), on the host clock of the IMU packets
    assert kit.KIT_EXPOSURE_LAG_MS == proto.FRAME_STAMP_LAG_MS - 3 * 500
    assert fr.t == pytest.approx(host0 + (cam0 + 1900 - kit.KIT_EXPOSURE_LAG_MS) / 1000.0, abs=0.01)


def test_kit_drops_frames_before_the_clock_is_known():
    k = make_kit(np.zeros((view.FRAME_H, view.FRAME_W, 3), np.uint8))
    k.feed(1.0, kit.video_packet(5000, b"\x00\x00\x01\x65aa"))
    assert k.decode_pending() == [] and k.unstamped == 1


def test_real_h264_key_frame_decodes_into_the_view():
    av = pytest.importorskip("av")
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = view.FRAME_W, view.FRAME_H, "yuv420p"
    enc.options = {"preset": "ultrafast", "tune": "zerolatency"}
    img = np.zeros((view.FRAME_H, view.FRAME_W, 3), np.uint8)
    img[:, :1920] = (0, 200, 0)                                           # left circle green
    data = b""
    for fr in [av.VideoFrame.from_ndarray(img, format="bgr24")]:
        for p in enc.encode(fr):
            data += bytes(p)
    for p in enc.encode(None):
        data += bytes(p)
    R = ii.mount_rotation(LYING)
    k = kit.Insta360Kit(ii.ImuStream(R, 5, CAL0, bias_at_rest=False), att.AttitudeFilter(),
                        view.NadirView(lenses(), R, 100.0, 60, 45))
    k.feed(10.0, imu_packet(1000, accel=(0.0, -1.0, 0.0)))
    k.feed(12.0, kit.video_packet(3000, data))
    frames = k.decode_pending()
    assert len(frames) == 1 and frames[0].image[22, 30, 1] > 150          # the view sees the left lens


def test_replay_all_gives_every_packet(tmp_path):
    recs = [(100.0 + 0.1 * i, imu_packet(1000 + 100 * i)) for i in range(5)]
    recs.insert(2, (100.15, kit.video_packet(1150, b"\x00\x00\x01\x65aa")))
    path = tmp_path / "raw360_0000.bin"
    with open(path, "wb") as f:
        f.write(proto.RAW_MAGIC)
        for t, p in recs:
            kind, ms = proto.stream_kind(p)
            f.write(proto.RAW_RECORD.pack(t, kind, ms, len(p)))
            f.write(p)
    got = list(kit.replay_all(str(tmp_path), rate=0, clock="recorded"))
    assert [g[0] for g in got] == [r[0] for r in recs]


@pytest.mark.skipif(not os.path.isdir(REAL), reason="real recording not on this machine")
def test_real_recording_at_rest_attitude_steady_and_frames_stamped():
    """The user's One R standing on a table (2026-10-20, 41 s): the attitude is steady, the yaw
    drifts little, every key frame is stamped at its exposure inside the IMU's span."""
    R = ii.mount_rotation("+y,+z,+x")                                     # standing, as recorded
    stream = ii.ImuStream(R, 5, proto.load_imu_calibration(), bias_at_rest=True)
    flt = att.AttitudeFilter()
    k = kit.Insta360Kit(stream, flt, view.NadirView(lenses(), R, 60.0, 64, 48))
    states, frames = [], []
    for t, p in kit.replay_all(REAL, rate=0, clock="recorded"):
        states += [s for _, s in k.feed(t, p)]
        frames += k.decode_pending()
    rolls = np.array([s.roll_deg for s in states[300:]])
    pitches = np.array([s.pitch_deg for s in states[300:]])
    heads = np.array([s.heading_deg for s in states[300:]])
    assert rolls.std() < 0.05 and pitches.std() < 0.05
    assert abs(att._wrap(heads[-1] - heads[0])) < 0.5
    assert len(frames) >= 30 and all(states[0].t - 2.0 < f.t < states[-1].t for f in frames)


# ── settings and the live camera ─────────────────────────────────────────
def test_settings_for_the_kit():
    from navera_common.vehicle import insta360_camera_params, insta360_kit_params, sensor_topics
    env = {"NAVERA_SENSOR_SOURCE": "insta360", "NAVERA_CAMERA_INPUT": "insta360"}
    t = sensor_topics(env)
    assert t["imu_topic"] == "/navera/sensors/insta360/imu" and t["attitude_source"] == "insta360"
    p = insta360_camera_params(env)
    assert p["input"] == "insta360" and p["input_topic"].endswith("nadir/image_raw")
    assert (p["width"], p["height"], p["camera_hfov_deg"]) == (1200, 900, 100.0)
    assert insta360_kit_params({})["mount_axes"] == LYING
    with pytest.raises(ValueError):
        insta360_camera_params(dict(env, NAVERA_CAMERA_MOUNT_RPY="0,-20,0"))
    with pytest.raises(ValueError):
        insta360_kit_params({"NAVERA_INSTA360_MOUNT_AXES": "+x,+y,-z"})        # a mirror
    with pytest.raises(ValueError):
        insta360_kit_params({"NAVERA_INSTA360_MOUNT_AXES": "+x,+x,+z"})


def test_live_camera_drops_a_heading_the_attitude_does_not_know():
    pytest.importorskip("rclpy")
    from camera_pkg.nodes.live_camera import LiveCamera
    from navera_common.sensor_history import History
    h = History(max_gap_s=0.2)
    for i in range(10):
        h.add(100.0 + 0.01 * i, 180.0 if i < 5 else 1.5)
    me = SimpleNamespace(yaw_sigma=h, max_heading_sigma=5.0)
    meta = {"heading_deg": 12.0}
    LiveCamera._check_heading(me, meta, 100.02)
    assert meta["heading_deg"] is None and meta["heading_sigma_deg"] == 180.0
    meta = {"heading_deg": 12.0}
    LiveCamera._check_heading(me, meta, 100.08)
    assert meta["heading_deg"] == 12.0
