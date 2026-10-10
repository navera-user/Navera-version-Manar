"""kalman.py — a linear Kalman filter for a constant-velocity vehicle (lesson 27).

State order (dims = 2):  x = [east, north, v_east, v_north]      (m, m, m/s, m/s)
State order (dims = 1):  x = [height, climb_rate]                 (m, m/s)

Run the demo:   python3 kalman.py
"""
import numpy as np

from uncertainty import chi2_threshold, mahalanobis2   # noqa: F401


def cv_model(dt, q, dims=2):
    """F and Q of the constant-velocity model with white-noise acceleration (spectral density q, m^2/s^3).
    For ONE axis, state [p, v]:
        F1 = [[1, dt],            Q1 = q * [[dt^4/4, dt^3/2],
              [0, 1 ]]                      [dt^3/2, dt^2  ]]
    For `dims` axes with state [p_1..p_d, v_1..v_d]:  F = kron(F1, I_d),  Q = kron(Q1, I_d)
    (numpy.kron and numpy.eye). Returns (F, Q)."""
    return None, None   # TODO 8


def kf_predict(x, P, F, Q):
    """Prediction:  x' = F x,   P' = F P F^T + Q.   Returns (x', P')."""
    return None, None   # TODO 9


def kf_update(x, P, z, H, R):
    """Update with a measurement z = H x + noise (covariance R):
        nu = z - H x                (innovation)
        S  = H P H^T + R            (innovation covariance)
        K  = P H^T S^-1             (Kalman gain)
        x' = x + K nu
        P' = (I - K H) P
    Returns (x', P', nu, S)."""
    return None, None, None, None   # TODO 10


def nees(err, P):
    """Normalised Estimation Error Squared: err^T P^-1 err (err = estimate - truth).
    For a consistent filter its average is the dimension of err."""
    return None   # TODO 11  (one line: you already wrote mahalanobis2)


def run_filter(times, zs, sigma_z, q, gate_p=None, v0_sigma=20.0):
    """Run the 2-D constant-velocity filter on a track.

    times   : list of times (s)
    zs      : list of measurements: np.array([east, north]) or None (no measurement at that time)
    sigma_z : measurement sigma per axis (m)          -> R = sigma_z^2 I
    q       : process noise (m^2/s^3)
    gate_p  : None = no gate; else refuse a measurement whose mahalanobis2(nu, S) > chi2_threshold(gate_p, 2)

    Start: x = [z0_e, z0_n, 0, 0], P = diag(sigma_z^2, sigma_z^2, v0_sigma^2, v0_sigma^2)
           (the first measurement is used as the start, it is not "updated" again).
           Entry 0 of the result: x = that start state, P = that start covariance,
           d2 = None (there is no prediction to compare with), accepted = True (it was used).
           You may assume zs[0] is not None.
    Every next step: predict with dt = times[k] - times[k-1]; then, if there is a measurement,
    compute nu and S, d2 = mahalanobis2(nu, S); update unless the gate refuses it.

    Returns a dict of lists, one entry per time:
      "x": state (np.array 4), "P": covariance (4x4), "d2": d2 or None, "accepted": True / False / None
    """
    return None   # TODO 12


# ---- you don't need to change anything below this line ----

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    F, Q = cv_model(1.0, 0.3, dims=1)
    if F is None or kf_predict(np.zeros(2), np.eye(2), np.eye(2), np.eye(2))[0] is None \
            or kf_update(np.zeros(2), np.eye(2), np.zeros(1), np.array([[1.0, 0.0]]), np.eye(1))[0] is None:
        raise SystemExit("cv_model / kf_predict / kf_update still return None: complete TODO 8 to 10 first.")
    print("1-D model, dt = 1 s, q = 0.3:\nF =\n", F, "\nQ =\n", Q)
    x, P = np.array([80.0, 0.0]), np.diag([9.0, 4.0])
    x, P = kf_predict(x, P, F, Q)
    print("after predict: x =", x, "\nP =\n", P)
    x, P, nu, S = kf_update(x, P, np.array([83.0]), np.array([[1.0, 0.0]]), np.array([[2.25]]))
    print("after a baro height of 83 m (sigma 1.5): x =", x, " innovation", nu, " S", S, "\nP =\n", P)
    print("NEES of an error (3, -1) for P = diag(4, 1):", nees(np.array([3.0, -1.0]), np.diag([4.0, 1.0])))
