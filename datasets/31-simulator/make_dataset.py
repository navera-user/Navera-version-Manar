#!/usr/bin/env python3
"""Make the lesson-28 dataset (run on the host, from this folder).

    python3 make_dataset.py [--campaign <dir with drift_target.csv ...>] [--measured <flight_measured.csv>]

What is in /data/academy/31-simulator/ and where it comes from:

* sample_flight.csv, sample_events.log, sample_estimator.log, sample_gps_node.log
  The sample flight recorded with record_sample.sh (drone over Sousse, simulated vision
  "target" profile, GPS jammed 60 s then spoofed by a 2 km jump for 30 s). SIMULATION.
* campaign/   the fault-injection campaign: one CSV per flight (sim_ctl.py columns) and the
  simulator's events. Flights:
    jam_spoof_target     = sample_flight.csv (record_sample.sh target)
    jam_spoof_measured   record_sample.sh measured (former day vision profile, DEGRADED,
                         forwarded to the autopilot); its CSV has no error columns
    drift_target, off_target, jam_camfail_target
                         record_campaign.sh with the scenarios/ files
  campaign/estimator_campaign.log: the arbiter's log of the record_campaign.sh session.
* gps_input.bin  a MAVLink 2 byte stream: what NAVERA's vehicle_output would send to the
  autopilot during the sample flight, at 1 Hz (the recording has one row per second):
  a HEARTBEAT (sys 1, comp 191, MAV_TYPE_ONBOARD_CONTROLLER) and a GPS_INPUT (id 232) per
  second. The GPS_INPUT fields are made by NAVERA's own navera_output.mavlink_out
  .gps_input_fields() from the recorded NAVERA state; the frames are packed by pymavlink.
  Three frames have one corrupted byte ON PURPOSE (the lab finds them by their CRC), and the
  two frames of one second are missing (the lab finds the gap in the sequence numbers).
* gps_input_truth.json  the expected decoding (for the teacher; the check recomputes it).

Needs: pymavlink, and ~/Navera (or base/) navera_output + navera_common on PYTHONPATH.
"""
import argparse
import csv
import json
import math
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "..", "..", "base")
for p in ("navera_output", "navera_common"):
    sys.path.insert(0, os.path.join(BASE, p))

from pymavlink.dialects.v20 import ardupilotmega as mavlink2  # noqa: E402
from navera_output import mavlink_out  # noqa: E402
from navera_output.policy import KIND_FIX, KIND_NONE, Output  # noqa: E402

T0_UTC = datetime(2026, 10, 7, 10, 13, 27, tzinfo=timezone.utc)   # start of the sample recording
HOME_ALT_MSL = 10.0                                                  # SITL --home altitude
GPS_SIGMA = 1.4                                                      # gps_node: hdop 0.7 x 2 m
CORRUPT = (57, 150, 230)                                             # rows whose GPS_INPUT is damaged
DROPPED = (300,)                                                     # rows whose two frames are lost
M_PER_DEG = 111_320.0


class _Buf:
    def __init__(self):
        self.data = bytearray()

    def write(self, b):
        self.data += b


def velocity(rows, i):
    """(north, east) m/s from the truth track (central difference) — the receiver's RMC velocity."""
    a, b = rows[max(0, i - 1)], rows[min(len(rows) - 1, i + 1)]
    try:
        dt = float(b["t_s"]) - float(a["t_s"])
        dn = (float(b["truth_lat"]) - float(a["truth_lat"])) * M_PER_DEG
        de = (float(b["truth_lon"]) - float(a["truth_lon"])) * M_PER_DEG * math.cos(math.radians(float(a["truth_lat"])))
        return dn / dt, de / dt
    except (ValueError, ZeroDivisionError):
        return math.nan, math.nan


def output_for(rows, i):
    r = rows[i]
    if r["navera_state"] not in ("FIX",) or not r["navera_lat"]:
        return Output(KIND_NONE, "no fix")
    lat, lon = float(r["navera_lat"]), float(r["navera_lon"])
    if r["navera_source"] == "GPS":
        vn, ve = velocity(rows, i)
        alt = HOME_ALT_MSL + float(r["truth_alt_m"] or 0.0)
        return Output(KIND_FIX, "fix", lat=lat, lon=lon, alt_ellipsoid_m=alt + 33.0, geoid_sep_m=33.0,
                      sigma_h_m=GPS_SIGMA, sigma_v_m=2 * GPS_SIGMA, satellites=12, gnss=True,
                      vel_n_mps=vn, vel_e_mps=ve)
    # day vision, target profile: stated sigma 15 m, no altitude, no velocity
    return Output(KIND_FIX, "fix", lat=lat, lon=lon, sigma_h_m=15.0, sigma_v_m=30.0, satellites=None)


def make_stream(flight, out_bin, out_truth):
    with open(flight, newline="") as f:
        rows = list(csv.DictReader(f))
    buf = _Buf()
    mav = mavlink2.MAVLink(buf, srcSystem=1, srcComponent=191)
    truth = []
    for i, r in enumerate(rows):
        t_utc = T0_UTC + timedelta(seconds=float(r["t_s"]))
        row_start = len(buf.data)
        mav.heartbeat_send(mavlink2.MAV_TYPE_ONBOARD_CONTROLLER, mavlink2.MAV_AUTOPILOT_INVALID, 0, 0,
                           mavlink2.MAV_STATE_ACTIVE)
        start = len(buf.data)
        fields = mavlink_out.gps_input_fields(output_for(rows, i), t_utc)
        mav.gps_input_send(**fields)
        if i in CORRUPT:                       # flip one payload byte: the CRC no longer matches
            buf.data[start + 10 + 9] ^= 0x5A
        if i in DROPPED:                       # both frames lost on the link: a gap in seq
            del buf.data[row_start:]
            continue
        truth.append(dict(t_s=float(r["t_s"]), corrupt=i in CORRUPT, fix_type=fields["fix_type"],
                          ignore_flags=fields["ignore_flags"], lat=fields["lat"] / 1e7, lon=fields["lon"] / 1e7,
                          horiz_accuracy=fields["horiz_accuracy"], source=r["navera_source"]))
    with open(out_bin, "wb") as f:
        f.write(bytes(buf.data))
    with open(out_truth, "w") as f:
        json.dump(truth, f)
    print(f"{out_bin}: {len(buf.data)} bytes, {len(rows) - len(DROPPED)} GPS_INPUT + HEARTBEAT pairs, "
          f"{len(CORRUPT)} corrupted, {2 * len(DROPPED)} dropped")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", help="folder written by record_campaign.sh (campaign/)")
    ap.add_argument("--measured", default=os.path.join(HERE, "..", "32-measuring", "flight_measured.csv"))
    a = ap.parse_args()
    camp = os.path.join(HERE, "campaign")
    os.makedirs(camp, exist_ok=True)
    shutil.copy(os.path.join(HERE, "sample_flight.csv"), os.path.join(camp, "jam_spoof_target.csv"))
    shutil.copy(os.path.join(HERE, "sample_events.log"), os.path.join(camp, "jam_spoof_target_events.log"))
    if os.path.exists(a.measured):
        shutil.copy(a.measured, os.path.join(camp, "jam_spoof_measured.csv"))
    if a.campaign:
        for fn in sorted(os.listdir(a.campaign)):
            src, dst = os.path.join(a.campaign, fn), os.path.join(camp, fn)
            if fn.endswith("_events.log"):
                # the simulator's event list still holds the previous mission's last events:
                # keep this mission's, from its own "step 1/4" line
                lines = open(src).readlines()
                starts = [i for i, ln in enumerate(lines) if "mission: step 1/4" in ln]
                open(dst, "w").writelines(lines[starts[-1]:] if starts else lines)
            elif fn.endswith((".csv", ".log")):
                shutil.copy(src, dst)
    make_stream(os.path.join(HERE, "sample_flight.csv"), os.path.join(HERE, "gps_input.bin"),
                os.path.join(HERE, "gps_input_truth.json"))


if __name__ == "__main__":
    main()
