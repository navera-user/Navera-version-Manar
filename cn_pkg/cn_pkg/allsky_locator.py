"""360 all-sky celestial fix for the flight node (cn_subscriber, solver_mode "allsky360"), without ROS.

The same solver as the field tools (allsky.locate and its quality gate, sky360 lenses, allsky_mount tilt
fit): this module only chooses where 'up' comes from, keeps the focal length found on the first fix, applies
and learns the tilt of 'up', and states the accuracy.

'up' in the camera frame:
  camera   frame_meta "up_imu": the 360 camera's own accelerometer (the field set-up); refused when
           frame_meta "accel_g" says the vehicle accelerates (|a| - 1 g > allsky.ACCEL_NORM_TOL);
  vehicle  the vehicle IMU's orientation at the exposure through the camera-to-body mount rotation
           R_cam_body (allsky_mount.up_camera_from_body);
  auto     camera when the frame carries up_imu, else vehicle.

Stated 1-sigma (allsky_mount.stated_sigma_km): the attitude of 'up' (the learned tilt's residual once
calibrated, else base_sigma_deg) and the star fit in quadrature, + MOVING_ATTITUDE_SIGMA_DEG when the frame
says the vehicle is not stopped, + the IMU timing error at the rotation rate (vehicle source).

Optional second attempt (NAVERA_STARSEG=1; default off, the product unchanged): when the normal solve fails,
the same frame is solved again with the star-segmentation network's spots (cn_pkg.starseg, spot_finder; mode
NAVERA_STARSEG_MODE, default "detect"). Same accept() / p_chance gates (allsky.locate). Skipped when the
network's last run took more than STARSEG_MAX_S (a slow box) or the network cannot be loaded.
"""
import math
import os
import time
from typing import Optional, Sequence, Tuple

import numpy as np

from cn_pkg import allsky, allsky_mount, sky360

UP_SOURCES = ("auto", "camera", "vehicle")
STARSEG_MAX_S = 3.0               # the second attempt is skipped once a run took longer than this
IMU_TIMING_S = 0.05               # the vehicle IMU's timing error at the exposure (cn_subscriber._sigma_m)


class AllSkyLocator:
    """State of the 360 mode across frames: catalogue, lenses, focal length found, tilt calibration."""

    def __init__(self, catalogue_path: Optional[str] = None, limit_mag: float = 4.0,
                 lens_file: Optional[str] = None, f_scale_search: Sequence[float] = (0.96, 1.0, 1.04),
                 f_scale: Optional[float] = None, R_cam_body=allsky_mount.R_CAM_BODY_STANDING,
                 up_source: str = "auto", base_sigma_deg: float = allsky_mount.ATTITUDE_SIGMA_360_DEG,
                 cal_min_samples: int = allsky_mount.CAL_MIN_SAMPLES, cal_samples: int = allsky_mount.CAL_SAMPLES,
                 cal_still_dps: float = 0.5, catalogue: Optional[allsky.Catalogue] = None):
        if up_source not in UP_SOURCES:
            raise ValueError(f"up_source {up_source!r} not in {UP_SOURCES}")
        self.cat = catalogue or allsky.Catalogue(limit_mag=limit_mag, path=catalogue_path or allsky.BUNDLED_CATALOGUE)
        self.lens_file = lens_file or None
        self.f_scale_search = tuple(float(f) for f in f_scale_search)
        self.f_scale = f_scale
        self.R_cam_body = allsky_mount.rotation_matrix(np.asarray(R_cam_body, float).ravel())
        self.up_source = up_source
        self.base_sigma_deg = float(base_sigma_deg)
        self.cal = allsky_mount.TiltCalibration(cal_min_samples, cal_samples)
        self.cal_still_dps = float(cal_still_dps)
        self.starseg_on = os.environ.get("NAVERA_STARSEG", "0") == "1"
        self.starseg_mode = os.environ.get("NAVERA_STARSEG_MODE", "detect")
        self.starseg_last_s: Optional[float] = None
        self._starseg = None                                 # loaded at first use; False: cannot be loaded

    def _starseg_finder(self):
        """starseg.finder for this frame, or None (off, cannot load, or the last run was too slow)."""
        if not self.starseg_on or self._starseg is False:
            return None
        if self.starseg_last_s is not None and self.starseg_last_s > STARSEG_MAX_S:
            return None
        if self._starseg is None:
            try:
                from cn_pkg import starseg
                self._starseg = starseg.StarSeg()
            except Exception:                                # noqa: BLE001 - no torch / weights: never retried
                self._starseg = False
                return None
        from cn_pkg import starseg
        return starseg.finder(self._starseg, mode=self.starseg_mode)

    def lenses(self):
        return sky360.default_lenses(self.lens_file)

    def up(self, meta: Optional[dict], q_xyzw=None) -> Tuple[Optional[np.ndarray], str, Optional[str]]:
        """('up' unit vector in the camera frame or None, source, why not)."""
        meta = meta or {}
        cam = meta.get("up_imu")
        use_cam = self.up_source == "camera" or (self.up_source == "auto" and cam is not None)
        if use_cam:
            if cam is None:
                return None, "camera", "no camera 'up' (frame_meta up_imu)"
            v = np.asarray(cam, float).ravel()
            if v.shape != (3,) or not np.all(np.isfinite(v)) or np.linalg.norm(v) < 1e-9:
                return None, "camera", f"bad frame_meta up_imu {cam!r}"
            g = meta.get("accel_g")
            if g is not None and abs(float(g) - 1.0) > allsky.ACCEL_NORM_TOL:
                return None, "camera", f"vehicle accelerating (|a| = {float(g):.3f} g): 'up' is not gravity"
            return v / np.linalg.norm(v), "camera", None
        if q_xyzw is None:
            return None, "vehicle", "no vehicle attitude (IMU) at the exposure"
        return allsky_mount.up_camera_from_body(q_xyzw, self.R_cam_body), "vehicle", None

    def process(self, frame: np.ndarray, utc: str, meta: Optional[dict] = None, q_xyzw=None,
                rate_dps: float = 0.0, reference: Optional[Tuple[float, float]] = None) -> dict:
        """One frame → the node's result dict: success, predicted_lat/lon, sigma_m, error and the solver's details.
        reference: a trusted position at the exposure (fresh GPS) — the fix then also teaches the tilt of 'up'.
        """
        meta = meta or {}
        up, src, why = self.up(meta, q_xyzw)
        out = {"success": False, "source": "allsky360", "up_source": src}
        if up is None:
            out["error"] = why
            return out
        moving = meta.get("stopped") is False
        fs = self.f_scale_search if self.f_scale is None else (self.f_scale,)
        r = allsky.locate(frame, up, utc, self.cat, lenses=self.lenses(), f_scales=fs)
        if not r.get("solved"):
            find = self._starseg_finder()
            if find is not None:
                t0 = time.monotonic()
                try:
                    r2 = allsky.locate(frame, up, utc, self.cat, lenses=self.lenses(), f_scales=fs, spot_finder=find)
                except Exception as e:                       # noqa: BLE001 - the second attempt never breaks a frame
                    r2 = {"solved": False, "why": f"starseg: {e}"}
                self.starseg_last_s = time.monotonic() - t0
                out["starseg"] = {"solved": bool(r2.get("solved")), "seconds": round(self.starseg_last_s, 2),
                                  "why": None if r2.get("solved") else str(r2.get("why") or "")[:120]}
                if r2.get("solved"):
                    r = r2
        out.update(up_cam=[round(float(v), 6) for v in up], moving=moving, spots=r.get("spots"),
                   **{k: r[k] for k in ("matched", "used", "rms_deg", "p_chance", "lens_disagree_deg", "sigma_fit_deg",
                                        "f_scale", "matched_per_lens", "retried_with") if k in r})
        if not r.get("solved"):
            out["error"] = str(r.get("why") or "not solved")[:200]
            return out
        if self.f_scale is None:
            self.f_scale = r["f_scale"]
            out["f_scale_found"] = self.f_scale
        R = np.array(r["R_icrs_imu"], float)
        lat, lon = r["lat"], r["lon"]
        base = self.base_sigma_deg
        cal = self.cal.fit
        if cal is not None:                                  # the learned tilt of 'up' removed
            lat, lon = self.cal.corrected(R, up, utc)
            base = cal["sigma_deg"]
            out["tilt_cal"] = {"n": cal["n"], "sigma_deg": round(cal["sigma_deg"], 4), "frozen": self.cal.frozen,
                               "tilt_deg": round(math.degrees(float(np.linalg.norm(cal["w"]))), 3)}
        if src == "vehicle" and rate_dps:
            base = math.hypot(base, IMU_TIMING_S * float(rate_dps))
        sigma_km = allsky_mount.stated_sigma_km(base, r.get("sigma_fit_deg"), moving)
        out.update(success=True, predicted_lat=float(lat), predicted_lon=float(lon), raw_lat=r["lat"], raw_lon=r["lon"],
                   sigma_m=round(sigma_km * 1000.0, 1), R_icrs_imu=r["R_icrs_imu"])
        # a reference position teaches the tilt while the vehicle is still (moving: acceleration in 'up')
        if reference is not None and not moving and abs(float(rate_dps or 0.0)) <= self.cal_still_dps \
                and not self.cal.frozen:
            fit = self.cal.add(R, up, allsky_mount.zenith_icrs(reference[0], reference[1], utc))
            out["cal_sample"] = len(self.cal.samples)
            if fit is not None:
                out["tilt_calibrated"] = {"samples": fit["n"], "samples_total": fit["n_total"],
                                          "rejected": fit["rejected"], "ok": fit["ok"], "why": fit["why"],
                                          "residual_deg": round(fit["rms_deg"], 3),
                                          "tilt_deg": round(math.degrees(float(np.linalg.norm(fit["w"]))), 3),
                                          "frozen": self.cal.frozen}
        return out
