"""Sim Lite stand-in for the autopilot's filter: a plain pass-through. Written for the course.

Sent to the browser instead of the course's Kalman filter while mission 28 is not passed: the autopilot takes
each position it receives as it is, and between two positions moves on with its IMU (dead reckoning). No gate:
every position is accepted (nis 0). Mission 28 replaces it."""


def cv_model(dt, q, dims=2):
    return float(dt), None


def kf_predict(x, P, F, Q):
    x = [float(v) for v in x]
    x[0] += x[2] * F
    x[1] += x[3] * F
    return x, P


def kf_update(x, P, z, H, R):
    return [float(z[0]), float(z[1]), float(x[2]), float(x[3])], [list(r) for r in P], 0.0
