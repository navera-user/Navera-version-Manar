"""Read a saved test and say what happened and what to fix.

    python3 -m navera_tools.field.analyze <test folder>

Writes report.json and report.md in the folder. Every figure is computed from what the
test saved: the camera frames, the solver's answer, and the phone's GPS as the truth.
The problem rules and their limits are in PROBLEM_RULES below, so they can be read and
changed in one place. The limits are first guesses until real sky nights calibrate them.
"""
import json
import math
import os
import statistics
import sys
from typing import Dict, List, Optional

from navera_tools.field.store import read_jsonl

MIN_STARS = 12                 # confirmed stars a frame needs for a reliable solve
SKY_KM_PER_SECOND = 0.4625     # the sky turns 15 arc-seconds per second: 1 s of clock error = 0.46 km
KM_PER_DEGREE = 111.2
WRONG_KM = 150.0               # a fix further than this from the phone is a wrong answer, not a rough one
STALE_GPS_S = 10.0             # a phone position older than this when sent is frozen, not a truth
TRUTH_MAX_GAP_S = 3.0          # a phone sample further than this from a frame is not its truth

PROBLEM_RULES = {
    "few_stars": f"more than 40 % of frames have fewer than {MIN_STARS} confirmed stars",
    "not_looking_at_sky": "more than 30 % of frames show something other than open sky",
    "sky_not_clear": "more than 30 % of frames are hazy, cloudy or too bright",
    "not_level": "the camera axis is more than 1 degree off vertical in the median frame",
    "clock_offset": "phone and Jetson clocks differ by more than 0.5 s",
    "phone_gps_poor": "the phone's GPS accuracy is worse than 30 m in the median sample",
    "no_truth": "no phone GPS was saved",
    "solver_timeouts": "more than 10 % of attempts ran out of time",
    "error_over_sigma": "more than 20 % of fixes are further than 2 x the stated uncertainty",
    "too_short": "fewer than 10 frames were recorded",
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _truth_at(phone: List[dict], t: float) -> Optional[dict]:
    """The phone's position at time t (interpolated between its two nearest samples)."""
    good = [p for p in phone if p.get("lat") is not None and p.get("lon") is not None
            and (p.get("gps_age_s") is None or p["gps_age_s"] <= STALE_GPS_S)]   # the page resends its last fix: skip frozen ones
    if not good:
        return None
    before = [p for p in good if p["t"] <= t]
    after = [p for p in good if p["t"] >= t]
    a = before[-1] if before else None
    b = after[0] if after else None
    if a is None and b is None:
        return None
    if a is None or b is None or a["t"] == b["t"]:
        p = a or b
        return p if abs(p["t"] - t) <= TRUTH_MAX_GAP_S else None
    if b["t"] - a["t"] > 2 * TRUTH_MAX_GAP_S:
        p = a if t - a["t"] < b["t"] - t else b
        return p if abs(p["t"] - t) <= TRUTH_MAX_GAP_S else None
    f = (t - a["t"]) / (b["t"] - a["t"])
    return {"lat": a["lat"] + f * (b["lat"] - a["lat"]), "lon": a["lon"] + f * (b["lon"] - a["lon"]),
            "acc": max(a.get("acc") or 0, b.get("acc") or 0)}


def _count(items) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for x in items:
        k = str(x or "no reason saved")[:60]
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _solve_times(frames: List[dict]):
    v = [f["solve_s"] for f in frames if isinstance(f.get("solve_s"), (int, float))]
    return {"median": round(statistics.median(v), 1), "max": round(max(v), 1)} if v else None


def _pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))] if s else None


def analyze(folder: str) -> dict:
    meta = {}
    p = os.path.join(folder, "session.json")
    if os.path.exists(p):
        with open(p) as f:
            meta = json.load(f)
    def rows_of(name):
        return [x for x in read_jsonl(os.path.join(folder, name)) if isinstance(x, dict) and isinstance(x.get("t"), (int, float))]
    phone = sorted(rows_of("phone.jsonl"), key=lambda p: p["t"])
    frames = rows_of("frames.jsonl")
    events = rows_of("events.jsonl")

    errs, within2, rows = [], [], []
    trusted_errs, flagged_errs, within3_trusted, within3_flagged = [], [], [], []
    no_truth = bad_answer = with_prior = 0
    for fr in frames:
        row = {"t": fr["t"], "idx": fr.get("idx"), "stars": fr.get("confirmed", fr.get("detected")),
               "sky": fr.get("sky"), "fix": bool(fr.get("solved")), "err_km": None, "why": fr.get("why")}
        if fr.get("solved"):
            if not all(isinstance(fr.get(k), (int, float)) and math.isfinite(fr[k]) for k in ("lat", "lon")):
                bad_answer += 1
                row["why"] = "answer is not a number"
            else:
                # the frame is stamped when its solve ended; the exposure was solve_s earlier (360: t_exp is recorded)
                truth = _truth_at(phone, fr["t_exp"] if isinstance(fr.get("t_exp"), (int, float))
                                  else fr["t"] - (fr.get("solve_s") or 0.0))
                if truth is None:
                    no_truth += 1
                else:
                    e = haversine_km(fr["lat"], fr["lon"], truth["lat"], truth["lon"])
                    row["err_km"] = round(e, 1)
                    errs.append(e)
                    prior = fr.get("prior") or []
                    if any(isinstance(v, (int, float)) and math.isfinite(v) for v in prior):
                        with_prior += 1               # the phone's position helped the solver: not independent
                        row["prior_used"] = True
                    if fr.get("sigma_km"):
                        within2.append(e <= 2 * fr["sigma_km"])
                    row["trusted"] = _trusted(fr)
                    (trusted_errs if row["trusted"] else flagged_errs).append(e)
                    if fr.get("sigma_km"):
                        (within3_trusted if row["trusted"] else within3_flagged).append(e <= 3 * fr["sigma_km"])
        rows.append(row)

    n = len(frames)
    solved = sum(1 for r in rows if r["fix"])
    stars = [r["stars"] for r in rows if r["stars"] is not None]
    sky_counts: Dict[str, int] = {}
    for fr in frames:
        sky_counts[fr.get("sky") or "unknown"] = sky_counts.get(fr.get("sky") or "unknown", 0) + 1
    started, ended = meta.get("started"), meta.get("ended")
    if frames or phone:
        stamps = [x["t"] for x in frames + phone]
        started, ended = started or min(stamps), ended or max(stamps)

    report = {
        "id": meta.get("id") or os.path.basename(folder.rstrip("/")),
        "started": started, "ended": ended,
        "duration_s": round(ended - started, 1) if started and ended else None,
        "frames": n, "solved": solved,
        "solved_frac": round(solved / n, 3) if n else 0.0,
        "scored": len(errs), "solved_no_truth": no_truth, "bad_answer": bad_answer,
        # a fix the system itself flags as not to be trusted (360: taken while the vehicle moved) is not a wrong answer
        # when its error is inside its stated 3 sigma; it is reported apart
        "wrong_answers": sum(1 for e in trusted_errs if e > WRONG_KM) + sum(1 for ok in within3_flagged if not ok),
        "scored_with_phone_prior": with_prior,
        "trusted_err_km": _stats(trusted_errs), "trusted_within_3sigma": _frac(within3_trusted),
        "flagged_err_km": _stats(flagged_errs), "flagged_within_3sigma": _frac(within3_flagged),
        "stopped_but_phone_moving": sum(1 for fr in frames if fr.get("solved") and fr.get("stopped_but_phone_moving")),
        "no_answer_by_reason": _count(r["why"] for r in rows if not r["fix"]),
        "solve_s": _solve_times(frames),
        "err_km": ({"median": round(statistics.median(errs), 1), "p90": round(_pct(errs, 0.9), 1),
                    "max": round(max(errs), 1)} if errs else None),
        "within_2sigma_frac": round(sum(within2) / len(within2), 3) if within2 else None,
        "stars_median": statistics.median(stars) if stars else None,
        "sky": sky_counts, "software": meta.get("software"), "notes": [e for e in events if e.get("kind") == "note"],
        "rows": rows,
    }
    report["drive_measurements"] = drive_measurements(frames, phone, events)
    report["problems"] = _problems(report, frames, phone, meta)
    report["verdict"] = _verdict(report)
    return report


STOP_MPS = 0.5                 # phone GPS speed below this = the car stands (a stop for fixes-per-stop)
DRIVE_MPS = 3.0                # and above this it drives (vibration while moving)
MIN_STOP_S = 8.0               # a stop shorter than this is not counted


def _speed_at(phone: List[dict], t: float) -> Optional[float]:
    pts = [p for p in phone if isinstance(p.get("speed"), (int, float)) and abs(p["t"] - t) <= 2.0]
    return min(pts, key=lambda p: abs(p["t"] - t))["speed"] if pts else None


def _med(v, nd=4):
    v = [x for x in v if isinstance(x, (int, float)) and math.isfinite(x)]
    return {"n": len(v), "median": round(statistics.median(v), nd), "p90": round(_pct(v, 0.9), nd),
            "max": round(max(v), nd)} if v else None


def drive_measurements(frames: List[dict], phone: List[dict], events: List[dict]) -> dict:
    """What the real drive measures that simulation only assumed (F19): stops and trusted fixes per stop, the
    stopped flag against the phone's speed (false stops / lost stops, the camera driver's test vs the long-window
    test), vibration at rest and while driving, solve times with the Jetson's load, the image standstill measure,
    the time source and the battery clock's error, camera reconnects. Every figure from the saved records."""
    fr360 = [f for f in frames if f.get("mode") == "360"]
    out: dict = {"frames_360": len(fr360)}
    sp = sorted((p["t"], p["speed"]) for p in phone if isinstance(p.get("speed"), (int, float)))
    stops, cur = [], None
    for t, v in sp:
        if v < STOP_MPS:
            cur = [t, t] if cur is None else [cur[0], t]
        else:
            if cur and cur[1] - cur[0] >= MIN_STOP_S:
                stops.append(cur)
            cur = None
    if cur and cur[1] - cur[0] >= MIN_STOP_S:
        stops.append(cur)
    per_stop = []
    for a, b in stops:
        inside = [f for f in fr360 if a <= (f.get("t_exp") or f["t"]) <= b]
        per_stop.append({"start": round(a, 1), "s": round(b - a, 1), "frames": len(inside),
                         "flagged_stopped": sum(1 for f in inside if f.get("stopped")),
                         "fixes_trusted": sum(1 for f in inside if f.get("solved") and _trusted(f))})
    out["stops"] = per_stop
    out["trusted_fixes_per_stop"] = _med([p["fixes_trusted"] for p in per_stop], 1)
    conf = {"stopped_flag_while_moving": 0, "stopped_flag_while_standing": 0, "moving_flag_while_standing": 0,
            "driver_said_stopped_long_window_refused": 0, "frames_with_speed": 0}
    vib_rest, vib_drive, gyro_rest, gyro_drive, gc_rest, gc_drive = [], [], [], [], [], []
    for f in fr360:
        v = _speed_at(phone, f.get("t_exp") or f["t"])
        st = f.get("stillness") or {}
        if st.get("driver_stopped") and not f.get("stopped"):
            conf["driver_said_stopped_long_window_refused"] += 1
        if v is None:
            continue
        conf["frames_with_speed"] += 1
        if v > 1.0 and f.get("stopped"):
            conf["stopped_flag_while_moving"] += 1
        if v < STOP_MPS:
            conf["stopped_flag_while_standing" if f.get("stopped") else "moving_flag_while_standing"] += 1
        vib = f.get("imu_vib") or {}
        if v < STOP_MPS:
            vib_rest.append(vib.get("acc_hp_rms_g"))
            gyro_rest.append(vib.get("gyro_rms_dps"))
            gc_rest.append(f.get("ground_change"))
        elif v > DRIVE_MPS:
            vib_drive.append(vib.get("acc_hp_rms_g"))
            gyro_drive.append(vib.get("gyro_rms_dps"))
            gc_drive.append(f.get("ground_change"))
    out["stopped_flag_vs_phone"] = conf
    out["vibration"] = {"rest_acc_hp_rms_g": _med(vib_rest), "drive_acc_hp_rms_g": _med(vib_drive),
                        "rest_gyro_rms_dps": _med(gyro_rest), "drive_gyro_rms_dps": _med(gyro_drive)}
    out["ground_change"] = {"rest": _med(gc_rest, 2), "drive": _med(gc_drive, 2)}
    solved = [f for f in fr360 if isinstance(f.get("solve_s"), (int, float))]
    quiet = [f["solve_s"] for f in solved if ((f.get("host") or {}).get("load1") or 99) < 2.0]
    out["solve_s"] = {"all": _med([f["solve_s"] for f in solved], 2), "quiet_jetson_load_lt_2": _med(quiet, 2),
                      "load1": _med([(f.get("host") or {}).get("load1") for f in fr360], 2),
                      "temp_c": _med([(f.get("host") or {}).get("temp_c") for f in fr360], 1)}
    out["time_source"] = _count(f.get("time_source") for f in fr360 if f.get("time_source"))
    out["rtc_minus_phone_s"] = _med([f.get("rtc_minus_phone_s") for f in fr360], 3)
    out["time_sigma_s"] = _med([f.get("time_sigma_s") for f in fr360], 3)
    health = [f.get("cam_health") or {} for f in fr360]
    out["camera"] = {"reconnects": max([h.get("reconnects") or 0 for h in health] or [0]),
                     "imu_restarts": max([h.get("imu_restarts") or 0 for h in health] or [0]),
                     "usb_resets": max([h.get("usb_resets") or 0 for h in health] or [0]),
                     "events": _count(e.get("kind") for e in events if e.get("kind") in
                                      ("camera_lost", "camera_back", "clock_jump", "tilt_calibrated", "tilt_fit_refused"))}
    return out


def _trusted(fr: dict) -> bool:
    """A fix the system stands behind: every strip-mode fix; a 360 fix only when the camera's own sensor said
    stopped and the phone's GPS did not see the car moving (the test's referee)."""
    if fr.get("mode") != "360":
        return True
    return bool(fr.get("stopped")) and not fr.get("stopped_but_phone_moving")


def _stats(v):
    return {"n": len(v), "median": round(statistics.median(v), 1), "p90": round(_pct(v, 0.9), 1),
            "max": round(max(v), 1)} if v else None


def _frac(v):
    return round(sum(v) / len(v), 3) if v else None


def _verdict(r: dict) -> str:
    """OK needs enough frames, most answers scored and right, and no 'bad' problem.
    A wrong answer counts against the test; it is not a 'solved' frame."""
    n = r["frames"]
    if n < 5:
        return "NO DATA"
    if r["solved"] and r["scored"] == 0:
        return "NO TRUTH"                    # the solver answered but nothing was there to compare with
    if r["solved_frac"] < 0.1 or r["scored"] == 0:
        return "NO FIX"
    good = r["scored"] - r["wrong_answers"]
    bad_problem = any(p["severity"] == "bad" for p in r["problems"])
    ok = (n >= 10 and r["scored"] >= 10 and r["scored"] >= 0.8 * r["solved"] and good >= 0.6 * n
          and r["err_km"]["p90"] <= 300 and r["scored_with_phone_prior"] <= 0.5 * r["scored"] and not bad_problem)
    return "OK" if ok else "PARTLY"


def _problems(r: dict, frames: List[dict], phone: List[dict], meta: dict) -> List[dict]:
    out: List[dict] = []

    def add(pid, sev, title, detail, fix):
        out.append({"id": pid, "severity": sev, "title": title, "detail": detail, "fix": fix})

    n = r["frames"]
    if n < 10:
        add("too_short", "warn", "Test too short", f"Only {n} frames were recorded.",
            "Drive at least 10 minutes with the sky check green.")
    if not any(p.get("lat") is not None for p in phone):
        add("no_truth", "bad", "No phone GPS saved",
            "Nothing to compare the answer with, so no error could be computed.",
            "Allow location for the page on the phone and keep the screen on.")
    else:
        accs = [p["acc"] for p in phone if p.get("acc") is not None]
        if accs and statistics.median(accs) > 1000:
            add("phone_gps_poor", "warn", "Phone GPS was poor",
                f"Median accuracy {statistics.median(accs):.0f} m, as large as the celestial fix itself would be good to.",
                "Check the phone has a real GPS fix (location on, high accuracy).")
    blocked = [f for f in frames if f.get("sky") == "blocked"]
    low = [f for f in frames if (f.get("confirmed", f.get("detected")) or 0) < MIN_STARS and f.get("sky") in (None, "clear", "hazy")]
    if n and len(low) / n > 0.4 and len(blocked) / n <= 0.3:
        med = statistics.median([f.get("confirmed", f.get("detected")) or 0 for f in low])
        add("few_stars", "bad", "Too few stars",
            f"{len(low)} of {n} frames had fewer than {MIN_STARS} confirmed stars (median {med:g}).",
            "On clear-sky frames the detector still found too few stars. Possible causes, not measured here: "
            "lights nearby, the camera's automatic exposure, or too little sky in view. Compare the saved frames/*.jpg "
            "with the sky by eye before deciding.")
    if n and len(blocked) / n > 0.3:
        add("not_looking_at_sky", "bad", "The camera was not looking at open sky",
            f"{len(blocked)} of {n} frames show a room, a roof, trees or other structure instead of flat dark sky.",
            "Point the camera straight up with nothing above it (no roof rack, windshield, trees or lamp posts).")
    notclear = [f for f in frames if f.get("sky") not in (None, "clear", "blocked")]
    if n and len(notclear) / n > 0.3:
        kinds = sorted({f["sky"] for f in notclear})
        add("sky_not_clear", "warn", "Sky was not clear", f"{len(notclear)} of {n} frames: {', '.join(kinds)}.",
            "Test on a clear night away from town and without a Moon.")
    offs = [f["off_vertical_deg"] for f in frames if f.get("off_vertical_deg") is not None]
    if offs and statistics.median(offs) > 1.0:
        m = statistics.median(offs)
        add("not_level", "bad", "Camera not pointing straight up",
            f"Median {m:.1f} degrees off vertical. The phone's tilt is used to correct this, but only if the phone "
            f"sits parallel to the camera (an uncorrected degree is {KM_PER_DEGREE:.0f} km).",
            "Level the mount before driving and fix the phone rigidly beside the camera.")
    off = meta.get("clock_offset_s")
    if off is not None and abs(off) > 0.5:
        add("clock_offset", "warn", "Phone and Jetson clocks differ",
            f"{off:+.2f} s, which includes the network delay. The time given to the solver was corrected by it; "
            f"an uncorrected error of this size would cost about {abs(off) * SKY_KM_PER_SECOND:.0f} km.",
            "Check the Jetson clock against the phone's before the drive.")
    timeouts = [f for f in frames if "timeout" in str(f.get("why") or "")]
    if n and len(timeouts) / n > 0.1:
        add("solver_timeouts", "warn", "Solver ran out of time", f"{len(timeouts)} of {n} frames.",
            "Check the Jetson's load and temperature (see solve_s in the report).")
    if r["within_2sigma_frac"] is not None and r["within_2sigma_frac"] < 0.8:
        add("error_over_sigma", "warn", "Stated uncertainty too optimistic",
            f"Only {r['within_2sigma_frac'] * 100:.0f} % of fixes are within 2 x the stated sigma.",
            "The stated sigma is a guess. Check first whether the errors are a constant bias (a wrong heading, time or "
            "mount offset) or a random spread, then change the cause or the sigma.")
    if r["solved"] and r["scored"] < 0.8 * r["solved"]:
        add("solved_without_truth", "warn", "Some answers could not be checked",
            f"{r['solved_no_truth']} of {r['solved']} answered frames had no phone GPS sample within {TRUTH_MAX_GAP_S:g} s.",
            "Keep the phone page open, screen on, with location allowed.")
    if r["scored"] and r["wrong_answers"] / r["scored"] > 0.2:
        add("wrong_answers", "bad", "Many answers were wrong",
            f"{r['wrong_answers']} of {r['scored']} checked answers were more than {WRONG_KM:g} km from the phone.",
            "Look at the error table by time: a constant bias points to heading, time or mount; scattered errors to bad star matches.")
    if r["scored"] and r["scored_with_phone_prior"] > 0.5 * r["scored"]:
        add("prior_used", "warn", "The phone position helped the solver",
            f"{r['scored_with_phone_prior']} of {r['scored']} checked frames used the phone position as a prior (camera tilted below 60 degrees), so their error is not independent.",
            "Point the camera straight up for an independent test.")
    if r["bad_answer"]:
        add("bad_answers", "bad", "Answers that were not numbers", f"{r['bad_answer']} frames.", "Report this to the developer with the folder.")
    order = {"bad": 0, "warn": 1}
    return sorted(out, key=lambda p: order[p["severity"]])


def write_report(folder: str) -> dict:
    r = analyze(folder)
    with open(os.path.join(folder, "report.json"), "w") as f:
        json.dump(r, f, indent=1, default=str)
    lines = [f"# Test {r['id']}: {r['verdict']}", "",
             f"- Frames: {r['frames']}, with a position: {r['solved']} ({r['solved_frac'] * 100:.0f} %)",
             f"- Checked against the phone GPS: {r['scored']} (answered but not checkable: {r['solved_no_truth']}, wrong by more than {WRONG_KM:g} km: {r['wrong_answers']})",
             f"- Error against the phone GPS: {r['err_km']}",
             f"- Trusted fixes (360: stopped): {r['trusted_err_km']}, within 3 sigma: {r['trusted_within_3sigma']}",
             f"- Flagged fixes (360: moving, not to be used): {r['flagged_err_km']}, within 3 sigma: {r['flagged_within_3sigma']}",
             f"- Stopped by the camera's sensor but moving by the phone's GPS: {r['stopped_but_phone_moving']}",
             f"- Median confirmed stars: {r['stars_median']}",
             f"- No answer, by reason: {r['no_answer_by_reason']}", f"- Solver time (s): {r['solve_s']}",
             f"- Sky: {r['sky']}", ""]
    dm = r.get("drive_measurements") or {}
    if dm.get("frames_360"):
        lines += ["## Drive measurements (F19)", "",
                  f"- Stops (phone speed < {STOP_MPS} m/s for >= {MIN_STOP_S:g} s): {len(dm['stops'])}; trusted fixes "
                  f"per stop: {dm['trusted_fixes_per_stop']}",
                  f"- Stopped flag against the phone's speed: {dm['stopped_flag_vs_phone']}",
                  f"- Vibration (camera IMU): {dm['vibration']}",
                  f"- Image standstill measure (ground_change, logged only): {dm['ground_change']}",
                  f"- Solve time (s): {dm['solve_s']}",
                  f"- Time source: {dm['time_source']}; DS3231 minus phone (s): {dm['rtc_minus_phone_s']}",
                  f"- Camera stream: {dm['camera']}", ""]
    lines += ["## Problems", ""]
    lines += [f"- **{p['title']}** ({p['severity']}): {p['detail']} Fix: {p['fix']}" for p in r["problems"]] or ["- none found"]
    with open(os.path.join(folder, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return r


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 -m navera_tools.field.analyze <test folder>")
    print(json.dumps({k: v for k, v in write_report(sys.argv[1]).items() if k != "rows"}, indent=1, default=str))
