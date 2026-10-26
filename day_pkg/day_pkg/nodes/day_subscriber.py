#!/usr/bin/env python3
"""
day_subscriber.py — NAVERA day_pkg, visual-localization subscriber.

Consumes the DAY camera stream published by camera_pkg and runs the existing
DayLocalizer (DINOv2 retrieval) on each frame:

    /day/image_raw    sensor_msgs/Image   (bgr8, BEST_EFFORT)
    /day/frame_meta   std_msgs/String     (JSON from camera_publisher.py, RELIABLE)

and emits:

    /day/position_estimate  sensor_msgs/NavSatFix
    /day/day_status         std_msgs/String   (JSON diagnostics)

This node ONLY wires camera_pkg → DayLocalizer. The localization logic in
day_localizer.py is used as-is through its public API
(DayLocalizer().load_models() / load_or_build_cache() / predict()).

Examples:
  ros2 launch day_pkg day_subscriber.launch.py
  ros2 launch day_pkg day_subscriber.launch.py conf_threshold:=0.80
  ros2 launch day_pkg day_subscriber.launch.py image_topic:=/day/image_raw \
                                               meta_topic:=/day/frame_meta
"""
import json
import logging
import math
import threading
import time
from collections import deque

import cv2

import rclpy
from navera_common import latency_cal, memory_trim, state_store
from navera_common.compute_health import watch_degraded
from navera_common.geo import is_finite_latlon
from navera_common.track import TrackVelocity
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.pairing import FramePairer, exposure_stamp, stamp_ns
from navera_common.prior import GpsPrior
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from sensor_msgs.msg import Image, Imu, NavSatFix, NavSatStatus, Range
from std_msgs.msg import String, Int32, Bool
from cv_bridge import CvBridge
from navera_msgs.msg import NavStatus, PositionEstimate

# Existing localization logic (UNMODIFIED user code).
# DayLocalizer().predict(bgr_array, threshold=...) -> dict
from day_pkg.nodes.day_localizer import IMAGES_DIR, DayLocalizer, haversine_m
from day_pkg.fix_sigma import SigmaCalibration, day_fix_sigma_m
from day_pkg.fix_sigma import load_stored as load_sigma_cal, save_stored as save_sigma_cal
from day_pkg.fix_consistency import FixConsistency
from day_pkg.fix_hypotheses import FixHypotheses
from day_pkg.frame_gate import FrameGate, focal_px
from day_pkg.frame_odometry import FrameOdometry
from day_pkg.gyro_heading import CourseReset, GyroHeading, heading_rate_dps
from day_pkg.map_levels import area_zooms, choose_zoom
from day_pkg.mount_cal import MountCalibration
from day_pkg.lens_selfcal import LensSelfCal, calibration_dict, lens_of_meta, list_pairs
from day_pkg.local_matcher import LocalMatcher
from day_pkg.reacquire import WindowScan, cover_windows
from day_pkg.carry_aids import (AttitudeYaw, VelocityRef, autopilot_sigma_growth, carry_autopilot,
                                 carry_with_turns, yaw_of_quaternion)
from day_pkg.carry_state import DrSnap, TRACK_STATE, restore_track, track_state, watchdog_carry
from day_pkg.vision_nav import VisionNavigator, _en, _move, kinematic_margin_m

# ── A priori spatial GPS-denied (fix matching cross-source) ─────────────────
# Sur une frame sans GPS, on restreint la recherche DINOv2 à un CERCLE autour du
# dernier point retenu (anchor), puis on prend le top-1 DINOv2 dans ce cercle.
# Rayon (cahier des charges) :
#     R = max(footprint_m × FOOTPRINT_MULT, altitude_m × ALTITUDE_MULT)
# où footprint_m = GSD_M_PER_PX × grand côté de la frame (≈1486 m pour 1536×730).
# R_MAX_M BORNE ce rayon théorique à la ZONE DE MATCHING FIABLE validée
# empiriquement au harnais (R≈400→600 m ⇒ médiane d'erreur ~564→611 m ; au-delà
# le cercle englobe trop de tuiles et l'erreur remonte vers ~3485 m).
GSD_M_PER_PX   = 0.967    # mesuré au diagnostic : tuile z17 = 248 m / 256 px
FOOTPRINT_MULT = 3.0
ALTITUDE_MULT  = 2.0
R_MIN_M        = 400.0    # plancher : ~1 pas inter-frame (frames à ~480 m)
ANCHOR_MEMORY_S = 300.0  # a saved position older than this is not reused after a restart
R_MAX_M        = 600.0    # PLAFOND décisif : garde R dans la bande validée

# ── source contract for navera_estimator (additive; see step 4) ──────────────
# Internal src label → honest provenance mode. This is the whole point of the
# mode field: a REPLAYED CSV point can NEVER pass itself off as a DINOv2
# MEASURED recognition, and a dead-reckon bridge is PROPAGATED, not measured.
_DAY_MODE_BY_SRC = {
    "gps":          PositionEstimate.MODE_REPLAYED,    # CSV ground truth, not a measurement
    "predicted":    PositionEstimate.MODE_MEASURED,    # real DINOv2 inference (global/gate)
    "visual_match": PositionEstimate.MODE_MEASURED,    # real DINOv2 inference (spatial a-priori)
    "dead_reckon":  PositionEstimate.MODE_PROPAGATED,  # heading/speed bridge from anchor
    "local_match":  PositionEstimate.MODE_MEASURED,    # local features vs the map (local_matcher)
}
_DAY_MODEL_BY_SRC = {
    "gps":          "csv_ground_truth",
    "predicted":    "dinov2_vits14+gem",
    "visual_match": "dinov2_vits14+gem",
    "dead_reckon":  "dead_reckon",
    "local_match":  "sift_local+ransac",
}


class DaySubscriber(Node):
    def __init__(self):
        super().__init__("day_subscriber")

        # ── Parameters ──────────────────────────────────────────
        declare_float(self, "conf_threshold", 0.75)
        self.declare_parameter("image_topic", "/day/image_raw")
        self.declare_parameter("meta_topic", "/day/frame_meta")
        self.declare_parameter("fix_topic", "/day/position_estimate")
        self.declare_parameter("status_topic", "/day/day_status")
        self.declare_parameter("estimate_topic", "/navera/estimate/day")  # typed source contract
        # Live GPS, used as the search prior: while it is valid the anchor follows
        # it and inference is skipped; when it drops, vision starts from its last fix.
        self.declare_parameter("gps_topic", "/navera/position")
        declare_float(self, "gps_prior_timeout_s", 2.0)
        # Mission start/stop gate of the camera: a stop (rewind) resets tracking.
        # Test flights only: run vision even while GPS is valid, to measure it
        # against GPS. GPS only seeds the track once (a prior re-centred on the
        # truth every frame would make the measured error meaningless).
        self.declare_parameter("shadow_mode", False)
        self.declare_parameter("start_topic", "/day/camera/start")
        self.declare_parameter("done_topic", "/day/frame_done")   # back-pressure ack (Int32 frame_id)
        self.declare_parameter("ready_topic", "/day/localizer_ready")  # handshake: modèle chargé
        # ── track filter (anchor, spatial prior, dead-reckoning) ──
        self.declare_parameter("antijump_enabled", True)      # false = raw per-frame output, no anchor
        # After this many consecutive frames without an accepted match, the anchor
        # is dropped and the next frame searches globally: a wrong anchor must not
        # confine the search forever.
        self.declare_parameter("max_consecutive_rejects", 3)
        # Dead-reckoning from the last accepted fix is only published for this long.
        # without a match, the last measured position is carried along the velocity of the
        # last measured fixes (turned by the IMU heading change) this long, while its stated
        # uncertainty stays under dead_reckon_max_sigma_m
        declare_float(self, "max_dead_reckon_s", 120.0)
        # 900 (was 500): below the vehicle output's max_forward_sigma_m (1000). A 60 s cloud bank at 10 m/s
        # reached +-500 m 20 s before vision came back: NAVERA went silent and the autopilot's EKF failed safe
        # 11 s later; with 900 it stayed aided (error 334 m at +-594 m) and the mission completed (Isaac Sim
        # closed loop, GPS cut 20 s after reaching altitude, F32)
        declare_float(self, "dead_reckon_max_sigma_m", 900.0)
        # unseen acceleration allowed for in the stated accuracy (1/2 a t^2). 0.25: outages
        # replayed on the real camera campaign's fixes (2026-10-19, 1606 per gap length, true
        # heading change given): still 100 % within 3 sigma at 5-60 s on a constant 900 m turn
        # and on a straight track; the 60 s sigma on a straight track 1078 -> 628 m (error 15 m
        # median, 55 m p95: the heading and velocity terms, not this one, keep it wide)
        declare_float(self, "dead_reckon_accel_mps2", 0.25)
        # Whole-map search (no prior). Measured on labelled frames: 12 % within
        # 300 m, and the similarity score does not separate good matches from
        # bad ones (docs/VALIDATION_STATUS.md). Off: without a prior (GPS fix or
        # tracked match) day vision reports no position instead of a guess.
        self.declare_parameter("allow_global_search", False)
        # Motion gate: a match farther from the last retained position than the
        # vehicle can travel (max_speed_mps x elapsed + gate_margin_m) is rejected.
        # The margin covers the tile quantisation (a match is a tile centre, tiles
        # ~250 m). Without it the track jumped 554 m in 1 s and stayed on wrong
        # tiles (0.4-1.1 km) in the mission simulator.
        declare_float(self, "max_speed_mps", 30.0)
        declare_float(self, "gate_margin_m", 250.0)
        # Matching method. "local": local features vs the satellite map around the prior
        # (local_matcher, SIFT; needs the frame altitude and camera_hfov_deg to know the
        # frame's scale — without them, falls back to "retrieval"); "learned": the same with
        # DISK + LightGlue (learned_matcher, GPU; SIFT as its fallback) — 28-29/33 real aerial
        # frames vs SIFT's 23-24/33 with the shipped 8 inliers, 0 wrong (docs/VALIDATION_STATUS.md,
        # re-measured 2026-10-20); "auto": "learned" when its models
        # load (GPU, kornia, weights), else "local"; "retrieval": DINOv2 tile retrieval
        # (the former method, ~440 m median).
        self.declare_parameter("matcher", "auto")
        # Between map matches (bench campaign 2026-10-06, day_pkg/vision_nav.py): the search
        # circle is k sigma of the carried position, never under local_min_radius_m; a fix
        # far from the prediction (gate_k sigma) is rejected — one with strong_inliers only beyond
        # strong_gate_k_sigma (it was believed at any distance: 2026-10-19 bench, 100-150 inlier
        # matches 270-650 m off were forwarded) — unless the next fix agrees with it,
        # one whose inliers cover < min_inlier_spread of the frame (with < 30 inliers) or at most
        # 1/8 of it (with < 50) too;
        # after height_retry_after failures in a row, the frame is also tried 20 % lower
        # and 25 % higher (a stale height makes every match fail).
        declare_float(self, "local_min_radius_m", 80.0)
        declare_float(self, "search_k_sigma", 3.0)
        declare_float(self, "gate_k_sigma", 3.0)
        self.declare_parameter("strong_inliers", 100)
        # 3 since 2026-10-22 (was 6: a confident wrong fix 3-6 sigma off was believed at once, F16): replay of
        # the recorded bench runs with 100-650 m wrong matches injected: believed 16 -> 5 of 579 (flights),
        # 20 -> 9 of 548 (missions), fewer right fixes refused (navera_tools/bench/replay_day_guards.py)
        declare_float(self, "strong_gate_k_sigma", 3.0)
        declare_float(self, "min_inlier_spread", 0.25)
        # day_pkg.fix_consistency (F16 / D17): while the carried position is lost (sigma > 50 m) a fix
        # further from it than 3 x its own sigma waits for a second agreeing fix (reacquire_confirm). Off:
        # on the recorded missions it refused 2.6x more right fixes (availability 94 -> 90 %) for 7 fewer
        # injected wrong fixes believed. A doubted fix is confirmed within 6 s, 20 s when lost.
        self.declare_parameter("reacquire_confirm", False)
        # D17 (2026-10-23): a doubted fix on a good track is believed after confirm_fixes doubted fixes
        # in a row agree (carried by the velocity); confirm_fixes_lost while the position is lost
        self.declare_parameter("confirm_fixes", 3)
        self.declare_parameter("confirm_fixes_lost", 2)
        # D17 (2026-10-23): alternative tracks (day_pkg.fix_hypotheses) instead of the confirmation above: a
        # far-off fix while the carried position is uncertain (sigma 30-250 m), or a doubted one, becomes the
        # track only once 3+ fixes agree with it and it leads (log-likelihood); meanwhile the published sigma
        # covers it. Replay (5 % injected wrong matches, 3 seeds): two-in-a-row believed 49 -> 11 (missions),
        # 33 -> 7 (flights) for 0.5 % more right fixes refused (navera_tools/bench/replay_day_guards.py)
        self.declare_parameter("fix_hypotheses", True)
        # a fix is averaged with the carried position, each weighted by its sigma (a Kalman update), when
        # the carry turns with a heading (frame attitude or gyro) and the fix is not a re-acquisition
        # (F20 / F23 / D17). Replay of the 2026-10-19/20 real-camera runs with the gyro-carried heading
        # (3 seeds): measured outputs > 50 m wind 51 -> 16, other conditions 57 -> 13, missions 6 -> 6; without
        # a heading it lagged in turns (other conditions 63 -> 75, F23), so it is not applied then.
        self.declare_parameter("blend_fixes", True)
        # day_pkg.frame_gate (F20): a frame smeared beyond frame_max_blur_px by the camera's rotation during
        # the exposure (gyro |w| at the frame time x frame_exposure_s x the focal length), or less sharp than
        # frame_sharp_rel x the flight's running median, is not matched. 0 = off (the default: on the
        # recorded shake runs neither removed wrong fixes beyond what blending does, and both refused
        # right ones — to be tried on a real vehicle).
        declare_float(self, "frame_max_blur_px", 0.0)
        declare_float(self, "frame_exposure_s", 1.0 / 60.0)
        declare_float(self, "frame_sharp_rel", 0.0)
        self.declare_parameter("height_retry_after", 3)
        declare_float(self, "camera_hfov_deg", float("nan"))   # day camera horizontal field of view
        # With camera_hfov_deg the position is the point under the camera from the matched pose
        # (local_matcher.refine_with_pose); that pose is used only when its tilt agrees with the
        # frame's tilt by the attitude (0 for a frame straightened with the IMU) within this, else
        # the frame centre is published (the match is kept). Real drone photos (UAV-VisLoc, 8
        # flights, 2026-10-20): the pose found 9-26 deg on a level drone, 70 of 2600 fixes 100-325 m
        # off with a 5-25 m sigma; with 4 deg, 2 (docs/VALIDATION_STATUS.md). 0 or less: off.
        declare_float(self, "pose_tilt_guard_deg", 4.0)
        # wrong places measured at <= 5 inliers on real aerial frames; correct ones 3-73
        self.declare_parameter("local_min_inliers", 8)
        # SIFT matcher: a frame that fills its feature budget and still finds too few inliers is described
        # again with this many features (heavy rain: the streaks take the budget). Real camera, screen bench
        # 2026-10-20: heavy rain 60 m/s 22 -> 33/40 frames matched (identical recorded frames), clear, haze,
        # flare, clouds, vibration unchanged; costs a second description on those frames only. 0 = off.
        self.declare_parameter("local_retry_features", 4000)
        declare_float(self, "local_scale_tol", 0.15)
        # widest scale window when the frame altitude is uncertain (frame_meta altitude_sigma_m)
        declare_float(self, "local_scale_tol_max", 0.35)
        declare_float(self, "local_heading_tol_deg", 20.0)
        # an IMU without magnetometer (its yaw drifts tens of degrees, or is unknown): the learned
        # matcher searches the heading (every 30 deg) when the IMU's fails — simulation
        # 2026-10-19, 300 m: heading 45 deg wrong 0/30 -> 30/30 located, 0 wrong
        self.declare_parameter("local_heading_search", False)
        # D18: the search is otherwise switched on frame by frame when the heading is uncertain — no frame
        # attitude heading and no gyro-carried one, or local_heading_search_after frames in a row without
        # a match while a heading was given (it may be wrong: the IRIS kit has no magnetometer). 0: never.
        self.declare_parameter("local_heading_search_after", 3)
        # frames without a heading in their meta (no attitude at the exposure): the carry between
        # fixes turns with the heading the vision measured on the last good fix (the matcher's
        # rotation, >= gyro_heading_min_inliers) carried on by the gyro's rate about the vertical
        # (gyro_imu_topic; "" = the IMU of NAVERA_SENSOR_SOURCE), until its 1-sigma (vision
        # gyro_heading_reset_sigma_deg, + bias x time, + noise random walk) passes
        # gyro_heading_max_sigma_deg: then straight on, as without it. Replay of the screen bench's real
        # frames through this node (2026-10-20, navera_tools/bench/replay_gyro_heading.py): heavy rain
        # 60 m/s max 210 -> 54 m (dead-reckoned 210 -> 23 m), clouds 340 -> 75 m, 0 new wrong fixes in 9
        # conditions; no effect on frames with an attitude heading.
        self.declare_parameter("gyro_heading", True)
        self.declare_parameter("gyro_imu_topic", "")
        declare_float(self, "gyro_heading_bias_dps", 0.1)
        declare_float(self, "gyro_heading_noise_dps_rthz", 0.004)   # Insta360 One R measured 0.0025-0.0033
        declare_float(self, "gyro_heading_reset_sigma_deg", 2.0)
        declare_float(self, "gyro_heading_max_sigma_deg", 10.0)
        self.declare_parameter("gyro_heading_min_inliers", 20)
        # while the GPS is trusted the gyro heading is also reset from the GPS course (above
        # gyro_course_min_speed_mps, on a steady course): the frame top = course + the camera's offset
        # from it, learned from vision headings, else -mount_yaw_deg of the frame meta (nose first,
        # 1-sigma gyro_course_crab_sigma_deg). The frames without attitude then have a heading for the
        # matcher (tolerance max(local_heading_tol_deg, 3 sigma)): MARS-LVIG AMvalley03 without
        # attitude, 0 fixes in 310 s before (see VALIDATION_STATUS.md)
        self.declare_parameter("gyro_course_reset", True)
        declare_float(self, "gyro_course_min_speed_mps", 5.0)
        declare_float(self, "gyro_course_crab_sigma_deg", 5.0)
        # a height measured by a match is trusted only from a strong match confirmed by
        # the next one (a wrong match must not set the altitude the next frames are judged by)
        self.declare_parameter("altitude_min_inliers", 20)
        # an area holding several map zooms (area.json "zooms"): each frame is matched against the
        # finest zoom at least this many times coarser than the frame (day_pkg.map_levels: a z18 map
        # located 54 % of a real 60-140 m flight's frames instead of 36 % at z17); one zoom: that one
        declare_float(self, "map_zoom_min_ratio", 2.0)
        # heights above ground measured by local matches (the camera uses them)
        self.declare_parameter("vision_altitude_topic", "/navera/vision/altitude_agl")
        # while GPS is trusted, match a frame this often around the GPS position: an
        # INDEPENDENT position for the estimator's GPS cross-check (a slow spoof drifts
        # GPS away from it), and the height above ground known when GPS is lost. 0 = off.
        declare_float(self, "gps_check_period_s", 2.0)
        declare_float(self, "gps_check_radius_m", 600.0)   # covers a GPS drifted this far
        # while GPS is trusted, also measure the frame-to-frame displacement (visual odometry, phase
        # correlation, ~0.14 s of CPU per 1200 px frame) at most once per gps_vo_period_s and publish it
        # for the estimator's relative-motion test (navera_common.gps_motion_check: a slow spoof adds
        # its drift to the GPS displacement, not to the image's). The VO scale uses the frame height
        # smoothed over gps_vo_height_tau_s (a jump in the height estimate is not a jump in the VO).
        self.declare_parameter("gps_vo_enabled", True)
        declare_float(self, "gps_vo_period_s", 1.0)
        self.declare_parameter("gps_vo_width_px", 1280)    # frames reduced to at most this width
        declare_float(self, "gps_vo_height_tau_s", 60.0)
        self.declare_parameter("gps_vo_topic", "/navera/vision/odometry")
        # tried first: a trusted GPS is metres off, and a small search window keeps a low (small)
        # frame matchable; the wide radius only when this fails (0 = wide only)
        declare_float(self, "gps_check_near_radius_m", 150.0)
        # faster checks while auto_latency has no stable delay yet (0 = gps_check_period_s always)
        declare_float(self, "gps_check_period_delay_s", 1.0)
        # an applied camera delay moving more than this forgets the map-bias / sigma samples dated by the old one
        declare_float(self, "latency_relearn_s", 0.2)
        # Stated accuracy (1 sigma, m) of a local match: day_pkg.fix_sigma.day_fix_sigma_m (the
        # matcher's inlier-class sigma, a floor, the frame-time and attitude terms): 99.2 % within
        # 3 sigma on NAVERA's camera on the screen bench (2026-10-19, median 10.6 m) but only 48 % on
        # real drone imagery (UAV-VisLoc flight 03: errors ~18 m whatever the inliers) — so it is
        # published through SigmaCalibration (below): calibrated against GPS in flight, else >= 30 m.
        # local_sigma_m is only the fallback for a result without its own sigma.
        declare_float(self, "local_sigma_m", 30.0)
        declare_float(self, "local_sigma_floor_m", 5.0)
        declare_float(self, "frame_time_sigma_s", 0.05)
        # the camera delay's 1-sigma while it is unknown (camera_latency_s 0 and no auto_latency
        # estimate applied): added, times the ground speed, to every stated fix accuracy
        declare_float(self, "unknown_delay_sigma_s", 1.0)
        declare_float(self, "attitude_sigma_deg", 0.5)
        # In-flight check of that sigma against the trusted GPS (fix_sigma.SigmaCalibration): the GPS check
        # frames measure this flight's real vision error; after min_samples the stated sigma is scaled to it.
        # Never calibrated (GPS denied from take-off): at least sigma_floor_no_cal_m.
        declare_float(self, "sigma_floor_no_cal_m", 30.0)
        self.declare_parameter("sigma_cal_min_samples", 15)
        # A slowly spoofed GPS stays trusted for a while (refused at ~35-100 m of drift, gps_crosscheck):
        # when GPS stops being trusted, the sigma calibration and the map bias forget what they
        # learned in the last calib_rollback_s, so the drift is not kept as "vision error" or "map shift"
        declare_float(self, "calib_rollback_s", 60.0)
        # The camera's boresight (mount roll/pitch) error, learned while GPS is trusted from the GPS-check
        # matches (day_pkg.mount_cal: per position kind, a map shift and a residual delay fitted beside it)
        # and removed from the fixes after the loss; forgotten like the map bias (calib_rollback_s). Until
        # it is learned every fix states height x tan(mount_sigma_deg) more (Isaac Sim 2026-10-21: a 4 deg
        # mount error 14 m at the exposure instead of 6-7 m at 250 m; 600 m: 16 outputs beyond 3 sigma).
        self.declare_parameter("mount_cal", True)
        declare_float(self, "mount_sigma_deg", 2.0)
        self.declare_parameter("mount_cal_min_samples", 12)
        # F41: a GPS check is a mount sample only while its dating error (ground speed x the camera delay's
        # sigma) is at most mount_cal_max_dating_m and the delay is known (set by the camera or estimated
        # and applied): with the delay unknown its offset along the track was learned as a mount pitch
        # (Isaac Sim 2026-10-22). An in-flight fit is used once its samples span mount_cal_min_heading_span_deg
        # of frame headings: on one heading the mount offset is a map shift (600 m climb: 10 -> 16 m).
        declare_float(self, "mount_cal_max_dating_m", 2.0)
        declare_float(self, "mount_cal_min_heading_span_deg", 90.0)
        # GPS may be good for the take-off only: the main source of the mount error is a PERSISTED
        # calibration — mount_cal_file (a ground/bench measurement or a chosen flight's: JSON {"frame
        # centre": {top_deg, right_deg, sigma_deg}, "camera pose": {...}}), else the last one learned in
        # flight (state file day_mount, written every mount_cal_save_period_s from GPS checks older than
        # calib_rollback_s, and at a GPS loss). Its sigma is at least mount_cal_persisted_min_sigma_deg
        # (the camera may have been knocked since). Without any, mount_sigma_deg stays in the stated sigma.
        self.declare_parameter("mount_cal_file", "")
        self.declare_parameter("mount_cal_persist", True)
        declare_float(self, "mount_cal_persisted_min_sigma_deg", 0.5)
        declare_float(self, "mount_cal_save_period_s", 30.0)
        # The lens calibrated in flight (day_pkg.lens_selfcal): while GPS is trusted every GPS-check match's
        # point pairs are a view of the map; with lens_selfcal_min_views of them (and every
        # lens_selfcal_every_views after) the lens is fitted in the background, and a clearly better
        # one is kept for this camera (state lens_auto_<lens_key>) and published on lens_topic — the live
        # camera applies it at once and at every start. "auto": only a lens not calibrated with a file
        # (navera-discover's starting value, or NAVERA_CAMERA_HFOV_DEG); "on": also a calibrated one;
        # "off". At most lens_selfcal_max_updates lenses applied per flight.
        self.declare_parameter("lens_selfcal", "auto")
        self.declare_parameter("lens_selfcal_min_views", 12)
        self.declare_parameter("lens_selfcal_every_views", 8)
        self.declare_parameter("lens_selfcal_max_updates", 3)
        self.declare_parameter("lens_topic", "/day/lens_update")
        # A consistent camera pose whose tilt disagrees with the attitude's (pose_tilt_guard_deg): the
        # frame centre and the point under the camera are both candidates — the one nearer the carried
        # position is taken and the fix states half their distance more (or the carried sigma, if less).
        # Beyond pose_guard_refuse_deg the match is refused: the frame is not where the attitude says (or
        # the match is wrong). Isaac Sim plane 30 m/s 2026-10-21: guarded frame centres 30-75 m off
        # (attitude 1.3 s stale in roll changes) and one 258 m (pose 32 deg) — the wrong fixes.
        self.declare_parameter("pose_guard_choose", True)
        declare_float(self, "pose_guard_refuse_deg", 15.0)
        # Local matching keeps its last position when frames fail (uniform ground, blur) and
        # widens the search by max_speed_mps x the time since its last match, up to this
        # radius, instead of dropping it after max_consecutive_rejects (a retrieval-era rule).
        declare_float(self, "local_max_radius_m", 600.0)   # wider: memory and 30-60 s frames (campaign 3)
        # Re-acquiring after a gap (day_pkg.reacquire, F32): a search circle wider than one window is
        # covered with windows of reacquire_window_frac x the frame's half diagonal on the ground
        # (at least local_min_radius_m), nearest the carried position first, reacquire_windows_per_frame
        # of them a frame (the carried position's always), up to reacquire_max_radius_m; a match in a
        # window other than the carried position's needs reacquire_min_inliers. One 600 m window found
        # 0-11 matches where 150 m windows found 90-170 inliers (Isaac Sim frames, 2026-10-22).
        self.declare_parameter("reacquire_windows", True)
        declare_float(self, "reacquire_window_frac", 0.65)
        self.declare_parameter("reacquire_windows_per_frame", 4)
        declare_float(self, "reacquire_max_radius_m", 1500.0)
        self.declare_parameter("reacquire_min_inliers", 25)
        # a frame stops trying windows after this long (s): the carry must not go stale between frames
        declare_float(self, "reacquire_budget_s", 2.5)
        # a frame that failed at its own height tries 20 % lower and 25 % higher only while it has
        # spent less than this (s) — the carried position must not wait for one frame
        declare_float(self, "frame_budget_s", 6.0)
        # the carried position is also published by a watchdog in its own thread (day_pkg.carry_state):
        # when no output for dr_watchdog_s (a match stalled: 5.7 s in the endurance flight endur2, 7-10 s
        # at 1200 m), checked every dr_watchdog_period_s. 0: off (only the matching thread publishes)
        declare_float(self, "dr_watchdog_s", 2.0)
        declare_float(self, "dr_watchdog_period_s", 0.5)
        # B23: the track (measured points, carried velocity, headings) persisted at most once a second
        # (state "day_track") and restored by a day node restarted in flight: it carries on at once,
        # its uncertainty grown by the time elapsed, and searches around that (not a 600 m circle)
        self.declare_parameter("track_persist", True)
        # the carry along the autopilot's own velocity (vehicle_link /navera/vehicle/velocity; open3,
        # day_pkg.carry_aids): its EKF integrates its IMU (turns, speed changes), but without GPS it is
        # corrected by NAVERA's positions — so a bias is fitted on this node's measured fixes of the last
        # 20 s and the velocity refused when they do not lie on its path. "" = off. Its drift while NAVERA
        # feeds the autopilot carried positions: 1/2 drift t^2 in the stated accuracy
        self.declare_parameter("autopilot_velocity_topic", "/navera/vehicle/velocity")
        declare_float(self, "autopilot_velocity_drift_mps2", 0.1)
        # the fitted bias is added to the autopilot's velocity only when the autopilot does NOT fly on
        # NAVERA's positions (its EKF then cannot absorb it); fed by NAVERA (the default installation) the
        # carry adding it ran away (_applied_bias), so it only widens the stated accuracy
        self.declare_parameter("autopilot_velocity_apply_bias", False)
        # the IMU attitude's absolute yaw (orientation of the gyro's IMU message): the turn across a
        # restart of this process, persisted with the snapshot (carry_aids.AttitudeYaw)
        self.declare_parameter("attitude_yaw_carry", True)

        self.conf_threshold = float(self.get_parameter("conf_threshold").value)
        image_topic   = self.get_parameter("image_topic").value
        meta_topic    = self.get_parameter("meta_topic").value
        fix_topic     = self.get_parameter("fix_topic").value
        status_topic  = self.get_parameter("status_topic").value
        done_topic    = self.get_parameter("done_topic").value
        ready_topic   = self.get_parameter("ready_topic").value
        self.antijump_enabled    = bool(self.get_parameter("antijump_enabled").value)
        self.max_consecutive_rejects = int(self.get_parameter("max_consecutive_rejects").value)
        self.max_dead_reckon_s   = float(self.get_parameter("max_dead_reckon_s").value)
        self.dr_max_sigma_m      = float(self.get_parameter("dead_reckon_max_sigma_m").value)
        self.track = TrackVelocity(accel_mps2=float(self.get_parameter("dead_reckon_accel_mps2").value))
        self._track_heading = None             # frame heading (IMU) at the last measured fix
        # the frames' attitude headings by their exposure time: the heading the track velocity was
        # measured at (its fit time) — GPS points and odometry steps have none of their own
        self._frame_headings = deque(maxlen=600)
        self.gyro = None                        # GyroHeading when gyro_heading is on
        if bool(self.get_parameter("gyro_heading").value):
            self.gyro = GyroHeading(float(self.get_parameter("gyro_heading_bias_dps").value),
                                    float(self.get_parameter("gyro_heading_noise_dps_rthz").value),
                                    float(self.get_parameter("gyro_heading_reset_sigma_deg").value),
                                    float(self.get_parameter("gyro_heading_max_sigma_deg").value))
        self.gyro_min_inliers = int(self.get_parameter("gyro_heading_min_inliers").value)
        self.course = None                      # CourseReset while GPS is trusted
        if self.gyro is not None and bool(self.get_parameter("gyro_course_reset").value):
            self.course = CourseReset(min_speed_mps=float(self.get_parameter("gyro_course_min_speed_mps").value),
                                      crab_sigma_deg=float(self.get_parameter("gyro_course_crab_sigma_deg").value))
        self._mount_yaw = None                  # the camera mount's yaw (frame meta), for the course offset
        self._dr_sigma = None
        self._anchor_sigma = None               # 1-sigma (m) of the anchor position, None: unknown
        p_ = lambda n: self.get_parameter(n).value               # noqa: E731
        self.local_min_radius_m, self.search_k = float(p_("local_min_radius_m")), float(p_("search_k_sigma"))
        self.gate_k, self.strong_inliers = float(p_("gate_k_sigma")), int(p_("strong_inliers"))
        self.strong_gate_k = float(p_("strong_gate_k_sigma"))
        self.min_spread, self.height_retry_after = float(p_("min_inlier_spread")), int(p_("height_retry_after"))
        self._compute_degraded = watch_degraded(self)     # H-11: hot / short of memory -> no height retries
        # the map's offset from the ground (registration, camera boresight), learned from the
        # GPS-check matches while GPS is good and removed from the fixes after its loss
        self.map_bias = VisionNavigator()
        # frame-to-frame visual odometry: the displacement through gaps in map matching
        self.vo = FrameOdometry()
        # the same, while GPS is trusted (gps_vo_*): its own previous frame, no prediction from GPS
        self.gps_vo = FrameOdometry(scale=1.0)
        self._gps_vo_t = None                   # stamp of the last frame given to it
        self._gps_vo_h = None                   # (smoothed height m, t)
        self._vo_step = None
        self.consistency = FixConsistency(self.gate_k, self.strong_inliers, self.strong_gate_k,
                                          reacquire_check=bool(p_("reacquire_confirm")),
                                          confirm_n=int(p_("confirm_fixes")),
                                          confirm_lost_n=int(p_("confirm_fixes_lost")))
        self.hypotheses = FixHypotheses(self.consistency) if bool(p_("fix_hypotheses")) else None
        self.blend_fixes = bool(p_("blend_fixes"))
        self.frame_gate = FrameGate(float(p_("frame_max_blur_px")), float(p_("frame_exposure_s")),
                                    sharp_rel=float(p_("frame_sharp_rel")))
        # the position carried frame by frame since the last fix (lat, lon, t, heading,
        # ve, vn, sigma): one turn from the fix's heading to the present folded a 180 deg
        # turn or a lap into a small one (bench campaign 4: 3-3.8 km off on the coast)
        self._carry = None
        # when the carry's velocity was last measured, if the track no longer gives one (None = the
        # track's last fix): the unseen-acceleration term of the stated accuracy grows from there
        self._vel_epoch = None
        # the trusted GPS by its measurement time: a bias sample compares a frame's fix with
        # the GPS at that frame's instant (the latest GPS is v x delay off along the track)
        from navera_common.sensor_history import History
        self._gps_hist = History(maxlen=600, max_gap_s=1.5)
        self.allow_global_search = bool(self.get_parameter("allow_global_search").value)
        self.max_speed_mps = float(self.get_parameter("max_speed_mps").value)
        self.gate_margin_m = float(self.get_parameter("gate_margin_m").value)

        # ── State ───────────────────────────────────────────────
        self.bridge        = CvBridge()
        self._busy_lock    = threading.Lock()
        # without frames at all (camera failed, unplugged), the measured track is still
        # carried on (1 Hz) — the case dead-reckoning matters most for
        self._last_frame = (time.time(), {})
        # the last output and the velocity it moves with (DrSnap), for the watchdog thread; set by
        # the matching thread at each output and by the GPS thread while the GPS is trusted
        self._dr_snap = None
        self.apv = VelocityRef() if str(self.get_parameter("autopilot_velocity_topic").value).strip() else None
        self.ap_drift = float(self.get_parameter("autopilot_velocity_drift_mps2").value)
        self.ap_apply_bias = bool(self.get_parameter("autopilot_velocity_apply_bias").value)
        self.att_yaw = AttitudeYaw() if bool(self.get_parameter("attitude_yaw_carry").value) else None
        self._ap_fit_cache = None               # ((t_last, n points), bias) of the last _ap_bias()
        self._restored_bias = None              # (be, bn, sigma, t_ref) persisted with a restored snapshot
        self._gps_ap_fit = (-math.inf, None)    # GPS thread: (t, bias) of its last fit
        self._last_out_wall = time.time()       # wall clock of the last output (position or "none")
        self.dr_watchdog_s = float(self.get_parameter("dr_watchdog_s").value)
        self.track_persist = bool(self.get_parameter("track_persist").value)
        self._track_saved_at = 0.0
        # GPS messages are read in their own thread (a 10 s match must not hold them back: their
        # points came in bursts, the track had no velocity at the GPS loss — F32 h1200); the
        # matching state is updated from them under _busy_lock (_drain_gps)
        self._gps_pending = deque()
        self._gps_vel = TrackVelocity()         # GPS thread only: the velocity of the GPS snapshot
        self._cb_gps = MutuallyExclusiveCallbackGroup()
        period = float(self.get_parameter("dr_watchdog_period_s").value)
        self.create_timer(period if period > 0 else 1.0, self._watchdog,
                          callback_group=MutuallyExclusiveCallbackGroup())
        self._memory_trim_init()
        self._pairer       = FramePairer()   # image/meta matched on the image stamp
        self._frame_count   = 0
        self._success_count = 0
        self._skip_count    = 0
        self._reject_count  = 0
        # anchor = last RETAINED position (GPS truth OR filtered output). dt source.
        self._anchor_lat  = None
        self._anchor_lon  = None
        self._anchor_time = None   # wall-clock (time.time()) of last retained frame
        self._last_measured_time = None   # wall-clock of the last MEASURED/known fix
        self._rejects_in_row     = 0
        self._anchor_saved_at    = 0.0
        # restarted (in flight): start from the last position this node was sure of, if
        # recent — the search circle grows with its age like after any gap
        saved = state_store.load("day_anchor", ANCHOR_MEMORY_S)
        if saved is not None and is_finite_latlon(saved.get("lat"), saved.get("lon")):
            self._anchor_lat, self._anchor_lon = float(saved["lat"]), float(saved["lon"])
            self._anchor_time = self._last_measured_time = float(saved["saved_at"])
            self.get_logger().warn(f"[day] restart: last known position {time.time() - saved['saved_at']:.0f} s "
                                   f"ago reused as the search centre")
        if self.track_persist:
            self._restore_track()

        # ── Banner (PRE-load) ──────────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("  NAVERA day_pkg — DAY visual-localization subscriber")
        self.get_logger().info(f"  image topic     : {image_topic}")
        self.get_logger().info(f"  meta  topic     : {meta_topic}")
        self.get_logger().info(f"  fix   topic     : {fix_topic}")
        self.get_logger().info(f"  status topic    : {status_topic}")
        self.get_logger().info(f"  conf_threshold  : {self.conf_threshold:.2f}")
        self.get_logger().info("  policy          : strictly-serial, back-pressure (acks frame_done)")
        self.get_logger().info("=" * 60)

        self.matcher_mode = str(self.get_parameter("matcher").value)
        self.camera_hfov_deg = float(self.get_parameter("camera_hfov_deg").value)
        self.local_sigma_m = float(self.get_parameter("local_sigma_m").value)
        self.local_sigma_floor_m = float(self.get_parameter("local_sigma_floor_m").value)
        self.frame_time_sigma_s = float(self.get_parameter("frame_time_sigma_s").value)
        self.unknown_delay_sigma_s = float(self.get_parameter("unknown_delay_sigma_s").value)
        self.attitude_sigma_deg = float(self.get_parameter("attitude_sigma_deg").value)
        self.sigma_cal = SigmaCalibration(float(self.get_parameter("sigma_floor_no_cal_m").value),
                                          int(self.get_parameter("sigma_cal_min_samples").value))
        self.calib_rollback_s = float(self.get_parameter("calib_rollback_s").value)
        self._sigma_store_init()
        self._init_mount_cal()
        self._init_lens_cal()
        self._last_fix_sigma = self.local_sigma_m
        self.local_max_radius_m = float(self.get_parameter("local_max_radius_m").value)
        self.reacquire_windows = bool(self.get_parameter("reacquire_windows").value)
        self.reacquire_window_frac = float(self.get_parameter("reacquire_window_frac").value)
        self.reacquire_per_frame = int(self.get_parameter("reacquire_windows_per_frame").value)
        self.reacquire_max_radius_m = float(self.get_parameter("reacquire_max_radius_m").value)
        self.reacquire_min_inliers = int(self.get_parameter("reacquire_min_inliers").value)
        self.reacquire_budget_s = float(self.get_parameter("reacquire_budget_s").value)
        self.frame_budget_s = float(self.get_parameter("frame_budget_s").value)
        self._scan = WindowScan()
        self.local_scale_tol_max = float(self.get_parameter("local_scale_tol_max").value)
        self.local_heading_tol_deg = float(self.get_parameter("local_heading_tol_deg").value)
        self.heading_search = bool(self.get_parameter("local_heading_search").value)
        self.heading_search_after = int(self.get_parameter("local_heading_search_after").value)
        self.alt_min_inliers = int(self.get_parameter("altitude_min_inliers").value)
        self._alt_candidate = None             # (height, time) of the last strong match
        self._check_fix = None                 # (lat, lon, time) of the last GPS-check match
        self._gps_was_trusted = False
        self.calib_period_s = float(self.get_parameter("gps_check_period_s").value)
        self.calib_radius_m = float(self.get_parameter("gps_check_radius_m").value)
        self.gps_vo_enabled = bool(self.get_parameter("gps_vo_enabled").value)
        self.gps_vo_period_s = float(self.get_parameter("gps_vo_period_s").value)
        self.gps_vo_width_px = int(self.get_parameter("gps_vo_width_px").value)
        self.gps_vo_height_tau_s = float(self.get_parameter("gps_vo_height_tau_s").value)
        self.calib_near_radius_m = float(self.get_parameter("gps_check_near_radius_m").value)
        self.calib_period_delay_s = float(self.get_parameter("gps_check_period_delay_s").value)
        self.latency_relearn_s = float(self.get_parameter("latency_relearn_s").value)
        # ── camera delay (exposure -> arrival), estimated online against the trusted GPS ──
        # navera_common.latency_cal: GPS-check matches vs the GPS track; applied (auto_latency)
        # when stable and significantly different from camera_latency_s, or — camera_latency_s 0 —
        # staged (combined with the prior: the delay kept from the last flight, else 0 +- unknown_delay_sigma_s)
        self.latency_cal, self.auto_latency, self.latency_rollback_s = latency_cal.from_node(self)
        if self.latency_cal.applied is not None:
            self.get_logger().info(f"[day] camera delay: {self.latency_cal.reason}")
        self._learned_delay = self.latency_cal.correction() if self.auto_latency else 0.0
        self._latency_applied = None
        self._init_camera_delay_pub()
        self._last_calib = 0.0
        self.local = None
        # the map's zooms (area.json; an area without it: 17), coarsest first: the matcher of the
        # coarsest is built now, finer ones when a frame first needs them (_select_map)
        self.map_zooms = area_zooms(IMAGES_DIR)
        self.map_zoom_min_ratio = float(self.get_parameter("map_zoom_min_ratio").value)
        self._matchers = {}
        kw = dict(min_inliers=int(self.get_parameter("local_min_inliers").value),
                  scale_tol=float(self.get_parameter("local_scale_tol").value),
                  pose_tilt_guard_deg=float(self.get_parameter("pose_tilt_guard_deg").value),
                  zoom=self.map_zooms[0])
        self._matcher_kw = kw
        if self.matcher_mode in ("learned", "auto"):
            try:
                from day_pkg.learned_matcher import LearnedMatcher
                self.local = LearnedMatcher(IMAGES_DIR, **kw)
                self.get_logger().info(f"matcher: DISK + LightGlue vs the map (GPU), SIFT as fallback, "
                                       f"camera_hfov_deg={self.camera_hfov_deg}")
            except Exception as e:                     # noqa: BLE001 — no GPU / kornia / weights
                if self.matcher_mode == "learned":
                    raise
                self.get_logger().warn(f"learned matcher unavailable ({e}): SIFT local matching instead")
            self.matcher_mode = "local"
        if self.matcher_mode == "local" and self.local is None:
            self.local = LocalMatcher(IMAGES_DIR, retry_features=int(self.get_parameter("local_retry_features").value),
                                      **kw)
        if self.local is not None:
            self._matchers[self.map_zooms[0]] = self.local
            self.get_logger().info(f"map zooms {self.map_zooms}"
                                   + (f" (finer for low frames, ratio {self.map_zoom_min_ratio})"
                                      if len(self.map_zooms) > 1 else ""))
            self.get_logger().info(
                f"matcher: local features vs the map ({'GPU' if self.local.torch else 'CPU'} matching), "
                f"camera_hfov_deg={self.camera_hfov_deg}"
                + ("" if math.isfinite(self.camera_hfov_deg) else
                   " — UNKNOWN: the frame scale cannot be computed, no position until it is set"))
        # ── DINOv2 retrieval (blocking): only for the "retrieval" matcher. Beside a local matcher it
        # never runs (a frame without a match publishes no fix), so it is not loaded: one heavy
        # model on the GPU at a time (perf 2026-10-21: DINOv2 + its cache cost the process memory)
        self.localizer = None
        if self.local is None:
            self.get_logger().info("⏳ Loading DayLocalizer (DINOv2)…")
            self.localizer = DayLocalizer()
            self.localizer.load_models()
            self.localizer.load_or_build_cache()
            self.localizer.warm_up()
            self.get_logger().info("✅ DayLocalizer ready, awaiting frames…")

        # A signal (SIGINT/SIGTERM) during the multi-second DINOv2 load makes rclpy
        # close the context; the create_publisher/create_subscription calls below
        # would then raise "rcl node's context is invalid" (RCLError, exit 1). Abort
        # construction cleanly — main() maps ExternalShutdownException to exit 0.
        if not rclpy.ok():
            raise ExternalShutdownException()

        # ── QoS per topic (must match camera_pkg publisher) ────
        # RELIABLE — MUST match the camera_publisher image publisher (also RELIABLE).
        # A RELIABLE subscriber + BEST_EFFORT publisher would NOT connect.
        image_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        meta_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # ── Publishers ──────────────────────────────────────────
        self.pub_fix    = self.create_publisher(NavSatFix, fix_topic,    10)
        self.pub_status = self.create_publisher(String,    status_topic, 10)
        self.pub_vision_alt = self.create_publisher(Range, self.get_parameter("vision_altitude_topic").value, 10)
        # visual odometry while GPS is trusted (JSON: t0, t1 s, east_m, north_m, quality) -> estimator
        self.pub_gps_vo = self.create_publisher(String, self.get_parameter("gps_vo_topic").value, 10)
        # Additive: typed per-source estimate for navera_estimator. Same RELIABLE
        # depth-10 class as the fix/status topics. /day/* topics are UNTOUCHED.
        estimate_topic = self.get_parameter("estimate_topic").value
        self.pub_est   = self.create_publisher(PositionEstimate, estimate_topic, 10)
        # back-pressure ack: published once per frame (RELIABLE, matches camera ack sub)
        done_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        self.pub_done   = self.create_publisher(Int32, done_topic, done_qos)

        # ── Subscribers ─────────────────────────────────────────
        self.sub_image = self.create_subscription(
            Image, image_topic, self.on_image, image_qos
        )
        self.sub_meta = self.create_subscription(
            String, meta_topic, self.on_meta, meta_qos
        )
        self._gps_prior = GpsPrior(float(self.get_parameter("gps_prior_timeout_s").value))
        # The arbiter's decision: GPS is the prior only while it is the source in use.
        self.create_subscription(NavStatus, "/navera/nav_status", self.on_nav_status, 10,
                                 callback_group=self._cb_gps)
        self.shadow_mode = bool(self.get_parameter("shadow_mode").value)
        if self.shadow_mode:
            self.get_logger().warn("SHADOW MODE: vision runs while GPS is valid (test flights)")
        self.sub_gps = self.create_subscription(
            PositionEstimate, self.get_parameter("gps_topic").value, self.on_gps, 10,
            callback_group=self._cb_gps)
        # a start position entered by the operator (page /mission) when there is no GPS:
        # where to search first — never published as a position (latched: heard on restart)
        self.create_subscription(
            PositionEstimate, "/navera/operator/start_position", self.on_operator_position,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        # Same latched QoS as the camera's gate (TRANSIENT_LOCAL, depth 1).
        start_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.TRANSIENT_LOCAL,
                               history=HistoryPolicy.KEEP_LAST, depth=1)
        self.sub_start = self.create_subscription(
            Bool, self.get_parameter("start_topic").value, self.on_start_cmd, start_qos)
        if self.apv is not None:
            from geometry_msgs.msg import TwistStamped
            self.create_subscription(TwistStamped, str(self.get_parameter("autopilot_velocity_topic").value).strip(),
                                     self.on_ap_velocity, 20, callback_group=MutuallyExclusiveCallbackGroup())
        if self.gyro is not None or self.att_yaw is not None:
            # read in its own thread (main(): multi-threaded executor): a frame takes 0.5-1 s
            # and the gyro must not stop being integrated meanwhile
            imu_topic = str(self.get_parameter("gyro_imu_topic").value).strip()
            if not imu_topic:
                try:
                    from navera_common.vehicle import sensor_topics
                    imu_topic = sensor_topics()["imu_topic"]
                except ValueError as e:
                    imu_topic = "/navera/sensors/imu"
                    self.get_logger().warn(f"gyro heading: {e}; reading {imu_topic}")
            from navera_common.qos import SENSOR_QOS
            self.create_subscription(Imu, imu_topic, self.on_imu, SENSOR_QOS,
                                     callback_group=MutuallyExclusiveCallbackGroup())
            self.get_logger().info(f"gyro heading carry ON: {imu_topic}")

        # ── Handshake "ready" ───────────────────────────────────
        # Le modèle est chargé ET les subscriptions sont en place → on signale au
        # camera_publisher qu'il peut envoyer la frame 1. Latché (TRANSIENT_LOCAL)
        # pour que le publisher reçoive le signal même s'il s'abonne après nous.
        ready_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        self.pub_ready = self.create_publisher(Bool, ready_topic, ready_qos)
        self.pub_ready.publish(Bool(data=True))
        self.get_logger().info(f"📣 localizer_ready=True publié sur {ready_topic} (latché)")

    # ────────────────────────────────────────────────────────────
    # Callbacks
    # ────────────────────────────────────────────────────────────
    def on_image(self, msg: Image):
        try:
            img = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as e:
            self.get_logger().warn(f"cv_bridge decode failed: {e}")
            img = None                      # still paired, so the frame is acked
        pair = self._pairer.add_image(stamp_ns(msg.header.stamp), img)
        if pair is not None:
            self._dispatch(*pair)

    def on_imu(self, msg: Imu):
        """A gyro sample (its sensor time): the heading rate, integrated by self.gyro."""
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if t <= 0:
            return
        w, q = msg.angular_velocity, msg.orientation
        att = None if msg.orientation_covariance[0] == -1.0 else (q.x, q.y, q.z, q.w)
        if self.gyro is not None:
            self.gyro.add_rate(t, heading_rate_dps((w.x, w.y, w.z), att))
        if getattr(self, "att_yaw", None) is not None and att is not None:
            self.att_yaw.add(t, yaw_of_quaternion(att))
        self.frame_gate.add_rate(t, (math.degrees(w.x), math.degrees(w.y), math.degrees(w.z)))

    def on_ap_velocity(self, msg):
        """The autopilot's velocity (TwistStamped ENU m/s, vehicle_link), by its stamp (else its arrival)."""
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if t <= 0:
            t = time.time()
        self.apv.add(t, float(msg.twist.linear.x), float(msg.twist.linear.y))

    def on_nav_status(self, msg: NavStatus):
        self._gps_prior.arbiter(msg.active_source == NavStatus.SOURCE_GPS
                                and msg.state in (NavStatus.STATE_FIX, NavStatus.STATE_DEGRADED))
        self._gps_refused_flag = bool(getattr(msg, "gps_refused", False))

    def on_gps(self, msg: PositionEstimate):
        """GPS position vetted by the arbiter → it becomes the anchor (the prior for GPS loss).

        Read from the arbiter's output (/navera/position, GPS source only): a GPS
        message the arbiter refuses (spoofed, implausible) never reaches it. Taken
        from the raw GPS, the first spoofed fix of an attack became the search
        centre, 2 km off (mission simulator). Any other source is ignored.
        In shadow mode it only seeds a missing anchor.

        Read in its own thread (main(): multi-threaded executor): here only what is thread-safe —
        the prior, the GPS history, the delay calibration, the gyro course and the watchdog's GPS
        snapshot; the track and the anchor are updated under _busy_lock (_drain_gps: now if no
        frame is being matched, else before the next frame), each point at its own time."""
        if msg.source != PositionEstimate.SOURCE_GPS:
            return
        if not self._gps_prior.update(msg.latitude, msg.longitude, msg.valid,
                                      msg.mode == PositionEstimate.MODE_MEASURED):
            return
        rx = time.time()
        st = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if st > 0:
            self._gps_hist.add(st, (float(msg.latitude), float(msg.longitude)))
            self.latency_cal.add_gps(st, float(msg.latitude), float(msg.longitude))
            if getattr(self, "course", None) is not None:
                self.course.maybe_reset(self.gyro, self._gps_hist, st, getattr(self, "_mount_yaw", None))
        # the point's time: the arbiter's stamp (the frames' time base), the arrival if it is far off
        t = st if st > 0 and abs(st - rx) <= 2.0 else rx
        cov = list(msg.position_covariance)
        sigma = math.sqrt(max(cov[0], cov[4])) if cov[0] > 0 else 5.0
        self._gps_snapshot(t, float(msg.latitude), float(msg.longitude), sigma)
        self._gps_pending.append((t, rx, float(msg.latitude), float(msg.longitude), sigma))
        if self._busy_lock.acquire(blocking=False):
            try:
                self._drain_gps()
            finally:
                self._busy_lock.release()

    def _gps_snapshot(self, t, lat, lon, sigma) -> None:
        """GPS thread: the trusted GPS position and its velocity (a GPS-only track) as the watchdog's
        snapshot — at a GPS loss during a long match the carried position starts from the last GPS
        point at once (F32 h1200: 13 s without a position after the cut)."""
        gv = getattr(self, "_gps_vel", None)
        if gv is None:
            return
        gv.add(t, lat, lon, sigma)
        v = gv.velocity(t)
        if v is None:
            return
        snap = self._dr_snap
        if snap is None or t >= snap.t:
            g = self.gyro.at(t) if getattr(self, "gyro", None) is not None else None
            ay = getattr(self, "att_yaw", None)
            yaw = ay.yaw(t) if ay is not None else None
            # along the autopilot's velocity when it draws the GPS track (its bias fitted at most twice a second)
            apv, b = getattr(self, "apv", None), None
            if apv is not None:
                tf, b = self._gps_ap_fit
                if t - tf >= 0.5:
                    b = DaySubscriber._applied_bias(self, apv.fit_bias(list(gv._pts), t))
                    self._gps_ap_fit = (t, b)
            va = apv.v(t) if b is not None else None
            if va is not None:
                self._dr_snap = DrSnap(lat, lon, t, sigma, va[0] + b[0], va[1] + b[1], b[2], 0.0, t,
                                       g[0] if g else None, yaw, b[0], b[1])
            else:
                self._dr_snap = DrSnap(lat, lon, t, sigma, v[0], v[1], v[2], 0.0, t, g[0] if g else None, yaw)

    def _drain_gps(self) -> None:
        """Under _busy_lock: the pending GPS points become the anchor and the track (at their own times)."""
        pending = getattr(self, "_gps_pending", None)
        while pending:
            t, rx, lat, lon, sigma = pending.popleft()
            if self.shadow_mode and self._anchor_lat is not None:
                continue
            self._anchor_lat, self._anchor_lon = lat, lon
            self._anchor_time = rx
            self._last_measured_time = rx
            self._rejects_in_row = 0
            self._anchor_sigma = sigma
            lt = self.track.last_time()
            if lt is None or t > lt:                # (an older point would read as a clock step back)
                self.track.add(t, lat, lon, sigma)
            if getattr(self, "hypotheses", None) is not None:
                self.hypotheses.clear()             # GPS: one track again
            # the GPS now measures the track: a carried velocity from an earlier dead-reckoning
            # (e.g. at power-on, standing still) must not outlive it. It did: after the GPS loss
            # the carry went on with that velocity — 0 m/s for a copter at 8 m/s, 97 m off in 10 s
            # with a stated +-28 m (Isaac Sim closed loop 2026-10-21, low clouds at the GPS loss)
            self._carry, self._vel_epoch = None, None
            self._remember_anchor()
            self._remember_track()

    def on_operator_position(self, msg: PositionEstimate):
        """The operator's start position: the search centre while no GPS is trusted, the
        search circle as wide as its stated accuracy (the circle grows with time since)."""
        if self._gps_prior.fresh() is not None or not is_finite_latlon(msg.latitude, msg.longitude):
            return
        acc = math.sqrt(max(msg.position_covariance[0], msg.position_covariance[4], 1.0))
        now = time.time()
        self._anchor_lat, self._anchor_lon, self._anchor_time = msg.latitude, msg.longitude, now
        self._anchor_sigma = acc
        # the search circle grows by max_speed x the time since the last measurement:
        # start it as wide as the operator's accuracy
        self._last_measured_time = now - acc / max(self.max_speed_mps, 1.0)
        self.track.reset()
        self.get_logger().warn(f"[day] operator start position {msg.latitude:.5f}, {msg.longitude:.5f} "
                               f"(±{acc:.0f} m): searching there (no GPS)")

    def on_start_cmd(self, msg: Bool):
        """Mission stop/rewind → forget the previous run's track (the next run
        starts from GPS, or reports no position until it has a prior)."""
        if msg.data or self._gps_prior.fresh() is not None:
            return
        self._anchor_lat = self._anchor_lon = self._anchor_time = None
        self._last_measured_time = None
        self.track.reset()
        if self.gyro is not None:
            self.gyro.clear()
        state_store.save("day_anchor", {"lat": None, "lon": None})   # forgotten too
        self._carry, self._vel_epoch, self._dr_snap = None, None, None
        self._ap_last_fit = self._restored_bias = None
        state_store.save(TRACK_STATE, {"pts": []})
        self._rejects_in_row = 0
        self.get_logger().info("[day] mission rewind — tracking state reset")

    def on_meta(self, msg: String):
        try:
            meta = json.loads(msg.data)
        except ValueError as e:
            self.get_logger().warn(f"meta JSON decode failed: {e}")
            return
        if not isinstance(meta, dict):
            self.get_logger().warn(f"meta is not a JSON object: {msg.data[:80]!r}")
            return
        pair = self._pairer.add_meta(meta)
        if pair is not None:
            self._dispatch(*pair)

    # ────────────────────────────────────────────────────────────
    # Pair + dispatch
    # ────────────────────────────────────────────────────────────
    def _dispatch(self, img, meta):
        """Handle one image/meta pair (matched on the image stamp)."""
        seq_id = meta.get("frame_id", "?")
        if img is None:
            self.get_logger().error(
                f"[day] frame={seq_id}: image missing or undecodable — acked, not localized")
            self._publish_done(seq_id)
            return
        self._camera_set_delay(meta)
        self._check_mount_id(meta)
        # camera delay hook: date the frame by the estimated delay (raw stamp kept in the meta)
        latency_cal.shift_meta(meta, self.latency_cal.correction() if self.auto_latency else 0.0)
        self._frame_count += 1
        self._last_frame = (time.time(), meta)
        self.get_logger().info(
            f"[day] 📷 paired frame={seq_id}  "
            f"shape={img.shape}  gps_valid={meta.get('gps_valid')}"
        )

        # Strictly serial — back-pressure (camera waits for our ack) guarantees a single
        # frame is ever in flight, so we process inline and NEVER skip/drop a frame.
        # The busy_lock stays as a defensive guard against a future multi-threaded executor.
        with self._busy_lock:
            self._process_frame(seq_id, img, meta)

    def _process_frame(self, seq_id, img, meta):
        try:
            self._drain_gps()
            # GPS connu (CSV lat/lon réelles) → naviguer vers CE point, SANS prédire.
            # (la paire img/meta est déjà consommée dans _dispatch ; le finally
            #  ci-dessous release _busy_lock → la frame suivante est traitée normalement)
            if meta.get("gps_valid") and meta.get("lat") is not None and meta.get("lon") is not None:
                self._publish_known(seq_id, meta)
                return
            self._note_frame_heading(meta)
            self._select_map(img, meta)
            # A live frame the camera could not use (e.g. too tilted): say why, no inference.
            if meta.get("usable") is False:
                why = meta.get("reason") or "frame marked unusable by the camera"
                if self._gps_prior.fresh() is None and \
                        self._dead_reckon(self.get_clock().now().to_msg(), seq_id, meta, {}, 0.0, why):
                    return
                self.pub_status.publish(String(data=json.dumps({
                    "frame_id": seq_id, "success": False, "source": "unusable", "reason": why})))
                return
            # GPS just stopped being trusted: if our own last independent fix disagrees with
            # the last GPS position (a spoofed GPS dragged the anchor away), start from ours
            trusted = self._gps_prior.fresh() is not None
            if self._gps_was_trusted and not trusted:
                self._handover_from_gps()
                # the last delay samples are dropped after a refusal only (as the sigma ones, F39)
                self.latency_cal.freeze("GPS lost or not trusted",
                                        self.latency_rollback_s if getattr(self, "_gps_refused_flag", True) else 0.0)
                self.latency_cal.persist()
                if self.auto_latency:
                    self._relearn_after_delay_change()
                self._rollback_gps_learning()
                self._sigma_store_save(final=True)
            self._gps_was_trusted = trusted
            # Live GPS healthy → it is the position source; no inference needed.
            if trusted and not self.shadow_mode:
                self.pub_status.publish(String(data=json.dumps({
                    "frame_id": seq_id, "success": False, "source": "gps_active",
                    "anchor": [self._anchor_lat, self._anchor_lon]
                    if self._anchor_lat is not None else None,
                    "reason": "GPS valid — vision idle, tracking GPS as prior",
                    "latency": dict(self.latency_cal.state(), auto=self.auto_latency)})))
                self._gps_odometry(img, meta)
                self._prewarm(img, meta)
                self._calibrate_altitude(seq_id, img, meta)
                return
            self._gps_vo_t = None                   # the GPS-time odometry chain ends here
            center, R = self._spatial_window(img, meta)
            if center is not None:
                self.get_logger().info(f"[day] 🔎 localizing frame={seq_id}… (cercle R={R:.0f}m autour de l'anchor)")
            elif not self.allow_global_search:
                self._publish_no_fix(self.get_clock().now().to_msg(), seq_id, meta,
                                     {"frame_id": seq_id}, 0.0,
                                     "no position prior (waiting for a GPS fix); "
                                     "whole-map search disabled — not reliable")
                return
            else:
                self.get_logger().info(f"[day] 🔎 localizing frame={seq_id}… (pas d'anchor → recherche globale)")
            if self._frame_refused(seq_id, img, meta):
                return
            mpp, why_not = self._frame_m_per_px(img, meta)
            self._vo_step = None
            if mpp is not None:
                ns = meta.get("image_stamp_ns")
                t_img = int(ns) / 1e9 if ns else time.time()
                v = self.track.velocity(time.time())
                pred = None
                if v is not None and self.vo._prev is not None:
                    dt = t_img - self.vo._prev[3]
                    pred = (v[0] * dt, v[1] * dt)
                self._vo_step = self._vo_gate(self.vo.step(img, self._heading_for_match(meta), mpp, t_img, pred),
                                              v, t_img, getattr(self.vo, "last_shift_px", None))
            if self.local is not None and center is not None and mpp is not None:
                # after height_retry_after failures, 20 % lower and 25 % higher too
                factors = [1.0] + ([0.8, 1.25] if self._rejects_in_row + 1 >= self.height_retry_after
                                   and not self._compute_degraded() else [])
                t_frame0, budget, result = time.monotonic(), getattr(self, "frame_budget_s", 6.0), {}
                for f in factors:
                    if f != 1.0 and time.monotonic() - t_frame0 > budget:
                        result["reason"] = (f"{result.get('reason')}; other heights not tried "
                                            f"(frame budget {budget:.0f} s)")
                        break
                    # the heading search (12 headings) only at the frame's own height: at 1200 m the
                    # three heights x 12 headings held one frame 58-93 s (Isaac Sim h1200)
                    result = self._locate_search(img, center, R, mpp * f, meta, windows=f == 1.0,
                                                 heading_search=f == 1.0)
                    if not result.get("accepted"):
                        result, f = self._rescaled_match(img, result, center, R, mpp, f, meta)
                    if result.get("accepted"):
                        break
                sc = float(result.get("scale_residual") or 1.0)
                if result.get("accepted") and abs(sc - 1.0) > 0.05:
                    # the fitted scale answers only ~half of a height error (campaign 2: slope
                    # 0.45-0.6): match again at the corrected height, keep it if it holds
                    wc, wr = result.get("_window") or (center, R)
                    again = self.local.locate(img, wc, wr, mpp * f * sc, scale_tol=self._scale_tol(meta),
                                              **self._match_heading_kw(meta), hfov_deg=self._hfov(meta),
                                              expected_tilt_deg=self._expected_tilt(meta), **self._heading_search_kw())
                    if result.get("_window_off"):
                        again = self._window_gate(dict(again, _window=result["_window"], _window_off=True))
                    if again.get("accepted") and int(again.get("inliers") or 0) >= int(result.get("inliers") or 0) // 2:
                        result, f = again, f * sc
                result["_frame_shape"], result["_frame_mpp"] = img.shape, mpp * f
                result["_height_factor"] = f
            elif self.local is not None:
                # retrieval (~440 m median on real frames) is no substitute for a local match
                # that cannot run: published, its positions were 1.1 km off (sim, near the ground)
                self._publish_no_fix(self.get_clock().now().to_msg(), seq_id, meta, {"frame_id": seq_id}, 0.0,
                                     why_not or "no prior: local matching needs a search centre")
                return
            else:
                result = self.localizer.predict(img, threshold=self.conf_threshold,
                                                center=center, radius_m=R)
            result["search_center"] = list(center) if center is not None else None
            self._log_top5(seq_id, result)
            self._publish_result(seq_id, meta, result)
        except Exception as e:
            self.get_logger().error(f"[day] localizer error frame={seq_id}: {e}")
        finally:
            # ALWAYS ack — known / accepted / rejected / error — so the camera never
            # hangs waiting for a frame whose outcome was "rejected" or "error".
            self._publish_done(seq_id)

    def _rescaled_match(self, img, result, center, R, mpp, f, meta):
        """(result, height factor). A strong match (>= strong_inliers) refused only for its fitted scale is
        matched again at the height that scale implies (mpp x f x scale), when that height is within
        local_scale_tol_max of the frame's own. Isaac Sim h1200: the frame failed at its own height (the
        carry outside its circle), its 25 % higher retry loaded a wider map, found the place with 150-355
        inliers at scale 0.81 — i.e. at the frame's own height (1.25 x 0.81 = 1.01) — and was refused as a
        "wrong place" 9 frames in a row while the carry drifted 1-3 km. The match again must pass the
        usual scale window (and every gate after it) at the corrected height."""
        sc = result.get("scale_residual")
        if not str(result.get("reason") or "").startswith("fitted scale") or sc is None or \
                int(result.get("inliers") or 0) < getattr(self, "strong_inliers", 100):
            return result, f
        g = f * float(sc)
        if not (math.isfinite(g) and abs(g - 1.0) <= getattr(self, "local_scale_tol_max", 0.35)):
            return result, f
        if result.get("predicted_lat") is None or result.get("predicted_lon") is None:
            return result, f
        # around the place it found (the frame's own circle had failed at that height), a small circle
        wc = (float(result["predicted_lat"]), float(result["predicted_lon"]))
        wr = max(getattr(self, "local_min_radius_m", 50.0), 50.0)
        again = self.local.locate(img, wc, wr, mpp * g, scale_tol=self._scale_tol(meta),
                                  **self._match_heading_kw(meta), hfov_deg=self._hfov(meta),
                                  expected_tilt_deg=self._expected_tilt(meta))
        if again.get("accepted") and int(again.get("inliers") or 0) >= getattr(self, "strong_inliers", 100):
            self.get_logger().info(f"[day] frame matched again at the height its fitted scale implies "
                                   f"(x{g:.2f}: {again.get('inliers')} inliers)")
            return dict(again, rescaled_from=round(float(sc), 3), radius_m=result.get("radius_m", R),
                        search_center_rescaled=list(wc)), g
        return result, f

    def _log_top5(self, seq_id, result):
        """Diagnostic correctif #1 : top-5 des matches (DINOv2) pour les frames sans GPS."""
        top5 = result.get("top5")
        if not top5:
            return
        self.get_logger().info(f"[day] 🔝 TOP-5 frame={seq_id} (retrieval=DINOv2)")
        for c in top5:
            self.get_logger().info(
                f"        #{c['rank']} idx={c['index']:4d} {c['image']:<28} "
                f"dino={c['dino']:.3f} "
                f"lat={c['lat']:+.5f} lon={c['lon']:+.5f}"
            )

    # ── frame quality and fix blending (F20, F23, D17) ──────────────────
    def _frame_refused(self, seq_id, img, meta) -> bool:
        """A frame day_pkg.frame_gate refuses (turning fast at the exposure, or blurred): not matched, the
        position carried (or 'no position') with the reason. False when the frame is to be matched."""
        g = self.frame_gate
        if g.max_blur_px <= 0 and g.sharp_rel <= 0:
            return False
        ns = meta.get("image_stamp_ns")
        q = g.check(int(ns) / 1e9 if ns else None, img if g.sharp_rel > 0 else None,
                    focal_px(img.shape[1], self._hfov(meta) or 0.0))
        if q["refuse"] is None:
            return False
        if not self._dead_reckon(self.get_clock().now().to_msg(), seq_id, meta, dict(frame_quality=q), 0.0,
                                 q["refuse"]):
            self._publish_no_fix(self.get_clock().now().to_msg(), seq_id, meta, {"frame_id": seq_id}, 0.0,
                                 q["refuse"] + "; " + self._dr_why)
        return True

    def _blend_fix(self, lat, lon, result, meta, status):
        """(lat, lon, sigma) of a local fix averaged with the carried position by their sigmas, or None
        (blend_fixes off, a re-acquisition, no carried position, or a carry without a heading: it lags in
        turns, F23). A fix with few inliers is noisy, not biased: averaged, its error is shared with the
        carry's; a confident wrong one that passed the gate pulls the output part of the way only.

        Only the fix's independent error is averaged (F41). The carry is made of the earlier fixes (the
        track holds the measured fixes, not this output), so the errors common to all of them — the
        unknown camera delay (speed x its sigma, along the track) and the camera mount's (height x
        tan(its sigma)) — are in the carry too: they set neither the weight nor shrink in the stated
        sigma, hypot(sqrt(k) x the independent part, the common part). Counted as independent, they
        were averaged down frame after frame: Isaac Sim closed loop 2026-10-22 (copter, delay unknown)
        stated 5-9 m for 13-20 m errors, 146 of 356 outputs beyond 3 sigma, and with the carry fed its
        own output it lagged 100 m behind (90 wrong fixes without the mount calibration)."""
        if not self.blend_fixes or status.get("reacquired") or self._carry_heading(meta)[0] is None:
            return None
        pred = self._predicted(meta)
        if pred is None:
            return None
        sig = self._fix_sigma(result, meta)
        common = min(sig, self._fix_sigma_common(result, meta))
        r2 = max(sig * sig - common * common, 0.0)               # the fix's own error
        q2 = max(float(pred[2]) ** 2 - common * common, 0.0)     # the carry's own (beyond the common part)
        k = q2 / (q2 + r2) if q2 + r2 > 0.0 else 1.0
        de, dn = _en((lat, lon), pred[:2])
        p = _move(pred[:2], k * de, k * dn)
        out_sig = math.hypot(math.sqrt(k * r2), common)
        status["blend"] = {"weight": round(k, 3), "fix_sigma_m": round(sig, 1), "carry_sigma_m": round(pred[2], 1),
                           "common_sigma_m": round(common, 1)}
        return p[0], p[1], out_sig

    def _publish_done(self, seq_id):
        self._publish_camera_delay()            # before the ack: the next frame is straightened with it
        try:
            fid = int(seq_id)
        except (TypeError, ValueError):
            fid = -1
        self.pub_done.publish(Int32(data=fid))
        self.get_logger().info(f"[day] ✓ done frame={seq_id} → ack ({self.pub_done.topic_name})")

    def _publish_known(self, seq_id, meta):
        """GPS connu (vérité terrain) : publie la position du CSV, sans prédiction."""
        now = self.get_clock().now().to_msg()
        lat = float(meta["lat"]); lon = float(meta["lon"])
        status = {
            "frame_id": seq_id, "success": True,
            "lat": lat, "lon": lon,
            "score": 1.0, "match": None, "total_ms": 0.0,
            "source": "gps", "error": None,
        }
        self.pub_status.publish(String(data=json.dumps(status)))
        fix = NavSatFix()
        fix.header.stamp    = now
        fix.header.frame_id = "day_camera_link"
        fix.status.status   = NavSatStatus.STATUS_FIX
        fix.status.service  = NavSatStatus.SERVICE_GPS
        fix.latitude        = lat
        fix.longitude       = lon
        _alt = meta.get("altitude_m")
        fix.altitude        = float(_alt) if _alt is not None else math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        self._success_count += 1
        # frame 11 (1ère prédiction) prendra CE point GPS (frame 10) comme référence
        self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, time.time()
        self._anchor_sigma = None
        self._last_measured_time = self._anchor_time
        self._rejects_in_row = 0
        # Additive contract: CSV truth → MODE_REPLAYED (never a DINOv2 measurement).
        self._publish_estimate(now, seq_id, "gps", lat, lon, meta, score=1.0,
                               details={"src": "gps", "score": 1.0, "note": "CSV ground truth"})
        self.get_logger().info(
            f"[day] 🛰 KNOWN frame={seq_id}  lat={lat:+.5f}  lon={lon:+.5f}  (GPS truth)"
        )

    # ────────────────────────────────────────────────────────────
    # Anti-jump helpers
    # ────────────────────────────────────────────────────────────
    PREFETCH_AHEAD_S = 8.0          # how far ahead (in time) the map features are prepared

    def _prefetch_ahead(self, lat, lon, t_now, img_shape=None, mpp=None):
        """From the last two matches, prepare the map features where the vehicle will be."""
        prev = (self._anchor_lat, self._anchor_lon, self._anchor_time)
        alat, alon = lat, lon
        if None not in prev and t_now > prev[2]:
            dt = t_now - prev[2]
            k = self.PREFETCH_AHEAD_S / dt
            alat, alon = lat + (lat - prev[0]) * k, lon + (lon - prev[1]) * k
        margin = 0.5 * math.hypot(*img_shape[:2]) * mpp if img_shape and mpp else 300.0
        self.local.tiles.prefetch(alat, alon, R_MAX_M + margin)

    def _handover_from_gps(self):
        """At GPS loss or refusal: the anchor is the last trusted GPS position, unless a
        recent independent vision fix disagrees with it by more than 100 m (the GPS was
        drifting: spoofing) — then the search starts from where vision last saw us."""
        c = self._check_fix
        if c is None or self._anchor_lat is None or time.time() - c[2] > 10.0:
            return
        d = haversine_m(self._anchor_lat, self._anchor_lon, c[0], c[1])
        if d > 100.0:
            self.get_logger().warn(f"[day] GPS lost/refused: starting from the last vision fix, "
                                   f"{d:.0f} m from the last GPS position (GPS was drifting)")
            self._anchor_lat, self._anchor_lon, self._anchor_time = c[0], c[1], c[2]
            self._anchor_sigma = self.local_sigma_m
            self._last_measured_time = c[2]
            self.track.reset()                      # its GPS points were the spoofed ones
            self.track.add(c[2], c[0], c[1], self.local_sigma_m)

    def _rollback_gps_learning(self):
        """GPS just stopped being trusted: forget the sigma-calibration and map-bias samples of the
        last calib_rollback_s (a slow spoof is trusted until refused; its drift must not be learned)."""
        if self.calib_rollback_s <= 0:
            return
        since = time.time() - self.calib_rollback_s
        # the sigma samples only after a REFUSAL (a slow spoof is trusted until refused); a GPS simply
        # lost keeps them: right after take-off they are all there is (Isaac endurance 2026-10-22: GPS
        # lost 12 s after reaching altitude, the 24 samples of the climb forgotten, F39). A drift
        # learned as vision error could only make the stated sigma larger. The map bias and the camera
        # mount (a spoof's drift would be learned as a mount error) are rolled back at any loss.
        refused = getattr(self, "_gps_refused_flag", True)
        n_sig = self.sigma_cal.rollback(since) if refused else 0
        n_bias = self.map_bias.rollback_bias(since)
        n_mount = self.mount_cal.rollback(since) if getattr(self, "mount_cal", None) is not None else 0
        self._save_mount_cal()
        if n_sig or n_bias or n_mount:
            self.get_logger().info(f"[day] GPS no longer trusted: forgot the last {self.calib_rollback_s:.0f} s of "
                                   f"GPS-learned samples (sigma calibration {n_sig}, map bias {n_bias}, "
                                   f"camera mount {n_mount})")
        if not refused and self.sigma_cal.samples:
            self.get_logger().info(f"[day] GPS lost (not refused): the sigma calibration keeps its "
                                   f"{self.sigma_cal.samples} samples")

    # ── memory: the heap pages freed by the frames go back to the system (F40) ──
    def _memory_trim_init(self):
        """A timer (in the node's serial callback group: never during a frame) that calls glibc
        malloc_trim every memory_trim_period_s (navera_common.memory_trim)."""
        declare_float(self, "memory_trim_period_s", 60.0,
                      "give freed heap memory back to the system this often (s); 0 = never")
        self._trimmer = memory_trim.Trimmer(float(self.get_parameter("memory_trim_period_s").value))
        if self._trimmer.period_s > 0:
            self.create_timer(min(self._trimmer.period_s, 30.0), self._memory_trim)

    def _memory_trim(self):
        if self._trimmer.maybe_trim():
            self.get_logger().info(f"[day] memory: RSS {memory_trim.rss_mib() or 0:.0f} MiB after malloc_trim "
                                   f"(gave back {self._trimmer.last_freed_mib or 0:.0f} MiB in "
                                   f"{self._trimmer.last_ms or 0:.0f} ms)", throttle_duration_sec=600.0)

    # ── the sigma calibration kept per camera across flights (F39) ──
    def _sigma_store_init(self):
        """Parameters of the stored sigma calibration, and the one kept for this camera (by the
        camera-delay key: latency_store_key / the calibration file's name) as this flight's prior."""
        self.declare_parameter("sigma_cal_store", True)
        self.declare_parameter("sigma_cal_store_key", "")
        declare_float(self, "sigma_cal_store_max_age_days", 30.0, "a stored sigma calibration older than this is ignored")
        declare_float(self, "sigma_cal_store_inflation", 1.3,
                      "a stored calibration is used scaled by this (terrain, light, height change between flights)")
        declare_float(self, "sigma_cal_store_floor_m", 10.0, "a stored calibration never states less than this (m)")
        self._gps_refused_flag = False
        self._sigma_store_t, self._sigma_store_saved = 0.0, None
        self._sigma_store_key = (latency_cal.store_key(str(self.get_parameter("sigma_cal_store_key").value))
                                 if bool(self.get_parameter("sigma_cal_store").value) else None)
        if self._sigma_store_key is None:
            return
        kept = load_sigma_cal(self._sigma_store_key,
                              float(self.get_parameter("sigma_cal_store_max_age_days").value) * 86400.0)
        if kept is None:
            return
        age_d = (time.time() - kept["saved_at"]) / 86400.0
        if self.sigma_cal.set_prior(kept["f"], kept["b"], f"stored ({self._sigma_store_key}, {age_d:.1f} d old)",
                                    float(self.get_parameter("sigma_cal_store_inflation").value),
                                    float(self.get_parameter("sigma_cal_store_floor_m").value)):
            self.get_logger().info(f"[day] sigma calibration: starting from the one kept for this camera "
                                   f"(f {kept['f']:.2f}, b {kept['b']:.1f} m, {kept['samples']} samples, "
                                   f"{age_d:.1f} days old) until this flight has its own")

    def _sigma_store_save(self, final: bool = False):
        """Keep this flight's sigma calibration for the next flight with this camera: every 60 s
        from the samples older than calib_rollback_s (a later spoof refusal could still roll the
        newer ones back), and at the GPS loss / refusal from what the rollback left."""
        if self._sigma_store_key is None or (not final and time.time() - self._sigma_store_t < 60.0):
            return
        self._sigma_store_t = time.time()
        terms = self.sigma_cal.export(None if final else time.time() - self.calib_rollback_s)
        if terms is None or terms == self._sigma_store_saved:
            return
        if save_sigma_cal(self._sigma_store_key, terms):
            self._sigma_store_saved = terms
            self.get_logger().info(f"[day] sigma calibration kept for the next flight ({self._sigma_store_key}): "
                                   f"f {terms['f']:.2f}, b {terms['b']:.1f} m, {terms['samples']} samples")

    def _calibrate_altitude(self, seq_id, img, meta):
        """GPS trusted: every gps_check_period_s, match this frame within gps_check_radius_m
        of the GPS position. A match is published as an independent day-vision estimate
        (the estimator never prefers it to a trusted GPS, but cross-checks GPS with it:
        a slowly spoofed GPS drifts away and is refused) and gives the height above
        ground. The tracking state (anchor) is not touched: GPS stays the prior."""
        if self.local is None or self.calib_period_s <= 0 or time.time() - self._last_calib < self._gps_check_period():
            return
        prior = self._gps_prior.fresh()
        mpp, _ = self._frame_m_per_px(img, meta)
        if prior is None or mpp is None:
            return
        self._last_calib = time.time()
        res = self._gps_check_locate(img, prior, mpp, meta)
        self.get_logger().info(
            f"[day] GPS check frame={seq_id}: " + (f"vision {haversine_m(prior[0], prior[1], res['predicted_lat'], res['predicted_lon']):.0f} m from GPS "
                                                  f"({res.get('inliers')} inliers)" if res.get("accepted") else f"no match ({res.get('reason')})"))
        if res.get("accepted"):
            self._check_fix = (float(res["predicted_lat"]), float(res["predicted_lon"]), time.time())
            self._latency_sample(meta)
            ns = meta.get("image_stamp_ns")
            self._gyro_reset(int(ns) / 1e9 if ns else time.time(), res)   # heading known at the GPS loss
            g = self._gps_hist.at(int(ns) / 1e9) if ns else None
            if g is not None:
                self._lens_sample(res, meta, img, g, int(ns) / 1e9)
            placed = self._mount_check_fix(res, meta, g)
            if placed is None:                      # refused (pose far from the attitude): no sample
                return
            self._check_fix = (placed[0], placed[1], self._check_fix[2])
            res["predicted_lat"], res["predicted_lon"] = placed
            if g is not None:                       # no GPS at the frame's instant: no sample
                self.map_bias.bias_sample(self._check_fix[:2], g, self._heading_for_match(meta), t=self._check_fix[2])
                # this flight's real vision error, the map bias removed as it will be after a GPS loss
                de, dn = self.map_bias.bias(self._check_fix[:2])
                v = _move(self._check_fix[:2], de, dn)
                self.sigma_cal.add(haversine_m(v[0], v[1], g[0], g[1]), self._model_sigma(res, meta),
                                   t=self._check_fix[2])
                self._sigma_store_save()
            st = {}
            self._publish_vision_altitude(meta, res, st)
            self._publish_estimate(exposure_stamp(meta, self.get_clock().now().to_msg()), seq_id, "local_match",
                                   float(res["predicted_lat"]), float(res["predicted_lon"]), meta,
                                   score=float(res.get("score") or 0.0),
                                   details={"src": "local_match", "gps_check": True,
                                            "inliers": res.get("inliers"), "sigma_m": self._fix_sigma(res, meta)})
            self.get_logger().info(f"[day] height above ground calibrated while GPS is good: "
                                   f"{st.get('altitude_measured_m')} m (frame said {meta.get('altitude_m')} m, "
                                   f"{res.get('inliers')} inliers)", throttle_duration_sec=30.0)

    def _gps_odometry(self, img, meta) -> None:
        """GPS trusted: one visual-odometry step (this frame against the last one given, at most every
        gps_vo_period_s) published for the estimator's relative-motion test. Needs the frame stamp, a
        height and a heading (the frame's attitude, else the gyro-carried one); otherwise the chain
        restarts."""
        ns = meta.get("image_stamp_ns")
        if not self.gps_vo_enabled or ns is None:
            return
        t = int(ns) / 1e9
        if self._gps_vo_t is not None and 0.0 <= t - self._gps_vo_t < self.gps_vo_period_s:
            return
        mpp, _ = self._frame_m_per_px(img, meta)
        heading = self._carry_heading(meta)[0]
        if mpp is None or heading is None:
            self.gps_vo.reset()
            self._gps_vo_t = None
            return
        alt = float(meta["altitude_m"])
        h = self._gps_vo_h
        if h is None or not 0.0 < t - h[1] <= 30.0:
            h = (alt, t)
        else:
            w = 1.0 - math.exp(-(t - h[1]) / self.gps_vo_height_tau_s) if self.gps_vo_height_tau_s > 0 else 1.0
            h = (h[0] + w * (alt - h[0]), t)
        self._gps_vo_h = h
        width = img.shape[1]
        self.gps_vo.scale = min(1.0, self.gps_vo_width_px / float(width)) if self.gps_vo_width_px > 0 else 1.0
        if self._gps_vo_t is None:
            self.gps_vo.reset()
        self._gps_vo_t = t
        step = self.gps_vo.step(img, heading, mpp * h[0] / alt, t)
        if step is None:
            return
        de, dn, dt, q = step
        self.pub_gps_vo.publish(String(data=json.dumps({
            "t0": t - dt, "t1": t, "east_m": round(de, 3), "north_m": round(dn, 3), "quality": round(q, 3)})))

    def _gps_check_period(self) -> float:
        """Seconds between GPS-check matches: gps_check_period_s, or the faster
        gps_check_period_delay_s while auto_latency has no stable delay yet — its 20 samples took
        more than the 75 s of GPS flight at altitude at one check per 2 s (Isaac Sim closed loop
        2026-10-21: 7-9 samples, never applied)."""
        fast = float(getattr(self, "calib_period_delay_s", 0.0))
        lc = getattr(self, "latency_cal", None)
        if fast > 0.0 and getattr(self, "auto_latency", False) and lc is not None and not lc.stable:
            return min(self.calib_period_s, fast)
        return self.calib_period_s

    def _gps_check_locate(self, img, prior, mpp, meta) -> dict:
        """The GPS-check match: first within gps_check_near_radius_m of the GPS (a trusted GPS is
        metres off), then, if that fails, within gps_check_radius_m (a GPS drifted that far).
        A small frame against a 600 m window gave the learned matcher too few matches: Isaac Sim
        closed loop 2026-10-21, copter at 250 m, 2 of 30 checks accepted while the same frames
        matched 96 % around the carried position after the GPS loss — no delay, sigma or
        spoof-check samples."""
        radii = [self.calib_radius_m]
        if 0.0 < self.calib_near_radius_m < self.calib_radius_m:
            radii.insert(0, self.calib_near_radius_m)
        res = {}
        for r in radii:
            res = self.local.locate(img, prior, r, mpp, scale_tol=self._scale_tol(meta),
                                    **self._match_heading_kw(meta), hfov_deg=self._hfov(meta),
                                    expected_tilt_deg=self._expected_tilt(meta))
            if res.get("accepted"):
                break
        return res

    def _camera_set_delay(self, meta):
        """The delay live_camera already subtracted (capture_latency_s: bench-measured, from the
        calibration file or NAVERA_CAMERA_LATENCY_S) is the set delay: the frames' raw stamps are
        arrival minus it. Without this the day node took a measured delay for an unknown one."""
        dm = meta.get("delay_monitor") or {}
        # live_camera's delay monitor (navera_common.delay_monitor): the delay moved since the start
        self._delay_change_s = abs(float(dm.get("change_s") or 0.0)) if dm.get("significant") else 0.0
        if self._delay_change_s:
            self.get_logger().warn(f"[day] camera delay changed by {dm.get('change_s')} s since the start: "
                                   "stated accuracy widened by speed x that", throttle_duration_sec=30.0)
        cl = meta.get("capture_latency_s")
        try:
            cl = float(cl)
        except (TypeError, ValueError):
            return
        lc = self.latency_cal
        if cl != lc.nominal:
            if lc.set_nominal(cl, "the camera's capture_latency_s"):
                self.get_logger().info(f"[day] camera delay {cl:.3f} s set by the camera (bench-measured)")
            else:
                self.get_logger().warn(f"[day] the camera subtracts {cl:.3f} s, the delay estimate is relative to "
                                       f"{lc.nominal:.3f} s", throttle_duration_sec=60.0)

    def _relearn_after_delay_change(self):
        """The applied delay moved by more than latency_relearn_s since the GPS-learned samples
        (map bias, sigma calibration) were taken: they compared vision with the GPS at the frame
        time of the OLD delay — speed x the change along the track, learned as a map shift or as
        vision error. Forget them; the GPS checks learn them again with the new dating (a
        consistency rule: in the Isaac Sim plane runs of 2026-10-22 no map bias was applied)."""
        d = self.latency_cal.correction()
        ref = getattr(self, "_learned_delay", 0.0)
        if abs(d - ref) <= float(getattr(self, "latency_relearn_s", 0.2)):
            return
        self._learned_delay = d
        n_sig, n_bias = self.sigma_cal.rollback(float("-inf")), self.map_bias.rollback_bias(float("-inf"))
        mc = getattr(self, "mount_cal", None)
        n_mount = mc.rollback(float("-inf")) if mc is not None else 0
        self.get_logger().info(f"[day] camera delay moved {d - ref:+.2f} s: forgot {n_bias} map-bias, {n_sig} "
                               f"sigma-calibration and {n_mount} camera-mount samples dated by the old delay")

    def _latency_sample(self, meta):
        """A GPS-check match is a camera-delay sample (its arrival = raw stamp + the camera's delay)."""
        raw = meta.get("image_stamp_raw_ns")
        if raw is None:
            return
        self.latency_cal.add_fix(int(raw) / 1e9 + self.latency_cal.nominal, *self._check_fix[:2])
        st = self.latency_cal.state()
        if st["applied_s"] != self._latency_applied:
            self._latency_applied = st["applied_s"]
            self.get_logger().warn(
                f"[day] camera delay {st['delay_s']} +- {st['applied_sigma_s']} s (estimate {st['estimate_s']} "
                f"+- {st['sigma_s']} s, {st['samples']} samples; set {st['nominal_s']} s; {st['reason']})"
                + ("" if self.auto_latency else " — auto_latency off: not applied"))
            if self.auto_latency:
                self.latency_cal.persist()
                self._relearn_after_delay_change()

    def _prewarm(self, img, meta):
        """While GPS is trusted, vision is idle: compute the map features around the current
        position now, so that the first frames after a GPS loss find them ready (computed
        on demand, the tiles of a whole search circle take seconds — stale positions).
        Only the tiles not yet cached cost anything; a frame's time budget is respected."""
        if self.local is None or self._anchor_lat is None:
            return
        mpp, _ = self._frame_m_per_px(img, meta)
        if mpp is None:
            return
        _, R = self._spatial_window(img, meta)
        margin = 0.5 * math.hypot(*img.shape[:2]) * mpp
        self.local.tiles.prefetch(self._anchor_lat, self._anchor_lon, R + margin)

    def _heading_search_kw(self, meta=None) -> dict:
        """locate() keywords: the heading search when the matcher has it and it is enabled, or when this
        frame's heading is uncertain (D18, local_heading_search_after): none known (no frame attitude
        heading, no gyro-carried one), or that many frames in a row without a match. meta: the frame's
        (default: the frame being processed)."""
        if not hasattr(self.local, "heading_search_deg"):
            return {}
        if self.heading_search:
            return {"heading_search": True}
        n = getattr(self, "heading_search_after", 0)
        if n <= 0:
            return {}
        if meta is None:
            last = getattr(self, "_last_frame", None)
            meta = last[1] if last else {}
        if self._match_heading_kw(meta)["heading_deg"] is None or self._rejects_in_row >= n:
            return {"heading_search": True}
        return {}

    def _hfov(self, meta):
        """Field of view of this frame: the live camera states it (undistorted image),
        else the camera_hfov_deg parameter."""
        try:
            v = float(meta.get("camera_hfov_deg"))
            if 1.0 < v < 179.0:
                return v
        except (TypeError, ValueError):
            pass
        return self.camera_hfov_deg

    @staticmethod
    def _expected_tilt(meta) -> float:
        """The tilt from straight down the attitude gives this frame (the pose guard's
        reference): 0 for a frame straightened with it (live camera) or without an attitude
        (assumed straight down); the measured tilt for a frame left as taken."""
        if meta.get("straightened") or meta.get("attitude_source") in (None, "none"):
            return 0.0
        try:
            t = float(meta.get("tilt_deg"))
        except (TypeError, ValueError):
            return 0.0
        return t if math.isfinite(t) else 0.0

    def _scale_tol(self, meta):
        """Accepted scale error: the configured one, widened to twice the frame's relative
        altitude uncertainty (e.g. GPS altitude over unknown terrain), capped."""
        tol = self.local.scale_tol
        try:
            rel = 2.0 * float(meta.get("altitude_sigma_m")) / float(meta.get("altitude_m"))
            if math.isfinite(rel):
                tol = min(max(tol, rel), self.local_scale_tol_max)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        return tol

    def _frame_m_per_px(self, img, meta):
        """(metres per frame pixel, None) from the frame altitude and the camera's field of
        view, or (None, why) when the scale of this frame cannot be known."""
        hfov = self._hfov(meta)
        if not math.isfinite(hfov) or not 1.0 < hfov < 179.0:
            return None, "camera_hfov_deg unknown"
        try:
            alt = float(meta.get("altitude_m"))
        except (TypeError, ValueError):
            return None, "frame altitude unknown"
        if not (math.isfinite(alt) and alt > 5.0):
            return None, "frame altitude unknown or on the ground"
        return LocalMatcher.frame_m_per_px(img.shape[1], alt, hfov), None

    def _spatial_window(self, img, meta):
        """Cercle de recherche pour une frame GPS-denied.
        Centre = dernier point retenu (anchor). Retourne (None, None) si aucun anchor.

        Formule (cahier des charges, gardée EXPLICITE) :
            footprint_m = GSD_M_PER_PX × max(largeur, hauteur) de la frame   (≈1486 m)
            R_theorique = max(footprint_m × FOOTPRINT_MULT, altitude_m × ALTITUDE_MULT)
            R           = clamp(R_theorique, R_MIN_M, R_MAX_M)

        R_MAX_M borne le rayon théorique à la zone de matching fiable validée au
        harnais (cf. constantes en tête de fichier) : sans ce plafond, R≈4458 m
        engloberait presque tout le dataset et l'erreur remonterait vers ~3485 m.
        """
        if self._anchor_lat is None or self._anchor_lon is None:
            return None, None
        h, w        = img.shape[:2]
        footprint_m = GSD_M_PER_PX * max(w, h)
        altitude_m  = float(meta.get("altitude_m") or 0.0)
        R_theorique = max(footprint_m * FOOTPRINT_MULT, altitude_m * ALTITUDE_MULT)
        R           = min(max(R_theorique, R_MIN_M), R_MAX_M)
        if self.local is not None:
            pred = self._predicted(meta)
            if pred is not None:
                # the carried position and k sigma of it: the window follows the uncertainty
                # (a lost vehicle is searched for wider, a tracked one cheaply)
                return (pred[0], pred[1]), min(max(self.search_k * pred[2], self.local_min_radius_m),
                                               self._search_cap_m())
            if self._last_measured_time is not None:
                # the vehicle may have gone this far since the last match: search that far
                grown = R + self.max_speed_mps * max(0.0, time.time() - self._last_measured_time)
                R = min(max(R, grown), max(R, self.local_max_radius_m))
        return (self._anchor_lat, self._anchor_lon), R

    # ── re-acquiring after a gap (F32, day_pkg.reacquire) ──────────────────
    def _search_cap_m(self) -> float:
        """Widest search radius around the carried position: local_max_radius_m for one window,
        reacquire_max_radius_m when wide circles are covered with several windows."""
        if getattr(self, "reacquire_windows", False):
            return max(self.local_max_radius_m, self.reacquire_max_radius_m)
        return self.local_max_radius_m

    def _reacquire_window_m(self, img, mpp: float) -> float:
        """Radius of one search window: a fraction of the frame's half diagonal on the ground (the
        matcher's margin; the map window is that plus this), never under local_min_radius_m. A small
        frame against a wide window drowns in the map's features."""
        margin = 0.5 * math.hypot(*img.shape[:2]) * mpp
        return max(self.local_min_radius_m, self.reacquire_window_frac * margin)

    def _window_gate(self, res: dict) -> dict:
        """A match found in a window other than the carried position's: one try among several, so it
        needs reacquire_min_inliers (more windows tried, more chances of an accidental match)."""
        if res.get("accepted") and res.get("_window_off") and \
                int(res.get("inliers") or 0) < self.reacquire_min_inliers:
            res = dict(res, accepted=False, reason=f"{res.get('inliers')} inliers in a re-acquisition window "
                                                   f"off the carried position (min {self.reacquire_min_inliers})")
        return res

    def _locate_search(self, img, center, R, mpp, meta, windows: bool = True, heading_search: bool = True) -> dict:
        """locate() over the search circle (center, R): one window when R is at most ~one window wide
        (or windows is False: only the carried position's), else the circle covered with windows
        (cover_windows), this frame's share of them (WindowScan) tried nearest first until a match.
        The result says the window it came from ("_window": (centre, radius)), "windows_tried" and
        "radius_m" = R (the circle searched in all). The heading search, when on, runs in the carried
        position's window only."""
        hk = self._match_heading_kw(meta)
        kw = dict(scale_tol=self._scale_tol(meta), **hk, hfov_deg=self._hfov(meta),
                  expected_tilt_deg=self._expected_tilt(meta), **self._heading_search_kw())
        if not heading_search and "heading_search" in kw:
            kw["heading_search"] = False
        w = self._reacquire_window_m(img, mpp)
        if not getattr(self, "reacquire_windows", False) or R <= 1.25 * w:
            self._scan.reset()
            return self.local.locate(img, center, R, mpp, **kw)
        if hk.get("heading_deg") is not None and "heading_search" in kw and not self.heading_search:
            # re-acquiring: the frames fail for the position, not for a heading the frame states — the
            # search after rejects in a row (local_heading_search_after) would try 12 headings in every
            # window and height: 12-19 s a frame after a 60 s outage (Isaac Sim), the carry 10 s stale
            kw["heading_search"] = False
        if not windows:
            res = self.local.locate(img, center, w, mpp, **kw)
            return dict(res, _window=(center, w), radius_m=float(R))
        cover = cover_windows(R, w)
        best, tried, t0 = None, 0, time.monotonic()
        for de, dn in self._scan.pick(cover, self.reacquire_per_frame):
            if tried and time.monotonic() - t0 > self.reacquire_budget_s:
                break                                   # the rest of the scan goes on next frame
            c = _move(center, de, dn) if (de or dn) else center
            # a heading search (12 headings) only in the carried position's window: in every window
            # it would multiply the frame's time, and the chances of an accidental match, by 12
            res = self.local.locate(img, c, w, mpp, **(dict(kw, heading_search=False) if (de or dn) and "heading_search" in kw else kw))
            res = self._window_gate(dict(res, _window=(c, w), _window_off=bool(de or dn)))
            tried += 1
            if res.get("accepted"):
                best = res
                break
            if best is None or int(res.get("inliers") or 0) > int(best.get("inliers") or 0):
                best = res
        best = dict(best, radius_m=float(R), windows_tried=tried, windows_cover=len(cover))
        if not best.get("accepted"):
            best["reason"] = f"{best.get('reason')} ({tried} of {len(cover)} windows of {w:.0f} m tried)"
        return best

    def _predicted(self, meta):
        """(lat, lon, sigma_m) of the last measured fix carried to now along the track
        (turned with the IMU heading), or None."""
        t_last = self.track.last_time()
        if t_last is None:
            return None
        h, h_sig = self._carry_heading(meta)
        t = self._frame_time(meta)
        ap = self._ap_predicted(t) if getattr(self, "apv", None) is not None else None
        self._pred_how = "autopilot velocity" if ap is not None else "track"
        if ap is not None:
            return ap[:3]
        if h_sig > 0.0:
            p = self._gyro_carry(t, t_last, h_sig)
            if p is not None:
                return p
        c = self._carry
        if c is not None and c[2] >= t_last:
            lat, lon, tc, hc, ve, vn, sig = c
            dt = max(0.0, t - tc)
            v = self.track.velocity(t_last + 1e-3)
            sig_v = v[2] if v is not None else 3.0
            since_v = tc - (self._vel_epoch if self._vel_epoch is not None else t_last)
            ay = getattr(self, "att_yaw", None)
            tr = ay.turn(tc, t) if ay is not None else None
            if tr is not None:
                # along the path the IMU attitude's yaw draws, sample by sample (the frames' headings give the
                # turn's total only, taken at a constant rate: a restart's carry 66 m off 9 s after a corner).
                # Measured turns: no half-turn term, but for the turn inside a gap (across a restart, from the
                # yaw persisted with the snapshot) and the yaw's drift
                speed = math.hypot(ve, vn)
                plat, plon, _, _ = carry_with_turns(lat, lon, tc, ve, vn, t,
                                                    lambda s_: (ay.turn(tc, s_) or (None,))[0])
                bias = self.gyro.bias if getattr(self, "gyro", None) is not None else 0.1
                return (plat, plon, sig + self.track.sigma_growth(sig_v, speed, dt, max(0.0, since_v))
                        + 0.5 * math.radians(tr[2]) * speed * tr[1] + 0.5 * math.radians(bias * dt) * speed * dt)
            turn = (h - hc + 180.0) % 360.0 - 180.0 if h is not None and hc is not None else DaySubscriber._imu_turn(self, tc, t)
            steps = max(1, int(abs(turn) / 5.0))
            de = dn = 0.0
            for i in range(steps):
                a = math.radians(turn * (i + 0.5) / steps)
                de += (ve * math.cos(a) + vn * math.sin(a)) * dt / steps
                dn += (-ve * math.sin(a) + vn * math.cos(a)) * dt / steps
            speed = math.hypot(ve, vn)
            p = _move((lat, lon), de, dn)
            # the unseen acceleration grows with the time since the last MEASURED fix (not
            # of each 1 s step: that sum is linear and was 5x too small after 100 s)
            return (p[0], p[1], sig + self.track.sigma_growth(sig_v, speed, dt, max(0.0, since_v), turn)
                    + 0.5 * math.radians(h_sig) * speed * dt)
        turn, hv = 0.0, self._velocity_heading(h_sig)
        if h is not None and hv is not None:
            turn = (h - hv + 180.0) % 360.0 - 180.0
        p = self.track.propagate(t, turn)
        if p is not None and h_sig > 0.0:
            # a gyro heading's error (its sigma at t) swings the carry sideways: half its reach
            v = self.track.velocity(t_last + 1e-3)
            p = (p[0], p[1], p[2] + 0.5 * math.radians(h_sig) * math.hypot(v[0], v[1]) * max(0.0, t - t_last))
        return p

    GYRO_STEP_S = 0.5

    def _gyro_carry(self, t, t_last, h_sig):
        """(lat, lon, sigma_m) carried to t along the path the gyro heading draws (each 0.5 s the
        velocity turned by the heading change since the instant it was measured at), or None when
        the gyro heading is not known all along. The turn is measured, not assumed at a constant
        rate: no half-turn term in the stated accuracy, but the gyro heading's own error."""
        c = self._carry
        if c is not None and c[2] >= t_last:
            lat, lon, t0, h0, ve, vn, sig = c
            v = self.track.velocity(t_last + 1e-3)
            sig_v = v[2] if v is not None else 3.0
            since_v = t0 - (self._vel_epoch if self._vel_epoch is not None else t_last)
        else:
            v, tm, last = self.track.velocity(t), self.track.fit_time(), self.track.last_fix()
            g = self.gyro.at(tm) if v is not None and tm is not None else None
            if g is None or last is None:
                return None
            (ve, vn, sig_v), h0, (t0, lat, lon, sig), since_v = v, g[0], last, 0.0
        if h0 is None:
            return None
        n = max(1, int(math.ceil(max(0.0, t - t0) / self.GYRO_STEP_S)))
        de = dn = 0.0
        for i in range(n):
            g = self.gyro.at(t0 + (t - t0) * (i + 0.5) / n)
            if g is None:
                return None
            a = math.radians(g[0] - h0)
            de += (ve * math.cos(a) + vn * math.sin(a)) * (t - t0) / n
            dn += (-ve * math.sin(a) + vn * math.cos(a)) * (t - t0) / n
        dt, speed = max(0.0, t - t0), math.hypot(ve, vn)
        p = _move((lat, lon), de, dn)
        return (p[0], p[1], sig + self.track.sigma_growth(sig_v, speed, dt, max(0.0, since_v))
                + 0.5 * math.radians(h_sig) * speed * dt)

    def _imu_turn(self, t0, t1) -> float:
        """The vehicle's turn (deg) from t0 to t1 when the frames give no heading: the IMU attitude's yaw
        (across a restart too: seeded with the persisted yaw), else the gyro's integrated rate, else 0."""
        ay = getattr(self, "att_yaw", None)
        r = ay.turn(t0, t1) if ay is not None else None
        if r is not None:
            return r[0]
        gyro = getattr(self, "gyro", None)
        d = gyro.turn(t0, t1) if gyro is not None else None
        return d if d is not None else 0.0

    def _ap_bias(self):
        """(be, bn, sigma m/s, t_ref) to add to the autopilot's velocity so that it draws the track's
        measured points up to the last one (t_ref), or None (no autopilot velocity, too few points
        covered, or the points off its path: carry_aids.VelocityRef.fit_bias). Cached per track state;
        after a restart (no velocity samples under the restored points) the persisted bias."""
        apv = getattr(self, "apv", None)
        last = self.track.last_fix()
        if apv is None or last is None:
            return None
        key = (last[0], len(self.track._pts))
        cache = getattr(self, "_ap_fit_cache", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        pts = list(self.track._pts)
        b = DaySubscriber._applied_bias(self, apv.fit_bias(pts, last[0]))
        r = None if b is None else (b[0], b[1], b[2], last[0])
        rb = getattr(self, "_restored_bias", None)
        if r is None and rb is not None and abs(rb[3] - last[0]) < 1e-6:
            r = rb
        prev = getattr(self, "_ap_last_fit", None)
        if r is None and prev is not None and last[0] - prev[3] <= self.max_dead_reckon_s and \
                apv.fit_bias(pts, last[0], max_chi2=math.inf) is None:
            # too few points since a gap to fit again (the first fixes after a GPS loss or a cloud bank:
            # Isaac Sim h1200, the carry fell back to the hover velocity after the first fix): the last fit
            # holds, its drift term counting from its own reference time. A refusal (chi-square) does not.
            r = prev
        if r is not None:
            self._ap_last_fit = r
        self._ap_fit_cache = (key, r)
        return r

    def _applied_bias(self, b):
        """The fitted bias as the carry applies it: as fitted when the autopilot does not fly on NAVERA's
        positions (autopilot_velocity_apply_bias), else none, its size added to the sigma. Fed NAVERA's
        positions, the autopilot's EKF takes a bias the carry adds in, its velocity moves by it, the carry
        adds it again: Isaac Sim outage60 (o3_o60b), its velocity 0.5 -> 7 m/s off in 45 s of cloud."""
        if b is None or getattr(self, "ap_apply_bias", False):
            return b
        return 0.0, 0.0, math.hypot(b[2], math.hypot(b[0], b[1]))

    def _ap_predicted(self, t):
        """(lat, lon, sigma_m, ve, vn) carried to t along the autopilot's velocity + its fitted bias, from
        the carried position (if carrying) else the last measured point; None when it cannot be."""
        b = self._ap_bias()
        if b is None:
            return None
        be, bn, sig_b, t_ref = b
        c, last = self._carry, self.track.last_fix()
        if c is not None and c[2] >= last[0]:
            lat, lon, t0, sig0, ve0, vn0 = c[0], c[1], c[2], c[6], c[4], c[5]
        else:
            (t0, lat, lon, sig0), ve0, vn0 = last, None, None
        r = carry_autopilot(lat, lon, t0, t, self.apv, (be, bn), ve0, vn0)
        if r is None:
            return None
        lat, lon, ve, vn, gap, dvg = r
        sigma = sig0 + autopilot_sigma_growth(sig_b, t - t0, t0 - t_ref, self.ap_drift, gap, dvg, self.track.accel)
        return lat, lon, sigma, ve, vn

    def _keep_carry_velocity(self, lat, lon, t, meta, sigma, t_vel) -> None:
        """A point was just added to the track. A point after a gap of more than 5 s leaves the track
        alone with it: no velocity across a gap (a chord is no velocity), so the next frame that
        gives no match could not be carried — no position at all, for as long as the track needs 3
        points over 4 s (simulator 2026-10-15: 19 s, then the autopilot's LAND). While the
        track has none, the carry goes on with the velocity it had; its accuracy keeps growing
        from the time that velocity was measured (t_vel), not from this point."""
        if self.track.velocity(t) is not None or self._carry is None:
            self._carry = None                      # the point is on a track that gives the velocity
            self._vel_epoch = None
            return
        if self._vel_epoch is None:
            self._vel_epoch = t_vel
        self._set_carry(lat, lon, t, meta, sigma)

    def _set_carry(self, lat, lon, t, meta, sigma):
        """Remember the carried position and its velocity turned to this frame's heading."""
        v = self.track.velocity(t)
        if v is None and self._carry is None:
            return
        if v is not None:
            self._vel_epoch = None
        h, h_sig = self._carry_heading(meta)
        b = self._ap_bias() if getattr(self, "apv", None) is not None else None
        va = self.apv.v(t) if b is not None else None
        if va is not None:                          # the autopilot's velocity now (carry_aids)
            self._carry = (lat, lon, t, h, va[0] + b[0], va[1] + b[1], sigma)
            return
        hc = self._carry[3] if self._carry is not None else self._velocity_heading(h_sig)
        ve, vn = (self._carry[4], self._carry[5]) if self._carry is not None else (v[0], v[1])
        if h is not None and hc is not None:
            a = math.radians((h - hc + 180.0) % 360.0 - 180.0)
            ve, vn = ve * math.cos(a) + vn * math.sin(a), -ve * math.sin(a) + vn * math.cos(a)
        elif self._carry is not None:
            a = math.radians(DaySubscriber._imu_turn(self, self._carry[2], t))
            ve, vn = ve * math.cos(a) + vn * math.sin(a), -ve * math.sin(a) + vn * math.cos(a)
        self._carry = (lat, lon, t, h, ve, vn, sigma)

    @staticmethod
    def _frame_time(meta) -> float:
        """The frame's exposure instant (its stamp), else now: a position carried to the
        processing instant but stamped at the exposure lands v x delay ahead (simulator
        plane, 2026-10-07: dead-reckoned frames 31-48 m ahead at 42 m/s)."""
        ns = meta.get("image_stamp_ns")
        return int(ns) / 1e9 if ns else time.time()

    def _watchdog(self):
        """Its own thread (dr_watchdog_period_s): while the GPS is not trusted, the carried position
        goes on being published. No camera frame for 2.5 s and no frame being matched: carried by
        the matching state itself (_dead_reckon, as before). A frame being matched (or none yet)
        and no output for dr_watchdog_s: the last output's snapshot carried to now (read-only —
        the matching thread's state is not touched; day_pkg.carry_state)."""
        if self._gps_prior.fresh() is not None:
            return
        t_frame, meta = self._last_frame
        if time.time() - t_frame >= 2.5 and time.time() - self._last_out_wall >= 1.0 and \
                self._busy_lock.acquire(blocking=False):
            try:
                self._drain_gps()
                m = dict(meta)
                m.pop("image_stamp_ns", None)                   # this is no frame: stamped now
                self._dead_reckon(self.get_clock().now().to_msg(), m.get("frame_id", -1), m, {}, 0.0,
                                  f"no camera frame for {time.time() - t_frame:.0f} s")
            finally:
                self._busy_lock.release()
            return
        if self.dr_watchdog_s > 0 and time.time() - self._last_out_wall >= self.dr_watchdog_s:
            self._watchdog_publish()

    def _watchdog_publish(self) -> bool:
        """Publish the snapshot (DrSnap) carried to now, turned by the gyro if it measured the turn;
        True if published."""
        snap, t = self._dr_snap, time.time()
        if snap is None:
            return False
        # the turn since the snapshot, integrated by the gyro (no heading reference needed): a copter at
        # a waypoint corner turns 90 deg in a few seconds (Isaac Sim fin_base: carried straight, 46-50 m
        # off at +-17 m); without it the snapshot's velocity goes straight on
        # (carry_snap_aided: along the autopilot's velocity when the snapshot has its bias, else turned by
        # the attitude's yaw, else by the gyro's turn, else straight)
        p, why = watchdog_carry(snap, t, self.track, self.max_dead_reckon_s, self.dr_max_sigma_m,
                                aids=DaySubscriber._carry_aids(self))
        if p is None:
            return False
        lat, lon, sigma = p
        now = self.get_clock().now().to_msg()
        reason = (f"no output for {t - self._last_out_wall:.1f} s (match in progress); carried "
                  f"{t - snap.t_meas:.0f} s{' along the autopilot velocity' if snap.be is not None else ''}, ±{sigma:.0f} m")
        self._last_out_wall = t
        self.pub_status.publish(String(data=json.dumps({
            "frame_id": None, "success": True, "source": "dead_reckon", "watchdog": True,
            "lat": lat, "lon": lon, "sigma_m": round(sigma, 1), "reason": reason})))
        self._publish_estimate(now, -1, "dead_reckon", lat, lon, {}, score=0.0,
                               details={"src": "dead_reckon", "watchdog": True, "reason": reason},
                               sigma_m=sigma)
        self.get_logger().info(f"[day] 🧭 DR watchdog lat={lat:+.5f} lon={lon:+.5f} ({reason})")
        return True

    def _carry_aids(self) -> dict:
        """carry_state.carry_snap_aided's aids (the autopilot's velocity, the attitude yaw, the gyro)."""
        gyro = getattr(self, "gyro", None)
        return {"apv": getattr(self, "apv", None), "yaw": getattr(self, "att_yaw", None), "gyro": gyro,
                "drift_mps2": getattr(self, "ap_drift", 0.1), "gyro_bias_dps": gyro.bias if gyro is not None else 0.1}

    def _snapshot_output(self, lat, lon, t, sigma, meta) -> None:
        """Matching thread, at each output: the snapshot the watchdog carries — this position and the
        velocity the next carry would use (the carried one, else the track's)."""
        t_last = self.track.last_time()
        if t_last is None:
            self._dr_snap = None
            return
        ay = getattr(self, "att_yaw", None)
        yaw = ay.yaw(t) if ay is not None else None
        b = self._ap_bias() if getattr(self, "apv", None) is not None else None
        va = self.apv.v(t) if b is not None else None
        if va is not None:
            # along the autopilot's velocity: sig_v is its bias's error, since_v counts from the fit
            h = self._carry_heading(meta)[0]
            self._dr_snap = DrSnap(lat, lon, t, sigma, va[0] + b[0], va[1] + b[1], b[2], max(0.0, t - b[3]),
                                   t_last, h, yaw, b[0], b[1])
            return
        c = self._carry
        if c is not None and c[2] >= t_last:
            v = self.track.velocity(t_last + 1e-3)
            ve, vn, sig_v = c[4], c[5], (v[2] if v is not None else 3.0)
            since_v = t - (self._vel_epoch if self._vel_epoch is not None else t_last)
        else:
            v = self.track.velocity(t)
            if v is None:
                self._dr_snap = None            # nothing to carry: an older snapshot must not outlive this output
                return
            ve, vn, sig_v = v
            since_v = t - t_last
            # the fit is the chord of its window: turned to this output's heading, as the carry is
            h, h_sig = self._carry_heading(meta)
            hv = self._velocity_heading(h_sig)
            if h is not None and hv is not None:
                a = math.radians((h - hv + 180.0) % 360.0 - 180.0)
                ve, vn = ve * math.cos(a) + vn * math.sin(a), -ve * math.sin(a) + vn * math.cos(a)
        h = self._carry_heading(meta)[0]
        if h is None and getattr(self, "gyro", None) is not None:
            g = self.gyro.at(t)
            h = g[0] if g is not None else None
        self._dr_snap = DrSnap(lat, lon, t, sigma, ve, vn, sig_v, max(0.0, since_v), t_last, h, yaw)

    def _remember_track(self) -> None:
        """Persist the track for a restart in flight (state "day_track", at most once a second)."""
        if not getattr(self, "track_persist", False) or time.time() - self._track_saved_at < 1.0:
            return
        self._track_saved_at = time.time()
        anchor = None
        if self._anchor_lat is not None and self._anchor_time is not None:
            anchor = (self._anchor_lat, self._anchor_lon, self._anchor_time,
                      self._anchor_sigma if self._anchor_sigma is not None else self.local_sigma_m)
        state_store.save(TRACK_STATE, track_state(
            self.track._pts, self._carry, self._vel_epoch, self._track_heading, self._frame_headings,
            anchor, self._last_measured_time, self._dr_snap))

    def _restore_track(self) -> bool:
        """Restarted in flight: the persisted track carried on (its original times: the uncertainty
        grows with the time elapsed, never a fresh fix); the anchor = that carry now. True if restored."""
        now = time.time()
        r = restore_track(state_store.load(TRACK_STATE, self.max_dead_reckon_s + 5.0), now, self.max_dead_reckon_s)
        if r is None:
            return False
        self.track.reset()
        for p in r["pts"]:
            self.track.add(*p)
        self._carry, self._vel_epoch, self._track_heading = r["carry"], r["vel_epoch"], r["track_heading"]
        for h in r["headings"]:
            self._frame_headings.append(h)
        self._dr_snap = r["snap"]
        self._last_measured_time = r["last_measured"]
        self._continue_snapshot(r["snap"])
        p = self._predicted({})
        if p is None or p[2] > self.dr_max_sigma_m:
            if r["anchor"] is None:
                return False
            lat, lon, ta, sig = r["anchor"]
            sig = sig + self.max_speed_mps * max(0.0, now - ta)       # no velocity: as far as it can go
            p = (lat, lon, sig)
        self._anchor_lat, self._anchor_lon, self._anchor_time = p[0], p[1], now
        self._anchor_sigma = self._dr_sigma = p[2]
        self.get_logger().warn(f"[day] restart: track restored, last measured fix {now - r['pts'][-1][0]:.1f} s ago; "
                               f"carried on at ±{p[2]:.0f} m (search around it)")
        return True

    def _continue_snapshot(self, snap) -> bool:
        """Restarted: carry on from a persisted snapshot newer than the restored carry (the last output
        of the killed process, or the early bridge's carry to the moment this node starts: day_entry),
        its velocity, the autopilot bias it moved with and its IMU yaw (the turn across the restart).
        True if taken."""
        t_last = self.track.last_time()
        if snap is None or t_last is None or snap.t < t_last or \
                (self._carry is not None and snap.t < self._carry[2]):
            return False
        self._carry = (snap.lat, snap.lon, snap.t, snap.heading, snap.ve, snap.vn, snap.sigma)
        self._vel_epoch = snap.t - snap.since_v
        self._dr_snap = snap
        self._restored_bias = (snap.be, snap.bn, snap.sig_v, t_last) if snap.be is not None else None
        self._ap_fit_cache = None
        ay = getattr(self, "att_yaw", None)
        if ay is not None and snap.yaw is not None:
            ay.seed(snap.t, snap.yaw)
        return True

    def take_early_bridge(self) -> bool:
        """day_entry, once the early bridge stopped and before spinning: its last carried snapshot (it
        went on carrying while this node loaded its matcher) continues here. True if taken."""
        if not getattr(self, "track_persist", False):
            return False
        r = restore_track(state_store.load(TRACK_STATE, self.max_dead_reckon_s + 5.0), time.time(),
                          self.max_dead_reckon_s)
        if r is None or r["snap"] is None or not self._continue_snapshot(r["snap"]):
            return False
        self.get_logger().warn(f"[day] restart: the early bridge's carry taken over "
                               f"({time.time() - r['snap'].t_meas:.0f} s after the last measured fix, ±{r['snap'].sigma:.0f} m)")
        return True

    def _dead_reckon(self, now, seq_id, meta, status, score, why) -> bool:
        """No measurement this frame: publish the last measured position carried along the
        measured track (PROPAGATED, with its growing stated uncertainty). False, with
        self._dr_why set, when it cannot be done honestly."""
        t_now = self._frame_time(meta)
        t_last = self.track.last_time()
        if t_last is None:
            self._dr_why = "no measured track to continue"
            return False
        if t_now - t_last > self.max_dead_reckon_s:
            self._dr_why = f"dead-reckoning limit {self.max_dead_reckon_s:.0f}s reached"
            return False
        vo, self._vo_step = self._vo_step, None
        if vo is not None and not self._odometry_continues(vo, self._anchor_time, t_now):
            vo = None            # frames in between gave no position: carry along the track instead
        if vo is not None and self._anchor_lat is not None and self._dr_sigma is not None:
            # visual odometry measured this frame's displacement: carry the last position by it
            # (and add it to the track: the velocity follows the turns)
            de, dn, dt, q = vo
            lat, lon = _move((self._anchor_lat, self._anchor_lon), de, dn)
            sigma = self._dr_sigma + self._odometry_rel_error(meta) * math.hypot(de, dn) + 1.0
            if sigma <= self.dr_max_sigma_m:
                t_vel = self.track.last_time()
                self.track.insert(t_now, lat, lon, sigma)
                self._keep_carry_velocity(lat, lon, t_now, meta, sigma, t_vel)
                self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, t_now
                self._dr_sigma = self._anchor_sigma = sigma
                self._emit_fix(now, seq_id, lat, lon, meta, status, "dead_reckon", score, None,
                               reason=f"{why}; visual odometry {math.hypot(de, dn):.0f} m in {dt:.1f} s, "
                                      f"±{sigma:.0f} m")
                return True
        p = self._predicted(meta)
        if p is None:
            self._dr_why = "velocity unknown (too few measured fixes), cannot dead-reckon"
            return False
        lat, lon, sigma = p
        if sigma > self.dr_max_sigma_m:
            self._dr_why = f"dead-reckoning uncertainty {sigma:.0f} m > {self.dr_max_sigma_m:.0f} m"
            return False
        self._set_carry(lat, lon, t_now, meta, sigma)
        self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, t_now
        self._dr_sigma = self._anchor_sigma = sigma
        how = " along the autopilot's velocity" if getattr(self, "_pred_how", None) == "autopilot velocity" else ""
        self._emit_fix(now, seq_id, lat, lon, meta, status, "dead_reckon", score, None,
                       reason=f"{why}; carried {t_now - t_last:.0f} s{how}, ±{sigma:.0f} m")
        return True

    # visual odometry that disagrees with the track's velocity is believed when two consecutive steps
    # agree with each other (VO_AGREE_MPS, or VO_AGREE_REL of the speed), each of quality >= VO_MIN_QUALITY
    # and an image shift of at least VO_MIN_SHIFT_PX (not a lock on what is fixed in the image)
    VO_AGREE_MPS, VO_AGREE_REL, VO_MIN_QUALITY, VO_MIN_SHIFT_PX, VO_MAX_GAP_S = 2.5, 0.25, 0.5, 4.0, 3.0

    def _vo_gate(self, step, v, t, shift_px):
        """The odometry step to use, or None. Agreeing with the velocity of the map fixes (v): used,
        as before. Disagreeing: phase correlation may have locked on something fixed in the image —
        or the track's velocity is stale: the vehicle turned round or stopped after its last map fix
        (Isaac Sim hills 2026-10-21: an RTL turn-round 10 s into a dead-reckoning, carried straight on,
        875 m off at +-488 m stated). It is then used only when this step and the previous one, both
        clear (quality, image shift), measure the same velocity: a fixed lock gives no shift, and two
        independent steps agreeing is the track's velocity being wrong, not the odometry."""
        prev, self._vo_last = getattr(self, "_vo_last", None), None
        if step is None:
            return None
        de, dn, dt, q = step
        ve, vn = de / dt, dn / dt
        clear = q >= self.VO_MIN_QUALITY and shift_px is not None and shift_px >= self.VO_MIN_SHIFT_PX
        self._vo_last = (t, ve, vn) if clear else None
        if v is None:
            return step
        if math.hypot(ve - v[0], vn - v[1]) <= max(3.0 * v[2], 0.3 * math.hypot(v[0], v[1]), 3.0):
            return step
        if clear and prev is not None and 0.0 < t - prev[0] <= self.VO_MAX_GAP_S and \
                math.hypot(ve - prev[1], vn - prev[2]) <= max(self.VO_AGREE_MPS,
                                                              self.VO_AGREE_REL * math.hypot(ve, vn)):
            return step
        return None

    ODOMETRY_MAX_UNSEEN_S = 0.5

    @classmethod
    def _odometry_continues(cls, vo, anchor_time, t_now) -> bool:
        """The odometry step (previous frame -> this frame) is added to the last published
        position only if that position IS the previous frame's. When a frame in between
        published nothing (the carry was refused, no match), the anchor is older than the
        previous frame by the motion nobody measured: adding the step to it leaves the position
        behind by v x that time while the stated accuracy has not grown (simulator 2026-10-15:
        error 1205 m, stated +-244 m)."""
        if anchor_time is None:
            return False
        de, dn, dt, _q = vo
        return (t_now - dt) - anchor_time <= cls.ODOMETRY_MAX_UNSEEN_S

    @staticmethod
    def _odometry_rel_error(meta) -> float:
        """Relative error of a visual-odometry displacement: the odometry scales the image by
        the frame's height above ground, so a height wrong by x % makes every displacement
        wrong by x %. 10 % at best, else the frame's own stated height uncertainty
        (simulator 2026-10-15: height held while the vehicle climbed, odometry 30 % short
        with 10 % stated)."""
        try:
            rel = float(meta.get("altitude_sigma_m")) / float(meta.get("altitude_m"))
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.1
        return max(0.1, rel) if math.isfinite(rel) else 0.1

    def _remember_anchor(self):
        """Persist the anchor (at most once a second) for a restart in flight."""
        if time.time() - self._anchor_saved_at >= 1.0 and self._anchor_lat is not None:
            self._anchor_saved_at = time.time()
            state_store.save("day_anchor", {"lat": self._anchor_lat, "lon": self._anchor_lon})

    def _select_map(self, img, meta) -> None:
        """Match this frame against the map zoom its ground resolution needs (day_pkg.map_levels);
        the matcher of a zoom is built the first time it is needed (sharing the networks)."""
        zooms = getattr(self, "map_zooms", None)
        if self.local is None or not zooms or len(zooms) < 2:
            return
        mpp, _ = self._frame_m_per_px(img, meta)
        lat = self._anchor_lat if self._anchor_lat is not None else None
        z = choose_zoom(zooms, mpp, lat, self.map_zoom_min_ratio)
        m = self._matchers.get(z)
        if m is None:
            base = self._matchers[zooms[0]]
            kw = dict(self._matcher_kw, zoom=z)
            if base.__class__.__name__ == "LearnedMatcher":
                m = base.__class__(IMAGES_DIR, models_from=base, **kw)
            else:
                m = LocalMatcher(IMAGES_DIR, retry_features=int(self.get_parameter("local_retry_features").value),
                                 **kw)
            self._matchers[z] = m
        if m is not self.local:
            self.get_logger().info(f"[day] map zoom {getattr(self.local, 'z', '?')} -> {z} "
                                   f"(frame {mpp:.2f} m/px)" if mpp else f"[day] map zoom -> {z}")
            self.local = m

    def _heading_for_match(self, meta):
        """The frame top's azimuth when the live camera measured it (straightened frames),
        else None (no rotation check)."""
        if meta.get("attitude_source") in (None, "none") or meta.get("heading_deg") is None:
            return None
        try:
            return float(meta["heading_deg"])
        except (TypeError, ValueError):
            return None

    def _match_heading_kw(self, meta) -> dict:
        """locate()'s heading and tolerance: the frame's attitude heading, else the gyro-carried one
        (reset by vision fixes and the GPS course) with a tolerance of at least 3 of its sigma, else none."""
        h = self._heading_for_match(meta)
        tol = self.local_heading_tol_deg
        if h is None and getattr(self, "gyro", None) is not None:
            g = self.gyro.at(self._frame_time(meta))
            if g is not None:
                h, tol = g[0], max(tol, 3.0 * g[1])
        return {"heading_deg": h, "heading_tol_deg": tol}

    def _carry_heading(self, meta):
        """(heading_deg or None, sigma_deg) the carry turns with: the frame's (its attitude; its
        error is in the track's heading term, sigma 0), else the gyro-carried vision heading."""
        h = self._heading_for_match(meta)
        if h is not None:
            return h, 0.0
        g = self.gyro.at(self._frame_time(meta)) if getattr(self, "gyro", None) is not None else None
        return (g[0], g[1]) if g is not None else (None, 0.0)

    def _velocity_heading(self, h_sig: float):
        """The heading the track's velocity was measured at, in the same reference as the carry's
        heading: a gyro heading (h_sig > 0) at the velocity fit's own instant (on a turn the fit is
        a chord: replay of the screen bench's heavy rain at 60 m/s, the velocity 37 m/s off after a
        20 s turn), else the frames' attitude heading at that instant, else the frame heading at the
        last vision fix. A track of GPS points or odometry steps has no vision fix: without the
        frames' headings its velocity was never turned — a real flight (MARS-LVIG AMvalley03, a
        U-turn 20 s after the GPS loss) was carried straight on, 100 m off in 20 s."""
        tm = self.track.fit_time()
        if h_sig > 0.0 and getattr(self, "gyro", None) is not None:
            g = self.gyro.at(tm) if tm is not None else None
            if g is not None:
                return g[0]
        hist = getattr(self, "_frame_headings", None)
        if h_sig == 0.0 and tm is not None and hist:
            h = DaySubscriber._heading_in(hist, tm)
            if h is not None:
                return h
        return self._track_heading

    def _note_frame_heading(self, meta) -> None:
        """Remember this frame's attitude heading at its exposure (for _velocity_heading), and the
        camera mount's yaw (for the GPS course offset)."""
        if meta.get("mount_yaw_deg") is not None:
            try:
                self._mount_yaw = float(meta["mount_yaw_deg"])
            except (TypeError, ValueError):
                pass
        h = self._heading_for_match(meta)
        hist = getattr(self, "_frame_headings", None)
        if h is None or hist is None:
            return
        t = self._frame_time(meta)
        if hist and t <= hist[-1][0]:
            return
        hist.append((t, h % 360.0))

    @staticmethod
    def _heading_in(hist, t: float, gap_s: float = 1.5):
        """The heading at t from (time, heading) samples in time order (interpolated across north
        between the samples around t, or the nearest within gap_s), or None."""
        if not hist:
            return None
        before = after = None
        for tf, h in reversed(hist):
            if tf <= t:
                before = (tf, h)
                break
            after = (tf, h)
        if before is not None and after is not None and after[0] - before[0] <= 2 * gap_s:
            f = (t - before[0]) / (after[0] - before[0]) if after[0] > before[0] else 0.0
            return (before[1] + f * ((after[1] - before[1] + 180.0) % 360.0 - 180.0)) % 360.0
        near = [x for x in (before, after) if x is not None and abs(x[0] - t) <= gap_s]
        return min(near, key=lambda x: abs(x[0] - t))[1] if near else None

    def _gyro_reset(self, t_fix, result) -> None:
        """A good fix's fitted rotation (the frame top's azimuth, measured by vision) restarts the
        gyro heading (GyroHeading.reset refuses one that disagrees with a valid carried heading)."""
        if getattr(self, "gyro", None) is None or result.get("rotation_deg") is None \
                or int(result.get("inliers") or 0) < self.gyro_min_inliers:
            return
        if getattr(self, "course", None) is not None and self._gps_prior.fresh() is not None:
            c = self.course.course(self._gps_hist, self.gyro, t_fix)     # the camera's offset from the course
            if c is not None:
                self.course.add_offset_sample(float(result["rotation_deg"]), c[0])
        self.gyro.reset(t_fix, float(result["rotation_deg"]))

    def _publish_vision_altitude(self, meta, result, status):
        """The height above ground this match measured: the frame was scaled for
        meta altitude_m, the fitted scale says how much more ground it saw. Published only
        from a strong match (altitude_min_inliers) agreeing within 5 % with the previous
        strong match of the last 10 s: one wrong match cannot set the altitude."""
        try:
            alt = float(meta.get("altitude_m")) * float(result.get("_height_factor", 1.0)) * \
                float(result.get("scale_residual"))
        except (TypeError, ValueError):
            return
        if not (math.isfinite(alt) and alt > 5.0) or int(result.get("inliers") or 0) < self.alt_min_inliers:
            return
        prev, self._alt_candidate = self._alt_candidate, (alt, time.time())
        if prev is None or time.time() - prev[1] > 10.0 or abs(alt - prev[0]) > 0.05 * prev[0]:
            return                                          # not confirmed yet
        r = Range()
        r.header.stamp = exposure_stamp(meta, self.get_clock().now().to_msg())
        r.header.frame_id = "day_camera_link"
        r.radiation_type = Range.INFRARED                     # (no "optical" type in the message)
        r.min_range, r.max_range, r.range = 5.0, 20000.0, float(alt)
        r.field_of_view = float(max(1.0, 0.03 * alt))         # 1-sigma of the measured height (m)
        self.pub_vision_alt.publish(r)
        status["altitude_measured_m"] = round(alt, 1)

    def _emit_fix(self, now, seq_id, lat, lon, meta, status, src, score, jump_m, reason=None):
        self._last_out_wall = time.time()
        self._snapshot_output(lat, lon, self._frame_time(meta),
                              self._dr_sigma if src == "dead_reckon" else self._last_fix_sigma, meta)
        self._remember_track()
        status["source"], status["lat"], status["lon"] = src, lat, lon
        status["jump_m"], status["reason"] = jump_m, reason
        status["sigma_cal"] = self.sigma_cal.state()
        status["latency"] = dict(self.latency_cal.state(), auto=self.auto_latency)
        status["success"] = True
        self.pub_status.publish(String(data=json.dumps(status)))
        fix = NavSatFix()
        fix.header.stamp    = now
        fix.header.frame_id = "day_camera_link"
        # Legacy/diagnostic topic; the authoritative output is /navera/position.
        # service 0 = not a GNSS position; dead-reckoning is not a fix.
        fix.status.status   = (NavSatStatus.STATUS_NO_FIX if src == "dead_reckon"
                               else NavSatStatus.STATUS_FIX)
        fix.status.service  = 0
        fix.latitude        = lat
        fix.longitude       = lon
        _alt = meta.get("altitude_m")
        fix.altitude        = float(_alt) if _alt is not None else math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        # Additive contract: same fix on the typed channel; mode derived from src.
        self._publish_estimate(now, seq_id, src, lat, lon, meta, score=score,
                               details={"src": src, "score": score, "jump_m": jump_m,
                                        "sigma_m": self._last_fix_sigma if src == "local_match" else None,
                                        "reason": reason,
                                        "fused_score": status.get("fused_score"),
                                        "match": status.get("match")})
        if src == "dead_reckon":
            self._reject_count += 1
        else:
            self._success_count += 1
        icon  = "🧭 DR" if src == "dead_reckon" else "✅"
        extra = f" jump={jump_m:.0f}m" if jump_m is not None else ""
        self.get_logger().info(
            f"[day] {icon} frame={seq_id} src={src} lat={lat:+.5f} lon={lon:+.5f} "
            f"score={score:.2f}{extra}" + (f" ({reason})" if reason else "")
        )

    # ────────────────────────────────────────────────────────────
    # Typed source contract (additive) → /navera/estimate/day
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _as_frame_index(seq_id):
        try:
            return int(seq_id)
        except (TypeError, ValueError):
            return -1

    def _publish_estimate(self, now, seq_id, src, lat, lon, meta, score, details, sigma_m=None):
        """Additive: emit the typed source contract on /navera/estimate/day.

        One PositionEstimate per NavSatFix, same lat/lon. `mode` is the honesty
        axis (REPLAYED/MEASURED/PROPAGATED via _DAY_MODE_BY_SRC). Covariance is
        UNKNOWN and confidence 0.0: the day pipeline has no measured sigma — the
        harness median error is sim-only and not a validated Gaussian (step-4
        note). Raw score lives in details_json, diagnostic only.
        """
        est = PositionEstimate()
        est.header.stamp    = now
        est.header.frame_id = "day_camera_link"
        # A NaN / out-of-range / (0,0) position is never published as valid.
        mode = _DAY_MODE_BY_SRC.get(src)
        valid = is_finite_latlon(lat, lon) and mode not in (None, PositionEstimate.MODE_REPLAYED)
        est.latitude  = float(lat) if valid else math.nan
        est.longitude = float(lon) if valid else math.nan
        # altitude NaN-if-unknown (contract): 0.0 is sea level, a REAL altitude —
        # same trap as null-island. Absent altitude_m must be NaN, never 0.0.
        _alt = meta.get("altitude_m")
        est.altitude  = float(_alt) if _alt is not None else math.nan
        if src in ("local_match", "dead_reckon") and valid:
            # local match: its stated sigma (details["sigma_m"], see _fix_sigma; local_sigma_m
            # without one); dead-reckoning: the anchor's plus the growth along the track
            sig = sigma_m or (details.get("sigma_m") if src == "local_match" else None) or \
                (self.local_sigma_m if src == "local_match" else self._dr_sigma)
            if getattr(self, "hypotheses", None) is not None:
                sig = self.hypotheses.cover_sigma(time.time(), float(sig))   # D17: 3 sigma reach an alternative
            var = float(sig) ** 2
            est.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 0.0]
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        else:
            est.position_covariance      = [0.0] * 9
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_DAY_VISION
        est.mode       = PositionEstimate.MODE_MEASURED if mode is None else mode
        est.valid      = valid
        est.confidence = 0.0
        est.reason     = ("" if valid else
                          "replayed ground truth (test data), never a measurement"
                          if mode == PositionEstimate.MODE_REPLAYED else
                          f"unknown source '{src}'" if mode is None else "non-finite position")
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "day_subscriber"
        est.model_id   = _DAY_MODEL_BY_SRC.get(src, "")
        est.frame_index = self._as_frame_index(seq_id)
        est.details_json = json.dumps(details)
        self.pub_est.publish(est)

    # ────────────────────────────────────────────────────────────
    # Publish result
    # ────────────────────────────────────────────────────────────
    def _fix_sigma(self, result, meta) -> float:
        """Stated 1-sigma (m) of a local match: the model (day_pkg.fix_sigma) scaled by this flight's
        calibration against GPS (or at least the no-calibration floor), local_sigma_m without one."""
        if not result.get("sigma_m"):
            return self.local_sigma_m
        s = self.sigma_cal.apply(self._model_sigma(result, meta))
        sd = self._unknown_delay_sigma_s()
        if sd > 0.0:
            v = self.track.velocity(time.time())
            if v is not None:
                s = math.hypot(s, sd * math.hypot(v[0], v[1]))
        return s

    def _fix_sigma_common(self, result, meta) -> float:
        """The part of a local fix's stated sigma that every fix of this flight shares (F41): the camera
        delay's (speed x its sigma, the frame-time sigma when it is known) and the camera mount's (height x
        tan(its sigma)), in quadrature. Averaging fixes does not reduce it."""
        v = self.track.velocity(time.time())
        speed = math.hypot(v[0], v[1]) if v is not None else 0.0
        sd = self._unknown_delay_sigma_s()
        d = speed * (sd if sd > 0.0 else float(getattr(self, "frame_time_sigma_s", 0.0)))
        return math.hypot(d, self._mount_term_m(result, meta))

    def _unknown_delay_sigma_s(self) -> float:
        """The camera delay's uncertainty while it is neither set (camera_latency_s) nor estimated
        (auto_latency): the frame time can be off by that much, the fix by speed x that along the
        track — a bias that turns with the track, which the in-flight calibration (map bias
        removed) cannot see. Isaac Sim closed loop 2026-10-21: 1.3 s unknown delay at 10 m/s,
        fixes stated +-7.8 m after the calibration, 24-40 m off after a turn (34 beyond 3 sigma).
        Once auto_latency applies an estimate, the sigma of what it applied (a staged correction
        before the estimate is stable keeps most of it, latency_cal)."""
        lc = getattr(self, "latency_cal", None)
        if lc is None:
            return 0.0
        sd = lc.delay_sigma() if getattr(self, "auto_latency", False) else \
            (lc.nominal_sigma if lc.nominal != 0.0 else None)
        sd = float(getattr(self, "unknown_delay_sigma_s", 0.0)) if sd is None else float(sd)
        # a change of the delay noticed since the start (live_camera's monitor) is not corrected: stated
        return math.hypot(sd, float(getattr(self, "_delay_change_s", 0.0)))

    def _model_sigma(self, result, meta) -> float:
        """The model sigma of a local match, before the in-flight calibration."""
        if not result.get("sigma_m"):
            return self.local_sigma_m
        v = self.track.velocity(time.time())
        alt = meta.get("altitude_m")
        s = day_fix_sigma_m(result.get("sigma_m"), self.local_sigma_floor_m,
                            math.hypot(v[0], v[1]) if v else None, self.frame_time_sigma_s,
                            float(alt) if alt is not None else None, self.attitude_sigma_deg)
        return self._mount_sigma(s, result, meta)

    def _check_local_fix(self, result, meta, lat, lon, status):
        """A local match before it is believed: the map bias removed, then the quality gates.
        (lat, lon, None) when it passes, (lat, lon, why) when rejected."""
        de, dn = self.map_bias.bias((lat, lon))
        if de or dn:
            lat, lon = _move((lat, lon), de, dn)
            status["map_bias_m"] = [round(de, 1), round(dn, 1)]
            status["lat"], status["lon"] = lat, lon
        inl = int(result.get("inliers") or 0)
        spread = float(result.get("spread", 1.0))
        if (inl < 30 and spread < self.min_spread) or (inl < 50 and spread <= 0.125):
            return lat, lon, (f"inliers cover {float(result.get('spread', 0)):.0%} of the frame ({inl}): "
                              "poorly conditioned — match rejected")
        pred = self._predicted(meta)
        sig = self._fix_sigma(result, meta)
        hyp = getattr(self, "hypotheses", None)
        if hyp is not None:
            # D17: the carried track and its alternatives (day_pkg.fix_hypotheses)
            if pred is None:
                hyp.clear()
                return lat, lon, None
            now = time.time()
            v = self.track.velocity(now)
            ok, why, switched = hyp.judge(now, lat, lon, sig, inl, pred, (v[0], v[1]) if v is not None else None)
            if not ok:
                return lat, lon, why
            if switched:
                status["reacquired"] = why
            return lat, lon, None
        # the gate against the carried position and the confirmation of a doubted fix: day_pkg.fix_consistency
        doubt = None if pred is None else \
            self.consistency.doubt(math.hypot(*_en((lat, lon), pred[:2])), pred[2], sig, inl)
        if doubt is None:
            self.consistency.clear()
            return lat, lon, None
        # doubted fixes in a row agreeing with each other (3 on a good track, 2 while lost: D17): the prediction is what is wrong
        now = time.time()
        v = self.track.velocity(now)
        if self.consistency.confirm(now, lat, lon, sig, (v[0], v[1]) if v is not None else None,
                                    pred[2] > self.consistency.lost_sigma_m):
            status["reacquired"] = doubt
            return lat, lon, None
        return lat, lon, doubt + " — match rejected (agreeing fixes in a row would confirm it)"

    # ────────────────────────────────────────────────────────────
    # Camera mount (F33) and the pose-attitude guard's choice (F35)
    # ────────────────────────────────────────────────────────────
    def _init_mount_cal(self):
        """The mount calibration and the guard parameters (mount_cal, pose_guard_*)."""
        p_ = lambda n: self.get_parameter(n).value               # noqa: E731
        self.mount_sigma_deg = float(p_("mount_sigma_deg"))
        self.mount_cal = (MountCalibration(prior_deg=self.mount_sigma_deg,
                                           min_samples=int(p_("mount_cal_min_samples")),
                                           min_heading_span_deg=float(p_("mount_cal_min_heading_span_deg")))
                          if bool(p_("mount_cal")) else None)
        self.mount_cal_max_dating_m = float(p_("mount_cal_max_dating_m"))
        self.pose_guard_choose = bool(p_("pose_guard_choose"))
        self.pose_guard_refuse_deg = float(p_("pose_guard_refuse_deg"))
        self.mount_cal_persist = bool(p_("mount_cal_persist"))
        self.mount_cal_save_period_s = float(p_("mount_cal_save_period_s"))
        self._mount_saved_at = time.time()
        if self.mount_cal is not None:
            self._load_mount_cal(str(p_("mount_cal_file")).strip(), float(p_("mount_cal_persisted_min_sigma_deg")))

    MOUNT_STATE = "day_mount"

    # ────────────────────────────────────────────────────────────
    # The lens, calibrated in flight against the map (day_pkg.lens_selfcal)
    # ────────────────────────────────────────────────────────────
    def _init_lens_cal(self):
        p_ = lambda n: self.get_parameter(n).value               # noqa: E731
        self.lens_mode = str(p_("lens_selfcal")).strip().lower()
        self.lens_cal = LensSelfCal(min_views=int(p_("lens_selfcal_min_views"))) if self.lens_mode != "off" else None
        self.lens_every = int(p_("lens_selfcal_every_views"))
        self.lens_max_updates = int(p_("lens_selfcal_max_updates"))
        self._lens_new, self._lens_updates, self._lens_fitting = 0, 0, False
        self.pub_lens = self.create_publisher(
            String, str(p_("lens_topic")),
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))

    def _lens_sample(self, res, meta, img, g, t):
        """A GPS-check match as a view for the lens calibration; a fit started when enough are new."""
        cal = getattr(self, "lens_cal", None)
        lens, key = lens_of_meta(meta), meta.get("lens_key")
        if cal is None or lens is None or not key or self._lens_updates >= self.lens_max_updates:
            return
        if self.lens_mode == "auto" and meta.get("lens_source") == "calibrated":
            return
        pairs = list_pairs(res)
        if pairs is None:
            return
        g0 = self._gps_hist.at(t - 1.0)
        speed = haversine_m(g0[0], g0[1], g[0], g[1]) if g0 is not None else 0.0
        try:
            why = cal.add_view(lens, meta.get("R_world_cam"), pairs[0], pairs[1], g[:2], float(meta["altitude_m"]),
                               speed, float(lens["size"][0]) / float(img.shape[1]), t)
        except (KeyError, TypeError, ValueError) as e:
            why = f"unusable ({e})"
        if why is not None:
            self.get_logger().debug(f"[day] lens view not kept: {why}")
            return
        self._lens_new += 1
        if cal.ready() and not self._lens_fitting and (cal.last is None or self._lens_new >= self.lens_every):
            self._lens_new, self._lens_fitting = 0, True
            threading.Thread(target=self._lens_fit, args=(key,), daemon=True).start()

    def _lens_fit(self, key: str):
        """Background: fit the lens; a clearly better one is kept for this camera and published."""
        try:
            out = self.lens_cal.fit()
        except Exception as e:                              # noqa: BLE001 — never takes the node down
            self.get_logger().error(f"[day] lens calibration failed: {e}")
            return
        finally:
            self._lens_fitting = False
        if out is None:
            return
        self.get_logger().info(
            f"[day] lens calibration ({out['views']} views, {out['points']} points): {out['model']}, field of view "
            f"{out['hfov_deg']} deg, k1 {out['k1']}, k2 {out['k2']}, {out['rms_before_px']} -> {out['rms_after_px']} px"
            f" — {'APPLIED' if out['accepted'] else 'not applied: ' + out['why']}")
        if not out["accepted"]:
            return
        rec = calibration_dict(out["lens"], out)
        doc = dict(lens=out["lens"], lens_key=key, views=out["views"], rms_px=out["rms_after_px"], date=rec["date"],
                   hfov_deg=out["hfov_deg"], summary={k: v for k, v in out.items() if k != "lens"})
        if not state_store.save(f"lens_auto_{key}", doc):
            self.get_logger().error("[day] the calibrated lens could not be kept for the next flight (state dir)")
        self._lens_updates += 1
        self.pub_lens.publish(String(data=json.dumps(doc)))

    def _load_mount_cal(self, path: str, min_sigma_deg: float) -> None:
        """The persisted mount calibration: mount_cal_file, else the last one learned in flight."""
        data, where = None, path
        if path:
            try:
                with open(path) as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                self.get_logger().error(f"[day] mount_cal_file {path} unreadable ({e}): no persisted mount calibration")
        else:
            data, where = state_store.load(self.MOUNT_STATE, float("inf")), "the last flight's (state day_mount)"
        self._mount_loaded_id = (data or {}).get("mount_id") if isinstance(data, dict) else None
        n = self.mount_cal.load(data, min_sigma_deg) if data else 0
        if n:
            self.get_logger().info(f"[day] camera mount calibration from {where}: "
                                   f"{json.dumps(self.mount_cal.state())}")
        else:
            self.get_logger().warn(f"[day] no camera mount calibration: every fix states height x tan("
                                   f"{self.mount_sigma_deg:g} deg) more until GPS checks measure it")

    def _save_mount_cal(self, before_t=None) -> None:
        """Persist the mount calibration learned in flight (samples taken before before_t only)."""
        if self.mount_cal is None or not getattr(self, "mount_cal_persist", False):
            return
        ex = self.mount_cal.export(before_t, self._delay_known_sigma_s())
        if not ex:
            return
        old = state_store.load(self.MOUNT_STATE, float("inf")) or {}
        mid = getattr(self, "_mount_id", None)
        same = old.get("mount_id") == mid or old.get("mount_id") is None   # an older mount's kinds are not carried
        data = {k: v for k, v in old.items() if k in ("frame centre", "camera pose") and same}
        data.update(ex)
        if mid:
            data["mount_id"] = mid
        data["source"] = "in-flight GPS checks " + time.strftime("%Y-%m-%d %H:%M")
        if state_store.save(self.MOUNT_STATE, data):
            self.get_logger().info(f"[day] camera mount calibration saved: {json.dumps(ex)}")

    def _check_mount_id(self, meta) -> None:
        """The frames' camera mount settings (live_camera mount_id: mount angles, lens file, crop): a mount
        calibration learned or stored with other settings is dropped, and the stored one with it (F33
        open item 4: a re-fitted or re-calibrated camera has another boresight error)."""
        from day_pkg.mount_cal import stale_reason
        mid = meta.get("mount_id")
        mc = getattr(self, "mount_cal", None)
        prev = getattr(self, "_mount_id", None)
        if not mid or mc is None or mid == prev:
            return
        self._mount_id = mid
        why = stale_reason(prev or getattr(self, "_mount_loaded_id", None), mid)
        if why is None:
            return
        mc.reset()
        self._mount_loaded_id = None
        if getattr(self, "mount_cal_persist", False) and \
                (state_store.load(self.MOUNT_STATE, float("inf")) or {}).get("mount_id") not in (None, mid):
            state_store.save(self.MOUNT_STATE, {"mount_id": mid, "source": "dropped: " + why})
        self.get_logger().error(f"[day] camera mount calibration dropped ({why}): every fix states height x "
                                f"tan({self.mount_sigma_deg:g} deg) more until GPS checks measure it again")

    def _init_camera_delay_pub(self) -> None:
        """camera_delay_topic: the camera-delay estimate for live_camera, which takes the attitude it
        straightens a frame with at the same instant the frame is dated (latency_cal.delay_message):
        a body-fixed camera on a banked plane straightened with the attitude 1.3 s stale put the frame
        centre 50-272 m off (Isaac Sim F35)."""
        topic = str(self.declare_parameter("camera_delay_topic", "/day/camera_delay").value)
        self.pub_cam_delay = self.create_publisher(String, topic, QoSProfile(
            depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST))
        self._cam_delay_sent = None
        self._publish_camera_delay()

    def _publish_camera_delay(self) -> None:
        """Publish the delay estimate when its correction changed (latched)."""
        pub, lc = getattr(self, "pub_cam_delay", None), getattr(self, "latency_cal", None)
        if pub is None or lc is None:
            return
        d = latency_cal.delay_message(lc, bool(getattr(self, "auto_latency", False)))
        key = (d["correction_s"], d["auto"])
        if key != self._cam_delay_sent:
            self._cam_delay_sent = key
            pub.publish(String(data=json.dumps(d)))

    def _delay_known_sigma_s(self) -> float:
        """The frame time's uncertainty for the mount fit's residual-delay term: the frame-time sigma
        when the camera delay is set or estimated, else unknown_delay_sigma_s."""
        sd = self._unknown_delay_sigma_s()
        return sd if sd > 0.0 else float(getattr(self, "frame_time_sigma_s", 0.05))

    @staticmethod
    def _fix_kind(result) -> str:
        return "camera pose" if result.get("position_from") == "camera pose" else "frame centre"

    @staticmethod
    def _fix_heading(result, meta):
        """The azimuth of the frame top: the matcher's fitted rotation (vision), else the frame's."""
        for v in (result.get("rotation_deg"), meta.get("heading_deg")):
            try:
                if v is not None and math.isfinite(float(v)):
                    return float(v)
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _fix_height(meta):
        try:
            h = float(meta.get("altitude_m"))
        except (TypeError, ValueError):
            return None
        return h if math.isfinite(h) and h > 5.0 else None

    def _mount_corrected(self, kind, lat, lon, result, meta):
        """(lat, lon, (east, north) m) of a vision position of this kind with the learned mount error removed."""
        mc = getattr(self, "mount_cal", None)
        if mc is None:
            return lat, lon, (0.0, 0.0)
        de, dn = mc.correction(kind, self._fix_heading(result, meta), self._fix_height(meta),
                               self._delay_known_sigma_s())
        if de or dn:
            lat, lon = _move((lat, lon), de, dn)
        return lat, lon, (de, dn)

    def _pose_guard_refusal(self, result, meta):
        """Why a match whose consistent pose is pose_guard_refuse_deg or more from the attitude's tilt
        is refused (None: not refused)."""
        if not result.get("pose_guard") or self.pose_guard_refuse_deg <= 0:
            return None
        try:
            d = abs(float(result.get("pose_tilt_deg")) - self._expected_tilt(meta))
        except (TypeError, ValueError):
            return None
        if d < self.pose_guard_refuse_deg:
            return None
        return (f"pose tilt {float(result['pose_tilt_deg']):.0f} deg vs {self._expected_tilt(meta):.0f} deg by the "
                f"attitude (>= {self.pose_guard_refuse_deg:g}): the frame is not where the attitude says, or the "
                "match is wrong — match rejected")

    def _place_fix(self, result, meta, status, pred=None):
        """Where a local match puts the vehicle, before the gates: the pose guard's candidates (the frame
        centre and the point under the camera) resolved, then the learned camera mount error removed.
        Sets result predicted_lat/lon, position_from and _guard_sigma_m; returns (lat, lon, why refused)."""
        lat, lon = float(result["predicted_lat"]), float(result["predicted_lon"])
        why = self._pose_guard_refusal(result, meta)
        if why is not None:
            return lat, lon, why
        cands = [(self._fix_kind(result), lat, lon)]
        if result.get("pose_guard") and result.get("pose_lat") is not None and self.pose_guard_choose:
            cands.append(("camera pose", float(result["pose_lat"]), float(result["pose_lon"])))
        placed = [(k,) + self._mount_corrected(k, la, lo, result, meta) for k, la, lo in cands]
        k, lat, lon, corr = placed[0]
        if len(placed) == 2:
            sep = math.hypot(*_en(placed[0][1:3], placed[1][1:3]))
            if pred is None:
                pred = self._predicted(meta)
            if pred is not None:
                d = [math.hypot(*_en(c[1:3], pred[:2])) for c in placed]
                k, lat, lon, corr = placed[int(d[1] < d[0])]
                result["_guard_sigma_m"] = min(0.5 * sep, float(pred[2]))
            else:
                result["_guard_sigma_m"] = 0.5 * sep
            status["pose_guard_choice"] = {"took": k, "apart_m": round(sep, 1),
                                           "guard_sigma_m": round(result["_guard_sigma_m"], 1)}
            result["position_from"] = k
        if corr[0] or corr[1]:
            status["mount_corr_m"] = [round(corr[0], 1), round(corr[1], 1)]
        if getattr(self, "mount_cal", None) is not None:
            status["mount_cal"] = self.mount_cal.state(self._delay_known_sigma_s()).get(k)
        result["predicted_lat"], result["predicted_lon"] = lat, lon
        status["lat"], status["lon"], status["position_from"] = lat, lon, result.get("position_from")
        return lat, lon, None

    def _mount_check_fix(self, res, meta, g):
        """A GPS-check match: its candidates are mount samples against the GPS at the frame's instant g
        (lat, lon; None: no sample), then it is placed like a fix (the GPS is the carried position).
        Returns (lat, lon) placed, or None when refused."""
        mc = getattr(self, "mount_cal", None)
        ns = meta.get("image_stamp_ns")
        vel = None
        if mc is not None and g is not None and ns is not None:
            g0 = self._gps_hist.at(int(ns) / 1e9 - 1.0)
            vel = _en(g, g0) if g0 is not None else None
        if mc is not None and g is not None and ns is not None and self._mount_sample_refused(vel) is None:
            hd, h = self._fix_heading(res, meta), self._fix_height(meta)
            seen = set()
            for kind, la, lo in (("frame centre", res.get("centre_lat"), res.get("centre_lon")),
                                 ("camera pose", res.get("pose_lat"), res.get("pose_lon"))):
                if la is not None and lo is not None:
                    mc.add(kind, _en(g, (float(la), float(lo))), hd, h, t=time.time(), vel_en=vel)
                    seen.add(kind)
            if not seen:                         # a matcher without the candidates: its own position
                mc.add(self._fix_kind(res), _en(g, (float(res["predicted_lat"]), float(res["predicted_lon"]))),
                       hd, h, t=time.time(), vel_en=vel)
        if mc is not None and time.time() - getattr(self, "_mount_saved_at", 0.0) >= \
                getattr(self, "mount_cal_save_period_s", 30.0) and hasattr(self, "get_logger"):
            self._mount_saved_at = time.time()
            self._save_mount_cal(before_t=time.time() - self.calib_rollback_s)
        pred = (g[0], g[1], 5.0) if g is not None else None
        lat, lon, why = self._place_fix(res, meta, {}, pred=pred)
        return None if why else (lat, lon)

    def _mount_sample_refused(self, vel):
        """Why a GPS check now gives no mount sample (None: it does): the camera delay unknown, or the
        frame's dating error (ground speed x the delay's sigma) above mount_cal_max_dating_m (F41)."""
        lc = getattr(self, "latency_cal", None)
        if lc is None:
            return None
        sd = lc.delay_sigma() if getattr(self, "auto_latency", False) else \
            (lc.nominal_sigma if lc.nominal != 0.0 else None)
        if sd is None:
            return "camera delay unknown"
        if vel is None:
            return "ground speed unknown"
        err = math.hypot(vel[0], vel[1]) * math.hypot(float(sd), float(getattr(self, "_delay_change_s", 0.0)))
        lim = float(getattr(self, "mount_cal_max_dating_m", 2.0))
        return None if err <= lim else f"frame dating error {err:.1f} m > {lim:g} m"

    def _mount_sigma(self, s: float, result, meta) -> float:
        """The model sigma s with the camera mount's uncertainty (height x tan(its sigma: the prior until
        learned)) and the guard's (_guard_sigma_m) added in quadrature."""
        s = math.hypot(s, self._mount_term_m(result, meta))
        return math.hypot(s, float(result.get("_guard_sigma_m") or 0.0))

    def _mount_term_m(self, result, meta) -> float:
        """height x tan(the camera mount's sigma) of a fix of this kind (0 without a height)."""
        mc = getattr(self, "mount_cal", None)
        h = self._fix_height(meta)
        if h is None:
            return 0.0
        sd = (mc.sigma_deg(self._fix_kind(result), self._delay_known_sigma_s()) if mc is not None
              else float(getattr(self, "mount_sigma_deg", 0.0)))
        return h * math.tan(math.radians(sd))

    def _jump_margin_m(self, result, meta) -> float:
        """The motion gate's allowance (beyond max_speed x elapsed) for a local match: the two
        positions' uncertainty (gate_k sigma), at most gate_margin_m — or gate_k x the anchor's own
        stated sigma when that is wider (a dead-reckoned anchor: its uncertainty IS how far the
        vehicle may be from it). Capped at gate_margin_m alone, the right fixes after a 50 s
        dead-reckoning (anchor +-430 m, 800-900 m off) were refused as 'implausible jumps' for
        good (Isaac Sim hills, 2026-10-21); the k-sigma gate of _check_local_fix still applies."""
        sig_a = float(self._anchor_sigma)
        cap = max(self.gate_margin_m, self.gate_k * sig_a)
        return kinematic_margin_m(self.gate_k, sig_a, self._fix_sigma(result, meta), cap)

    def _publish_result(self, seq_id, meta, result):
        now      = self.get_clock().now().to_msg()
        score    = float(result.get("score") or 0.0)
        accepted = bool(result.get("accepted", False))
        err      = result.get("error")
        raw_lat  = result.get("predicted_lat")
        raw_lon  = result.get("predicted_lon")

        status = {
            "frame_id":    seq_id,
            "success":     accepted,
            "lat":         raw_lat, "lon": raw_lon,
            "raw_lat":     raw_lat, "raw_lon": raw_lon,
            "score":       result.get("score"),
            "fused_score": result.get("fused_score"),
            "match":       result.get("match"),
            "total_ms":    result.get("total_ms"),
            "source":      "predicted",
            "error":       err,
            # The search, for display: circle (centre = last retained position),
            # how many tiles it held, and the best candidates.
            "search_center":   result.get("search_center"),
            "search_radius_m": result.get("radius_m"),
            "n_candidates":    result.get("n_candidates"),
            "threshold":       self.conf_threshold,
            "top5": [{"lat": c["lat"], "lon": c["lon"], "score": c["dino"], "image": c["image"]}
                     for c in (result.get("top5") or [])],
            "matcher": result.get("matcher", "retrieval"),
            "inliers": result.get("inliers"),
            "scale_residual": result.get("scale_residual"),
            "rotation_deg": result.get("rotation_deg"),
            "matcher_note": result.get("matcher_note"),
            # point under the camera ("camera pose") or "frame centre"; pose_guard: why the pose was not used
            "position_from": result.get("position_from"),
            "pose_tilt_deg": result.get("pose_tilt_deg"),
            "pose_guard": result.get("pose_guard"),
        }
        if accepted and result.get("pose_guard"):
            self.get_logger().info(f"[day] frame={seq_id}: {result['pose_guard']}")

        # ───── filtre OFF → comportement BRUT historique (inchangé, pour comparaison) ─────
        if not self.antijump_enabled:
            if err:
                status["success"] = False
                self.pub_status.publish(String(data=json.dumps(status)))
                self.get_logger().warn(f"[day] ✗  frame={seq_id} localizer error: {err}")
                return
            if not accepted:
                self._reject_count += 1
                status["rejected"] = True
                status["reason"]   = f"score {score:.2f} < threshold {self.conf_threshold:.2f}"
                self.pub_status.publish(String(data=json.dumps(status)))
                self.get_logger().warn(
                    f"[day] ⚠  frame={seq_id} REJECTED (score={score:.2f} < {self.conf_threshold:.2f})")
                return
            self._emit_fix(now, seq_id, float(raw_lat), float(raw_lon), meta, status,
                           "predicted", score, jump_m=None)
            return

        # ───── filtre ON ─────
        t_now = time.time()
        spatial_empty = bool(result.get("spatial_empty"))
        measured = (not err) and accepted and not spatial_empty and is_finite_latlon(raw_lat, raw_lon)
        gated = None
        if measured and result.get("matcher") == "local":
            raw_lat, raw_lon, gated = self._place_fix(result, meta, status)
            measured = gated is None
        if measured and result.get("matcher") == "local":
            raw_lat, raw_lon, gated = self._check_local_fix(result, meta, float(raw_lat), float(raw_lon), status)
            measured = gated is None
        if measured and self._anchor_lat is not None and self._anchor_time is not None:
            jump = haversine_m(self._anchor_lat, self._anchor_lon, float(raw_lat), float(raw_lon))
            margin = self.gate_margin_m
            if result.get("matcher") == "local" and self._anchor_sigma is not None:
                margin = self._jump_margin_m(result, meta)
            reach = self.max_speed_mps * max(0.0, t_now - self._anchor_time) + margin
            if jump > reach:
                measured = False
                gated = (f"implausible jump {jump:.0f} m in {t_now - self._anchor_time:.1f} s "
                         f"(max {reach:.0f} m) — match rejected")

        if measured:
            # Accepted match: in spatial mode it lies within R of the anchor by
            # construction; in global mode (no anchor) it passed conf_threshold.
            out_lat, out_lon = float(raw_lat), float(raw_lon)
            meas_sigma = self._fix_sigma(result, meta) if result.get("matcher") == "local" else self.local_sigma_m
            blended = self._blend_fix(out_lat, out_lon, result, meta, status) \
                if result.get("matcher") == "local" else None
            if blended is not None:
                out_lat, out_lon = blended[0], blended[1]
            jump_m = (haversine_m(self._anchor_lat, self._anchor_lon, out_lat, out_lon)
                      if self._anchor_lat is not None else None)
            src = ("local_match" if result.get("matcher") == "local" else
                   "visual_match" if result.get("spatial") else "predicted")
            reason = (f"in-circle R={float(result.get('radius_m') or 0.0):.0f}m "
                      f"n={result.get('n_candidates')}") if result.get("spatial") else None
            if self.local is not None and src == "local_match":
                self._prefetch_ahead(out_lat, out_lon, t_now, img_shape=result.get("_frame_shape"),
                                     mpp=result.get("_frame_mpp"))
            self._anchor_lat, self._anchor_lon, self._anchor_time = out_lat, out_lon, t_now
            self._last_measured_time = t_now
            fix_sigma = meas_sigma
            if blended is not None:
                fix_sigma = blended[2]
            self._dr_sigma = self._anchor_sigma = fix_sigma
            self._last_fix_sigma = fix_sigma
            self._rejects_in_row = 0
            self._remember_anchor()
            if src == "local_match":
                ns = meta.get("image_stamp_ns")         # the photo's instant, not the processing's
                t_vel, t_fix = self.track.last_time(), (int(ns) / 1e9 if ns else t_now)
                # the track (the carry's velocity and start) holds the MEASURED fix with its own sigma,
                # never the blended output: fed its own output the carry was a filter of itself — its
                # velocity fitted to smoothed points, its sigma shrinking, the fixes weighted down and
                # the output lagging (Isaac Sim 2026-10-22: 100 m behind a copter, F41)
                self.track.insert(t_fix, float(raw_lat), float(raw_lon), meas_sigma)
                if getattr(self, "hypotheses", None) is not None:
                    self.hypotheses.accepted()     # the alternatives are offsets from the track: moved back
                self._gyro_reset(t_fix, result)
                self._track_heading = self._carry_heading(meta)[0]
                self._keep_carry_velocity(float(raw_lat), float(raw_lon), t_fix, meta, meas_sigma, t_vel)
            else:
                self._carry, self._vel_epoch = None, None
            if src == "local_match":
                self._publish_vision_altitude(meta, result, status)
            self._emit_fix(now, seq_id, out_lat, out_lon, meta, status, src, score, jump_m, reason)
            return

        # ── No usable match this frame ──
        # A motion-gate rejection keeps the (trusted) anchor: it does not count
        # towards dropping it.
        if not gated:
            self._rejects_in_row += 1
        if gated:
            why = gated
        elif err:
            why = str(err)
        elif spatial_empty:
            why = f"no tile within R={float(result.get('radius_m') or 0.0):.0f}m"
        else:
            why = (result.get("reason") if result.get("matcher") == "local" and result.get("reason")
                   else f"score {score:.2f} < {self.conf_threshold:.2f}")

        if not self._dead_reckon(now, seq_id, meta, status, score, why):
            self._publish_no_fix(now, seq_id, meta, status, score, why + "; " + self._dr_why)

        if (self._anchor_lat is not None and self._rejects_in_row >= self.max_consecutive_rejects
                and self.local is None):           # local matching widens its search instead
            self.get_logger().warn(
                f"[day] {self._rejects_in_row} frames without a match — dropping the anchor, "
                "next frame searches the whole map")
            self._anchor_lat = self._anchor_lon = self._anchor_time = None
            self._rejects_in_row = 0

    def _publish_no_fix(self, now, seq_id, meta, status, score, reason):
        """Declare a frame that produced no position (valid=False, NaN) — never a guess."""
        self._reject_count += 1
        self._last_out_wall = time.time()
        status.update({"success": False, "rejected": True, "reason": reason,
                       "lat": None, "lon": None, "source": "none"})
        self.pub_status.publish(String(data=json.dumps(status)))
        est = PositionEstimate()
        est.header.stamp    = now
        est.header.frame_id = "day_camera_link"
        est.latitude = est.longitude = est.altitude = math.nan
        est.position_covariance      = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_DAY_VISION
        est.mode       = PositionEstimate.MODE_MEASURED
        est.valid      = False
        est.confidence = 0.0
        est.reason     = reason
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "day_subscriber"
        est.model_id   = _DAY_MODEL_BY_SRC["predicted"]
        est.frame_index = self._as_frame_index(seq_id)
        est.details_json = json.dumps({"score": score, "reason": reason,
                                       "match": status.get("match")})
        self.pub_est.publish(est)
        self.get_logger().warn(f"[day] ✗ frame={seq_id} no position: {reason}")


def main(args=None, init: bool = True, before_spin=None):
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    init False: rclpy is already initialised (day_entry: the early bridge ran first);
    before_spin(): called once the node is constructed (or failed to be), before spinning.
    """
    if init:
        # The localizer libraries log through the standard logging module.
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] [%(name)s]: %(message)s")
        die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
        rclpy.init(args=args)
    node = None
    try:
        try:
            node = DaySubscriber()   # may abort if a signal lands during model load
        finally:
            if before_spin is not None:
                before_spin()
        node.take_early_bridge()
        # the gyro, the GPS (with the arbiter's decision) and the dead-reckoning watchdog in their own
        # callback groups, run while a frame is matched; every other callback stays in the node's
        # default (mutually exclusive) group, serial as before
        ex = MultiThreadedExecutor(num_threads=4)
        ex.add_node(node)
        ex.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
