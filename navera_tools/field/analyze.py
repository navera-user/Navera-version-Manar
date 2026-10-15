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
    good = [p for p in phone if p.get("lat") is not None and p.get("lon") is not None]
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


def _pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))] if s else None


def analyze(folder: str) -> dict:
    meta = {}
    p = os.path.join(folder, "session.json")
    if os.path.exists(p):
        with open(p) as f:
            meta = json.load(f)
    phone = sorted(read_jsonl(os.path.join(folder, "phone.jsonl")), key=lambda p: p["t"])
    frames = read_jsonl(os.path.join(folder, "frames.jsonl"))
    events = read_jsonl(os.path.join(folder, "events.jsonl"))

    errs, within2, rows = [], [], []
    for fr in frames:
        row = {"t": fr["t"], "idx": fr.get("idx"), "stars": fr.get("confirmed", fr.get("detected")),
               "sky": fr.get("sky"), "fix": bool(fr.get("solved")), "err_km": None, "why": fr.get("why")}
        if fr.get("solved") and fr.get("lat") is not None:
            truth = _truth_at(phone, fr["t"])
            if truth is not None:
                e = haversine_km(fr["lat"], fr["lon"], truth["lat"], truth["lon"])
                row["err_km"] = round(e, 1)
                errs.append(e)
                if fr.get("sigma_km"):
                    within2.append(e <= 2 * fr["sigma_km"])
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
        "scored": len(errs),
        "err_km": ({"median": round(statistics.median(errs), 1), "p90": round(_pct(errs, 0.9), 1),
                    "max": round(max(errs), 1)} if errs else None),
        "within_2sigma_frac": round(sum(within2) / len(within2), 3) if within2 else None,
        "stars_median": statistics.median(stars) if stars else None,
        "sky": sky_counts, "software": meta.get("software"), "notes": [e for e in events if e.get("kind") == "note"],
        "rows": rows,
    }
    report["problems"] = _problems(report, frames, phone, meta)
    report["verdict"] = _verdict(report)
    return report


def _verdict(r: dict) -> str:
    if r["frames"] < 5:
        return "NO DATA"
    if r["solved_frac"] < 0.1 or r["scored"] == 0:
        return "NO FIX"
    ok_err = r["err_km"]["median"] <= 150
    return "OK" if r["solved_frac"] >= 0.6 and ok_err else "PARTLY"


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
        if accs and statistics.median(accs) > 30:
            add("phone_gps_poor", "warn", "Phone GPS was poor",
                f"Median accuracy {statistics.median(accs):.0f} m.", "Put the phone near a window with sky view.")
    blocked = [f for f in frames if f.get("sky") == "blocked"]
    low = [f for f in frames if (f.get("confirmed", f.get("detected")) or 0) < MIN_STARS]
    if n and len(low) / n > 0.4 and len(blocked) / n <= 0.3:
        med = statistics.median([f.get("confirmed", f.get("detected")) or 0 for f in frames])
        add("few_stars", "bad", "Too few stars",
            f"{len(low)} of {n} frames had fewer than {MIN_STARS} confirmed stars (median {med:g}).",
            "Park away from lights and wait for a clear sky. If it stays low on a clear dark night, "
            "the camera's automatic exposure is the limit: try the other lens module or a camera with manual exposure.")
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
            f"Median {m:.1f} degrees off vertical; each degree moves the answer {KM_PER_DEGREE:.0f} km "
            "if it is not corrected.", "Level the mount with the phone's bubble before driving; avoid steep roads.")
    off = meta.get("clock_offset_s")
    if off is not None and abs(off) > 0.5:
        add("clock_offset", "warn", "Phone and Jetson clocks differ",
            f"{off:+.2f} s, about {abs(off) * SKY_KM_PER_SECOND:.0f} km of error.",
            "Connect the Jetson to the internet (NTP) or keep the phone's clock automatic.")
    timeouts = [f for f in frames if "timeout" in str(f.get("why") or "")]
    if n and len(timeouts) / n > 0.1:
        add("solver_timeouts", "warn", "Solver ran out of time", f"{len(timeouts)} of {n} frames.",
            "Check the Jetson's load and temperature; fewer stars make the solver slower.")
    if r["within_2sigma_frac"] is not None and r["within_2sigma_frac"] < 0.8:
        add("error_over_sigma", "warn", "Stated uncertainty too optimistic",
            f"Only {r['within_2sigma_frac'] * 100:.0f} % of fixes are within 2 x the stated sigma.",
            "Raise the celestial sigma to the measured spread.")
    order = {"bad": 0, "warn": 1}
    return sorted(out, key=lambda p: order[p["severity"]])


def write_report(folder: str) -> dict:
    r = analyze(folder)
    with open(os.path.join(folder, "report.json"), "w") as f:
        json.dump(r, f, indent=1, default=str)
    lines = [f"# Test {r['id']}: {r['verdict']}", "",
             f"- Frames: {r['frames']}, with a position: {r['solved']} ({r['solved_frac'] * 100:.0f} %)",
             f"- Error against the phone GPS: {r['err_km']}", f"- Median confirmed stars: {r['stars_median']}",
             f"- Sky: {r['sky']}", "", "## Problems", ""]
    lines += [f"- **{p['title']}** ({p['severity']}): {p['detail']} Fix: {p['fix']}" for p in r["problems"]] or ["- none found"]
    with open(os.path.join(folder, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return r


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 -m navera_tools.field.analyze <test folder>")
    print(json.dumps({k: v for k, v in write_report(sys.argv[1]).items() if k != "rows"}, indent=1, default=str))
