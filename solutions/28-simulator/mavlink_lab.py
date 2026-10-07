#!/usr/bin/env python3
"""mavlink_lab.py — decode what NAVERA sends to the autopilot, byte by byte (Part A).

    python3 mavlink_lab.py                       decode /data/academy/28-simulator/gps_input.bin
    python3 mavlink_lab.py some_other_file.bin

The file is a MAVLink 2 byte stream: one HEARTBEAT and one GPS_INPUT (id 232) per second of the
recorded sample flight, as NAVERA's vehicle_output would send them (see the lesson, section 3).
No pymavlink here: you write the decoder yourself with `struct` and bit operations.
"""
import struct
import sys
from datetime import datetime, timedelta, timezone

STREAM = "/data/academy/28-simulator/gps_input.bin"

STX_V2 = 0xFD
HEADER_LEN = 10                 # STX, len, incompat, compat, seq, sysid, compid, msgid (3 bytes)
SIGNATURE_LEN = 13              # present only when incompat_flags & 1
MSG_HEARTBEAT = 0
MSG_GPS_INPUT = 232
CRC_EXTRA = {MSG_HEARTBEAT: 50, MSG_GPS_INPUT: 151}

GPS_INPUT_FORMAT = "<QIiifffffffffHHBBBH"          # wire order (fields sorted by size)
GPS_INPUT_FIELDS = ("time_usec", "time_week_ms", "lat", "lon", "alt", "hdop", "vdop", "vn", "ve", "vd",
                    "speed_accuracy", "horiz_accuracy", "vert_accuracy", "ignore_flags", "time_week",
                    "gps_id", "fix_type", "satellites_visible", "yaw")
GPS_INPUT_LEN = struct.calcsize(GPS_INPUT_FORMAT)    # 65

IGNORE_FLAG_NAMES = ("ALT", "HDOP", "VDOP", "VEL_HORIZ", "VEL_VERT", "SPEED_ACCURACY",
                     "HORIZONTAL_ACCURACY", "VERTICAL_ACCURACY")   # bit 0, bit 1, ... bit 7

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
GPS_UTC_LEAP_S = 18


def crc_x25(data, crc=0xFFFF):
    """CRC-16/MCRF4XX ("X.25" in MAVLink) of the bytes `data`, starting from `crc`."""
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def parse_frames(data):
    """Split a MAVLink 2 byte stream into frames."""
    frames = []
    i = 0
    while i + HEADER_LEN + 2 <= len(data):
        if data[i] != STX_V2:
            i += 1
            continue
        n = data[i + 1]
        incompat = data[i + 2]
        end = i + HEADER_LEN + n + 2
        sig = SIGNATURE_LEN if incompat & 1 else 0
        if end + sig > len(data):
            break
        msgid = data[i + 7] | (data[i + 8] << 8) | (data[i + 9] << 16)
        payload = bytes(data[i + HEADER_LEN:i + HEADER_LEN + n])
        if msgid in CRC_EXTRA:
            crc = crc_x25(data[i + 1:i + HEADER_LEN + n])
            crc = crc_x25(bytes([CRC_EXTRA[msgid]]), crc)
            crc_ok = crc == (data[end - 2] | (data[end - 1] << 8))
        else:
            crc_ok = None
        frames.append(dict(seq=data[i + 4], sysid=data[i + 5], compid=data[i + 6], msgid=msgid,
                           payload=payload, crc_ok=crc_ok))
        i = end + sig
    return frames


def decode_gps_input(payload):
    """The fields of a GPS_INPUT payload as a dict (lat / lon in degrees)."""
    p = bytes(payload) + bytes(GPS_INPUT_LEN - len(payload))
    d = dict(zip(GPS_INPUT_FIELDS, struct.unpack(GPS_INPUT_FORMAT, p)))
    d["lat"] = d["lat"] / 1e7
    d["lon"] = d["lon"] / 1e7
    return d


def ignored(flags):
    """Names of the ignore flags that are set, in bit order."""
    return [name for bit, name in enumerate(IGNORE_FLAG_NAMES) if flags & (1 << bit)]


def gps_time_to_utc(week, week_ms):
    """GPS week + milliseconds of the week -> UTC datetime (GPS time is 18 s ahead of UTC)."""
    return GPS_EPOCH + timedelta(weeks=week, milliseconds=week_ms) - timedelta(seconds=GPS_UTC_LEAP_S)


def summarize(frames):
    """Counts for the report (see the lab, Step 4)."""
    good = [f for f in frames if f["msgid"] == MSG_GPS_INPUT and f["crc_ok"]]
    dec = [decode_gps_input(f["payload"]) for f in good]
    by_flags = {}
    for d in dec:
        if d["fix_type"] >= 3:
            by_flags[d["ignore_flags"]] = by_flags.get(d["ignore_flags"], 0) + 1
    return {
        "frames": len(frames),
        "bad_crc": sum(1 for f in frames if f["crc_ok"] is False),
        "heartbeats": sum(1 for f in frames if f["msgid"] == MSG_HEARTBEAT and f["crc_ok"]),
        "gps_input_ok": len(good),
        "fix_3d": sum(1 for d in dec if d["fix_type"] >= 3),
        "no_fix": sum(1 for d in dec if d["fix_type"] <= 1),
        "fix_by_ignore_flags": {str(k): v for k, v in sorted(by_flags.items())},
        "lost_frames": lost_frames(frames),
    }


# ---- you don't need to change anything below this line (but you can read it!) ----

def lost_frames(frames):
    """Frames missing according to the sequence numbers (seq counts 0..255 and wraps)."""
    lost = 0
    for a, b in zip(frames, frames[1:]):
        lost += (b["seq"] - a["seq"] - 1) % 256
    return lost


def main(path):
    with open(path, "rb") as f:
        data = f.read()
    print(f"{path}: {len(data)} bytes")
    print(f"crc_x25(b'123456789') = {crc_x25(b'123456789'):#06x}   (the standard check value is 0x6f91)")
    frames = parse_frames(data)
    if not frames:
        print("parse_frames() found no frame: complete TODO 2")
        return
    for f in frames[:4]:
        print(f"  seq {f['seq']:3d} sys {f['sysid']} comp {f['compid']} msgid {f['msgid']:3d} "
              f"len {len(f['payload']):2d} crc_ok {f['crc_ok']}")
    g = [f for f in frames if f["msgid"] == MSG_GPS_INPUT and f["crc_ok"]]
    if g and decode_gps_input(g[100]["payload"]) is not None:
        d = decode_gps_input(g[100]["payload"])
        print(f"GPS_INPUT #100: lat {d['lat']:.7f} lon {d['lon']:.7f} fix_type {d['fix_type']} "
              f"horiz_accuracy {d['horiz_accuracy']:.1f} m ignore {d['ignore_flags']} {ignored(d['ignore_flags'])}")
        t = gps_time_to_utc(d["time_week"], d["time_week_ms"])
        print(f"  GPS week {d['time_week']} + {d['time_week_ms']} ms = {t} UTC")
    print("summary:", summarize(frames))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else STREAM)
