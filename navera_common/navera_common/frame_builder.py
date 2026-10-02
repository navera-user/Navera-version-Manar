"""Turns a raw camera frame + the sensors at its exposure into a frame vision can use.

For each frame: remove the lens distortion, straighten it into a level straight-down
view at the same heading (when the attitude is known), and describe it — height above
ground, heading of the image top, field of view, tilt, time — in the JSON `frame_meta`
the vision pipelines read. Used by camera_pkg (NAVERA's camera, a USB camera such as
the Insta360 ONE R in webcam mode, or any ROS image topic) and by the simulator.

Meta keys (all optional except frame_id and image_stamp_ns):
  altitude_m, altitude_sigma_m, altitude_source   height above ground (navera_common.altitude)
  heading_deg        azimuth of the image top, deg clockwise from north (after straightening)
  camera_hfov_deg    horizontal field of view of the published (undistorted) image
  roll_deg, pitch_deg, tilt_deg, straightened      attitude used, and whether it was applied
  attitude_source    "imu", "vehicle", ... or "none" (then the frame is assumed straight down)
  usable / reason    false + why when the frame cannot be used (e.g. camera too tilted)
  gps_lat, gps_lon   the GPS at exposure, for recording and evaluation ONLY — vision never
                     reads them (gps_valid stays false: a live frame is never ground truth)
"""
import math
import time
from typing import Optional, Sequence, Tuple

import numpy as np

from navera_common.camera_model import (CameraModel, body_rpy_enu, camera_rotation,
                                        heading_of_image_up_deg, nadir_homography, tilt_deg)


class FrameBuilder:
    def __init__(self, camera: CameraModel, mount_rpy_deg: Sequence[float] = (0.0, 0.0, 0.0),
                 max_tilt_deg: float = 45.0, camera_type: str = "day", gimbal: bool = False,
                 require_attitude: bool = True):
        """max_tilt_deg: frames looking further from straight down are not compared (measured:
        straightened frames tilted 45 deg still matched 31/33 benchmark places, simulation).
        gimbal: the camera is held level by a stabiliser — only the vehicle's heading
        turns it; its roll and pitch are ignored."""
        self.cam, self.mount = camera, tuple(float(a) for a in mount_rpy_deg)
        self.max_tilt_deg, self.camera_type, self.gimbal = max_tilt_deg, camera_type, gimbal
        # without an attitude at exposure a fixed camera's tilt is unknown: assuming it
        # straight down puts the match tens of metres off, silently. A level (gimbal)
        # camera is straight down by construction.
        self.require_attitude = require_attitude and not gimbal

    def build(self, img: np.ndarray, frame_id: int, exposure_ns: int,
              q_body_enu: Optional[Sequence[float]] = None, attitude_source: str = "imu",
              altitude: Optional[Tuple[float, float, str]] = None,
              gps: Optional[Tuple[float, float]] = None, utc: Optional[str] = None):
        """(image, meta) for one frame. q_body_enu: the body attitude at exposure (None:
        unknown); altitude: (agl_m, sigma_m, source) at exposure (None: unknown)."""
        import cv2
        out = self.cam.undistort(img)
        meta = dict(frame_id=int(frame_id), image_stamp_ns=int(exposure_ns), camera_type=self.camera_type,
                    lat=None, lon=None, gps_valid=False, speed_mps=None,
                    camera_hfov_deg=round(self.cam.out_hfov_deg, 3),
                    timestamp=time.strftime("%H:%M:%S", time.gmtime(exposure_ns / 1e9)),
                    image_file=f"live_{int(frame_id):06d}.jpg", usable=True,
                    straightened=False, attitude_source="none", heading_deg=None)
        if altitude is not None:
            meta.update(altitude_m=round(altitude[0], 2), altitude_sigma_m=round(altitude[1], 2),
                        altitude_source=altitude[2])
        else:
            meta.update(altitude_m=None, altitude_source="unknown")
        if gps is not None:
            meta.update(gps_lat=gps[0], gps_lon=gps[1])
        if utc:
            meta["utc_time"] = utc
        if q_body_enu is None and self.require_attitude:
            meta.update(usable=False, reason="no attitude at the frame's exposure (IMU or vehicle link "
                                             "silent): the camera's tilt is unknown")
            return out, meta
        if q_body_enu is not None:
            if self.gimbal:                            # level camera: keep the heading only
                x, y, z, w = q_body_enu
                yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
                q_body_enu = (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))
            R = camera_rotation(q_body_enu, self.mount)
            roll, pitch, _ = body_rpy_enu(q_body_enu)
            tilt = tilt_deg(R)
            meta.update(roll_deg=round(roll, 2), pitch_deg=round(pitch, 2), tilt_deg=round(tilt, 2),
                        attitude_source=attitude_source,
                        heading_deg=round(heading_of_image_up_deg(R), 2))
            if tilt > self.max_tilt_deg:
                meta.update(usable=False, reason=f"camera tilted {tilt:.0f} deg from vertical "
                                                 f"(max {self.max_tilt_deg:.0f}): not compared with the map")
                return out, meta
            if tilt > 0.05:
                H = nadir_homography(self.cam.K_out, R)
                h, w = out.shape[:2]
                out = cv2.warpPerspective(out, H, (w, h), flags=cv2.INTER_LINEAR,
                                          borderMode=cv2.BORDER_CONSTANT)
            meta["straightened"] = True
        return out, meta
