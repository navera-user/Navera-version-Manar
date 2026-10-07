# Lesson 17 — the camera as a measuring instrument (ideal pinhole camera).
# Fill in the TODOs, save (Ctrl+S), then run:   python3 camera_math.py
#
# Conventions (the same as NAVERA's navera_common/camera_model.py):
#   world  : ENU, metres — x east, y north, z up. Origin ON THE GROUND under the drone,
#            so the camera centre is C = (0, 0, h). The ground is the plane z = 0.
#   camera : OpenCV — x to the image right, y to the image bottom, z along the optical axis.
#   R_wc   : 3x3 rotation that maps a CAMERA vector to a WORLD vector:  v_world = R_wc @ v_cam.
#            Its inverse is its transpose:                               v_cam = R_wc.T @ v_world.
# Angles are given in DEGREES; math.tan() / np.tan() want RADIANS: use math.radians(deg).
import math

import numpy as np

EQUATOR_M = 40075016.7      # NAVERA's day_pkg constant: Earth's circumference at the equator (m)
TILE_PX = 256               # a map tile is 256 x 256 pixels (lesson 07)


# ---------------------------------------------------------------- TODO 1 — intrinsics
def focal_px(hfov_deg, width_px):
    """Focal length (pixels) of a pinhole camera that sees hfov_deg across width_px pixels.
    In: angle in degrees, width in pixels. Out: a float (pixels)."""
    # TODO 1: lesson section 2, "Field of view" — draw the half-angle triangle
    return None


def intrinsic_matrix(hfov_deg, width_px, height_px):
    """The 3x3 intrinsic matrix K (numpy array, float) of an ideal camera: square pixels
    (fx = fy = f), no skew, principal point at the image centre (width/2, height/2)."""
    # TODO 1: lesson section 2 (the intrinsic matrix K) — reuse focal_px()
    return None


def fov_deg(f_px, size_px):
    """Field of view (degrees) seen across size_px pixels by a camera of focal length f_px.
    (Use it for the vertical FOV: fov_deg(f, height_px).)"""
    # TODO 1: the same relation as focal_px(), solved for the angle (out: degrees)
    return None


# ---------------------------------------------------------------- TODO 2 — projection
def project(K, R_wc, C, X):
    """Pixel (u, v) — a numpy array of 2 floats — where the world point X (3 values, metres)
    appears, for a camera with intrinsics K, orientation R_wc and centre C.
    Return None if the point is behind the camera."""
    # TODO 2: lesson sections 1-2 and worked example 1: world -> camera frame, then K.
    #         Read the R_wc convention at the top of this file.
    return None


# ---------------------------------------------------------------- TODO 3 — back-projection
def ground_point(K, R_wc, C, u, v):
    """Where the ray of pixel (u, v) hits the flat ground z = 0: numpy array [east, north] (m).
    Return None when the ray does not go down (it sees the sky or the horizon)."""
    # TODO 3: lesson section 3 (back-projection) and worked example 2:
    #         the ray direction in the world, the "goes down" test, then the ray-ground intersection
    return None


# ---------------------------------------------------------------- TODO 4 — footprint
def footprint_polygon(K, R_wc, C, width_px, height_px):
    """The ground footprint: a (4, 2) numpy array of the [east, north] ground points of the
    four image corners, in this order: (0, 0), (width, 0), (width, height), (0, height).
    Return None if any corner does not hit the ground."""
    # TODO 4: lesson section 4 — reuse ground_point()
    return None


def polygon_area(pts):
    """Area (m^2, positive) of a simple polygon given as an (N, 2) array of vertices in order
    (clockwise or anticlockwise)."""
    # TODO 4: the shoelace formula of lesson section 4
    return None


# ---------------------------------------------------------------- TODO 5 — resolution and map
def meters_per_pixel(height_m, hfov_deg, width_px):
    """Ground sampling distance (m/px) of a NADIR camera: footprint width / image width."""
    # TODO 5: lesson section 5
    return None


def map_m_per_px(lat_deg, zoom):
    """Metres per pixel of a Web-Mercator map tile at this latitude and zoom.
    Use the constants EQUATOR_M and TILE_PX above."""
    # TODO 5: lesson section 6 (and lesson 07)
    return None


def best_zoom(height_m, hfov_deg, width_px, lat_deg, zooms=range(13, 20)):
    """The zoom (an int from `zooms`) whose map m/px is closest to the photo's GSD, closest
    in RATIO: minimise abs(math.log(map_mpp / photo_mpp))."""
    # TODO 5: lesson section 6 — try every zoom, keep the best one
    return None


# ---------------------------------------------------------------- TODO 6 — measuring and errors
def height_from_object(size_m, size_px, f_px):
    """Height (m) of a nadir camera that sees a ground object of size_m metres as size_px
    pixels."""
    # TODO 6: lesson section 2 — the similar triangles of the pinhole model
    return None


def fitted_scale(h_believed_m, h_true_m):
    """The scale a map match measures when the photo was resized for h_believed but taken at
    h_true (1.0 = height right; > 1 when the drone is higher than believed)."""
    # TODO 6: lesson section 7
    return None


def tilt_position_error(height_m, tilt_deg, dtilt_deg):
    """Ground error (m) of the point seen along the optical axis when the tilt is wrong by
    dtilt_deg (all angles in degrees). Out: metres."""
    # TODO 6: lesson section 7 — where the optical axis hits the ground, with and without the error
    return None


# ---- you don't need to change anything below this line (but read it!) ----
R_BODY_NADIR_CAM = np.array([[0.0, -1.0, 0.0],      # camera axes in the body (FLU) frame:
                             [-1.0, 0.0, 0.0],      # image right = body right, image down = body back,
                             [0.0, 0.0, -1.0]])     # optical axis = body down (NAVERA's constant)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1.0, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def camera_rotation(heading_deg=0.0, pitch_deg=0.0, roll_deg=0.0):
    """R_wc of a camera fixed under the drone, looking down (lesson 16's angles):
    heading clockwise from north, pitch positive NOSE UP, roll positive RIGHT WING DOWN.
    Same as NAVERA: R_world_body = Rz(yaw_enu) Ry(-pitch) Rx(roll), then the nadir mount."""
    R_wb = rot_z(math.radians(90.0 - heading_deg)) @ rot_y(math.radians(-pitch_deg)) @ rot_x(math.radians(roll_deg))
    return R_wb @ R_BODY_NADIR_CAM


def _show(label, value, unit=""):
    if value is None:
        print(f"  {label:<48} TODO not done yet (or None)")
    elif isinstance(value, np.ndarray):
        print(f"  {label:<48} {np.array2string(value, precision=2, suppress_small=True)} {unit}")
    else:
        print(f"  {label:<48} {value:.3f} {unit}")


if __name__ == "__main__":
    print("Insta360 top lens, straightened view: 1920 x 540 px, HFOV 111 deg")
    f = focal_px(111, 1920)
    _show("focal length f", f, "px")
    _show("vertical FOV", fov_deg(f, 540) if f else None, "deg")
    K = intrinsic_matrix(111, 1920, 540)
    if K is None:
        print("  K                                                TODO not done yet")
    else:
        print("  K =\n    " + np.array2string(np.asarray(K, float), precision=1, suppress_small=True, prefix="    "))

    print("\nThe lab's camera: 960 x 540 px, HFOV 90 deg, at 150 m")
    K = intrinsic_matrix(90, 960, 540)
    C = np.array([0.0, 0.0, 150.0])
    R0 = camera_rotation(0, 0, 0)
    if K is not None:
        _show("pixel of the ground point (30 m E, 45 m N)", project(K, R0, C, [30.0, 45.0, 0.0]), "px")
        _show("ground point of pixel (0, 0)", ground_point(K, R0, C, 0, 0), "m (E, N)")
        R = camera_rotation(30, -12, 4)
        _show("tilted (hdg 30, pitch -12, roll 4): centre hits", ground_point(K, R, C, 480, 270), "m (E, N)")
        poly = footprint_polygon(K, R, C, 960, 540)
        _show("tilted footprint area", polygon_area(poly) if poly is not None else None, "m^2")
    else:
        print("  (needs TODO 1 first)")

    print("\nResolution and map (Reykjavik 64.15 N, Sousse 35.83 N)")
    _show("GSD of the Insta360 view at 150 m", meters_per_pixel(150, 111, 1920), "m/px")
    for name, lat in (("Reykjavik", 64.15), ("Sousse", 35.83)):
        _show(f"map m/px at zoom 17, {name}", map_m_per_px(lat, 17), "m/px")
    bz = best_zoom(300, 111, 1920, 64.15)
    print(f"  {'best zoom at 300 m over Reykjavik':<48} {bz if bz is not None else 'TODO not done yet'}")

    print("\nMeasuring and errors")
    _show("height when a 12 m pad is 48 px (f = 480)", height_from_object(12, 48, 480), "m")
    _show("fitted scale: believed 150 m, true 200 m", fitted_scale(150, 200))
    _show("error from 1 deg of tilt error (150 m, 10 deg)", tilt_position_error(150, 10, 1), "m")
