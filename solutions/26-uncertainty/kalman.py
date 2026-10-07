"""kalman.py — a linear Kalman filter for a constant-velocity vehicle (lesson 26).

State order (dims = 2):  x = [east, north, v_east, v_north]      (m, m, m/s, m/s)
State order (dims = 1):  x = [height, climb_rate]                 (m, m/s)

Run the demo:   python3 kalman.py
"""
import math

import numpy as np

from uncertainty import chi2_threshold, mahalanobis2


def cv_model(dt, q, dims=2):
    """F and Q of the constant-velocity model with white-noise acceleration (spectral density q, m^2/s^3).
    For ONE axis, state [p, v]:
        F1 = [[1, dt],            Q1 = q * [[dt^4/4, dt^3/2],
              [0, 1 ]]                      [dt^3/2, dt^2  ]]
    For `dims` axes with state [p_1..p_d, v_1..v_d]:  F = kron(F1, I_d),  Q = kron(Q1, I_d)
    (numpy.kron and numpy.eye). Returns (F, Q)."""
    F1 = np.array([[1.0, dt], [0.0, 1.0]])
    Q1 = q * np.array([[dt ** 4 / 4.0, dt ** 3 / 2.0], [dt ** 3 / 2.0, dt ** 2]])
    I = np.eye(dims)
    return np.kron(F1, I), np.kron(Q1, I)


def kf_predict(x, P, F, Q):
    """Prediction:  x' = F x,   P' = F P F^T + Q.   Returns (x', P')."""
    return F @ x, F @ P @ F.T + Q


def kf_update(x, P, z, H, R):
    """Update with a measurement z = H x + noise (covariance R):
        nu = z - H x                (innovation)
        S  = H P H^T + R            (innovation covariance)
        K  = P H^T S^-1             (Kalman gain)
        x' = x + K nu
        P' = (I - K H) P
    Returns (x', P', nu, S)."""
    nu = z - H @ x
    S = H @ P @ H.T + R
    K = P @ H.T @ np.linalg.inv(S)
    x2 = x + K @ nu
    P2 = (np.eye(len(x)) - K @ H) @ P
    return x2, P2, nu, S


def nees(err, P):
    """Normalised Estimation Error Squared: err^T P^-1 err (err = estimate - truth).
    For a consistent filter its average is the dimension of err."""
    return mahalanobis2(err, P)


def run_filter(times, zs, sigma_z, q, gate_p=None, v0_sigma=20.0):
    """Run the 2-D constant-velocity filter on a track.

    times   : list of times (s)
    zs      : list of measurements: np.array([east, north]) or None (no measurement at that time)
    sigma_z : measurement sigma per axis (m)          -> R = sigma_z^2 I
    q       : process noise (m^2/s^3)
    gate_p  : None = no gate; else refuse a measurement whose mahalanobis2(nu, S) > chi2_threshold(gate_p, 2)

    Start: x = [z0_e, z0_n, 0, 0], P = diag(sigma_z^2, sigma_z^2, v0_sigma^2, v0_sigma^2)
           (the first measurement is used as the start, it is not "updated" again).
    Every next step: predict with dt = times[k] - times[k-1]; then, if there is a measurement,
    compute nu and S, d2 = mahalanobis2(nu, S); update unless the gate refuses it.

    Returns a dict of lists, one entry per time:
      "x": state (np.array 4), "P": covariance (4x4), "d2": d2 or None, "accepted": True / False / None
    """
    H = np.hstack([np.eye(2), np.zeros((2, 2))])
    R = sigma_z ** 2 * np.eye(2)
    out = {"x": [], "P": [], "d2": [], "accepted": []}
    x = P = None
    for k, (t, z) in enumerate(zip(times, zs)):
        if x is None:
            if z is None:
                continue
            x = np.array([z[0], z[1], 0.0, 0.0])
            P = np.diag([sigma_z ** 2, sigma_z ** 2, v0_sigma ** 2, v0_sigma ** 2])
            out["x"].append(x.copy()); out["P"].append(P.copy()); out["d2"].append(None); out["accepted"].append(True)
            continue
        F, Q = cv_model(times[k] - times[k - 1], q)
        x, P = kf_predict(x, P, F, Q)
        d2, acc = None, None
        if z is not None:
            nu = np.asarray(z, dtype=float) - H @ x
            S = H @ P @ H.T + R
            d2 = mahalanobis2(nu, S)
            acc = gate_p is None or d2 <= chi2_threshold(gate_p, 2)
            if acc:
                x, P, _, _ = kf_update(x, P, np.asarray(z, dtype=float), H, R)
        out["x"].append(x.copy()); out["P"].append(P.copy()); out["d2"].append(d2); out["accepted"].append(acc)
    return out


# ---- you don't need to change anything below this line ----

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    F, Q = cv_model(1.0, 0.3, dims=1)
    print("1-D model, dt = 1 s, q = 0.3:\nF =\n", F, "\nQ =\n", Q)
    x, P = np.array([80.0, 0.0]), np.diag([9.0, 4.0])
    x, P = kf_predict(x, P, F, Q)
    print("after predict: x =", x, "\nP =\n", P)
    x, P, nu, S = kf_update(x, P, np.array([83.0]), np.array([[1.0, 0.0]]), np.array([[2.25]]))
    print("after a baro height of 83 m (sigma 1.5): x =", x, " innovation", nu, " S", S, "\nP =\n", P)
    print("NEES of an error (3, -1) for P = diag(4, 1):", nees(np.array([3.0, -1.0]), np.diag([4.0, 1.0])))
