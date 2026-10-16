"""my_metric.py — ONLY if no metric of project.py fits your project ("metric": {"name": "custom"} in project.json).
It is part of your ruler: commit it with your red test, before the baseline; never change it afterwards.
You don't need this file otherwise.

A run is a list of rows (dicts), one every 0.2 s of mission time, with the columns of navera_lite/sim/world.py
(COLUMNS): "t_s", "lite_err_m", "lite_sigma_m", "ap_err_m", "gps_err_m", "vis_err_m", "truth_speed_mps" are floats
(None when empty); "lite_state", "lite_source", "guard", "gps_mode", "camera", "ap_mode", "reason" are texts.
The scenario is the dict of its campaign/*.json file (with "faults").
"""


def metric(rows, scenario):
    """One number for one run — the same function for every run, before and after.

    Example (a metric that counts the seconds in NO_FIX): metric(rows, scenario) → 3.2
    """
    return None   # TODO: replace this line with your code
