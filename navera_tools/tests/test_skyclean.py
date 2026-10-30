"""cn_pkg.skyclean (SYNTHETIC frames): static junk removed, moving stars kept, cloud blocks blanked, nothing added."""
import numpy as np

from cn_pkg import skyclean


def _gauss(img, x, y, amp, s=1.0):
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    img += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s))


def _frame(rng, t, star=True, cloud=False):
    f = 10.0 + rng.normal(0, 1.0, (256, 384)).astype(np.float32)
    _gauss(f, 60, 60, 12.0)                     # a lamp / hot spot fixed to the camera
    f[200, 300] += 30.0                         # a hot pixel
    if star:
        _gauss(f, 100 + 0.04 * t, 150, 8.0)     # a star drifting 2.4 px per minute
    if cloud:
        c = rng.normal(0, 1.0, (256 // 8, 384 // 8)).astype(np.float32)
        import cv2
        f[:, 192:] += 6.0 * cv2.resize(c, (384, 256), interpolation=cv2.INTER_CUBIC)[:, 192:]
    return np.clip(np.rint(f), 0, 255).astype(np.uint8)


def _ring(rng, cloud=False):
    cl = skyclean.SkyCleaner(gap_s=45.0)
    for i in range(12):
        cl.add(_frame(rng, i * 45.0, cloud=cloud), i * 45.0)
    return cl


def test_not_ready_returns_the_frame_unchanged():
    rng = np.random.default_rng(1)
    cl = skyclean.SkyCleaner()
    f = _frame(rng, 0.0)
    out, info = cl.clean(f, 0.0)
    assert not info["static"] and np.array_equal(out, f.astype(np.float32))


def test_static_junk_removed_star_kept_and_nothing_added():
    rng = np.random.default_rng(2)
    cl = _ring(rng)
    t = 12 * 45.0 + 60.0
    f = _frame(rng, t)
    out, info = cl.clean(f, t)
    assert info["static"] and info["ring_used"] >= skyclean.RING_MIN_FRAMES
    assert np.all(out <= f.astype(np.float32) + 1e-4)            # never more light than the input
    lamp_before = float(f[55:66, 55:66].max()) - 10.0
    lamp_after = float(out[55:66, 55:66].max()) - 10.0
    assert lamp_after < 0.4 * lamp_before
    assert out[200, 300] < 20.0                                   # hot pixel gone
    sx = int(round(100 + 0.04 * t))
    assert out[150, sx] - 10.0 > 6.0                              # the moving star keeps most of its peak


def test_moving_cloud_blocks_are_blanked():
    rng = np.random.default_rng(3)
    cl = _ring(rng, cloud=True)
    t = 12 * 45.0 + 60.0
    f = _frame(rng, t, cloud=True)
    out, info = cl.clean(f, t)
    assert info["cloud_frac"] > 0.3
    assert np.all(out <= f.astype(np.float32) + 1e-4)
    # the clear half keeps its star
    assert out[150, int(round(100 + 0.04 * t))] - 10.0 > 6.0


def test_clear_noise_is_not_called_cloud():
    rng = np.random.default_rng(4)
    cl = _ring(rng)
    t = 12 * 45.0 + 60.0
    _, info = cl.clean(_frame(rng, t), t)
    assert info["cloud_frac"] == 0.0


def test_ring_reset_on_shape_change_and_gap():
    cl = skyclean.SkyCleaner(gap_s=45.0)
    a = np.zeros((32, 32), np.uint8)
    assert cl.add(a, 0.0) and not cl.add(a, 10.0) and cl.add(a, 50.0)
    assert cl.add(np.zeros((16, 16), np.uint8), 100.0) and len(cl.ring) == 1


def test_starlight_gate_blocks_noise_and_passes_stars():
    """forcedcheck.StarlightGate (SYNTHETIC 360 frames): noise only -> 'too cloudy / blocked'; catalogue at 4 DN
    (true place, heading 100) -> starlight seen at that heading."""
    from cn_pkg import sky360
    from cn_pkg.allsky_mount import zenith_icrs
    from navera_tools.field import forcedcheck
    lenses = sky360.default_lenses()
    up = lenses[1].R_lens_imu.T @ np.array([0.0, 0.0, 1.0])          # the right lens looks at the zenith
    utc, lat, lon = "2026-10-29 23:00:00", 35.83, 10.64
    rng = np.random.default_rng(5)
    noise = forcedcheck.StarlightGate(lenses, n_frames=3)
    stars = forcedcheck.StarlightGate(lenses, n_frames=3)
    vec, _ = forcedcheck.points(stars.cat, utc, lat, lon, 3.0)
    for _ in range(3):
        f = (8.0 + rng.normal(0, 1.0, (1920, 3840))).astype(np.float32)
        noise.add(f, up, utc, lat, lon)
        g = f.copy()
        for L in lenses:
            g = forcedcheck.inject(g, L, up, zenith_icrs(lat, lon, utc), 100.0, vec, 4.0)
        v = stars.add(g, up, utc, lat, lon)
    assert noise.reason() and "too cloudy / blocked" in noise.reason()
    assert v["starlight"] and stars.reason() is None and abs(v["heading_deg"] - 100.0) < 1.0


def test_field_server_starlight_reason_rewrites_only_the_why():
    """server.Field._starlight_reason (SYNTHETIC noise frames, still camera, fresh phone fix): after 3 unsolved
    frames the 'why' starts with 'too cloudy / blocked'; moving or without a phone fix nothing changes."""
    import time
    from types import SimpleNamespace
    from cn_pkg import sky360
    from navera_tools.field import server as sv
    up = sky360.default_lenses()[1].R_lens_imu.T @ np.array([0.0, 0.0, 1.0])
    f = SimpleNamespace(phone={"lat": 35.83, "lon": 10.64}, phone_recv=time.time(), starlight=None)
    rng = np.random.default_rng(6)
    rec = {}
    for _ in range(3):
        rec = {"why": "no star pattern identified", "stopped": True}
        sv.Field._starlight_reason(f, rec, (8.0 + rng.normal(0, 1.0, (1920, 3840))).astype(np.float32), up,
                                   "2026-10-29 23:00:00")
    assert rec["why"].startswith("too cloudy / blocked") and rec["why"].endswith("no star pattern identified")
    moving = {"why": "x", "stopped": False}
    sv.Field._starlight_reason(f, moving, np.zeros((1920, 3840), np.float32), up, "2026-10-29 23:00:00")
    assert moving == {"why": "x", "stopped": False} and len(f.starlight.ring) == 0
