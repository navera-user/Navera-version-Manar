"""Camera geometry shared by the camera node and the vision pipelines.

* CameraModel — the lens (pinhole or fisheye intrinsics from a calibration file,
  or an ideal lens from its horizontal field of view) and the distortion-free
  pinhole image NAVERA works on (`undistort`).
* Attitude — where the camera looks. Frames: world ENU, body FLU (REP-103: x
  forward, y left, z up), camera OpenCV (x right, y down, z = optical axis).
  A downward camera with no mounting offset has its image top towards the
  vehicle's nose.
* nadir_homography — straightens a tilted frame into the view of a level camera
  pointing straight down with the same heading. Its image centre is then the
  ground point under the camera, so a match locates the vehicle itself, not the
  ground the tilted camera looks at (150 m altitude, 10 deg pitch: 26 m apart).
* altitude_from_scale — the camera's height above the ground from the scale a
  map match measures (independent of GPS altitude and terrain).

Quaternions are (x, y, z, w), rotation matrices map the first named frame's
vectors into the second: R_world_cam @ v_cam = v_world.
"""
import math
from typing import Optional, Sequence, Tuple

import numpy as np

# camera axes expressed in the body frame, for a camera looking straight down:
# x_cam (image right) = body right (-y), y_cam (image down) = body back (-x),
# z_cam (optical axis) = body down (-z)
R_BODY_NADIR_CAM = np.array([[0.0, -1.0, 0.0],
                             [-1.0, 0.0, 0.0],
                             [0.0, 0.0, -1.0]])


def quat_to_matrix(q: Sequence[float]) -> np.ndarray:
    x, y, z, w = (float(c) for c in q)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if not n > 0:
        raise ValueError("invalid quaternion")
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Fixed-axis roll, pitch, yaw (rad), ROS convention: R = Rz(yaw) Ry(pitch) Rx(roll)."""
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch),
                              math.cos(yaw), math.sin(yaw))
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def body_rpy_enu(q: Sequence[float]) -> Tuple[float, float, float]:
    """(roll, pitch, heading) in degrees from a body ENU quaternion; heading clockwise
    from north, pitch positive nose up, roll positive right wing down."""
    R = quat_to_matrix(q)
    yaw = math.atan2(R[1, 0], R[0, 0])                       # ENU, counter-clockwise from east
    pitch = -math.asin(max(-1.0, min(1.0, R[2, 0])))         # FLU: +y left, nose up = negative rot about y
    roll = math.atan2(R[2, 1], R[2, 2])
    return math.degrees(roll), -math.degrees(pitch), (90.0 - math.degrees(yaw)) % 360.0


class CameraModel:
    """A lens and the undistorted pinhole image NAVERA works on.

    model 'pinhole' (OpenCV k1,k2,p1,p2[,k3]) or 'fisheye' (OpenCV k1..k4), K 3x3,
    for images of `size` (w, h). `ideal(hfov_deg, size)` is a distortion-free lens.
    The undistorted image keeps the same size; its horizontal field of view is
    `out_hfov_deg` (default: the field of view of the central row, slightly
    cropped so no black border shows; never wider than max_out_hfov_deg(), which keeps
    the lens' resolution at the centre)."""

    def __init__(self, K, D, size: Tuple[int, int], model: str = "pinhole",
                 out_hfov_deg: Optional[float] = None, balance: float = 0.0):
        if model not in ("pinhole", "fisheye"):
            raise ValueError("model must be 'pinhole' or 'fisheye'")
        self.K = np.asarray(K, dtype=float).reshape(3, 3)
        self.D = np.asarray(D if D is not None else [], dtype=float).ravel()
        self.size, self.model = (int(size[0]), int(size[1])), model
        self._maps = None
        w, h = self.size
        if out_hfov_deg is None:
            out_hfov_deg = self._native_hfov_deg() * (1.0 - 0.06 * (1.0 - balance) if self.D.any() else 1.0)
        if self.D.any():
            # a straight (pinhole) image of a very wide lens stretches its edges and shrinks
            # its centre: wider than 2 atan(w/2 / fx), the centre has fewer pixels per degree
            # than the lens gives (a 166 deg fisheye shown 169 deg wide: 7x fewer) — the
            # matcher needs the centre's detail more than the far edges
            out_hfov_deg = min(float(out_hfov_deg), self.max_out_hfov_deg())
        f = (w / 2.0) / math.tan(math.radians(out_hfov_deg) / 2.0)
        self.K_out = np.array([[f, 0.0, w / 2.0], [0.0, f, h / 2.0], [0.0, 0.0, 1.0]])
        self.out_hfov_deg = float(out_hfov_deg)

    @classmethod
    def ideal(cls, hfov_deg: float, size: Tuple[int, int]) -> "CameraModel":
        w, h = int(size[0]), int(size[1])
        f = (w / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        return cls([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1]], [], (w, h), "pinhole", hfov_deg)

    @classmethod
    def from_calibration(cls, d: dict) -> "CameraModel":
        """From a calibration dict (navera_tools/calibrate_camera.py writes it as YAML):
        {model, image_width, image_height, camera_matrix: [9], distortion: [n]}."""
        try:
            return cls(d["camera_matrix"], d.get("distortion", []),
                       (d["image_width"], d["image_height"]), d.get("model", "pinhole"),
                       d.get("out_hfov_deg"))
        except KeyError as e:
            raise ValueError(f"calibration file: missing {e}") from None

    def max_out_hfov_deg(self) -> float:
        """The widest undistorted view keeping the lens' own resolution at the centre."""
        return math.degrees(2.0 * math.atan((self.size[0] / 2.0) / self.K[0, 0]))

    def _native_hfov_deg(self) -> float:
        """Horizontal field of view of the lens along the central image row. A fisheye's angle
        comes from its own model (theta_d = theta (1 + k1 theta^2 + ...)), up to the angle where
        that model stops increasing: past it OpenCV returns -1e6 and the Insta360 strip read
        180 deg (its rows reach beyond what its calibration describes)."""
        w, h = self.size
        if self.model == "fisheye":
            return math.degrees(self._fisheye_theta(abs(self.K[0, 2]) / self.K[0, 0])
                                + self._fisheye_theta(abs(w - 1.0 - self.K[0, 2]) / self.K[0, 0]))
        pts = np.array([[[0.0, h / 2.0]], [[w - 1.0, h / 2.0]]])
        und = self.undistort_points(pts, to_normalised=True)
        return math.degrees(math.atan(abs(und[0, 0])) + math.atan(abs(und[1, 0])))

    def fisheye_valid_theta(self) -> float:
        """The largest angle (rad, < pi) up to which the fisheye model's theta_d grows."""
        k = list(self.D[:4]) + [0.0] * (4 - min(4, self.D.size))
        last = 0.0
        for i in range(1, 1800):
            t = i * math.pi / 1800
            td = t * (1 + k[0] * t ** 2 + k[1] * t ** 4 + k[2] * t ** 6 + k[3] * t ** 8)
            if td <= last:
                return (i - 1) * math.pi / 1800
            last = td
        return math.pi

    def _fisheye_theta(self, theta_d: float) -> float:
        """theta (rad) of a normalised fisheye radius theta_d, capped at fisheye_valid_theta()."""
        k = list(self.D[:4]) + [0.0] * (4 - min(4, self.D.size))

        def f(t):
            return t * (1 + k[0] * t ** 2 + k[1] * t ** 4 + k[2] * t ** 6 + k[3] * t ** 8)
        hi = self.fisheye_valid_theta()
        if f(hi) <= theta_d:
            return hi
        lo = 0.0
        for _ in range(60):                                   # bisection: f grows on [0, hi]
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if f(mid) < theta_d else (lo, mid)
        return 0.5 * (lo + hi)

    def undistort_points(self, pts, to_normalised: bool = False) -> np.ndarray:
        """Distorted pixel points (N,1,2) → undistorted pixels of the output image
        (or normalised coordinates)."""
        import cv2
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        P = None if to_normalised else self.K_out
        if self.model == "fisheye":
            out = cv2.fisheye.undistortPoints(pts, self.K, self.D[:4] if self.D.size else np.zeros(4), P=P)
        else:
            out = cv2.undistortPoints(pts, self.K, self.D if self.D.size else None, P=P)
        return out.reshape(-1, 2)

    def undistort(self, img: np.ndarray) -> np.ndarray:
        """The distortion-free pinhole image (K_out), same size as the input."""
        import cv2
        h, w = img.shape[:2]
        if (w, h) != self.size:
            raise ValueError(f"image is {w}x{h}, the calibration is for {self.size[0]}x{self.size[1]}")
        if not self.D.any() and np.allclose(self.K, self.K_out):
            return img
        if self._maps is None:
            if self.model == "fisheye":
                self._maps = cv2.fisheye.initUndistortRectifyMap(
                    self.K, self.D[:4], np.eye(3), self.K_out, self.size, cv2.CV_16SC2)
            else:
                self._maps = cv2.initUndistortRectifyMap(
                    self.K, self.D if self.D.size else None, np.eye(3), self.K_out, self.size, cv2.CV_16SC2)
        return cv2.remap(img, *self._maps, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def camera_rotation(q_body_enu: Sequence[float], mount_rpy_deg: Sequence[float] = (0.0, 0.0, 0.0)) -> np.ndarray:
    """R_world_cam for a camera mounted on the body: the nadir mount, then rotated by
    mount roll/pitch/yaw (deg, body frame) — e.g. pitch -30 tilts it 30 deg forward."""
    R_wb = quat_to_matrix(q_body_enu)
    R_mount = rpy_to_matrix(*(math.radians(float(a)) for a in mount_rpy_deg))
    return R_wb @ R_mount @ R_BODY_NADIR_CAM


def level_nadir_rotation(R_world_cam: np.ndarray) -> np.ndarray:
    """R_world_virt of a level camera looking straight down whose image top points
    where the real camera's image top points on the ground (same heading)."""
    up_img = R_world_cam @ np.array([0.0, -1.0, 0.0])        # image "up" in the world
    yaw = math.atan2(up_img[1], up_img[0])                    # ENU azimuth of image-up
    if math.hypot(up_img[0], up_img[1]) < 1e-6:              # looking at the horizon: no heading
        yaw = 0.0
    R_wb = rpy_to_matrix(0.0, 0.0, yaw)                       # level body facing image-up
    return R_wb @ R_BODY_NADIR_CAM


def tilt_deg(R_world_cam: np.ndarray) -> float:
    """Angle between the optical axis and straight down (deg)."""
    z = R_world_cam @ np.array([0.0, 0.0, 1.0])
    return math.degrees(math.acos(max(-1.0, min(1.0, -z[2]))))


def nadir_homography(K: np.ndarray, R_world_cam: np.ndarray, K_virt: Optional[np.ndarray] = None) -> np.ndarray:
    """Pixel homography from the real (undistorted) camera to the level nadir camera
    at the same place: x_virt ~ K_v R_virt_cam K^-1 x_cam."""
    R_world_virt = level_nadir_rotation(R_world_cam)
    R_virt_cam = R_world_virt.T @ R_world_cam
    Kv = K if K_virt is None else K_virt
    return Kv @ R_virt_cam @ np.linalg.inv(K)


def heading_of_image_up_deg(R_world_cam: np.ndarray) -> float:
    """Azimuth (deg clockwise from north) of the image's top on the ground."""
    up = R_world_cam @ np.array([0.0, -1.0, 0.0])
    return (math.degrees(math.atan2(up[0], up[1]))) % 360.0


def ground_m_per_px(altitude_agl_m: float, hfov_deg: float, width_px: int) -> float:
    return 2.0 * altitude_agl_m * math.tan(math.radians(hfov_deg) / 2.0) / width_px


def altitude_from_scale(predicted_altitude_m: float, fitted_scale: float) -> float:
    """Height above ground that a map match measures. The frame was scaled for
    predicted_altitude_m; a fitted scale s (frame ground size / predicted) means the
    camera saw s times more ground: it was s times higher."""
    return predicted_altitude_m * fitted_scale


def parse_crop(spec, width: int, height: int):
    """The part of the camera's picture NAVERA uses, as (x, y, w, h), or None for all of it.
    spec: "" (all), "top" / "bottom" / "left" / "right" (that half — a 360 camera's two
    lenses side by side or one above the other), or "x,y,w,h" in pixels.
    Raises ValueError for a region outside the picture."""
    s = str(spec or "").strip().lower()
    if not s:
        return None
    halves = {"top": (0, 0, width, height // 2), "bottom": (0, height // 2, width, height - height // 2),
              "left": (0, 0, width // 2, height), "right": (width // 2, 0, width - width // 2, height)}
    if s in halves:
        return halves[s]
    try:
        x, y, w, h = (int(v) for v in s.split(","))
    except ValueError:
        raise ValueError(f"crop {spec!r}: expected top, bottom, left, right or x,y,w,h") from None
    if x < 0 or y < 0 or w < 64 or h < 64 or x + w > width or y + h > height:
        raise ValueError(f"crop {spec!r} is not inside the {width}x{height} picture")
    return x, y, w, h
