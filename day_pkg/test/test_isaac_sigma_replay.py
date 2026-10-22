"""F41 regression: the GPS-lost part of two Isaac Sim closed-loop flights (copter 250 m, 10 m/s, camera
delay 1.3 s unknown to NAVERA; 2026-10-22, code d0ab1c2) replayed offline through the day node's own fix
logic (navera_tools/bench/replay_sigma_isaac.py: the recorded matcher answers -> mount correction, map
bias, gates, blending, track, carry, dead-reckoning; the node built by its own __init__ with the shipped
defaults).

Live, the stated sigma had shrunk to 5-9 m for 13-20 m errors: pd_ref_base 146 of 356 outputs beyond
3 sigma; pd_nomc_base (mount calibration off) 182 of 461 and 90 fixes > 50 m off. The causes: the blend
counted the error every fix shares (unknown delay, camera mount) as independent and the carry was fed
the blended output (a filter of itself, 100 m behind); the mount calibration learned the delay's offset.
Fixtures: day_pkg/test/data/isaac_<run>.json.gz (replay_sigma_isaac.py --extract)."""
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _harness():
    spec = importlib.util.spec_from_file_location(
        "replay_sigma_isaac", os.path.join(ROOT, "navera_tools", "bench", "replay_sigma_isaac.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("run", ["pd_ref_base", "pd_nomc_base"])
def test_stated_sigma_covers_the_error_and_no_wrong_fix(run):
    R = _harness()
    rec = R.load(os.path.join(HERE, "data", f"isaac_{run}.json.gz"))
    params = {"mount_cal": False} if run == "pd_nomc_base" else {}       # as that flight was run
    s = R.score(R.replay(rec, params))
    assert s["fixes"] >= 330
    # >= 99 % of the outputs within 3 stated sigma (was 45 % / 43 % beyond)
    assert s["beyond_3sigma"] <= 0.01 * s["outputs"], s
    assert s["wrong"] == 0, s                                             # was 0 / 99 (live 90)
    # the error at the stated time back to the unblended fixes' level (was 19.8 / 38.7 m median)
    assert s["err"][0] <= 18.0 and s["err"][1] <= 30.0, s
