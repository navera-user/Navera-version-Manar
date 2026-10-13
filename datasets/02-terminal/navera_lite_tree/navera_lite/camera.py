"""navera_lite/camera.py — pinhole and fisheye camera models, timing.

Part of NAVERA Lite, the course's teaching stack (mission 18). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 18.
"""


def K_from_hfov(hfov_deg, w, h):
    """The camera matrix K."""
    ...


def gsd(h_m, hfov_deg, w_px):
    """Metres per pixel."""
    ...


def attitude_at(t, imu_t, imu_q, max_gap_s=0.2):
    """The attitude when a frame was taken (mission 20)."""
    ...
