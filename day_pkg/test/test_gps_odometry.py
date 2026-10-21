"""Visual odometry published while GPS is trusted (gps_vo_*): the estimator's relative-motion test."""
import json
import math
from types import MethodType, SimpleNamespace

import numpy as np

from day_pkg.frame_odometry import FrameOdometry
from day_pkg.nodes.day_subscriber import DaySubscriber

MPP = 2.0          # m per frame pixel at the stated altitude


def _node(period=1.0, tau=60.0):
    out = []
    n = SimpleNamespace(gps_vo_enabled=True, gps_vo_period_s=period, gps_vo_width_px=1280,
                        gps_vo_height_tau_s=tau, gps_vo=FrameOdometry(scale=1.0), _gps_vo_t=None, _gps_vo_h=None,
                        pub_gps_vo=SimpleNamespace(publish=lambda m: out.append(json.loads(m.data))))
    n._frame_m_per_px = lambda img, meta: (MPP * float(meta["altitude_m"]) / 100.0, None)
    n._carry_heading = lambda meta: (0.0, 0.0)
    n._gps_odometry = MethodType(DaySubscriber._gps_odometry, n)
    return n, out


def _ground(shift_px):
    """A textured 480 x 640 view of the ground, the camera moved shift_px pixels north (heading 0)."""
    rng = np.random.default_rng(5)
    big = rng.random((900, 900)).astype(np.float32)
    big = (255 * (big - big.min()) / (big.max() - big.min())).astype(np.uint8)
    y0 = 200 - int(shift_px)
    return np.ascontiguousarray(big[y0:y0 + 480, 100:740])


def test_one_step_per_period_with_its_displacement_and_instants():
    n, out = _node(period=1.0)
    for k, t in enumerate((10.0, 10.5, 11.0, 12.0)):
        n._gps_odometry(_ground(5 * k), {"image_stamp_ns": int(t * 1e9), "altitude_m": 100.0})
    # 10.5 is inside the period: 10 -> 11 (10 px = 20 m north), then 11 -> 12 (5 px = 10 m)
    assert [(o["t0"], o["t1"]) for o in out] == [(10.0, 11.0), (11.0, 12.0)]
    assert math.hypot(out[0]["east_m"], out[0]["north_m"] - 20.0) < 1.0
    assert math.hypot(out[1]["east_m"], out[1]["north_m"] - 10.0) < 1.0


def test_a_jump_in_the_height_estimate_is_not_a_jump_in_the_odometry():
    n, out = _node(period=0.0, tau=60.0)
    for k in range(3):
        alt = 100.0 if k < 2 else 110.0        # the height estimate jumps 10 % (the ground did not move)
        n._gps_odometry(_ground(5 * k), {"image_stamp_ns": int((10.0 + k) * 1e9), "altitude_m": alt})
    assert abs(out[1]["north_m"] - 10.0) < 1.0      # 10 % at once would read 11 m


def test_no_heading_or_no_stamp_publishes_nothing():
    n, out = _node(period=0.0)
    n._carry_heading = lambda meta: (None, 0.0)
    for k in range(3):
        n._gps_odometry(_ground(5 * k), {"image_stamp_ns": int((10.0 + k) * 1e9), "altitude_m": 100.0})
    n, out2 = _node(period=0.0)
    for k in range(3):
        n._gps_odometry(_ground(5 * k), {"altitude_m": 100.0})
    assert out == [] and out2 == []
