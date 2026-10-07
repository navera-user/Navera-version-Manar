# Lesson 16 — rotations: matrices, Euler angles, quaternions, SLERP.
# Fill in the TODOs one by one, save (Ctrl+S), then run:   python3 quaternions.py
#
# Conventions of this file (read them twice):
#   * angles in RADIANS (use math.radians / math.degrees, or np.radians / np.degrees)
#   * frames: body FLU (x forward, y left, z up), world ENU (x east, y north, z up) — like ROS
#   * a rotation matrix R = R_world_body maps a BODY vector into the WORLD:  v_world = R @ v_body
#   * Euler angles: ZYX ("yaw, then pitch, then roll"):  R = Rz(yaw) @ Ry(pitch) @ Rx(roll)
#     (ROS signs: positive roll = right side down, positive pitch = nose DOWN, yaw from EAST)
#   * a quaternion is a numpy array (w, x, y, z)  — SCALAR FIRST.
#     ROS messages and NAVERA's code use (x, y, z, w): convert with xyzw_to_wxyz / wxyz_to_xyzw.
import math

import numpy as np


def rot_x(a):
    """Rotation by angle a (rad) about the x axis."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rot_y(a):
    """Rotation by angle a (rad) about the y axis."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rot_z(a):
    """Rotation by angle a (rad) about the z axis."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


# TODO 1: the rotation matrix of ZYX Euler angles (radians):  R = Rz(yaw) Ry(pitch) Rx(roll).
#   Return a 3x3 numpy array. (`@` is the matrix product in numpy.)
def euler_to_matrix(roll, pitch, yaw):
    return None   # TODO 1: replace this line with your code

# TODO 2: the inverse: (roll, pitch, yaw) in radians from a rotation matrix R (ZYX).
#   pitch = -asin(R[2,0])             (clamp R[2,0] into [-1, 1] first!)
#   roll  = atan2(R[2,1], R[2,2])
#   yaw   = atan2(R[1,0], R[0,0])
#   At gimbal lock (|R[2,0]| close to 1) roll and yaw are not separable: return roll = 0 and
#   put the whole rotation into yaw:  yaw = atan2(-R[0,1], R[1,1]).
def matrix_to_euler(R):
    return None   # TODO 2: replace this line with your code

# TODO 3: the Hamilton product p ⊗ q of two quaternions (w, x, y, z).
#   (pw, pv) ⊗ (qw, qv) = (pw·qw − pv·qv,  pw·qv + qw·pv + pv × qv)
#   np.dot and np.cross help. Return a numpy array of 4 numbers.
def quat_mul(p, q):
    return None   # TODO 3: replace this line with your code

# TODO 4: the unit quaternion of a rotation by `angle` (rad) about `axis` (3 numbers, any length):
#   q = (cos(angle/2), sin(angle/2) · axis / |axis|)
def quat_from_axis_angle(axis, angle):
    return None   # TODO 4: replace this line with your code

# TODO 5: rotate the 3-vector v by the unit quaternion q:  (0, v') = q ⊗ (0, v) ⊗ q*
#   Use your quat_mul and quat_conj (given below). Return a numpy array of 3 numbers.
def quat_rotate(q, v):
    return None   # TODO 5: replace this line with your code

# TODO 6: the rotation matrix of a unit quaternion (w, x, y, z) (formula in the course).
#   Normalise q first (divide by its norm) so a slightly-off quaternion still gives a rotation.
def quat_to_matrix(q):
    return None   # TODO 6: replace this line with your code

# TODO 7: SLERP — spherical linear interpolation between unit quaternions q0 and q1, t in [0, 1].
#   d = q0·q1 ; if d < 0: use -q1 and -d (shortest path: q and -q are the same rotation)
#   if d > 0.9995: normalised linear interpolation (the two are almost equal)
#   else: θ = acos(d),  q = (sin((1−t)θ)·q0 + sin(tθ)·q1) / sin θ
#   Return a unit quaternion (numpy array, w first). Lesson 19 uses this function.
def slerp(q0, q1, t):
    return None   # TODO 7: replace this line with your code

# ---- you don't need to change anything below this line (but read it!) ----
def quat_conj(q):
    """Conjugate (w, -x, -y, -z): the inverse rotation of a unit quaternion."""
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=float)


def xyzw_to_wxyz(q):
    """ROS / NAVERA order (x, y, z, w) -> this file's order (w, x, y, z)."""
    return np.array([q[3], q[0], q[1], q[2]], dtype=float)


def wxyz_to_xyzw(q):
    """This file's order (w, x, y, z) -> ROS / NAVERA order (x, y, z, w)."""
    return np.array([q[1], q[2], q[3], q[0]], dtype=float)


def quat_from_euler(roll, pitch, yaw):
    """ZYX Euler angles (rad) -> quaternion (w, x, y, z), built by COMPOSING three
    axis-angle rotations exactly like R = Rz Ry Rx."""
    qx = quat_from_axis_angle((1, 0, 0), roll)
    qy = quat_from_axis_angle((0, 1, 0), pitch)
    qz = quat_from_axis_angle((0, 0, 1), yaw)
    return quat_mul(quat_mul(qz, qy), qx)


def quat_angle_deg(q0, q1):
    """The angle (deg) of the rotation that takes q0 to q1 (0 = same attitude)."""
    d = abs(float(np.dot(q0, q1))) / (np.linalg.norm(q0) * np.linalg.norm(q1))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


def heading_deg(q):
    """Compass heading (deg clockwise from north) of the body x axis, q = (w, x, y, z), ENU."""
    R = quat_to_matrix(q)
    yaw = math.atan2(R[1, 0], R[0, 0])
    return (90.0 - math.degrees(yaw)) % 360.0


def _demo():
    np.set_printoptions(precision=4, suppress=True)
    print("1) Worked example of the course: roll 10, pitch 5, yaw 60 deg (ZYX)")
    R = euler_to_matrix(math.radians(10), math.radians(5), math.radians(60))
    if R is None:
        print("   TODO 1: euler_to_matrix() returns None")
        return
    print(R)
    print(f"   R^T R = I ? {np.allclose(R.T @ R, np.eye(3))}    det(R) = {np.linalg.det(R):.6f}")
    back = matrix_to_euler(R)
    if back is None:
        print("   TODO 2: matrix_to_euler() returns None")
        return
    print("   back to Euler (deg):", np.round(np.degrees(back), 4))

    print("\n2) Gimbal lock: pitch = 90 deg. Two different (roll, yaw) give the SAME matrix:")
    Ra = euler_to_matrix(math.radians(30), math.radians(90), math.radians(50))
    Rb = euler_to_matrix(math.radians(0), math.radians(90), math.radians(20))
    print(f"   roll 30, yaw 50  vs  roll 0, yaw 20  ->  same matrix? {np.allclose(Ra, Rb)}")
    print("   matrix_to_euler gives (deg):", np.round(np.degrees(matrix_to_euler(Ra)), 3))

    print("\n3) Quaternions")
    q = quat_from_axis_angle((0, 0, 1), math.radians(90))
    if q is None or quat_mul(q, q) is None:
        print("   TODO 3/4: quat_mul() or quat_from_axis_angle() returns None")
        return
    print("   90 deg about z:", q)
    v = quat_rotate(q, (1.0, 0.0, 0.0))
    print("   rotates (1, 0, 0) into", None if v is None else np.round(v, 6))
    i, j = np.array([0, 1.0, 0, 0]), np.array([0, 0, 1.0, 0])
    print("   i*j =", quat_mul(i, j), "  j*i =", quat_mul(j, i), " (not commutative!)")
    qe = quat_from_euler(math.radians(10), math.radians(5), math.radians(60))
    Rq = quat_to_matrix(qe)
    if Rq is not None:
        print(f"   quat_to_matrix(quat_from_euler(10, 5, 60)) == euler_to_matrix(...) ? {np.allclose(Rq, R)}")
    try:
        from navera_common.camera_model import quat_to_matrix as navera_q2m
        print(f"   NAVERA's quat_to_matrix (x, y, z, w order) agrees ? "
              f"{np.allclose(navera_q2m(wxyz_to_xyzw(qe)), R)}")
    except ImportError:
        print("   (NAVERA's camera_model not found: source ~/navera/install/setup.bash)")

    print("\n4) SLERP from heading 0 (north) to heading 90 (east), level")
    q0 = quat_from_euler(0, 0, math.radians(90))     # yaw 90 = nose north
    q1 = quat_from_euler(0, 0, 0)                    # yaw 0  = nose east
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        qt = slerp(q0, q1, t)
        if qt is None:
            print("   TODO 7: slerp() returns None")
            break
        print(f"   t = {t:4.2f}   heading {heading_deg(qt):6.2f} deg   angle from q0 {quat_angle_deg(q0, qt):6.2f} deg")


if __name__ == "__main__":
    _demo()
