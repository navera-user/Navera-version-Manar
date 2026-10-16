"""baseline.py — the baseline every navigation method must beat (lab 32, TODO A).

"Do nothing clever": when GPS is jammed, keep giving the LAST GPS position the judge gave before the jam.
Your vision source is worth something only if its errors are smaller than this baseline's, at the same
seconds. measure_lab.py calls your function on the three flights.
"""
import numpy as np

from navera_lite.logbook import haversine_m


# TODO A ----------------------------------------------------------------------------------------
def last_fix_baseline(df):
    """The error (m) of the baseline "repeat the last GPS position" during the jam: one value per row whose
    gps column is "jammed", in the order of the rows. The frozen position is the last position the judge
    gave with source "gps" BEFORE the first jammed row (the judge's output, not the truth). Its error at a
    jammed row is the distance from that frozen position to the row's truth (logbook.haversine_m).
    A flight without a jammed row gives an empty array.

    df: a flight table (columns t_s, gps, state, source, lat, lon, truth_lat, truth_lon), sorted by t_s.
    Returns a 1-D numpy array of floats (m).
    Example: rows gps ok / source gps at 35.80000 (t 0) and 35.80010 (t 1) (their truth 0.00002° further north),
             then gps ok / source day at 35.80050 (t 2), then two jammed rows whose truth is 35.80020 and
             35.80030 (same longitude) → array([11.12, 22.24])
    """
    return None   # TODO: replace this line with your code
